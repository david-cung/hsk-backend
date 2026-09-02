from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Question,
    ReviewCard,
    ReviewHistory,
    SavedWord,
    User,
)
from app.models import (
    QuestionAttempt as AnswerAttempt,
)
from app.review_scheduler import (
    CardSchedulingState,
    ReviewRating,
    ReviewState,
    SpacedRepetitionScheduler,
)
from app.skill_schemas import (
    RecommendationOut,
    ReviewCardOut,
    ReviewCardStatusOut,
    ReviewDueOut,
    ReviewHistoryOut,
    ReviewRatingPreviewOut,
    ReviewSummaryOut,
)

logger = logging.getLogger("hsk.review")
SCHEDULER = SpacedRepetitionScheduler()
REVIEW_SOURCES = {"MANUAL_REVIEW", "PRACTICE", "LISTENING", "SPEAKING", "WRITING"}


def user_timezone(user: User) -> ZoneInfo:
    name = getattr(user.profile, "timezone", None) or settings.review_default_timezone
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        logger.warning("invalid_user_timezone", extra={"user_id": user.id, "timezone": name})
        return ZoneInfo(settings.review_default_timezone)


def user_today_bounds(user: User, now: datetime | None = None) -> tuple[datetime, datetime, date]:
    current = _utc(now)
    tz = user_timezone(user)
    local_today = current.astimezone(tz).date()
    start = datetime.combine(local_today, time.min, tzinfo=tz).astimezone(UTC)
    end = start + timedelta(days=1)
    return start, end, local_today


def enroll_saved_word(db: Session, user: User, saved_word: SavedWord) -> ReviewCard:
    content = {
        "hanzi": saved_word.hanzi,
        "pinyin": saved_word.pinyin,
        "meaning": saved_word.meaning,
        "hsk_level": saved_word.hsk_level,
    }
    return enroll_card(
        db,
        user,
        "VOCABULARY",
        vocabulary_id=saved_word.id,
        content_key=f"saved-word:{saved_word.id}",
        content=content,
        source="SAVED_WORD",
    )


def enroll_card(
    db: Session,
    user: User,
    card_type: str,
    *,
    vocabulary_id: int | None = None,
    grammar_id: str | None = None,
    content_key: str | None = None,
    content: dict[str, Any] | None = None,
    source: str = "MANUAL",
) -> ReviewCard:
    normalized_type = card_type.upper()
    if normalized_type not in {"VOCABULARY", "GRAMMAR"}:
        raise ValueError("Unsupported review card type")
    if normalized_type == "VOCABULARY":
        if vocabulary_id is None and not content_key:
            raise ValueError("Vocabulary review cards need vocabulary_id or content_key")
        grammar_id = None
        key = content_key or f"saved-word:{vocabulary_id}"
    else:
        if not grammar_id and not content_key:
            raise ValueError("Grammar review cards need grammar_id or content_key")
        vocabulary_id = None
        key = content_key or f"grammar:{grammar_id}"

    existing = db.scalar(
        select(ReviewCard).where(
            ReviewCard.user_id == user.id,
            ReviewCard.card_type == normalized_type,
            ReviewCard.content_key == key,
        )
    )
    if existing:
        if content:
            existing.content_snapshot = {**(existing.content_snapshot or {}), **content}
        return existing

    initial = SCHEDULER.initialize_card()
    card = ReviewCard(
        user_id=user.id,
        card_type=normalized_type,
        content_key=key,
        vocabulary_id=vocabulary_id,
        grammar_id=grammar_id if normalized_type == "GRAMMAR" else None,
        state=initial.state.value,
        due_at=initial.due_at,
        last_reviewed_at=initial.last_reviewed_at,
        reps=initial.reps,
        lapses=initial.lapses,
        stability=initial.stability,
        difficulty=initial.difficulty,
        interval_days=initial.interval_days,
        scheduler_version=SCHEDULER.version,
        content_snapshot=content or {},
        card_metadata={"enrolled_source": source},
    )
    db.add(card)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ReviewCard).where(
                ReviewCard.user_id == user.id,
                ReviewCard.card_type == normalized_type,
                ReviewCard.content_key == key,
            )
        )
        if existing:
            return existing
        raise
    return card


def due_cards(db: Session, user: User, limit: int | None = None, now: datetime | None = None) -> ReviewDueOut:
    current = _utc(now)
    review_limit = getattr(user.profile, "daily_review_cards_limit", None) or settings.review_cards_per_day
    new_limit = getattr(user.profile, "daily_new_cards_limit", None) or settings.review_new_cards_per_day
    max_items = limit or review_limit + new_limit
    due_existing = list(
        db.scalars(
            select(ReviewCard)
            .where(
                ReviewCard.user_id == user.id,
                ReviewCard.due_at <= current,
                ReviewCard.state != ReviewState.NEW.value,
            )
            .order_by(ReviewCard.due_at, ReviewCard.id)
            .limit(review_limit)
        ).all()
    )
    new_cards = list(
        db.scalars(
            select(ReviewCard)
            .where(
                ReviewCard.user_id == user.id,
                ReviewCard.due_at <= current,
                ReviewCard.state == ReviewState.NEW.value,
            )
            .order_by(ReviewCard.created_at, ReviewCard.id)
            .limit(new_limit)
        ).all()
    )
    items = (due_existing + new_cards)[:max_items]
    due_count = int(
        db.scalar(
            select(func.count()).select_from(ReviewCard).where(ReviewCard.user_id == user.id, ReviewCard.due_at <= current)
        )
        or 0
    )
    overdue_count = int(
        db.scalar(
            select(func.count()).select_from(ReviewCard).where(ReviewCard.user_id == user.id, ReviewCard.due_at < current)
        )
        or 0
    )
    total_new = int(
        db.scalar(
            select(func.count())
            .select_from(ReviewCard)
            .where(ReviewCard.user_id == user.id, ReviewCard.state == ReviewState.NEW.value, ReviewCard.due_at <= current)
        )
        or 0
    )
    next_review_at = db.scalar(
        select(func.min(ReviewCard.due_at)).where(ReviewCard.user_id == user.id, ReviewCard.due_at > current)
    )
    return ReviewDueOut(
        items=[card_to_out(card, current) for card in items],
        due_count=due_count,
        overdue_count=overdue_count,
        new_count=total_new,
        review_limit=review_limit,
        new_limit=new_limit,
        next_review_at=next_review_at,
    )


def review_card(
    db: Session,
    user: User,
    card_id: int,
    rating: ReviewRating,
    idempotency_key: str,
    source: str = "MANUAL_REVIEW",
    metadata: dict[str, Any] | None = None,
    reviewed_at: datetime | None = None,
) -> tuple[ReviewCard, ReviewHistory, bool]:
    if source not in REVIEW_SOURCES:
        logger.warning("invalid_review_source", extra={"user_id": user.id, "source": source})
        raise ValueError("Invalid review source")

    existing_history = db.scalar(
        select(ReviewHistory).where(ReviewHistory.user_id == user.id, ReviewHistory.idempotency_key == idempotency_key)
    )
    if existing_history:
        card = db.scalar(select(ReviewCard).where(ReviewCard.id == existing_history.card_id, ReviewCard.user_id == user.id))
        if not card:
            raise ValueError("Review card not found")
        return card, existing_history, True

    stmt = select(ReviewCard).where(ReviewCard.id == card_id, ReviewCard.user_id == user.id)
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    card = db.scalar(stmt)
    if not card:
        raise ValueError("Review card not found")

    current = _utc(reviewed_at)
    previous = _state_from_card(card)
    result = SCHEDULER.process_review(previous, rating, current)
    history = ReviewHistory(
        card_id=card.id,
        user_id=user.id,
        rating=rating.value,
        reviewed_at=current,
        previous_state=card.state,
        new_state=result.state.value,
        previous_due_at=card.due_at,
        new_due_at=result.due_at,
        previous_stability=card.stability,
        new_stability=result.stability,
        previous_difficulty=card.difficulty,
        new_difficulty=result.difficulty,
        source=source,
        idempotency_key=idempotency_key,
        review_metadata=metadata or {},
    )
    card.state = result.state.value
    card.due_at = result.due_at
    card.last_reviewed_at = current
    card.reps = result.reps
    card.lapses = result.lapses
    card.stability = result.stability
    card.difficulty = result.difficulty
    card.interval_days = result.interval_days
    card.scheduler_version = result.scheduler_version
    db.add(history)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing_history = db.scalar(
            select(ReviewHistory).where(ReviewHistory.user_id == user.id, ReviewHistory.idempotency_key == idempotency_key)
        )
        if existing_history:
            existing_card = db.scalar(select(ReviewCard).where(ReviewCard.id == existing_history.card_id, ReviewCard.user_id == user.id))
            if existing_card:
                return existing_card, existing_history, True
        raise
    return card, history, False


def review_summary(db: Session, user: User, now: datetime | None = None) -> ReviewSummaryOut:
    current = _utc(now)
    start, end, _today = user_today_bounds(user, current)
    due_count = int(
        db.scalar(
            select(func.count()).select_from(ReviewCard).where(ReviewCard.user_id == user.id, ReviewCard.due_at <= current)
        )
        or 0
    )
    overdue_count = int(
        db.scalar(
            select(func.count()).select_from(ReviewCard).where(ReviewCard.user_id == user.id, ReviewCard.due_at < current)
        )
        or 0
    )
    new_count = int(
        db.scalar(
            select(func.count()).select_from(ReviewCard).where(ReviewCard.user_id == user.id, ReviewCard.state == ReviewState.NEW.value)
        )
        or 0
    )
    reviewed_today = int(
        db.scalar(
            select(func.count())
            .select_from(ReviewHistory)
            .where(ReviewHistory.user_id == user.id, ReviewHistory.reviewed_at >= start, ReviewHistory.reviewed_at < end)
        )
        or 0
    )
    retention_row = db.execute(
        select(
            func.count(ReviewHistory.id),
            func.sum(case((ReviewHistory.rating != ReviewRating.AGAIN.value, 1), else_=0)),
        ).where(ReviewHistory.user_id == user.id, ReviewHistory.reviewed_at >= start - timedelta(days=30))
    ).one()
    total = int(retention_row[0] or 0)
    remembered = int(retention_row[1] or 0)
    next_review_at = db.scalar(
        select(func.min(ReviewCard.due_at)).where(ReviewCard.user_id == user.id, ReviewCard.due_at > current)
    )
    return ReviewSummaryOut(
        due_count=due_count,
        overdue_count=overdue_count,
        new_count=new_count,
        reviewed_today=reviewed_today,
        retention=round((remembered / total) * 100, 2) if total else None,
        review_streak_days=review_streak(db, user, current),
        next_review_at=next_review_at,
    )


def review_streak(db: Session, user: User, now: datetime | None = None) -> int:
    current = _utc(now)
    tz = user_timezone(user)
    rows = db.scalars(
        select(ReviewHistory.reviewed_at)
        .where(ReviewHistory.user_id == user.id, ReviewHistory.reviewed_at >= current - timedelta(days=90))
        .order_by(ReviewHistory.reviewed_at.desc())
    ).all()
    active = {row.astimezone(tz).date() if row.tzinfo else row.replace(tzinfo=UTC).astimezone(tz).date() for row in rows}
    if not active:
        return 0
    cursor = current.astimezone(tz).date()
    if cursor not in active:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor in active:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def history(db: Session, user: User, limit: int = 50) -> list[ReviewHistoryOut]:
    rows = db.execute(
        select(ReviewHistory, ReviewCard.card_type)
        .join(ReviewCard, ReviewCard.id == ReviewHistory.card_id)
        .where(ReviewHistory.user_id == user.id)
        .order_by(ReviewHistory.reviewed_at.desc(), ReviewHistory.id.desc())
        .limit(limit)
    ).all()
    return [
        ReviewHistoryOut(
            id=row.id,
            card_id=row.card_id,
            card_type=card_type,
            rating=row.rating,
            reviewed_at=row.reviewed_at,
            previous_state=row.previous_state,
            new_state=row.new_state,
            previous_due_at=row.previous_due_at,
            new_due_at=row.new_due_at,
            source=row.source,
        )
        for row, card_type in rows
    ]


def card_statuses(db: Session, user: User, card_type: str | None = None) -> list[ReviewCardStatusOut]:
    stmt = select(ReviewCard).where(ReviewCard.user_id == user.id).order_by(ReviewCard.updated_at.desc(), ReviewCard.id.desc())
    if card_type:
        stmt = stmt.where(ReviewCard.card_type == card_type.upper())
    cards = db.scalars(stmt).all()
    return [
        ReviewCardStatusOut(
            id=card.id,
            card_type=card.card_type,
            vocabulary_id=card.vocabulary_id,
            grammar_id=card.grammar_id,
            content_key=card.content_key,
            state=card.state,
            due_at=card.due_at,
            last_reviewed_at=card.last_reviewed_at,
        )
        for card in cards
    ]


def practice_review_signal(
    db: Session,
    user: User,
    question: Question,
    attempt: AnswerAttempt,
    *,
    pronunciation_score: float | None = None,
) -> None:
    source = _source_for_question(question)
    content_review_signal(
        db,
        user,
        question,
        correct=attempt.is_correct,
        source=source,
        idempotency_key=f"{source.lower()}:{attempt.id}",
        metadata={"question_id": question.id, "attempt_id": attempt.id},
        reviewed_at=attempt.attempted_at,
        pronunciation_score=pronunciation_score,
    )


def content_review_signal(
    db: Session,
    user: User,
    question: Question,
    *,
    correct: bool,
    source: str,
    idempotency_key: str,
    metadata: dict[str, Any] | None = None,
    reviewed_at: datetime | None = None,
    pronunciation_score: float | None = None,
) -> None:
    card_payload = _card_payload_from_question(question)
    if not card_payload:
        return
    rating = _rating_from_practice(correct, source, pronunciation_score)
    card = enroll_card(db, user, card_payload["card_type"], **card_payload["kwargs"], source=source)
    review_card(
        db,
        user,
        card.id,
        rating,
        idempotency_key=idempotency_key,
        source=source,
        metadata=metadata or {"question_id": question.id},
        reviewed_at=reviewed_at,
    )


def review_recommendation(db: Session, user: User) -> RecommendationOut | None:
    summary = review_summary(db, user)
    if summary.due_count <= 0:
        return None
    return RecommendationOut(
        type="DUE_REVIEW",
        target_label="Daily Review",
        reason=f"{summary.due_count} review cards are due today.",
        activity_type="REVIEW",
    )


def card_to_out(card: ReviewCard, now: datetime | None = None) -> ReviewCardOut:
    current = _utc(now)
    previews = SCHEDULER.preview(_state_from_card(card), current)
    return ReviewCardOut(
        id=card.id,
        card_type=card.card_type,
        state=card.state,
        due_at=card.due_at,
        last_reviewed_at=card.last_reviewed_at,
        overdue_seconds=max(round((current - _utc(card.due_at)).total_seconds()), 0) if card.due_at <= current else 0,
        content=card.content_snapshot or {},
        rating_previews=[
            ReviewRatingPreviewOut(
                rating=rating.value,
                due_at=result.due_at,
                interval_days=result.interval_days,
                interval_label=_interval_label(current, result.due_at),
            )
            for rating, result in previews.items()
        ],
    )


def _state_from_card(card: ReviewCard) -> CardSchedulingState:
    return CardSchedulingState(
        state=ReviewState(card.state),
        due_at=_utc(card.due_at),
        last_reviewed_at=_utc(card.last_reviewed_at) if card.last_reviewed_at else None,
        reps=card.reps,
        lapses=card.lapses,
        stability=card.stability,
        difficulty=card.difficulty,
        interval_days=card.interval_days,
    )


def _source_for_question(question: Question) -> str:
    qtype = (question.question_type or "").upper()
    if qtype in {"WORD_ORDER", "SENTENCE_REORDER", "TRANSLATION_TO_CHINESE", "GUIDED_WRITING"}:
        return "WRITING"
    if qtype in {"SPEAKING", "PRONUNCIATION"}:
        return "SPEAKING"
    if qtype in {"LISTENING", "DICTATION"}:
        return "LISTENING"
    return "PRACTICE"


def _rating_from_practice(correct: bool, source: str, pronunciation_score: float | None) -> ReviewRating:
    if source == "SPEAKING" and pronunciation_score is not None:
        if pronunciation_score < settings.review_speaking_again_threshold:
            return ReviewRating.AGAIN
        if pronunciation_score < settings.review_speaking_hard_threshold:
            return ReviewRating.HARD
        if pronunciation_score < settings.review_speaking_good_threshold:
            return ReviewRating.GOOD
        return ReviewRating.EASY
    return ReviewRating.GOOD if correct else ReviewRating.AGAIN


def _card_payload_from_question(question: Question) -> dict[str, Any] | None:
    reference_type = (question.reference_type or "").upper()
    qtype = (question.question_type or "").upper()
    config = question.configuration or {}
    if reference_type == "VOCABULARY" and question.reference_id:
        key = str(question.reference_id).strip()
        return {
            "card_type": "VOCABULARY",
            "kwargs": {
                "content_key": f"vocab:{key}",
                "content": _vocabulary_snapshot(question, key),
            },
        }
    if reference_type == "GRAMMAR" or qtype == "GRAMMAR":
        key = str(question.reference_id or config.get("grammar_id") or question.prompt).strip()
        if not key:
            return None
        return {
            "card_type": "GRAMMAR",
            "kwargs": {
                "grammar_id": key[:180],
                "content_key": f"grammar:{key[:160]}",
                "content": _grammar_snapshot(question, key),
            },
        }
    if qtype in {"LISTENING", "DICTATION"}:
        transcript = config.get("transcript") or config.get("expected_text")
        if isinstance(transcript, str) and 0 < len(transcript.strip()) <= 24:
            key = transcript.strip()
            return {
                "card_type": "VOCABULARY",
                "kwargs": {
                    "content_key": f"vocab:{key}",
                    "content": _vocabulary_snapshot(question, key),
                },
            }
    if qtype in {"SPEAKING", "PRONUNCIATION"}:
        text = config.get("expected_text") or config.get("display_text")
        if isinstance(text, str) and 0 < len(text.strip()) <= 24:
            key = text.strip()
            return {
                "card_type": "VOCABULARY",
                "kwargs": {
                    "content_key": f"vocab:{key}",
                    "content": _vocabulary_snapshot(question, key),
                },
            }
    if qtype in {"WORD_ORDER", "SENTENCE_REORDER", "TRANSLATION_TO_CHINESE", "GUIDED_WRITING"}:
        vocabulary = config.get("required_vocabulary") or config.get("required_keywords") or []
        if isinstance(vocabulary, list) and vocabulary:
            key = str(vocabulary[0]).strip()
            if key:
                return {
                    "card_type": "VOCABULARY",
                    "kwargs": {
                        "content_key": f"vocab:{key}",
                        "content": _vocabulary_snapshot(question, key),
                    },
                }
        grammar = config.get("required_grammar") or []
        if isinstance(grammar, list) and grammar:
            key = str(grammar[0]).strip()
            if key:
                return {
                    "card_type": "GRAMMAR",
                    "kwargs": {
                        "grammar_id": key[:180],
                        "content_key": f"grammar:{key[:160]}",
                        "content": _grammar_snapshot(question, key),
                    },
                }
    return None


def _vocabulary_snapshot(question: Question, hanzi: str) -> dict[str, Any]:
    config = question.configuration or {}
    return {
        "hanzi": hanzi,
        "pinyin": config.get("pinyin"),
        "meaning": config.get("translation") or config.get("meaning") or question.explanation,
        "prompt": question.prompt,
        "example": config.get("example"),
        "audio_asset_id": config.get("audio_asset_id"),
        "lesson_id": question.lesson_id,
    }


def _grammar_snapshot(question: Question, key: str) -> dict[str, Any]:
    config = question.configuration or {}
    return {
        "grammar_id": key,
        "pattern": config.get("pattern") or question.prompt,
        "meaning": config.get("meaning"),
        "example": config.get("example"),
        "explanation": question.explanation,
        "lesson_id": question.lesson_id,
    }


def _interval_label(now: datetime, due_at: datetime) -> str:
    seconds = max((due_at - now).total_seconds(), 0)
    if seconds < 3600:
        minutes = max(round(seconds / 60), 1)
        return f"{minutes} min"
    if seconds < 86400:
        hours = max(round(seconds / 3600), 1)
        return f"{hours} h"
    days = max(round(seconds / 86400), 1)
    return f"{days} d"


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
