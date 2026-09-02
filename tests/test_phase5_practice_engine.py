from app.models import Question
from app.practice_engine import (
    evaluate_answer,
    normalize_text_answer,
    public_question_config,
    validate_question_config,
)


def test_multiple_choice_evaluates_server_side() -> None:
    question = Question(
        lesson_id=1,
        question_type="MULTIPLE_CHOICE",
        prompt="你好 means:",
        correct_answer="a",
        points=2,
        config={
            "options": [{"id": "a", "text": "Hello"}, {"id": "b", "text": "Goodbye"}],
            "correct_option_ids": ["a"],
        },
    )

    assert evaluate_answer(question, "a")["correct"] is True
    assert evaluate_answer(question, "b")["score"] == 0
    assert public_question_config(question) == {
        "options": [{"id": "a", "text": "Hello"}, {"id": "b", "text": "Goodbye"}]
    }


def test_text_normalization_can_ignore_pinyin_tones_and_punctuation() -> None:
    config = {
        "accepted_answers": ["ni hao"],
        "normalization": {"pinyin_tones": "ignore", "punctuation": "ignore", "spaces": "collapse"},
    }
    question = Question(
        lesson_id=1,
        question_type="TEXT_INPUT",
        prompt="Type pinyin",
        correct_answer="ni hao",
        config=config,
    )

    assert normalize_text_answer(" nǐ hǎo！ ", config) == "ni hao"
    assert evaluate_answer(question, "nǐ hǎo！")["correct"] is True


def test_invalid_config_is_rejected() -> None:
    try:
        validate_question_config(
            "MULTIPLE_CHOICE",
            {"options": [{"id": "a", "text": "Hello"}], "correct_option_ids": ["missing"]},
        )
    except ValueError as exc:
        assert "correct_option_ids" in str(exc)
    else:
        raise AssertionError("Expected invalid config to fail")
