from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Conversation,
    Course,
    GrammarPoint,
    HskLevel,
    Lesson,
    LessonGrammarPoint,
    LessonVocabulary,
    QuestionAttempt,
    User,
    Vocabulary,
)
from app.progress_service import _skill_metrics, _weak_areas

PRIVACY_BLOCKLIST = {
    "password",
    "password_hash",
    "refresh_token",
    "access_token",
    "token",
    "oauth",
    "email",
    "api_key",
    "secret",
}

MAX_VOCAB = 8
MAX_GRAMMAR = 4
MAX_MISTAKES = 5
MAX_WEAK = 4


def build_tutor_context(
    db: Session,
    user: User,
    *,
    conversation: Conversation | None = None,
    lesson_id: int | None = None,
    course_id: int | None = None,
    hsk_level: int | None = None,
    mode: str | None = None,
    scenario_id: str | None = None,
) -> dict[str, Any]:
    profile = user.profile
    level = int(hsk_level or (conversation.hsk_level if conversation else None) or profile.current_hsk_level or 1)
    lesson_id = lesson_id or (conversation.lesson_id if conversation else None)
    course_id = course_id or (conversation.course_id if conversation else None)
    mode = mode or (conversation.mode if conversation else "FREE_CHAT")
    scenario_id = scenario_id or (conversation.scenario_id if conversation else None)

    lesson = _load_lesson(db, lesson_id)
    course = _load_course(db, course_id or (lesson.course_id if lesson else None))
    vocabulary = _vocabulary_rows(db, lesson, level)
    grammar = _grammar_rows(db, lesson, level)
    weak = [
        {"skill": item.skill, "label": item.label, "reason": item.reason}
        for item in _weak_areas(_skill_metrics(db, user.id))[:MAX_WEAK]
    ]
    mistakes = _recent_mistakes(db, user.id)
    context = {
        "hsk_level": level,
        "target_hsk_level": profile.target_hsk_level,
        "learning_goal": profile.learning_goal,
        "mode": mode,
        "scenario": scenario_id,
        "course": {"title": course.title} if course else None,
        "lesson": {"title": lesson.title, "type": lesson.lesson_type} if lesson else None,
        "vocabulary": vocabulary,
        "grammar": grammar,
        "weak_areas": weak,
        "recent_mistakes": mistakes,
    }
    return sanitize_context(context)


def sanitize_context(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in PRIVACY_BLOCKLIST):
                continue
            cleaned[key] = sanitize_context(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_context(item) for item in value[:20]]
    if isinstance(value, str):
        return value[:240]
    return value


def context_contains_private_data(context: dict[str, Any]) -> bool:
    blob = str(context).lower()
    return any(token in blob for token in ("password", "refresh_token", "access_token", "oauth", "api_key"))


def _load_lesson(db: Session, lesson_id: int | None) -> Lesson | None:
    if not lesson_id:
        return None
    return db.scalar(
        select(Lesson)
        .options(
            selectinload(Lesson.vocabulary_links).selectinload(LessonVocabulary.vocabulary),
            selectinload(Lesson.grammar_links).selectinload(LessonGrammarPoint.grammar_point),
        )
        .where(Lesson.id == lesson_id)
    )


def _load_course(db: Session, course_id: int | None) -> Course | None:
    if not course_id:
        return None
    return db.get(Course, course_id)


def _vocabulary_rows(db: Session, lesson: Lesson | None, hsk_level: int) -> list[dict[str, Any]]:
    rows: list[Vocabulary] = []
    if lesson:
        rows = [link.vocabulary for link in lesson.vocabulary_links if link.vocabulary][:MAX_VOCAB]
    if not rows:
        rows = list(
            db.scalars(
                select(Vocabulary)
                .join(HskLevel, Vocabulary.hsk_level_id == HskLevel.id)
                .where(HskLevel.level_number == hsk_level)
                .order_by(Vocabulary.display_order, Vocabulary.id)
                .limit(MAX_VOCAB)
            )
        )
    return [
        {
            "hanzi": item.simplified,
            "pinyin": item.pinyin,
            "meaning": (item.meaning_translations or {}).get("en")
            or next(iter((item.meaning_translations or {}).values()), None),
        }
        for item in rows
    ]


def _grammar_rows(db: Session, lesson: Lesson | None, hsk_level: int) -> list[dict[str, Any]]:
    rows: list[GrammarPoint] = []
    if lesson:
        rows = [link.grammar_point for link in lesson.grammar_links if link.grammar_point][:MAX_GRAMMAR]
    if not rows:
        rows = list(
            db.scalars(
                select(GrammarPoint)
                .join(HskLevel, GrammarPoint.hsk_level_id == HskLevel.id)
                .where(HskLevel.level_number == hsk_level)
                .order_by(GrammarPoint.display_order, GrammarPoint.id)
                .limit(MAX_GRAMMAR)
            )
        )
    return [{"title": item.title, "pattern": item.pattern} for item in rows]


def _recent_mistakes(db: Session, user_id: int) -> list[dict[str, Any]]:
    attempts = db.scalars(
        select(QuestionAttempt)
        .options(selectinload(QuestionAttempt.question))
        .where(QuestionAttempt.user_id == user_id, QuestionAttempt.is_correct.is_(False))
        .order_by(QuestionAttempt.attempted_at.desc())
        .limit(MAX_MISTAKES)
    )
    rows = []
    for attempt in attempts:
        question = attempt.question
        prompt = str(getattr(question, "prompt", "") or "")[:120] if question is not None else ""
        rows.append(
            {
                "skill": str(getattr(question, "question_type", None) or "practice"),
                "prompt": prompt,
            }
        )
    return rows
