from app.audio_service import audio_asset_url, validate_audio_asset_payload
from app.models import AudioAsset, Question
from app.practice_engine import evaluate_answer, public_question_config


def test_audio_asset_tts_url_does_not_expose_credentials() -> None:
    asset = AudioAsset(
        id=42,
        provider="tts",
        storage_key="tts/hsk1/q1",
        transcript="你好。",
        mime_type="audio/mpeg",
    )

    payload = audio_asset_url(asset, expires_minutes=5)

    assert payload["url"].startswith("tts://zh-CN/")
    assert "secret" not in payload["url"]
    assert payload["audio_asset_id"] == 42


def test_invalid_audio_asset_is_rejected() -> None:
    try:
        validate_audio_asset_payload("audio/hsk1/q1.wav", "local", "audio/wav")
    except ValueError as exc:
        assert "Unsupported audio" in str(exc)
    else:
        raise AssertionError("Expected invalid audio payload to fail")


def test_listening_question_hides_transcript_before_submit() -> None:
    question = Question(
        lesson_id=1,
        question_type="LISTENING",
        prompt="听录音，选择正确答案。",
        correct_answer="a",
        config={
            "audio_asset_id": 7,
            "answer_type": "MULTIPLE_CHOICE",
            "options": [{"id": "a", "text": "你好"}, {"id": "b", "text": "再见"}],
            "correct_option_ids": ["a"],
            "transcript": "你好。",
            "translation": "Hello.",
            "show_transcript_after_submit": True,
        },
    )

    public_config = public_question_config(question)

    assert public_config["audio_asset_id"] == 7
    assert public_config["options"] == [{"id": "a", "text": "你好"}, {"id": "b", "text": "再见"}]
    assert "transcript" not in public_config
    assert "translation" not in public_config


def test_listening_text_answer_reuses_text_evaluator() -> None:
    question = Question(
        lesson_id=1,
        question_type="LISTENING",
        prompt="听录音，写关键词。",
        correct_answer="你好",
        config={
            "audio_asset_id": 7,
            "answer_type": "TEXT_INPUT",
            "accepted_answers": ["你好"],
            "normalization": {"punctuation": "ignore", "spaces": "remove"},
        },
    )

    assert evaluate_answer(question, " 你 好。")["correct"] is True
