from __future__ import annotations

# ruff: noqa: B008
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audio_service import (
    audio_asset_url,
    get_ready_audio_asset,
    validate_audio_asset_payload,
    verify_audio_signature,
)
from app.auth import get_current_user
from app.database import get_db
from app.models import AudioAsset, User
from app.skill_schemas import AudioAssetIn, AudioAssetOut, AudioUrlOut

logger = logging.getLogger("hsk.audio")
router = APIRouter(prefix="/api/v1/audio", tags=["audio"])
admin_router = APIRouter(prefix="/api/v1/admin/audio", tags=["admin-audio"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


def audio_asset_to_out(asset: AudioAsset) -> AudioAssetOut:
    return AudioAssetOut(
        id=asset.id,
        storage_key=asset.storage_key,
        provider=asset.provider,
        mime_type=asset.mime_type,
        duration_seconds=asset.duration_seconds,
        language=asset.language,
        transcript=asset.transcript,
        pinyin=asset.pinyin,
        translation=asset.translation,
        status=asset.status,
        metadata=asset.metadata_json or {},
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.get("/{audio_asset_id}/url", response_model=AudioUrlOut)
def get_audio_url(
    audio_asset_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AudioUrlOut:
    asset = get_ready_audio_asset(db, audio_asset_id)
    try:
        return AudioUrlOut(**audio_asset_url(asset))
    except Exception as exc:
        logger.warning("audio_url_generation_failed", extra={"audio_asset_id": audio_asset_id})
        raise HTTPException(status_code=500, detail="Could not generate audio URL") from exc


@router.get("/{audio_asset_id}/media")
def get_audio_media(
    audio_asset_id: int,
    expires: int,
    signature: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    if not verify_audio_signature(audio_asset_id, expires, signature):
        raise HTTPException(status_code=403, detail="Audio URL expired")
    asset = get_ready_audio_asset(db, audio_asset_id)
    if asset.provider != "local":
        raise HTTPException(status_code=404, detail="Audio media is not stored locally")
    media_path = Path(asset.storage_key)
    if not media_path.is_absolute():
        media_path = Path(__file__).resolve().parent / "media" / asset.storage_key
    if not media_path.exists() or not media_path.is_file():
        logger.warning("local_audio_missing", extra={"audio_asset_id": audio_asset_id})
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(media_path, media_type=asset.mime_type)


@admin_router.post("", response_model=AudioAssetOut)
def create_audio_asset(
    payload: AudioAssetIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AudioAssetOut:
    try:
        validate_audio_asset_payload(
            payload.storage_key,
            payload.provider,
            payload.mime_type,
            payload.duration_seconds,
        )
    except ValueError as exc:
        logger.warning("invalid_audio_asset", extra={"storage_key": payload.storage_key, "provider": payload.provider})
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing = db.scalar(
        select(AudioAsset).where(AudioAsset.provider == payload.provider, AudioAsset.storage_key == payload.storage_key)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Audio asset already exists")
    asset = AudioAsset(
        storage_key=payload.storage_key,
        storage_provider=payload.provider,
        provider=payload.provider,
        duration_ms=round(payload.duration_seconds * 1000) if payload.duration_seconds is not None else None,
        format=payload.mime_type.split("/")[-1],
        locale=payload.language,
        mime_type=payload.mime_type,
        duration_seconds=payload.duration_seconds,
        language=payload.language,
        transcript=payload.transcript,
        pinyin=payload.pinyin,
        translation=payload.translation,
        status=payload.status,
        metadata_json=payload.metadata,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return audio_asset_to_out(asset)


@admin_router.patch("/{audio_asset_id}", response_model=AudioAssetOut)
def update_audio_asset(
    audio_asset_id: int,
    payload: AudioAssetIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AudioAssetOut:
    asset = db.get(AudioAsset, audio_asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Audio asset not found")
    validate_audio_asset_payload(payload.storage_key, payload.provider, payload.mime_type, payload.duration_seconds)
    asset.storage_key = payload.storage_key
    asset.storage_provider = payload.provider
    asset.provider = payload.provider
    asset.duration_ms = round(payload.duration_seconds * 1000) if payload.duration_seconds is not None else None
    asset.format = payload.mime_type.split("/")[-1]
    asset.locale = payload.language
    asset.mime_type = payload.mime_type
    asset.duration_seconds = payload.duration_seconds
    asset.language = payload.language
    asset.transcript = payload.transcript
    asset.pinyin = payload.pinyin
    asset.translation = payload.translation
    asset.status = payload.status
    asset.metadata_json = payload.metadata
    db.commit()
    db.refresh(asset)
    return audio_asset_to_out(asset)


@admin_router.post("/{audio_asset_id}/archive", response_model=AudioAssetOut)
def archive_audio_asset(
    audio_asset_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AudioAssetOut:
    asset = db.get(AudioAsset, audio_asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Audio asset not found")
    asset.status = "ARCHIVED"
    db.commit()
    db.refresh(asset)
    return audio_asset_to_out(asset)


@admin_router.get("/{audio_asset_id}/preview", response_model=AudioAssetOut)
def preview_audio_asset(
    audio_asset_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AudioAssetOut:
    asset = db.get(AudioAsset, audio_asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Audio asset not found")
    return audio_asset_to_out(asset)
