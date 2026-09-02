from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnswerAttempt, LessonProgress, PracticeSession, Question, User
from app.writing_service import (
    WRITING_FILL_TYPE,
    WRITING_TYPES,
    validate_writing_answer,
    validate_writing_config,
    writing_evaluator,
)


class ExerciseType(StrEnum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    MULTIPLE_SELECT = "MULTIPLE_SELECT"
    FILL_BLANK = "FILL_BLANK"
    MATCHING = "MATCHING"
    ORDERING = "ORDERING"
    TRANSLATION = "TRANSLATION"
    GRAMMAR = "GRAMMAR"
    READING = "READING"
    LISTENING = "LISTENING"
    SPEAKING = "SPEAKING"
    PRONUNCIATION = "PRONUNCIATION"
    DICTATION = "DICTATION"
    TEXT_INPUT = "TEXT_INPUT"
    WORD_ORDER = "WORD_ORDER"
    SENTENCE_REORDER = "SENTENCE_REORDER"
    TRANSLATION_TO_CHINESE = "TRANSLATION_TO_CHINESE"
    GUIDED_WRITING = "GUIDED_WRITING"


LEGACY_TYPE_MAP = {
    "multiple_choice": ExerciseType.MULTIPLE_CHOICE,
    "multiple_select": ExerciseType.MULTIPLE_SELECT,
    "fill_blank": ExerciseType.FILL_BLANK,
    "matching": ExerciseType.MATCHING,
    "rearrange": ExerciseType.ORDERING,
    "ordering": ExerciseType.ORDERING,
    "translation": ExerciseType.TRANSLATION,
    "grammar": ExerciseType.GRAMMAR,
    "reading": ExerciseType.READING,
    "listening": ExerciseType.LISTENING,
    "speaking": ExerciseType.SPEAKING,
    "pronunciation": ExerciseType.PRONUNCIATION,
    "word_pronunciation": ExerciseType.PRONUNCIATION,
    "sentence_pronunciation": ExerciseType.PRONUNCIATION,
    "read_aloud": ExerciseType.PRONUNCIATION,
    "repeat_after_audio": ExerciseType.PRONUNCIATION,
    "pinyin_pronunciation": ExerciseType.PRONUNCIATION,
    "dictation": ExerciseType.DICTATION,
    "text_input": ExerciseType.TEXT_INPUT,
    "chinese_character_input": ExerciseType.TEXT_INPUT,
    "vocabulary_recall": ExerciseType.TEXT_INPUT,
    "word_order": ExerciseType.WORD_ORDER,
    "sentence_reorder": ExerciseType.SENTENCE_REORDER,
    "translation_to_chinese": ExerciseType.TRANSLATION_TO_CHINESE,
    "guided_writing": ExerciseType.GUIDED_WRITING,
}

CHINESE_PUNCTUATION = "，。！？；：“”‘’、（）《》〈〉【】"
ASCII_PUNCTUATION = r""".,!?;:'"()[\]{}"""
WHITESPACE_RE = re.compile(r"\s+")
PUNCTUATION_RE = re.compile(f"[{re.escape(CHINESE_PUNCTUATION + ASCII_PUNCTUATION)}]")
PINYIN_TONES = str.maketrans(
    {
        "ā": "a",
        "á": "a",
        "ǎ": "a",
        "à": "a",
        "ē": "e",
        "é": "e",
        "ě": "e",
        "è": "e",
        "ī": "i",
        "í": "i",
        "ǐ": "i",
        "ì": "i",
        "ō": "o",
        "ó": "o",
        "ǒ": "o",
        "ò": "o",
        "ū": "u",
        "ú": "u",
        "ǔ": "u",
        "ù": "u",
        "ǖ": "u",
        "ǘ": "u",
        "ǚ": "u",
        "ǜ": "u",
        "ü": "u",
    }
)


def canonical_type(value: str | None) -> ExerciseType:
    if not value:
        return ExerciseType.TEXT_INPUT
    normalized = value.strip()
    upper = normalized.upper()
    if upper in ExerciseType.__members__:
        return ExerciseType[upper]
    return LEGACY_TYPE_MAP.get(normalized.lower(), ExerciseType.TEXT_INPUT)


def build_legacy_question_config(question_type: str, options: list[str] | None, correct_answer: str) -> dict[str, Any]:
    qtype = canonical_type(question_type)
    if qtype == ExerciseType.MULTIPLE_CHOICE:
        option_rows = [
            {"id": str(index), "text": option}
            for index, option in enumerate(options or [], start=1)
        ]
        correct_ids = [row["id"] for row in option_rows if row["text"] == correct_answer]
        return {"options": option_rows, "correct_option_ids": correct_ids or [correct_answer]}
    if qtype == ExerciseType.MULTIPLE_SELECT:
        return {"options": [], "correct_option_ids": [correct_answer]}
    if qtype == ExerciseType.ORDERING:
        items = [{"id": str(index), "text": item} for index, item in enumerate(options or [], start=1)]
        return {"items": items, "correct_order": [item["id"] for item in items]}
    return {
        "accepted_answers": [correct_answer],
        "case_sensitive": False,
        "normalization": {"trim": True, "case": "lower", "punctuation": "ignore"},
    }


def validate_question_config(question_type: str, config: dict[str, Any]) -> None:
    qtype = canonical_type(question_type)
    if qtype == ExerciseType.LISTENING:
        if not config.get("audio_asset_id"):
            raise ValueError("audio_asset_id is required for listening questions")
        answer_type = canonical_type(str(config.get("answer_type", "MULTIPLE_CHOICE")))
        nested_config = dict(config)
        validate_question_config(answer_type.value, nested_config)
        return
    if qtype in {ExerciseType.SPEAKING, ExerciseType.PRONUNCIATION}:
        expected_text = config.get("expected_text") or config.get("display_text") or config.get("text")
        if not isinstance(expected_text, str) or not expected_text.strip():
            raise ValueError("expected_text is required for speaking questions")
        mode = str(config.get("pronunciation_mode", "READ_ALOUD")).upper()
        supported_modes = {
            "WORD",
            "SENTENCE",
            "REPEAT_AFTER_AUDIO",
            "READ_ALOUD",
            "PINYIN",
            "CONVERSATION",
            "ROLE_PLAY",
        }
        if mode not in supported_modes:
            raise ValueError("Unsupported pronunciation_mode")
        score = config.get("minimum_acceptable_score", 70)
        if not isinstance(score, int | float) or score < 0 or score > 100:
            raise ValueError("minimum_acceptable_score must be between 0 and 100")
        return
    if qtype.value in WRITING_TYPES:
        validate_writing_config(qtype.value, config)
        return
    if qtype in {ExerciseType.MULTIPLE_CHOICE, ExerciseType.MULTIPLE_SELECT, ExerciseType.GRAMMAR, ExerciseType.READING}:
        options = config.get("options")
        correct_ids = config.get("correct_option_ids")
        if not isinstance(options, list) or not options:
            raise ValueError("options must be a non-empty list")
        option_ids = set()
        for option in options:
            if not isinstance(option, dict) or not option.get("id") or "text" not in option:
                raise ValueError("each option requires id and text")
            option_ids.add(str(option["id"]))
        if not isinstance(correct_ids, list) or not correct_ids:
            raise ValueError("correct_option_ids must be a non-empty list")
        if not set(map(str, correct_ids)).issubset(option_ids):
            raise ValueError("correct_option_ids must match option ids")
        if qtype != ExerciseType.MULTIPLE_SELECT and len(correct_ids) != 1:
            raise ValueError("single-answer questions require one correct option")
    elif qtype in {
        ExerciseType.FILL_BLANK,
        ExerciseType.TRANSLATION,
        ExerciseType.DICTATION,
        ExerciseType.TEXT_INPUT,
    }:
        answers = config.get("accepted_answers")
        if not isinstance(answers, list) or not any(str(answer).strip() for answer in answers):
            raise ValueError("accepted_answers must contain at least one answer")
    elif qtype == ExerciseType.ORDERING:
        items = config.get("items")
        correct_order = config.get("correct_order")
        if not isinstance(items, list) or not items:
            raise ValueError("items must be a non-empty list")
        item_ids = {str(item.get("id")) for item in items if isinstance(item, dict) and item.get("id")}
        if not isinstance(correct_order, list) or set(map(str, correct_order)) != item_ids:
            raise ValueError("correct_order must include each item id exactly once")
    elif qtype == ExerciseType.MATCHING:
        pairs = config.get("pairs")
        if not isinstance(pairs, list) or not pairs:
            raise ValueError("pairs must be a non-empty list")


def public_question_config(question: Question) -> dict[str, Any]:
    config = question.config or build_legacy_question_config(question.question_type, question.options, question.correct_answer)
    qtype = canonical_type(question.question_type)
    if qtype == ExerciseType.LISTENING:
        answer_type = canonical_type(str(config.get("answer_type", "MULTIPLE_CHOICE")))
        visible = {
            "audio_asset_id": config.get("audio_asset_id"),
            "answer_type": answer_type.value,
            "replay_limit": config.get("replay_limit"),
            "allow_seek": config.get("allow_seek", False),
            "auto_play": config.get("auto_play", False),
            "show_transcript_after_submit": config.get("show_transcript_after_submit", True),
        }
        if answer_type in {
            ExerciseType.MULTIPLE_CHOICE,
            ExerciseType.MULTIPLE_SELECT,
            ExerciseType.GRAMMAR,
            ExerciseType.READING,
        }:
            visible["options"] = config.get("options", [])
        elif answer_type == ExerciseType.ORDERING:
            visible["items"] = config.get("items", [])
        elif answer_type == ExerciseType.MATCHING:
            visible["left"] = config.get("left", [])
            visible["right"] = config.get("right", [])
        else:
            visible["placeholder"] = config.get("placeholder", "")
            visible["word_bank"] = config.get("word_bank", [])
        return visible
    if qtype in {ExerciseType.SPEAKING, ExerciseType.PRONUNCIATION}:
        return {
            key: value
            for key, value in config.items()
            if key
            in {
                "expected_text",
                "display_text",
                "pinyin",
                "translation",
                "audio_asset_id",
                "pronunciation_mode",
                "scoring_mode",
                "minimum_acceptable_score",
                "recording",
                "reference_type",
                "reference_id",
                "feedback_thresholds",
                "metadata",
            }
        }
    if qtype in {ExerciseType.MULTIPLE_CHOICE, ExerciseType.MULTIPLE_SELECT, ExerciseType.GRAMMAR, ExerciseType.READING}:
        return {"options": config.get("options", [])}
    if qtype == ExerciseType.ORDERING:
        return {"items": config.get("items", [])}
    if qtype == ExerciseType.MATCHING:
        return {"left": config.get("left", []), "right": config.get("right", [])}
    if qtype.value in WRITING_TYPES:
        visible_keys = {
            "items",
            "tokens",
            "placeholder",
            "word_bank",
            "required_vocabulary",
            "required_grammar",
            "required_keywords",
            "min_characters",
            "max_characters",
            "min_chinese_ratio",
            "rubric",
        }
        return {key: value for key, value in config.items() if key in visible_keys}
    return {
        key: value
        for key, value in config.items()
        if key in {"placeholder", "word_bank", "case_sensitive", "pinyin_mode"}
    }


def normalize_text_answer(value: str, config: dict[str, Any]) -> str:
    raw_rules = config.get("normalization")
    rules: dict[str, Any] = raw_rules if isinstance(raw_rules, dict) else {}
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if not config.get("case_sensitive", False) and rules.get("case", "lower") != "preserve":
        text = text.lower()
    if rules.get("pinyin_tones") == "ignore":
        text = text.translate(PINYIN_TONES)
        text = re.sub(r"([a-züv])([1-5])\b", r"\1", text)
    if rules.get("punctuation", "ignore") == "ignore":
        text = PUNCTUATION_RE.sub("", text)
    if rules.get("spaces", "collapse") == "remove":
        text = WHITESPACE_RE.sub("", text)
    else:
        text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _answer_value(answer: Any) -> Any:
    if isinstance(answer, dict) and "value" in answer:
        return answer["value"]
    return answer


def is_writing_question_type(question_type: str | None, config: dict[str, Any] | None = None) -> bool:
    qtype = canonical_type(question_type).value
    return qtype in WRITING_TYPES or (qtype == WRITING_FILL_TYPE and bool((config or {}).get("writing")))


def evaluate_writing_answer(question: Question, answer: Any, config: dict[str, Any]) -> dict[str, Any]:
    points = question.points or 1
    evaluation = writing_evaluator().evaluate(canonical_type(question.question_type).value, answer, config)
    score = round(float(points) * evaluation.score_ratio, 2)
    return {
        "correct": evaluation.correct,
        "score": score,
        "max_score": float(points),
        "normalized_answer": {
            "value": evaluation.normalized_answer,
            "raw_answer": _answer_value(answer),
            "evaluation_source": writing_evaluator().provider_name,
            "writing_evaluation": evaluation.feedback,
        },
        "correct_answer": evaluation.correct_answer,
        "explanation": question.explanation,
    }


def evaluate_answer(question: Question, answer: Any) -> dict[str, Any]:
    config = question.config or build_legacy_question_config(question.question_type, question.options, question.correct_answer)
    qtype = canonical_type(question.question_type)
    if qtype == ExerciseType.LISTENING:
        qtype = canonical_type(str(config.get("answer_type", "MULTIPLE_CHOICE")))
    points = question.points or 1
    validate_question_config(question.question_type, config)
    if qtype.value in WRITING_TYPES or (qtype.value == WRITING_FILL_TYPE and bool(config.get("writing"))):
        return evaluate_writing_answer(question, answer, config)
    validate_writing_answer(answer, config)
    submitted = _answer_value(answer)
    normalized: Any
    correct_answer: Any

    if qtype in {ExerciseType.SPEAKING, ExerciseType.PRONUNCIATION}:
        provider_result = submitted.get("_provider_result") if isinstance(submitted, dict) else {}
        if not isinstance(provider_result, dict):
            provider_result = {}
        score = provider_result.get("pronunciation_score")
        minimum = float(config.get("minimum_acceptable_score", 70))
        correct = isinstance(score, int | float) and float(score) >= minimum
        normalized = {"speech_analysis": provider_result, "processing_status": provider_result.get("processing_status")}
        correct_answer = config.get("expected_text") or config.get("display_text") or question.correct_answer
    elif qtype in {ExerciseType.MULTIPLE_CHOICE, ExerciseType.GRAMMAR, ExerciseType.READING}:
        correct = str(submitted) in set(map(str, config["correct_option_ids"]))
        normalized = str(submitted)
        correct_answer = config["correct_option_ids"][0]
    elif qtype == ExerciseType.MULTIPLE_SELECT:
        submitted_set = set(map(str, submitted if isinstance(submitted, list) else []))
        correct_set = set(map(str, config["correct_option_ids"]))
        correct = submitted_set == correct_set
        normalized = sorted(submitted_set)
        correct_answer = sorted(correct_set)
    elif qtype == ExerciseType.ORDERING:
        submitted_order = list(map(str, submitted if isinstance(submitted, list) else []))
        correct_order = list(map(str, config["correct_order"]))
        correct = submitted_order == correct_order
        normalized = submitted_order
        correct_answer = correct_order
    elif qtype == ExerciseType.MATCHING:
        submitted_pairs = submitted if isinstance(submitted, list) else []
        correct_pairs = config["pairs"]
        correct = submitted_pairs == correct_pairs
        normalized = submitted_pairs
        correct_answer = correct_pairs
    else:
        normalized = normalize_text_answer(str(submitted or ""), config)
        normalized_answers = [normalize_text_answer(str(candidate), config) for candidate in config["accepted_answers"]]
        correct = bool(normalized) and normalized in normalized_answers
        correct_answer = config["accepted_answers"]

    return {
        "correct": correct,
        "score": float(points if correct else 0),
        "max_score": float(points),
        "normalized_answer": {"value": normalized},
        "correct_answer": correct_answer,
        "explanation": question.explanation,
    }


def recalculate_session(db: Session, session: PracticeSession) -> None:
    attempts = db.scalars(
        select(AnswerAttempt)
        .where(AnswerAttempt.practice_session_id == session.id)
        .order_by(AnswerAttempt.attempted_at, AnswerAttempt.id)
    ).all()
    latest_by_question: dict[int, AnswerAttempt] = {}
    for attempt in attempts:
        latest_by_question[attempt.question_id] = attempt
    session.answered_questions = len(latest_by_question)
    session.correct_answers = sum(1 for attempt in latest_by_question.values() if attempt.is_correct)
    session.score = round((session.correct_answers / session.total_questions) * 100, 2) if session.total_questions else 0
    session.time_spent_seconds = sum(attempt.time_spent_seconds for attempt in attempts)


def update_lesson_progress(db: Session, user: User, session: PracticeSession) -> None:
    if not session.lesson_id:
        return
    progress = db.scalar(
        select(LessonProgress).where(LessonProgress.user_id == user.id, LessonProgress.lesson_id == session.lesson_id)
    )
    if progress is None:
        progress = LessonProgress(user_id=user.id, lesson_id=session.lesson_id)
        db.add(progress)
    progress.status = "completed" if session.status == "COMPLETED" and session.score >= 60 else "in_progress"
    progress.score_percent = round(session.score)
    progress.minutes_studied = max(progress.minutes_studied or 0, round((session.time_spent_seconds or 0) / 60))
    active_date = datetime.now(UTC).date()
    last_active = user.profile.last_active_date
    if last_active == active_date:
        pass
    elif last_active == active_date - timedelta(days=1):
        user.profile.study_streak_days = (user.profile.study_streak_days or 0) + 1
    else:
        user.profile.study_streak_days = 1
    user.profile.last_active_date = active_date
    user.profile.longest_streak_days = max(user.profile.longest_streak_days or 0, user.profile.study_streak_days or 0)


def complete_session(db: Session, user: User, session: PracticeSession) -> PracticeSession:
    if session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Practice session not found")
    recalculate_session(db, session)
    session.status = "COMPLETED"
    session.completed_at = datetime.now(UTC)
    update_lesson_progress(db, user, session)
    return session
