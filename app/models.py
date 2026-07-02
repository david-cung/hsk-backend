from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    profile: Mapped["Profile"] = relationship(back_populates="user", cascade="all, delete-orphan")


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    target_hsk_level: Mapped[int] = mapped_column(Integer, default=1)
    current_hsk_level: Mapped[int] = mapped_column(Integer, default=1)
    learning_goal: Mapped[str | None] = mapped_column(String(80), nullable=True)
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=30)
    study_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="profile")


class HskLevel(Base):
    __tablename__ = "hsk_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    level_number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_characters: Mapped[int] = mapped_column(Integer, default=0)

    lessons: Mapped[list["Lesson"]] = relationship(back_populates="hsk_level")


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    hsk_level_id: Mapped[int] = mapped_column(ForeignKey("hsk_levels.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lesson_type: Mapped[str] = mapped_column(String(40), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=10)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    hsk_level: Mapped[HskLevel] = relationship(back_populates="lessons")
    questions: Mapped[list["Question"]] = relationship(back_populates="lesson")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    question_type: Mapped[str] = mapped_column(String(40), default="multiple_choice")
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    lesson: Mapped[Lesson] = relationship(back_populates="questions")


class LessonProgress(TimestampMixin, Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress_user_lesson"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="in_progress")
    score_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes_studied: Mapped[int] = mapped_column(Integer, default=0)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    total_questions: Mapped[int] = mapped_column(Integer)
    correct_count: Mapped[int] = mapped_column(Integer)
    answers: Mapped[dict[str, str]] = mapped_column(JSONB)
    results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavedWord(Base):
    __tablename__ = "saved_words"
    __table_args__ = (UniqueConstraint("user_id", "hanzi", name="uq_saved_words_user_hanzi"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    hanzi: Mapped[str] = mapped_column(String(40))
    pinyin: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meaning: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hsk_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Achievement(Base):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MockTest(Base):
    __tablename__ = "mock_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    hsk_level: Mapped[int] = mapped_column(Integer, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    question_count: Mapped[int] = mapped_column(Integer)
