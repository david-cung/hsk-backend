from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Achievement,
    HskLevel,
    LearningEvent,
    Lesson,
    LessonProgress,
    Profile,
    QuizAttempt,
    SavedWord,
    User,
    UserAchievement,
    UserDailyActivity,
    XPTransaction,
)
from app.review_service import user_timezone

logger = logging.getLogger(__name__)

EVENT_XP = {
    "LESSON_COMPLETED": lambda: settings.xp_lesson_completed,
    "PRACTICE_COMPLETED": lambda: settings.xp_practice_completed,
    "QUESTION_CORRECT": lambda: settings.xp_question_correct,
    "WRITING_COMPLETED": lambda: settings.xp_writing_completed,
    "LISTENING_COMPLETED": lambda: settings.xp_listening_completed,
    "SPEAKING_COMPLETED": lambda: settings.xp_speaking_completed,
    "EXAM_COMPLETED": lambda: settings.xp_exam_completed,
    "SRS_REVIEW_COMPLETED": lambda: settings.xp_srs_review_completed,
    "AI_CONVERSATION_COMPLETED": lambda: settings.xp_ai_conversation_completed,
    "DAILY_GOAL_COMPLETED": lambda: settings.xp_daily_goal_bonus,
}

DAILY_GOAL_TYPES = {"minutes", "exercises", "xp", "lessons"}


def record_event(
    db: Session,
    user: User,
    event_type: str,
    source_key: str,
    *,
    minutes: int = 0,
    exercises: int = 0,
    lessons: int = 0,
    reviews: int = 0,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> LearningEvent | None:
    if event_type not in EVENT_XP:
        raise ValueError("Unsupported learning event")
    if not source_key or len(source_key) > 180:
        raise ValueError("Invalid event source")
    xp_amount = int(EVENT_XP[event_type]())
    if xp_amount < 0:
        raise ValueError("XP must be non-negative")
    current = now or datetime.now(UTC)
    profile = _lock_profile(db, user)
    existing = db.scalar(
        select(LearningEvent).where(
            LearningEvent.user_id == user.id,
            LearningEvent.event_type == event_type,
            LearningEvent.source_key == source_key,
        )
    )
    if existing:
        return existing
    event = LearningEvent(
        user_id=user.id,
        event_type=event_type,
        source_key=source_key,
        event_metadata=metadata or {},
        created_at=current,
    )
    nested = db.begin_nested()
    try:
        db.add(event)
        db.flush()
        if xp_amount:
            db.add(
                XPTransaction(
                    user_id=user.id,
                    event_type=event_type,
                    source_key=source_key,
                    xp=xp_amount,
                    event_metadata=metadata or {},
                    created_at=current,
                )
            )
            profile.xp_total = int(profile.xp_total or 0) + xp_amount
        nested.commit()
    except IntegrityError:
        nested.rollback()
        return db.scalar(
            select(LearningEvent).where(
                LearningEvent.user_id == user.id,
                LearningEvent.event_type == event_type,
                LearningEvent.source_key == source_key,
            )
        )
    _touch_daily_activity(
        db,
        user,
        profile,
        minutes=minutes,
        exercises=exercises,
        lessons=lessons,
        reviews=reviews,
        xp=xp_amount,
        now=current,
    )
    evaluate_achievements(db, user)
    return event


def level_progress(xp: int) -> dict[str, int | float]:
    total = max(int(xp or 0), 0)
    level = 1
    remaining = total
    needed = settings.xp_level_base
    while remaining >= needed:
        remaining -= needed
        level += 1
        needed = settings.xp_level_base + (level - 1) * settings.xp_level_step
    percent = round((remaining / needed) * 100, 2) if needed else 100
    return {
        "xp": total,
        "level": level,
        "xp_into_level": remaining,
        "xp_to_next_level": max(needed - remaining, 0),
        "level_xp_required": needed,
        "progress_percent": min(percent, 100),
    }


def gamification_profile(db: Session, user: User, *, now: datetime | None = None) -> dict[str, Any]:
    profile = user.profile
    progress = level_progress(profile.xp_total or 0)
    today = _local_today(user, now)
    daily = _daily_row(db, user.id, today)
    goal = daily_goal_state(profile, daily)
    return {
        **progress,
        "streak_days": profile.study_streak_days,
        "longest_streak_days": profile.longest_streak_days,
        "timezone": profile.timezone,
        "daily_goal_type": profile.daily_goal_type or "minutes",
        "daily_goal_target": _goal_target(profile),
        "daily_goal_current": goal["current"],
        "daily_goal_completed": goal["completed"],
        "today_xp": daily.xp if daily else 0,
        "today_minutes": daily.minutes if daily else 0,
        "today_exercises": daily.exercises if daily else 0,
        "today_lessons": daily.lessons if daily else 0,
        "today_reviews": daily.reviews if daily else 0,
        "today": today.isoformat(),
    }


def xp_history(db: Session, user: User, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset))
    total = db.scalar(select(func.count(XPTransaction.id)).where(XPTransaction.user_id == user.id)) or 0
    rows = db.scalars(
        select(XPTransaction)
        .where(XPTransaction.user_id == user.id)
        .order_by(XPTransaction.created_at.desc(), XPTransaction.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "source_id": row.source_key,
                "xp": row.xp,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


def daily_snapshot(db: Session, user: User, *, now: datetime | None = None) -> dict[str, Any]:
    profile = user.profile
    today = _local_today(user, now)
    daily = _daily_row(db, user.id, today)
    goal = daily_goal_state(profile, daily)
    return {
        "date": today.isoformat(),
        "timezone": profile.timezone,
        "xp": daily.xp if daily else 0,
        "minutes": daily.minutes if daily else 0,
        "exercises": daily.exercises if daily else 0,
        "lessons": daily.lessons if daily else 0,
        "reviews": daily.reviews if daily else 0,
        "goal_type": profile.daily_goal_type or "minutes",
        "goal_target": _goal_target(profile),
        "goal_current": goal["current"],
        "goal_completed": goal["completed"],
        "streak_days": profile.study_streak_days,
    }


def update_daily_goal(db: Session, user: User, *, goal_type: str | None, target: int | None) -> dict[str, Any]:
    profile = user.profile
    if goal_type:
        kind = goal_type.lower()
        if kind not in DAILY_GOAL_TYPES:
            raise ValueError("Unsupported daily goal type")
        profile.daily_goal_type = kind
    if target is not None:
        if target < 1 or target > 500:
            raise ValueError("Daily goal target is out of range")
        if (profile.daily_goal_type or "minutes") == "minutes" and target > 240:
            raise ValueError("Daily goal target is out of range")
        profile.daily_goal_minutes = target
    db.commit()
    db.refresh(user)
    return daily_snapshot(db, user)


def list_achievements(db: Session, user: User) -> list[dict[str, Any]]:
    evaluate_achievements(db, user)
    db.commit()
    earned = {
        row.achievement_id: row.earned_at
        for row in db.scalars(select(UserAchievement).where(UserAchievement.user_id == user.id))
    }
    rows = db.scalars(select(Achievement).order_by(Achievement.sort_order, Achievement.id)).all()
    return [
        {
            "id": item.id,
            "code": item.code,
            "title": item.title,
            "description": item.description,
            "icon": item.icon,
            "earned": item.id in earned,
            "earned_at": earned.get(item.id),
            "progress": _achievement_progress(db, user, item),
        }
        for item in rows
    ]


def evaluate_achievements(db: Session, user: User) -> list[str]:
    earned_ids = set(
        db.scalars(select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id))
    )
    unlocked: list[str] = []
    for achievement in db.scalars(select(Achievement)).all():
        if achievement.id in earned_ids:
            continue
        if not _achievement_met(db, user, achievement):
            continue
        nested = db.begin_nested()
        try:
            db.add(UserAchievement(user_id=user.id, achievement_id=achievement.id))
            db.flush()
            nested.commit()
        except IntegrityError:
            nested.rollback()
            continue
        unlocked.append(achievement.code)
        try:
            from app.notification_service import notify_achievement_unlocked

            notify_achievement_unlocked(db, user, achievement)
        except Exception:
            logger.warning("achievement_notification_failed", exc_info=True, extra={"user_id": user.id})
    return unlocked


def daily_goal_state(profile: Profile, daily: UserDailyActivity | None) -> dict[str, Any]:
    target = _goal_target(profile)
    kind = profile.daily_goal_type or "minutes"
    current = 0
    if daily:
        current = {
            "minutes": daily.minutes,
            "exercises": daily.exercises,
            "xp": daily.xp,
            "lessons": daily.lessons,
        }.get(kind, daily.minutes)
    return {"current": current, "target": target, "completed": current >= target}


def _lock_profile(db: Session, user: User) -> Profile:
    stmt = select(Profile).where(Profile.user_id == user.id)
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    profile = db.scalar(stmt)
    if profile is None:
        raise ValueError("Profile not found")
    user.profile = profile
    return profile


def _touch_daily_activity(
    db: Session,
    user: User,
    profile: Profile,
    *,
    minutes: int,
    exercises: int,
    lessons: int,
    reviews: int,
    xp: int,
    now: datetime,
) -> None:
    local_day = _local_today(user, now)
    row = _daily_row_for_update(db, user.id, local_day)
    row.minutes += max(int(minutes), 0)
    row.exercises += max(int(exercises), 0)
    row.lessons += max(int(lessons), 0)
    row.reviews += max(int(reviews), 0)
    row.xp += max(int(xp), 0)
    _update_streak(profile, local_day)
    goal = daily_goal_state(profile, row)
    if goal["completed"] and not row.goal_completed:
        row.goal_completed = True
        _award_daily_goal_bonus(db, user, profile, row, local_day, now)


def _update_streak(profile: Profile, local_day: date) -> None:
    last = profile.last_active_date
    if last == local_day:
        profile.study_streak_days = max(profile.study_streak_days or 0, 1)
    elif last is not None and (local_day - last).days == 1:
        profile.study_streak_days = (profile.study_streak_days or 0) + 1
    else:
        profile.study_streak_days = 1
    profile.last_active_date = local_day
    profile.longest_streak_days = max(profile.longest_streak_days or 0, profile.study_streak_days)


def _local_today(user: User, now: datetime | None = None) -> date:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(user_timezone(user)).date()


def _daily_row(db: Session, user_id: int, local_day: date) -> UserDailyActivity | None:
    return db.scalar(
        select(UserDailyActivity).where(
            UserDailyActivity.user_id == user_id, UserDailyActivity.local_date == local_day
        )
    )


def _daily_row_for_update(db: Session, user_id: int, local_day: date) -> UserDailyActivity:
    stmt = select(UserDailyActivity).where(
        UserDailyActivity.user_id == user_id, UserDailyActivity.local_date == local_day
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is not None:
        return row
    nested = db.begin_nested()
    try:
        row = UserDailyActivity(user_id=user_id, local_date=local_day)
        db.add(row)
        db.flush()
        nested.commit()
        return row
    except IntegrityError:
        nested.rollback()
        existing = db.scalar(stmt)
        if existing is None:
            raise
        return existing


def _award_daily_goal_bonus(
    db: Session,
    user: User,
    profile: Profile,
    row: UserDailyActivity,
    local_day: date,
    now: datetime,
) -> None:
    bonus_key = f"daily-goal:{local_day.isoformat()}"
    if db.scalar(
        select(LearningEvent.id).where(
            LearningEvent.user_id == user.id,
            LearningEvent.event_type == "DAILY_GOAL_COMPLETED",
            LearningEvent.source_key == bonus_key,
        )
    ):
        return
    nested = db.begin_nested()
    try:
        bonus = int(settings.xp_daily_goal_bonus)
        db.add(
            LearningEvent(
                user_id=user.id,
                event_type="DAILY_GOAL_COMPLETED",
                source_key=bonus_key,
                event_metadata={"date": local_day.isoformat()},
                created_at=now,
            )
        )
        if bonus > 0:
            db.add(
                XPTransaction(
                    user_id=user.id,
                    event_type="DAILY_GOAL_COMPLETED",
                    source_key=bonus_key,
                    xp=bonus,
                    event_metadata={"date": local_day.isoformat()},
                    created_at=now,
                )
            )
            profile.xp_total = int(profile.xp_total or 0) + bonus
            row.xp += bonus
        nested.commit()
    except IntegrityError:
        nested.rollback()


def _goal_target(profile: Profile) -> int:
    # One numeric target field: daily_goal_minutes is reused for every goal type.
    return profile.daily_goal_minutes or 30


def _event_count(db: Session, user_id: int, event_type: str) -> int:
    return db.scalar(
        select(func.count(LearningEvent.id)).where(
            LearningEvent.user_id == user_id, LearningEvent.event_type == event_type
        )
    ) or 0


def _achievement_met(db: Session, user: User, achievement: Achievement) -> bool:
    criteria = achievement.criteria or {}
    kind = str(criteria.get("type") or achievement.code)
    if achievement.code == "first_quiz" or kind == "first_quiz":
        return (db.scalar(select(func.count(QuizAttempt.id)).where(QuizAttempt.user_id == user.id)) or 0) > 0
    if achievement.code == "first_word" or kind == "first_word":
        return (db.scalar(select(func.count(SavedWord.id)).where(SavedWord.user_id == user.id)) or 0) > 0
    if achievement.code == "three_lessons" or kind == "three_lessons":
        return (
            db.scalar(
                select(func.count(LessonProgress.id)).where(
                    LessonProgress.user_id == user.id, LessonProgress.status == "completed"
                )
            )
            or 0
        ) >= 3
    if kind == "event_count":
        return _event_count(db, user.id, str(criteria.get("event"))) >= int(criteria.get("count") or 1)
    if kind == "xp_total":
        return int(user.profile.xp_total or 0) >= int(criteria.get("count") or 0)
    if kind == "streak":
        return int(user.profile.study_streak_days or 0) >= int(criteria.get("count") or 0)
    if kind == "perfect_practice":
        return db.scalar(
            select(LearningEvent.id).where(
                LearningEvent.user_id == user.id,
                LearningEvent.event_type == "PRACTICE_COMPLETED",
                LearningEvent.event_metadata.contains({"perfect": True}),
            )
        ) is not None
    if kind == "hsk_complete":
        level_number = int(criteria.get("level") or 1)
        level = db.scalar(select(HskLevel).where(HskLevel.level_number == level_number))
        if level is None:
            return False
        total = db.scalar(select(func.count(Lesson.id)).where(Lesson.hsk_level_id == level.id)) or 0
        if total <= 0:
            return False
        done = db.scalar(
            select(func.count(LessonProgress.id))
            .join(Lesson, Lesson.id == LessonProgress.lesson_id)
            .where(
                LessonProgress.user_id == user.id,
                LessonProgress.status == "completed",
                Lesson.hsk_level_id == level.id,
            )
        ) or 0
        return done >= total
    return False


def _achievement_progress(db: Session, user: User, achievement: Achievement) -> dict[str, int] | None:
    criteria = achievement.criteria or {}
    kind = str(criteria.get("type") or "")
    if kind == "event_count":
        current = _event_count(db, user.id, str(criteria.get("event")))
        target = int(criteria.get("count") or 1)
        return {"current": min(current, target), "target": target}
    if kind == "xp_total":
        target = int(criteria.get("count") or 0)
        return {"current": min(int(user.profile.xp_total or 0), target), "target": target}
    if kind == "streak":
        target = int(criteria.get("count") or 0)
        return {"current": min(int(user.profile.study_streak_days or 0), target), "target": target}
    if achievement.code == "three_lessons":
        current = db.scalar(
            select(func.count(LessonProgress.id)).where(
                LessonProgress.user_id == user.id, LessonProgress.status == "completed"
            )
        ) or 0
        return {"current": min(int(current), 3), "target": 3}
    return None
