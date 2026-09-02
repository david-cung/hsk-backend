from __future__ import annotations

# ruff: noqa: B008
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import SpeakingAttempt, SpeechRecording, User
from app.schemas import (
    SpeakingAttemptOut,
    SpeechAnalysisOut,
    SpeechRecordingOut,
    SpeechUploadCompleteIn,
    SpeechUploadOut,
    SpeechUploadRequestIn,
)
from app.speech_service import (
    generated_recording_key,
    upload_contract,
    validate_recording_upload,
)

logger = logging.getLogger("hsk.speaking")
router = APIRouter(prefix="/api/v1/speaking", tags=["speaking"])


def recording_to_out(recording: SpeechRecording) -> SpeechRecordingOut:
    return SpeechRecordingOut(
        id=recording.id,
        storage_key=recording.storage_key,
        mime_type=recording.mime_type,
        size_bytes=recording.size_bytes,
        duration_seconds=recording.duration_seconds,
        language=recording.language,
        status=recording.status,
        upload_expires_at=recording.upload_expires_at,
        uploaded_at=recording.uploaded_at,
        expires_at=recording.expires_at,
        created_at=recording.created_at,
        updated_at=recording.updated_at,
    )


def speaking_attempt_to_out(attempt: SpeakingAttempt) -> SpeakingAttemptOut:
    analysis: dict[str, Any] = {
        "recognized_text": attempt.recognized_text,
        "confidence": attempt.confidence,
        "pronunciation_score": attempt.pronunciation_score,
        "accuracy_score": attempt.accuracy_score,
        "fluency_score": attempt.fluency_score,
        "completeness_score": attempt.completeness_score,
        "words": attempt.word_feedback or [],
        "feedback_label": attempt.feedback_label,
        "provider": attempt.provider,
        "provider_model_version": attempt.provider_model_version,
        "tone_feedback": attempt.tone_feedback,
    }
    return SpeakingAttemptOut(
        id=attempt.id,
        answer_attempt_id=attempt.answer_attempt_id,
        recording_id=attempt.recording_id,
        practice_session_id=attempt.practice_session_id,
        question_id=attempt.question_id,
        provider=attempt.provider,
        provider_model_version=attempt.provider_model_version,
        recognized_text=attempt.recognized_text,
        pronunciation_score=attempt.pronunciation_score,
        accuracy_score=attempt.accuracy_score,
        fluency_score=attempt.fluency_score,
        completeness_score=attempt.completeness_score,
        processing_status=attempt.processing_status,
        error_code=attempt.error_code,
        error_message=attempt.error_message,
        speech_analysis=SpeechAnalysisOut.model_validate(analysis),
    )


@router.post("/upload", response_model=SpeechUploadOut, status_code=status.HTTP_201_CREATED)
def create_recording_upload(
    payload: SpeechUploadRequestIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeechUploadOut:
    try:
        extension = validate_recording_upload(payload.filename, payload.mime_type, payload.size_bytes)
    except ValueError as exc:
        logger.warning("invalid_recording_upload", extra={"user_id": user.id, "mime_type": payload.mime_type})
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = datetime.now(UTC)
    recording = SpeechRecording(
        user_id=user.id,
        storage_provider=settings.speech_provider,
        storage_key=generated_recording_key(user.id, extension),
        original_filename=payload.filename,
        mime_type=payload.mime_type,
        extension=extension,
        size_bytes=payload.size_bytes,
        duration_seconds=payload.duration_seconds,
        language=payload.language,
        status="UPLOAD_AUTHORIZED",
        upload_expires_at=now + timedelta(minutes=settings.speech_upload_url_expire_minutes),
        expires_at=now + timedelta(days=settings.speech_recording_retention_days),
        recording_metadata={"client": payload.metadata, "retention_days": settings.speech_recording_retention_days},
    )
    db.add(recording)
    db.commit()
    db.refresh(recording)
    return SpeechUploadOut(**upload_contract(recording))


@router.post("/upload/{recording_id}/complete", response_model=SpeechRecordingOut)
def complete_recording_upload(
    recording_id: int,
    payload: SpeechUploadCompleteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeechRecordingOut:
    recording = db.scalar(select(SpeechRecording).where(SpeechRecording.id == recording_id, SpeechRecording.user_id == user.id))
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    if recording.upload_expires_at < datetime.now(UTC):
        recording.status = "FAILED"
        db.commit()
        logger.warning("recording_upload_expired", extra={"recording_id": recording.id})
        raise HTTPException(status_code=410, detail="Recording upload authorization expired")
    if payload.size_bytes is not None and payload.size_bytes > settings.speech_max_upload_bytes:
        recording.status = "FAILED"
        db.commit()
        logger.warning("recording_too_large", extra={"recording_id": recording.id})
        raise HTTPException(status_code=422, detail="Recording is too large")
    recording.status = "UPLOADED"
    recording.size_bytes = payload.size_bytes if payload.size_bytes is not None else recording.size_bytes
    recording.duration_seconds = payload.duration_seconds if payload.duration_seconds is not None else recording.duration_seconds
    recording.uploaded_at = datetime.now(UTC)
    recording.recording_metadata = {**(recording.recording_metadata or {}), "upload": payload.metadata}
    db.commit()
    db.refresh(recording)
    return recording_to_out(recording)


@router.get("/recordings/{recording_id}", response_model=SpeechRecordingOut)
def get_recording(
    recording_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeechRecordingOut:
    recording = db.scalar(select(SpeechRecording).where(SpeechRecording.id == recording_id, SpeechRecording.user_id == user.id))
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    return recording_to_out(recording)


@router.get("/attempts/{attempt_id}", response_model=SpeakingAttemptOut)
def get_speaking_attempt(
    attempt_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeakingAttemptOut:
    attempt = db.scalar(select(SpeakingAttempt).where(SpeakingAttempt.id == attempt_id, SpeakingAttempt.user_id == user.id))
    if not attempt:
        raise HTTPException(status_code=404, detail="Speaking attempt not found")
    return speaking_attempt_to_out(attempt)


def cleanup_expired_recordings(db: Session, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    result = db.execute(
        delete(SpeechRecording).where(
            SpeechRecording.expires_at.is_not(None),
            SpeechRecording.expires_at < current,
            SpeechRecording.status.in_(["UPLOAD_AUTHORIZED", "FAILED", "EXPIRED"]),
        )
    )
    deleted = int(getattr(result, "rowcount", 0) or 0)
    if deleted:
        logger.info("expired_speech_recordings_cleaned", extra={"count": deleted})
    return deleted
