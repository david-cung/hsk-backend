from __future__ import annotations

import hashlib
import hmac
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AnswerAttempt,
    LessonProgress,
    PracticeSession,
    Question,
    SpeakingAttempt,
    SpeechRecording,
    User,
)

logger = logging.getLogger("hsk.speaking")

SUPPORTED_RECORDING_MIME_TYPES = {"audio/mp4", "audio/x-m4a", "audio/aac", "audio/mpeg", "audio/mp3", "audio/webm"}
SUPPORTED_RECORDING_EXTENSIONS = {".m4a", ".mp4", ".aac", ".mp3", ".webm"}
SPEAKING_TYPES = {"SPEAKING", "PRONUNCIATION"}


class SpeechProviderError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class SpeechWordFeedback:
    expected: str
    recognized: str | None = None
    pronunciation_score: float | None = None
    accuracy_score: float | None = None
    expected_pinyin: str | None = None
    recognized_pinyin: str | None = None
    tone_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "expected": self.expected,
                "recognized": self.recognized,
                "pronunciation_score": self.pronunciation_score,
                "accuracy_score": self.accuracy_score,
                "expected_pinyin": self.expected_pinyin,
                "recognized_pinyin": self.recognized_pinyin,
                "tone_score": self.tone_score,
            }.items()
            if value is not None
        }


@dataclass(frozen=True)
class SpeechAnalysisResult:
    recognized_text: str | None
    confidence: float | None = None
    pronunciation_score: float | None = None
    accuracy_score: float | None = None
    fluency_score: float | None = None
    completeness_score: float | None = None
    words: list[SpeechWordFeedback] = field(default_factory=list)
    feedback_label: str | None = None
    provider: str = "mock"
    provider_model_version: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> dict[str, Any]:
        return {
            "recognized_text": self.recognized_text,
            "confidence": self.confidence,
            "pronunciation_score": self.pronunciation_score,
            "accuracy_score": self.accuracy_score,
            "fluency_score": self.fluency_score,
            "completeness_score": self.completeness_score,
            "words": [word.to_dict() for word in self.words],
            "feedback_label": self.feedback_label,
            "provider": self.provider,
            "provider_model_version": self.provider_model_version,
            "tone_feedback": {"supported": False},
        }


class SpeechProvider(Protocol):
    name: str
    model_version: str | None

    def transcribe(self, recording: SpeechRecording, language: str) -> SpeechAnalysisResult:
        ...

    def analyze_pronunciation(
        self,
        recording: SpeechRecording,
        expected_text: str,
        language: str,
        config: dict[str, Any],
    ) -> SpeechAnalysisResult:
        ...


def _clamp_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(100.0, float(value))), 2)


def _normalize_speech_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = re.sub(r"[\s，。！？；：“”‘’、,.!?;:'\"()\[\]{}]+", "", text)
    return text


def feedback_for_score(score: float | None, thresholds: dict[str, Any] | None = None) -> str | None:
    if score is None:
        return None
    raw_thresholds = thresholds or {}
    excellent = float(raw_thresholds.get("excellent", settings.speech_feedback_excellent_threshold))
    good = float(raw_thresholds.get("good", settings.speech_feedback_good_threshold))
    needs = float(raw_thresholds.get("needs_improvement", settings.speech_feedback_needs_improvement_threshold))
    if score >= excellent:
        return "EXCELLENT"
    if score >= good:
        return "GOOD"
    if score >= needs:
        return "NEEDS_IMPROVEMENT"
    return "PRACTICE_AGAIN"


class MockSpeechProvider:
    name: str = "mock"
    model_version: str | None = "mock-v1"

    def transcribe(self, recording: SpeechRecording, language: str) -> SpeechAnalysisResult:
        metadata = recording.recording_metadata or {}
        if recording.status == "FAILED" or metadata.get("force_provider_failure"):
            raise SpeechProviderError("PROVIDER_UNAVAILABLE", "Mock speech provider failed")
        recognized = metadata.get("mock_transcript")
        return SpeechAnalysisResult(
            recognized_text=str(recognized) if recognized else None,
            confidence=1.0 if recognized else None,
            provider=self.name,
            provider_model_version=self.model_version,
            raw_metadata={"language": language},
        )

    def analyze_pronunciation(
        self,
        recording: SpeechRecording,
        expected_text: str,
        language: str,
        config: dict[str, Any],
    ) -> SpeechAnalysisResult:
        if not expected_text.strip():
            raise SpeechProviderError("INVALID_EXPECTED_TEXT", "Expected text is required", retryable=False)
        transcription = self.transcribe(recording, language)
        recognized = transcription.recognized_text or expected_text
        expected_normalized = _normalize_speech_text(expected_text)
        recognized_normalized = _normalize_speech_text(recognized)
        if not recognized_normalized:
            raise SpeechProviderError("EMPTY_RECORDING", "Recording did not contain recognizable speech")
        similarity = SequenceMatcher(None, expected_normalized, recognized_normalized).ratio()
        score = _clamp_score(similarity * 100)
        include_metrics = bool(config.get("mock_include_metrics", True))
        words = [
            SpeechWordFeedback(
                expected=expected_char,
                recognized=recognized_normalized[index] if index < len(recognized_normalized) else None,
                pronunciation_score=100.0 if index < len(recognized_normalized) and expected_char == recognized_normalized[index] else 0.0,
                accuracy_score=100.0 if index < len(recognized_normalized) and expected_char == recognized_normalized[index] else 0.0,
            )
            for index, expected_char in enumerate(expected_normalized)
        ]
        feedback_label = feedback_for_score(score, config.get("feedback_thresholds") if isinstance(config.get("feedback_thresholds"), dict) else None)
        return SpeechAnalysisResult(
            recognized_text=recognized,
            confidence=transcription.confidence,
            pronunciation_score=score if include_metrics else None,
            accuracy_score=score if include_metrics else None,
            fluency_score=score if include_metrics else None,
            completeness_score=score if include_metrics else None,
            words=words if include_metrics else [],
            feedback_label=feedback_label,
            provider=self.name,
            provider_model_version=self.model_version,
            raw_metadata={"language": language, "mock_similarity": similarity},
        )


def get_speech_provider() -> SpeechProvider:
    provider = settings.speech_provider.lower()
    if provider == "mock":
        return MockSpeechProvider()
    logger.warning("unsupported_speech_provider", extra={"provider": settings.speech_provider})
    raise SpeechProviderError("PROVIDER_UNAVAILABLE", "Configured speech provider is unavailable")


def validate_recording_upload(filename: str | None, mime_type: str, size_bytes: int | None) -> str:
    if mime_type not in SUPPORTED_RECORDING_MIME_TYPES:
        raise ValueError("Unsupported recording MIME type")
    suffix = Path(filename or "").suffix.lower()
    if not suffix:
        suffix = ".m4a" if mime_type in {"audio/mp4", "audio/x-m4a"} else f".{mime_type.split('/')[-1]}"
    if suffix not in SUPPORTED_RECORDING_EXTENSIONS:
        raise ValueError("Unsupported recording file extension")
    if size_bytes is not None and size_bytes > settings.speech_max_upload_bytes:
        raise ValueError("Recording is too large")
    if size_bytes is not None and size_bytes < 0:
        raise ValueError("Recording size must be positive")
    return suffix


def generated_recording_key(user_id: int, extension: str) -> str:
    return f"users/{user_id}/speaking/{uuid4()}{extension}"


def sign_recording_upload(recording_id: int, user_id: int, expires_at: int) -> str:
    payload = f"{recording_id}:{user_id}:{expires_at}".encode()
    return hmac.new(settings.jwt_secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_recording_upload_signature(recording_id: int, user_id: int, expires_at: int, signature: str) -> bool:
    if expires_at < int(datetime.now(UTC).timestamp()):
        return False
    expected = sign_recording_upload(recording_id, user_id, expires_at)
    return hmac.compare_digest(expected, signature)


def upload_contract(recording: SpeechRecording) -> dict[str, Any]:
    expires_at = int(recording.upload_expires_at.timestamp())
    signature = sign_recording_upload(recording.id, recording.user_id, expires_at)
    return {
        "recording_id": recording.id,
        "storage_key": recording.storage_key,
        "upload_url": f"mock-upload://{recording.storage_key}?expires={expires_at}&signature={signature}",
        "headers": {"Content-Type": recording.mime_type},
        "expires_at": recording.upload_expires_at.isoformat(),
        "max_size_bytes": settings.speech_max_upload_bytes,
        "status": recording.status,
    }


def expected_text_for_question(question: Question) -> str:
    config = question.config or {}
    for key in ("expected_text", "display_text", "text"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return question.correct_answer.strip()


def speaking_payload_from_attempt(attempt: AnswerAttempt | None) -> dict[str, Any] | None:
    if not attempt:
        return None
    analysis = (attempt.normalized_answer or {}).get("speech_analysis")
    return analysis if isinstance(analysis, dict) else None


def update_speaking_progress(
    db: Session,
    user: User,
    session: PracticeSession,
    result: SpeechAnalysisResult,
    acceptable: bool,
) -> None:
    if not session.lesson_id:
        return
    progress = db.scalar(
        select(LessonProgress).where(LessonProgress.user_id == user.id, LessonProgress.lesson_id == session.lesson_id)
    )
    if progress is None:
        progress = LessonProgress(user_id=user.id, lesson_id=session.lesson_id)
        db.add(progress)
        db.flush()
    previous_attempts = progress.speaking_attempts or 0
    previous_average = progress.pronunciation_score_avg or 0
    progress.speaking_attempts = previous_attempts + 1
    progress.speaking_acceptable_attempts = (progress.speaking_acceptable_attempts or 0) + int(acceptable)
    if result.pronunciation_score is not None:
        progress.pronunciation_score_avg = round(
            ((previous_average * previous_attempts) + result.pronunciation_score) / (previous_attempts + 1),
            2,
        )
    progress.last_speaking_practice = datetime.now(UTC)


def create_failed_speaking_attempt(
    db: Session,
    user: User,
    session: PracticeSession,
    question: Question,
    answer_attempt: AnswerAttempt,
    recording: SpeechRecording,
    provider_name: str,
    exc: SpeechProviderError,
) -> SpeakingAttempt:
    speaking_attempt = SpeakingAttempt(
        user_id=user.id,
        practice_session_id=session.id,
        question_id=question.id,
        answer_attempt_id=answer_attempt.id,
        recording_id=recording.id,
        provider=provider_name,
        provider_model_version=None,
        processing_status="FAILED",
        error_code=exc.code,
        error_message=exc.message,
        analysis_metadata={"retryable": exc.retryable},
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db.add(speaking_attempt)
    answer_attempt.normalized_answer = {
        "recording_id": recording.id,
        "processing_status": "FAILED",
        "error_code": exc.code,
        "error_message": exc.message,
    }
    return speaking_attempt


def complete_speaking_attempt(
    db: Session,
    user: User,
    session: PracticeSession,
    question: Question,
    answer_attempt: AnswerAttempt,
    recording: SpeechRecording,
    config: dict[str, Any],
) -> SpeakingAttempt:
    provider = get_speech_provider()
    expected_text = expected_text_for_question(question)
    result = provider.analyze_pronunciation(recording, expected_text, str(config.get("language", "zh-CN")), config)
    minimum_score = float(config.get("minimum_acceptable_score", settings.speech_minimum_acceptable_score))
    acceptable = result.pronunciation_score is not None and result.pronunciation_score >= minimum_score
    answer_attempt.is_correct = acceptable
    answer_attempt.score = float(question.points or 1) if acceptable else 0.0
    answer_attempt.normalized_answer = {
        "recording_id": recording.id,
        "expected_text": expected_text,
        "processing_status": "COMPLETED",
        "speech_analysis": result.normalized(),
    }
    speaking_attempt = SpeakingAttempt(
        user_id=user.id,
        practice_session_id=session.id,
        question_id=question.id,
        answer_attempt_id=answer_attempt.id,
        recording_id=recording.id,
        provider=result.provider,
        provider_model_version=result.provider_model_version,
        recognized_text=result.recognized_text,
        confidence=result.confidence,
        pronunciation_score=result.pronunciation_score,
        accuracy_score=result.accuracy_score,
        fluency_score=result.fluency_score,
        completeness_score=result.completeness_score,
        word_feedback=[word.to_dict() for word in result.words],
        tone_feedback={"supported": False},
        feedback_label=result.feedback_label,
        processing_status="COMPLETED",
        analysis_metadata=result.raw_metadata,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db.add(speaking_attempt)
    update_speaking_progress(db, user, session, result, acceptable)
    return speaking_attempt


def ensure_recording_ready_for_user(db: Session, recording_id: int, user_id: int) -> SpeechRecording:
    recording = db.scalar(select(SpeechRecording).where(SpeechRecording.id == recording_id, SpeechRecording.user_id == user_id))
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    if recording.status != "UPLOADED":
        logger.warning("recording_not_uploaded", extra={"recording_id": recording_id, "status": recording.status})
        raise HTTPException(status_code=409, detail="Recording is not uploaded")
    return recording
