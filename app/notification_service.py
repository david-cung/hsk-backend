from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.gamification_service import _daily_row, _local_today
from app.models import (
    Achievement,
    DeviceToken,
    NotificationLog,
    NotificationPreference,
    User,
)
from app.review_service import due_cards, user_timezone

REMINDER_COPY = {
    "daily": ("Daily reminder", "Your daily Chinese goal is waiting."),
    "srs": ("Review reminder", "{count} vocabulary reviews are due."),
    "streak": ("Streak reminder", "Your {count}-day streak is at risk."),
}


class NotificationProvider(Protocol):
    name: str

    def send(self, *, token: str, platform: str, title: str, body: str) -> None: ...


class MockNotificationProvider:
    name = "mock"

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, *, token: str, platform: str, title: str, body: str) -> None:
        self.sent.append({"token": token, "platform": platform, "title": title, "body": body})


def get_notification_provider() -> NotificationProvider:
    if settings.notification_provider == "mock":
        return MockNotificationProvider()
    return MockNotificationProvider()


def ensure_preferences(db: Session, user: User) -> NotificationPreference:
    row = db.scalar(select(NotificationPreference).where(NotificationPreference.user_id == user.id))
    if row is None:
        row = NotificationPreference(user_id=user.id)
        db.add(row)
        db.flush()
    return row


def update_preferences(
    db: Session,
    user: User,
    payload: dict[str, bool | None],
) -> NotificationPreference:
    row = ensure_preferences(db, user)
    for field in ("daily_reminder", "streak_reminder", "srs_reminder", "exam_reminder", "achievement_notification"):
        if payload.get(field) is not None:
            setattr(row, field, bool(payload[field]))
    db.commit()
    db.refresh(row)
    return row


def register_device(db: Session, user: User, *, token: str, platform: str) -> DeviceToken:
    token = (token or "").strip()
    platform = (platform or "local").lower()
    if not token or len(token) > 255:
        raise ValueError("Device token is invalid")
    if platform not in {"ios", "android", "web", "local"}:
        raise ValueError("Unsupported device platform")
    existing = db.scalar(select(DeviceToken).where(DeviceToken.token == token))
    if existing:
        existing.user_id = user.id
        existing.platform = platform
        existing.active = True
        db.commit()
        db.refresh(existing)
        return existing
    device = DeviceToken(user_id=user.id, token=token, platform=platform, active=True)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def unregister_device(db: Session, user: User, token: str) -> None:
    device = db.scalar(select(DeviceToken).where(DeviceToken.token == token, DeviceToken.user_id == user.id))
    if device is None:
        raise ValueError("Device token not found")
    device.active = False
    db.commit()


def dispatch_reminders(
    db: Session,
    *,
    now: datetime | None = None,
    provider: NotificationProvider | None = None,
) -> int:
    current = now or datetime.now(UTC)
    sender = provider or get_notification_provider()
    sent = 0
    users = db.scalars(select(User)).all()
    for user in users:
        prefs = ensure_preferences(db, user)
        local_day = _local_today(user, current)
        hour = current.astimezone(user_timezone(user)).hour
        if hour < 18:
            continue
        devices = list(
            db.scalars(select(DeviceToken).where(DeviceToken.user_id == user.id, DeviceToken.active.is_(True)))
        )
        if not devices:
            continue
        daily = _daily_row(db, user.id, local_day)
        if prefs.daily_reminder and (daily is None or not daily.goal_completed):
            sent += _deliver(db, user, devices, "daily", local_day, REMINDER_COPY["daily"][1], sender)
        if prefs.streak_reminder and (user.profile.study_streak_days or 0) >= 2 and (daily is None or (daily.minutes == 0 and daily.xp == 0)):
            body = REMINDER_COPY["streak"][1].format(count=user.profile.study_streak_days)
            sent += _deliver(db, user, devices, "streak", local_day, body, sender)
        if prefs.srs_reminder:
            due = due_cards(db, user, limit=1)
            if due.due_count:
                body = REMINDER_COPY["srs"][1].format(count=due.due_count)
                sent += _deliver(db, user, devices, "srs", local_day, body, sender)
    db.commit()
    return sent


def notify_achievement_unlocked(
    db: Session,
    user: User,
    achievement: Achievement,
    *,
    now: datetime | None = None,
    provider: NotificationProvider | None = None,
) -> bool:
    prefs = ensure_preferences(db, user)
    if not prefs.achievement_notification:
        return False
    devices = list(
        db.scalars(select(DeviceToken).where(DeviceToken.user_id == user.id, DeviceToken.active.is_(True)))
    )
    if not devices:
        return False
    current = now or datetime.now(UTC)
    local_day = _local_today(user, current)
    kind = f"achievement:{achievement.id}"
    existing = db.scalar(
        select(NotificationLog).where(
            NotificationLog.user_id == user.id,
            NotificationLog.kind == kind,
            NotificationLog.local_date == local_day,
        )
    )
    if existing:
        return False
    title = "Achievement unlocked"
    body = achievement.title
    db.add(NotificationLog(user_id=user.id, kind=kind, title=title, body=body, local_date=local_day))
    db.flush()
    sender = provider or get_notification_provider()
    for device in devices:
        sender.send(token=device.token, platform=device.platform, title=title, body=body)
    return True


def _deliver(
    db: Session,
    user: User,
    devices: list[DeviceToken],
    kind: str,
    local_day,
    body: str,
    provider: NotificationProvider,
) -> int:
    existing = db.scalar(
        select(NotificationLog).where(
            NotificationLog.user_id == user.id,
            NotificationLog.kind == kind,
            NotificationLog.local_date == local_day,
        )
    )
    if existing:
        return 0
    title = REMINDER_COPY[kind][0]
    db.add(NotificationLog(user_id=user.id, kind=kind, title=title, body=body, local_date=local_day))
    db.flush()
    for device in devices:
        provider.send(token=device.token, platform=device.platform, title=title, body=body)
    return 1
