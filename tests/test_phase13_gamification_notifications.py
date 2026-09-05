from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.gamification_service import level_progress, record_event
from app.models import (
    Achievement,
    DeviceToken,
    LearningEvent,
    NotificationLog,
    Profile,
    User,
    UserAchievement,
    UserDailyActivity,
    XPTransaction,
)
from app.notification_service import MockNotificationProvider, dispatch_reminders
from tests.conftest import bearer, register_user


def test_xp_transactions_are_awarded_once_and_auditable(client):
    tokens = register_user(client)
    client.get("/health")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "learner@example.com"))
        assert user is not None
        now = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)

        record_event(
            db,
            user,
            "LESSON_COMPLETED",
            "lesson:phase13",
            minutes=10,
            lessons=1,
            now=now,
        )
        record_event(
            db,
            user,
            "LESSON_COMPLETED",
            "lesson:phase13",
            minutes=10,
            lessons=1,
            now=now,
        )
        db.commit()

        profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
        transactions = db.scalars(select(XPTransaction).where(XPTransaction.user_id == user.id)).all()
        events = db.scalars(select(LearningEvent).where(LearningEvent.user_id == user.id)).all()
        daily = db.scalar(select(UserDailyActivity).where(UserDailyActivity.user_id == user.id))

    assert profile is not None
    assert profile.xp_total == settings.xp_lesson_completed
    assert len(transactions) == 1
    assert transactions[0].source_key == "lesson:phase13"
    assert len(events) == 1
    assert daily is not None
    assert daily.xp == settings.xp_lesson_completed
    assert daily.minutes == 10
    assert daily.lessons == 1

    response = client.get("/api/v1/gamification/history", headers=bearer(tokens["access_token"]))
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_negative_xp_configuration_is_rejected(client):
    register_user(client)
    original = settings.xp_lesson_completed
    settings.xp_lesson_completed = -1
    try:
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == "learner@example.com"))
            assert user is not None
            with pytest.raises(ValueError, match="XP"):
                record_event(db, user, "LESSON_COMPLETED", "lesson:negative")
    finally:
        settings.xp_lesson_completed = original


def test_level_progress_uses_configured_curve():
    progress = level_progress(260)
    assert progress["level"] == 3
    assert progress["xp_into_level"] == 10
    assert progress["xp_to_next_level"] == 190
    assert progress["progress_percent"] == 5


def test_streak_timezone_missed_day_and_same_day_events(client):
    register_user(client)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "learner@example.com"))
        assert user is not None
        user.profile.timezone = "America/Los_Angeles"
        db.commit()

        record_event(
            db,
            user,
            "PRACTICE_COMPLETED",
            "practice:day-one",
            minutes=5,
            now=datetime(2026, 1, 2, 2, 0, tzinfo=UTC),
        )
        record_event(
            db,
            user,
            "SRS_REVIEW_COMPLETED",
            "review:same-day",
            reviews=1,
            now=datetime(2026, 1, 2, 3, 0, tzinfo=UTC),
        )
        assert user.profile.last_active_date == date(2026, 1, 1)
        assert user.profile.study_streak_days == 1

        record_event(
            db,
            user,
            "PRACTICE_COMPLETED",
            "practice:day-two",
            minutes=5,
            now=datetime(2026, 1, 3, 2, 0, tzinfo=UTC),
        )
        assert user.profile.last_active_date == date(2026, 1, 2)
        assert user.profile.study_streak_days == 2

        record_event(
            db,
            user,
            "PRACTICE_COMPLETED",
            "practice:after-gap",
            minutes=5,
            now=datetime(2026, 1, 5, 2, 0, tzinfo=UTC),
        )
        assert user.profile.last_active_date == date(2026, 1, 4)
        assert user.profile.study_streak_days == 1
        assert user.profile.longest_streak_days == 2


def test_daily_goal_api_updates_goal_but_not_progress(client):
    tokens = register_user(client)
    response = client.patch(
        "/api/v1/gamification/daily",
        json={"goal_type": "xp", "target": 50},
        headers=bearer(tokens["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["goal_type"] == "xp"
    assert body["goal_target"] == 50
    assert body["goal_current"] == 0


def test_achievements_unlock_once_with_progress_and_user_isolation(client):
    first = register_user(client)
    second = register_user(client, email="second@example.com")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "learner@example.com"))
        assert user is not None
        db.add(
            Achievement(
                code="phase13_xp",
                title="Phase 13 XP",
                description="Earn XP.",
                icon="star",
                criteria={"type": "xp_total", "count": 20},
                sort_order=1,
            )
        )
        db.commit()
        record_event(db, user, "LESSON_COMPLETED", "lesson:achievement", minutes=1)
        db.commit()

        custom = db.scalar(select(Achievement).where(Achievement.code == "phase13_xp"))
        assert custom is not None
        earned_count = db.scalar(
            select(func.count(UserAchievement.id))
            .where(UserAchievement.user_id == user.id, UserAchievement.achievement_id == custom.id)
        )
        assert earned_count == 1

    response = client.get("/api/v1/gamification/achievements", headers=bearer(first["access_token"]))
    assert response.status_code == 200
    row = next(item for item in response.json() if item["code"] == "phase13_xp")
    assert row["earned"] is True
    assert row["progress"] == {"current": 20, "target": 20}

    response = client.get("/api/v1/gamification/achievements", headers=bearer(second["access_token"]))
    assert response.status_code == 200
    row = next(item for item in response.json() if item["code"] == "phase13_xp")
    assert row["earned"] is False
    assert row["progress"] == {"current": 0, "target": 20}


def test_notification_preferences_device_registration_and_deduped_reminders(client):
    tokens = register_user(client)
    headers = bearer(tokens["access_token"])

    response = client.post(
        "/api/v1/notifications/devices",
        json={"token": "phase13-device-token", "platform": "ios"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["active"] is True

    response = client.patch(
        "/api/v1/notifications/preferences",
        json={"exam_reminder": True, "srs_reminder": False},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["exam_reminder"] is True
    assert response.json()["srs_reminder"] is False

    provider = MockNotificationProvider()
    with SessionLocal() as db:
        sent = dispatch_reminders(
            db,
            now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            provider=provider,
        )
        sent_again = dispatch_reminders(
            db,
            now=datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
            provider=provider,
        )

    assert sent == 1
    assert sent_again == 0
    assert len(provider.sent) == 1

    response = client.delete("/api/v1/notifications/devices/phase13-device-token", headers=headers)
    assert response.status_code == 204


def test_notification_dedupe_uses_user_timezone_local_date(client):
    register_user(client)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "learner@example.com"))
        assert user is not None
        user.profile.timezone = "America/Los_Angeles"
        db.add(DeviceToken(user_id=user.id, token="timezone-device-token", platform="ios"))
        db.commit()

        provider = MockNotificationProvider()
        dispatch_reminders(
            db,
            now=datetime(2026, 1, 2, 2, 0, tzinfo=UTC),
            provider=provider,
        )
        log = db.scalar(select(NotificationLog).where(NotificationLog.user_id == user.id))

    assert len(provider.sent) == 1
    assert log is not None
    assert log.local_date == date(2026, 1, 1)
