from datetime import UTC, datetime, timedelta

from app.models import Question, SpeechRecording
from app.practice_engine import (
    evaluate_answer,
    public_question_config,
    validate_question_config,
)
from app.speech_service import (
    MockSpeechProvider,
    SpeechProviderError,
    validate_recording_upload,
)


def _recording(metadata: dict[str, object] | None = None) -> SpeechRecording:
    return SpeechRecording(
        id=1,
        user_id=1,
        storage_provider="mock",
        storage_key="users/1/speaking/sample.m4a",
        mime_type="audio/mp4",
        extension=".m4a",
        status="UPLOADED",
        upload_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        recording_metadata=metadata or {},
    )


def test_mock_provider_returns_normalized_pronunciation_result() -> None:
    provider = MockSpeechProvider()

    result = provider.analyze_pronunciation(_recording({"mock_transcript": "你好"}), "你好", "zh-CN", {})

    payload = result.normalized()
    assert payload["provider"] == "mock"
    assert payload["recognized_text"] == "你好"
    assert payload["pronunciation_score"] == 100
    assert payload["accuracy_score"] == 100
    assert payload["fluency_score"] == 100
    assert payload["completeness_score"] == 100
    assert payload["words"][0]["expected"] == "你"
    assert payload["tone_feedback"] == {"supported": False}


def test_mock_provider_failure_is_explicit() -> None:
    provider = MockSpeechProvider()

    try:
        provider.analyze_pronunciation(_recording({"force_provider_failure": True}), "你好", "zh-CN", {})
    except SpeechProviderError as exc:
        assert exc.code == "PROVIDER_UNAVAILABLE"
        assert exc.retryable is True
    else:
        raise AssertionError("Expected provider failure")


def test_speaking_question_public_config_exposes_target_without_provider_shape() -> None:
    question = Question(
        lesson_id=1,
        question_type="PRONUNCIATION",
        prompt="Read aloud",
        correct_answer="你好",
        config={
            "expected_text": "你好",
            "pinyin": "nǐ hǎo",
            "translation": "Hello",
            "pronunciation_mode": "READ_ALOUD",
            "scoring_mode": "PRONUNCIATION",
            "minimum_acceptable_score": 70,
            "provider_raw": {"vendor": "secret"},
        },
    )

    validate_question_config(question.question_type, question.config)
    public_config = public_question_config(question)

    assert public_config["expected_text"] == "你好"
    assert public_config["pinyin"] == "nǐ hǎo"
    assert "provider_raw" not in public_config


def test_client_cannot_control_speaking_score_or_recognized_text() -> None:
    question = Question(
        lesson_id=1,
        question_type="PRONUNCIATION",
        prompt="Read aloud",
        correct_answer="你好",
        points=2,
        config={"expected_text": "你好", "pronunciation_mode": "READ_ALOUD", "minimum_acceptable_score": 70},
    )

    result = evaluate_answer(question, {"pronunciation_score": 100, "recognized_text": "你好"})

    assert result["correct"] is False
    assert result["score"] == 0


def test_internal_provider_result_scores_speaking_attempt() -> None:
    question = Question(
        lesson_id=1,
        question_type="PRONUNCIATION",
        prompt="Read aloud",
        correct_answer="你好",
        points=2,
        config={"expected_text": "你好", "pronunciation_mode": "READ_ALOUD", "minimum_acceptable_score": 70},
    )

    result = evaluate_answer(question, {"_provider_result": {"pronunciation_score": 86, "processing_status": "COMPLETED"}})

    assert result["correct"] is True
    assert result["score"] == 2


def test_recording_upload_validation_rejects_unsafe_format() -> None:
    try:
        validate_recording_upload("../voice.wav", "audio/wav", 12)
    except ValueError as exc:
        assert "Unsupported recording" in str(exc)
    else:
        raise AssertionError("Expected unsafe recording format to fail")
