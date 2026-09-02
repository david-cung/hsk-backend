from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    profile: Mapped["Profile"] = relationship(back_populates="user", cascade="all, delete-orphan")


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    target_hsk_level: Mapped[int] = mapped_column(Integer, default=1)
    current_hsk_level: Mapped[int] = mapped_column(Integer, default=1)
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=30)
    study_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Ho_Chi_Minh")
    daily_new_cards_limit: Mapped[int] = mapped_column(Integer, default=10)
    daily_review_cards_limit: Mapped[int] = mapped_column(Integer, default=50)
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
    exercise_sets: Mapped[list["ExerciseSet"]] = relationship(back_populates="lesson")


class ExerciseSet(TimestampMixin, Base):
    __tablename__ = "exercise_sets"
    __table_args__ = (
        UniqueConstraint("lesson_id", "slug", name="uq_exercise_sets_lesson_slug"),
        Index("ix_exercise_sets_lesson_active", "lesson_id", "is_archived"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skill: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    lesson: Mapped[Lesson] = relationship(back_populates="exercise_sets")
    exercises: Mapped[list["Exercise"]] = relationship(back_populates="exercise_set")


class Exercise(TimestampMixin, Base):
    __tablename__ = "exercises"
    __table_args__ = (
        UniqueConstraint("exercise_set_id", "slug", name="uq_exercises_set_slug"),
        Index("ix_exercises_set_active", "exercise_set_id", "is_archived"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_set_id: Mapped[int] = mapped_column(ForeignKey("exercise_sets.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
    slug: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(180))
    exercise_type: Mapped[str] = mapped_column(String(40), index=True)
    skill: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    exercise_set: Mapped[ExerciseSet] = relationship(back_populates="exercises")
    questions: Mapped[list["Question"]] = relationship(back_populates="exercise")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_exercise_order", "exercise_id", "sort_order"),
        Index("ix_questions_lesson_order", "lesson_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int | None] = mapped_column(ForeignKey("exercises.id", ondelete="SET NULL"), nullable=True, index=True)
    question_type: Mapped[str] = mapped_column(String(40), default="multiple_choice")
    prompt: Mapped[str] = mapped_column(Text)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    points: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    lesson: Mapped[Lesson] = relationship(back_populates="questions")
    exercise: Mapped[Exercise | None] = relationship(back_populates="questions")
    answer_options: Mapped[list["AnswerOption"]] = relationship(back_populates="question")


class AudioAsset(TimestampMixin, Base):
    __tablename__ = "audio_assets"
    __table_args__ = (
        UniqueConstraint("provider", "storage_key", name="uq_audio_assets_provider_key"),
        Index("ix_audio_assets_status_language", "status", "language"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    storage_provider: Mapped[str] = mapped_column(String(40), default="tts")
    storage_key: Mapped[str] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), default="tts")
    mime_type: Mapped[str] = mapped_column(String(120), default="audio/mpeg")
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    language: Mapped[str] = mapped_column(String(20), default="zh-CN", index=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinyin: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="READY", index=True)
    asset_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class AnswerOption(TimestampMixin, Base):
    __tablename__ = "answer_options"
    __table_args__ = (UniqueConstraint("question_id", "option_id", name="uq_answer_options_question_option"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    option_id: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    option_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    question: Mapped[Question] = relationship(back_populates="answer_options")


class PracticeSession(TimestampMixin, Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        Index("ix_practice_sessions_user_status", "user_id", "status"),
        Index("ix_practice_sessions_lesson_user", "lesson_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
    exercise_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercise_sets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="IN_PROGRESS", index=True)
    question_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    answered_questions: Mapped[int] = mapped_column(Integer, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class AnswerAttempt(Base):
    __tablename__ = "answer_attempts"
    __table_args__ = (
        UniqueConstraint("practice_session_id", "idempotency_key", name="uq_answer_attempts_session_key"),
        Index("ix_answer_attempts_session_question", "practice_session_id", "question_id"),
        Index("ix_answer_attempts_user_attempted", "user_id", "attempted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    practice_session_id: Mapped[int] = mapped_column(ForeignKey("practice_sessions.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"), index=True)
    submitted_answer: Mapped[dict[str, Any]] = mapped_column(JSONB)
    normalized_answer: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    attempt_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SpeechRecording(TimestampMixin, Base):
    __tablename__ = "speech_recordings"
    __table_args__ = (
        UniqueConstraint("storage_provider", "storage_key", name="uq_speech_recordings_storage_key"),
        Index("ix_speech_recordings_user_status", "user_id", "status"),
        Index("ix_speech_recordings_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    storage_provider: Mapped[str] = mapped_column(String(40), default="mock")
    storage_key: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(120))
    extension: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    language: Mapped[str] = mapped_column(String(20), default="zh-CN", index=True)
    status: Mapped[str] = mapped_column(String(40), default="UPLOAD_AUTHORIZED", index=True)
    upload_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recording_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class SpeakingAttempt(Base):
    __tablename__ = "speaking_attempts"
    __table_args__ = (
        UniqueConstraint("answer_attempt_id", name="uq_speaking_attempts_answer_attempt"),
        Index("ix_speaking_attempts_user_status", "user_id", "processing_status"),
        Index("ix_speaking_attempts_session_question", "practice_session_id", "question_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    practice_session_id: Mapped[int] = mapped_column(ForeignKey("practice_sessions.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"), index=True)
    answer_attempt_id: Mapped[int] = mapped_column(ForeignKey("answer_attempts.id", ondelete="CASCADE"), index=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("speech_recordings.id", ondelete="RESTRICT"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    provider_model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recognized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    pronunciation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fluency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_feedback: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    tone_feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    feedback_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(40), default="PENDING", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LessonProgress(TimestampMixin, Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress_user_lesson"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="in_progress")
    score_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes_studied: Mapped[int] = mapped_column(Integer, default=0)
    speaking_attempts: Mapped[int] = mapped_column(Integer, default=0)
    speaking_acceptable_attempts: Mapped[int] = mapped_column(Integer, default=0)
    pronunciation_score_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_speaking_practice: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    total_questions: Mapped[int] = mapped_column(Integer)
    correct_count: Mapped[int] = mapped_column(Integer)
    answers: Mapped[dict[str, str]] = mapped_column(JSONB)
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


class ReviewCard(TimestampMixin, Base):
    __tablename__ = "review_cards"
    __table_args__ = (
        CheckConstraint(
            "(card_type = 'VOCABULARY' AND grammar_id IS NULL) "
            "OR (card_type = 'GRAMMAR' AND grammar_id IS NOT NULL AND vocabulary_id IS NULL)",
            name="ck_review_cards_one_content_ref",
        ),
        UniqueConstraint("user_id", "card_type", "content_key", name="uq_review_cards_user_content"),
        Index("ix_review_cards_user_due", "user_id", "due_at"),
        Index("ix_review_cards_user_type", "user_id", "card_type"),
        Index("ix_review_cards_vocabulary", "vocabulary_id"),
        Index("ix_review_cards_grammar", "grammar_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    card_type: Mapped[str] = mapped_column(String(40))
    content_key: Mapped[str] = mapped_column(String(180))
    vocabulary_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grammar_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    state: Mapped[str] = mapped_column(String(40), default="NEW", index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_days: Mapped[float] = mapped_column(Float, default=0)
    scheduler_version: Mapped[str] = mapped_column(String(40), default="fsrs-5-default")
    content_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    card_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class ReviewHistory(Base):
    __tablename__ = "review_history"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_review_history_user_key"),
        Index("ix_review_history_card_reviewed", "card_id", "reviewed_at"),
        Index("ix_review_history_user_reviewed", "user_id", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("review_cards.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rating: Mapped[str] = mapped_column(String(20))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    previous_state: Mapped[str] = mapped_column(String(40))
    new_state: Mapped[str] = mapped_column(String(40))
    previous_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    previous_stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    review_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


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
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hsk_level: Mapped[int] = mapped_column(Integer, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    question_count: Mapped[int] = mapped_column(Integer)
    exam_type: Mapped[str] = mapped_column(String(40), default="MOCK")
    status: Mapped[str] = mapped_column(String(40), default="PUBLISHED", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    blueprint: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    scoring_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExamAttempt(TimestampMixin, Base):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        Index("ix_exam_attempts_user_status", "user_id", "status"),
        Index("ix_exam_attempts_user_created", "user_id", "created_at"),
        Index("ix_exam_attempts_exam_user", "exam_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("mock_tests.id", ondelete="RESTRICT"), index=True)
    exam_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="IN_PROGRESS", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    random_seed: Mapped[int] = mapped_column(Integer)
    current_section: Mapped[str | None] = mapped_column(String(40), nullable=True)
    question_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    section_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ExamQuestionResult(Base):
    __tablename__ = "exam_question_results"
    __table_args__ = (
        UniqueConstraint("exam_attempt_id", "question_id", name="uq_exam_question_results_attempt_question"),
        Index("ix_exam_question_results_attempt", "exam_attempt_id"),
        Index("ix_exam_question_results_question", "question_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_attempt_id: Mapped[int] = mapped_column(ForeignKey("exam_attempts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"), index=True)
    section: Mapped[str] = mapped_column(String(40), index=True)
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    points: Mapped[float] = mapped_column(Float, default=0)
    max_points: Mapped[float] = mapped_column(Float, default=1)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
