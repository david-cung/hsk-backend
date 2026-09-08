from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.media_storage import get_media_storage
from app.models import AudioAsset

logger = logging.getLogger("hsk.audio")

SUPPORTED_MIME_TYPES = {"audio/mpeg", "audio/mp3", "audio/aac", "audio/mp4", "audio/x-m4a"}
SUPPORTED_EXTENSIONS = {".mp3", ".aac", ".m4a"}


def validate_audio_asset_payload(
    storage_key: str,
    provider: str,
    mime_type: str,
    duration_seconds: float | None = None,
) -> None:
    if not storage_key.strip():
        raise ValueError("storage_key is required")
    if provider not in {"tts", "local", "http", "s3"}:
        raise ValueError("Unsupported audio provider")
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise ValueError("Unsupported audio MIME type")
    if duration_seconds is not None and duration_seconds < 0:
        raise ValueError("duration_seconds must be positive")
    if provider in {"local", "s3"}:
        suffix = Path(storage_key).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError("Unsupported audio file extension")


def sign_audio_url(audio_asset_id: int, expires_at: int) -> str:
    payload = f"{audio_asset_id}:{expires_at}".encode()
    return hmac.new(settings.jwt_secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_audio_signature(audio_asset_id: int, expires_at: int, signature: str) -> bool:
    if expires_at < int(datetime.now(UTC).timestamp()):
        return False
    expected = sign_audio_url(audio_asset_id, expires_at)
    return hmac.compare_digest(expected, signature)


def audio_asset_url(asset: AudioAsset, expires_minutes: int | None = None) -> dict[str, Any]:
    expires = datetime.now(UTC) + timedelta(minutes=expires_minutes or settings.audio_url_expire_minutes)
    expires_at = int(expires.timestamp())
    signature = sign_audio_url(asset.id, expires_at)
    if asset.provider == "http":
        url = asset.storage_key
    elif asset.provider == "tts":
        # The mobile app treats this controlled URL as a TTS-backed audio source.
        url = f"tts://zh-CN/{quote(asset.transcript or asset.storage_key)}"
    elif asset.provider == "s3":
        url = get_media_storage().get_download_url(asset.storage_key, max(60, int((expires - datetime.now(UTC)).total_seconds())))
    else:
        url = f"/api/v1/audio/{asset.id}/media?expires={expires_at}&signature={signature}"
    return {
        "audio_asset_id": asset.id,
        "url": url,
        "provider": asset.provider,
        "mime_type": asset.mime_type,
        "expires_at": expires.isoformat(),
    }


def get_ready_audio_asset(db: Session, audio_asset_id: int) -> AudioAsset:
    asset = db.get(AudioAsset, audio_asset_id)
    if not asset or asset.status != "READY":
        logger.warning("missing_or_unready_audio_asset", extra={"audio_asset_id": audio_asset_id})
        raise HTTPException(status_code=404, detail="Audio asset not found")
    return asset


def local_audio_path(storage_key: str) -> Path:
    """Resolve server-owned local audio keys without accepting client paths."""
    root = Path(settings.media_storage_dir).resolve()
    candidate = (root / storage_key).resolve()
    if root == candidate or root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid audio storage key")
    if candidate.exists():
        return candidate
    # Keep serving Phase 4 local imports while deployments migrate the directory.
    root = Path(settings.exam_import_storage_dir).resolve()
    candidate = (root / storage_key).resolve()
    if root != candidate and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid audio storage key")
    if candidate.exists():
        return candidate
    legacy_root = Path(__file__).resolve().parent / "media"
    legacy_candidate = (legacy_root / storage_key).resolve()
    if legacy_root == legacy_candidate or legacy_root not in legacy_candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid audio storage key")
    return legacy_candidate


def transcript_payload(asset: AudioAsset | None) -> dict[str, str | None]:
    if not asset:
        return {"transcript": None, "pinyin": None, "translation": None}
    return {
        "transcript": asset.transcript,
        "pinyin": asset.pinyin,
        "translation": asset.translation,
    }
