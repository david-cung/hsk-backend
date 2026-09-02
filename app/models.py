from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
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


class OAuthProvider(StrEnum):
    GOOGLE = "google"


class ContentStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class VocabularyLearningStatus(StrEnum):
    NEW = "new"
    LEARNING = "learning"
    LEARNED = "learned"
    MASTERED = "mastered"


class GrammarLearningStatus(StrEnum):
    VIEWED = "viewed"
    COMPLETED = "completed"


class ExerciseType(StrEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    MULTIPLE_SELECT = "multiple_select"
    FILL_BLANK = "fill_blank"
    MATCHING = "matching"
    ORDERING = "ordering"
    TRANSLATION = "translation"
    GRAMMAR = "grammar"
    READING = "reading"
    DICTATION = "dictation"
    TEXT_INPUT = "text_input"
    VOCABULARY_RECALL = "vocabulary_recall"
    LISTENING = "listening"
    SPEAKING = "speaking"
    WRITING = "writing"
    PRONUNCIATION = "pronunciation"


class PracticeSessionStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ImportJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportEntityType(StrEnum):
    HSK_LEVELS = "hsk_levels"
    COURSES = "courses"
    LESSONS = "lessons"
    VOCABULARY = "vocabulary"
    GRAMMAR = "grammar"
    EXAMPLE_SENTENCES = "example_sentences"
    EXERCISES = "exercises"


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_type]


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    profile: Mapped["Profile"] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(cascade="all, delete-orphan")
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(cascade="all, delete-orphan")
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[OAuthProvider] = mapped_column(
        Enum(OAuthProvider, name="oauth_provider", values_callable=lambda values: [item.value for item in values])
    )
    provider_user_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    learning_goal: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_hsk_level: Mapped[int] = mapped_column(Integer, default=1)
    current_hsk_level: Mapped[int] = mapped_column(Integer, default=1)
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=30)
    study_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(80), default="Asia/Ho_Chi_Minh", server_default="Asia/Ho_Chi_Minh"
    )
    daily_new_cards_limit: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    daily_review_cards_limit: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="profile")


class HskLevel(TimestampMixin, Base):
    __tablename__ = "hsk_levels"
    __table_args__ = (
        UniqueConstraint("display_order", name="uq_hsk_levels_display_order"),
        CheckConstraint("level_number BETWEEN 1 AND 6", name="ck_hsk_levels_level_number"),
        CheckConstraint("display_order >= 0", name="ck_hsk_levels_display_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    level_number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_characters: Mapped[int] = mapped_column(Integer, default=0)
    display_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", values_callable=enum_values),
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    lessons: Mapped[list["Lesson"]] = relationship(back_populates="hsk_level")
    courses: Mapped[list["Course"]] = relationship(back_populates="hsk_level")


class Course(TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("hsk_level_id", "course_type", name="uq_course_level_type"),
        UniqueConstraint("hsk_level_id", "sort_order", name="uq_course_level_order"),
        CheckConstraint("sort_order >= 0", name="ck_courses_sort_order"),
        CheckConstraint("length(trim(title)) > 0", name="ck_courses_title_not_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hsk_level_id: Mapped[int] = mapped_column(
        ForeignKey("hsk_levels.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(180))
    title_translations: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_translations: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    course_type: Mapped[str] = mapped_column(String(40))
    sort_order: Mapped[int] = mapped_column(Integer)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", values_callable=enum_values),
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    hsk_level: Mapped[HskLevel] = relationship(back_populates="courses")
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="course")


class Lesson(TimestampMixin, Base):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("course_id", "title", name="uq_lesson_course_title"),
        UniqueConstraint("course_id", "sort_order", name="uq_lesson_course_order"),
        CheckConstraint("duration_minutes > 0", name="ck_lessons_duration"),
        CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 1 AND 6",
            name="ck_lessons_difficulty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hsk_level_id: Mapped[int] = mapped_column(ForeignKey("hsk_levels.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lesson_type: Mapped[str] = mapped_column(String(40), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=10)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    listening_audio_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content_status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", values_callable=enum_values),
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    hsk_level: Mapped[HskLevel] = relationship(back_populates="lessons")
    course: Mapped[Course] = relationship(back_populates="lessons")
    listening_audio_asset: Mapped["AudioAsset | None"] = relationship(
        foreign_keys=[listening_audio_asset_id]
    )
    questions: Mapped[list["Question"]] = relationship(back_populates="lesson")
    vocabulary_links: Mapped[list["LessonVocabulary"]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", order_by="LessonVocabulary.sort_order"
    )
    grammar_links: Mapped[list["LessonGrammarPoint"]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", order_by="LessonGrammarPoint.sort_order"
    )
    exercise_sets: Mapped[list["ExerciseSet"]] = relationship(back_populates="lesson")


class AudioAsset(TimestampMixin, Base):
    __tablename__ = "audio_assets"
    __table_args__ = (
        UniqueConstraint("storage_provider", "storage_key", name="uq_audio_storage_key"),
        Index("ix_audio_assets_status_language", "status", "language"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    storage_provider: Mapped[str] = mapped_column(String(40), default="external")
    storage_key: Mapped[str] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), default="tts", server_default="tts")
    mime_type: Mapped[str] = mapped_column(
        String(120), default="audio/mpeg", server_default="audio/mpeg"
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    language: Mapped[str] = mapped_column(
        String(20), default="zh-CN", server_default="zh-CN", index=True
    )
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinyin: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), default="READY", server_default="READY", index=True
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)


class ExampleSentence(TimestampMixin, Base):
    __tablename__ = "example_sentences"
    __table_args__ = (
        UniqueConstraint("chinese", "pinyin", name="uq_example_chinese_pinyin"),
        CheckConstraint(
            "length(trim(chinese)) > 0", name="ck_example_chinese_not_empty"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chinese: Mapped[str] = mapped_column(Text)
    pinyin: Mapped[str | None] = mapped_column(Text, nullable=True)
    translations: Mapped[dict[str, str]] = mapped_column(JSONB)
    audio_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", values_callable=enum_values),
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    audio_asset: Mapped[AudioAsset | None] = relationship()
    vocabulary_links: Mapped[list["VocabularyExample"]] = relationship(
        back_populates="example", cascade="all, delete-orphan"
    )
    grammar_links: Mapped[list["GrammarExample"]] = relationship(
        back_populates="example", cascade="all, delete-orphan"
    )


class Vocabulary(TimestampMixin, Base):
    __tablename__ = "vocabulary"
    __table_args__ = (
        UniqueConstraint(
            "hsk_level_id",
            "simplified",
            "pinyin",
            name="uq_vocabulary_level_simplified_pinyin",
        ),
        Index("ix_vocabulary_search", "simplified", "pinyin"),
        Index(
            "uq_vocabulary_level_simplified_missing_pinyin",
            "hsk_level_id",
            "simplified",
            unique=True,
            postgresql_where=text("pinyin IS NULL"),
        ),
        CheckConstraint(
            "length(trim(simplified)) > 0",
            name="ck_vocabulary_simplified_not_empty",
        ),
        CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 1 AND 6",
            name="ck_vocabulary_difficulty",
        ),
        CheckConstraint(
            "display_order >= 0", name="ck_vocabulary_display_order"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hsk_level_id: Mapped[int] = mapped_column(
        ForeignKey("hsk_levels.id", ondelete="RESTRICT"), index=True
    )
    simplified: Mapped[str] = mapped_column(String(80), index=True)
    traditional: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pinyin: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    meaning_translations: Mapped[dict[str, str]] = mapped_column(JSONB)
    part_of_speech: Mapped[str] = mapped_column(String(40), default="other", index=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    audio_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", values_callable=enum_values),
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    hsk_level: Mapped[HskLevel] = relationship()
    audio_asset: Mapped[AudioAsset | None] = relationship()
    lesson_links: Mapped[list["LessonVocabulary"]] = relationship(
        back_populates="vocabulary", cascade="all, delete-orphan"
    )
    example_links: Mapped[list["VocabularyExample"]] = relationship(
        back_populates="vocabulary", cascade="all, delete-orphan", order_by="VocabularyExample.sort_order"
    )


class GrammarPoint(TimestampMixin, Base):
    __tablename__ = "grammar_points"
    __table_args__ = (
        UniqueConstraint("hsk_level_id", "title", name="uq_grammar_level_title"),
        CheckConstraint(
            "length(trim(title)) > 0", name="ck_grammar_title_not_empty"
        ),
        CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 1 AND 6",
            name="ck_grammar_difficulty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hsk_level_id: Mapped[int] = mapped_column(
        ForeignKey("hsk_levels.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(180))
    title_translations: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    explanation_translations: Mapped[dict[str, str]] = mapped_column(JSONB)
    pattern: Mapped[str | None] = mapped_column(String(500), nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", values_callable=enum_values),
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    hsk_level: Mapped[HskLevel] = relationship()
    lesson_links: Mapped[list["LessonGrammarPoint"]] = relationship(
        back_populates="grammar_point", cascade="all, delete-orphan"
    )
    example_links: Mapped[list["GrammarExample"]] = relationship(
        back_populates="grammar_point", cascade="all, delete-orphan", order_by="GrammarExample.sort_order"
    )


class LessonVocabulary(Base):
    __tablename__ = "lesson_vocabulary"
    __table_args__ = (
        UniqueConstraint("lesson_id", "vocabulary_id", name="uq_lesson_vocabulary"),
        UniqueConstraint("lesson_id", "sort_order", name="uq_lesson_vocabulary_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), index=True
    )
    vocabulary_id: Mapped[int] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer)

    lesson: Mapped[Lesson] = relationship(back_populates="vocabulary_links")
    vocabulary: Mapped[Vocabulary] = relationship(back_populates="lesson_links")


class LessonGrammarPoint(Base):
    __tablename__ = "lesson_grammar_points"
    __table_args__ = (
        UniqueConstraint("lesson_id", "grammar_point_id", name="uq_lesson_grammar"),
        UniqueConstraint("lesson_id", "sort_order", name="uq_lesson_grammar_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), index=True
    )
    grammar_point_id: Mapped[int] = mapped_column(
        ForeignKey("grammar_points.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer)

    lesson: Mapped[Lesson] = relationship(back_populates="grammar_links")
    grammar_point: Mapped[GrammarPoint] = relationship(back_populates="lesson_links")


class VocabularyExample(Base):
    __tablename__ = "vocabulary_examples"
    __table_args__ = (
        UniqueConstraint("vocabulary_id", "example_id", name="uq_vocabulary_example"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vocabulary_id: Mapped[int] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="CASCADE"), index=True
    )
    example_id: Mapped[int] = mapped_column(
        ForeignKey("example_sentences.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    vocabulary: Mapped[Vocabulary] = relationship(back_populates="example_links")
    example: Mapped[ExampleSentence] = relationship(back_populates="vocabulary_links")


class GrammarExample(Base):
    __tablename__ = "grammar_examples"
    __table_args__ = (
        UniqueConstraint("grammar_point_id", "example_id", name="uq_grammar_example"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grammar_point_id: Mapped[int] = mapped_column(
        ForeignKey("grammar_points.id", ondelete="CASCADE"), index=True
    )
    example_id: Mapped[int] = mapped_column(
        ForeignKey("example_sentences.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    grammar_point: Mapped[GrammarPoint] = relationship(back_populates="example_links")
    example: Mapped[ExampleSentence] = relationship(back_populates="grammar_links")


class ExerciseSet(TimestampMixin, Base):
    __tablename__ = "exercise_sets"
    __table_args__ = (
        UniqueConstraint("lesson_id", "slug", name="uq_exercise_set_lesson_slug"),
        UniqueConstraint("lesson_id", "sort_order", name="uq_exercise_set_lesson_order"),
        CheckConstraint("sort_order >= 0", name="ck_exercise_sets_sort_order"),
        CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 1 AND 6",
            name="ck_exercise_sets_difficulty",
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_exercise_sets_title_not_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="RESTRICT"), index=True
    )
    slug: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skill: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", values_callable=enum_values),
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    lesson: Mapped[Lesson] = relationship(back_populates="exercise_sets")
    exercises: Mapped[list["Exercise"]] = relationship(
        back_populates="exercise_set", order_by="Exercise.sort_order"
    )


class Exercise(TimestampMixin, Base):
    __tablename__ = "exercises"
    __table_args__ = (
        UniqueConstraint(
            "exercise_set_id", "external_id", name="uq_exercise_set_external_id"
        ),
        UniqueConstraint(
            "exercise_set_id", "sort_order", name="uq_exercise_set_exercise_order"
        ),
        CheckConstraint("sort_order >= 0", name="ck_exercises_sort_order"),
        CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 1 AND 6",
            name="ck_exercises_difficulty",
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_exercises_title_not_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_set_id: Mapped[int] = mapped_column(
        ForeignKey("exercise_sets.id", ondelete="RESTRICT"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(180))
    exercise_type: Mapped[ExerciseType] = mapped_column(
        Enum(ExerciseType, name="exercise_type", values_callable=enum_values),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(180))
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    skill: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    vocabulary_id: Mapped[int | None] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="SET NULL"), nullable=True, index=True
    )
    grammar_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("grammar_points.id", ondelete="SET NULL"), nullable=True, index=True
    )
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", values_callable=enum_values),
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    exercise_set: Mapped[ExerciseSet] = relationship(back_populates="exercises")
    vocabulary: Mapped[Vocabulary | None] = relationship()
    grammar_point: Mapped[GrammarPoint | None] = relationship()
    questions: Mapped[list["Question"]] = relationship(
        back_populates="exercise", order_by="Question.sort_order"
    )


class Question(TimestampMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id", "external_id", name="uq_question_exercise_external_id"
        ),
        UniqueConstraint("exercise_id", "sort_order", name="uq_question_exercise_order"),
        CheckConstraint("sort_order >= 0", name="ck_questions_sort_order"),
        CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 1 AND 6",
            name="ck_questions_difficulty",
        ),
        CheckConstraint("points > 0", name="ck_questions_points"),
        CheckConstraint("length(trim(prompt)) > 0", name="ck_questions_prompt_not_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    question_type: Mapped[str] = mapped_column(String(40), default="multiple_choice")
    prompt: Mapped[str] = mapped_column(Text)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    points: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", values_callable=enum_values),
        default=ContentStatus.PUBLISHED,
        server_default=ContentStatus.PUBLISHED.value,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    lesson: Mapped[Lesson] = relationship(back_populates="questions")
    exercise: Mapped[Exercise | None] = relationship(back_populates="questions")


class LessonProgress(TimestampMixin, Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress_user_lesson"),
        Index("ix_lesson_progress_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="in_progress")
    score_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes_studied: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    speaking_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    speaking_acceptable_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    pronunciation_score_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_speaking_practice: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (Index("ix_quiz_attempts_user_finished", "user_id", "finished_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    total_questions: Mapped[int] = mapped_column(Integer)
    correct_count: Mapped[int] = mapped_column(Integer)
    answers: Mapped[dict[str, str]] = mapped_column(JSONB)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PracticeSession(TimestampMixin, Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        Index("ix_practice_sessions_user_status", "user_id", "status"),
        Index("ix_practice_sessions_user_lesson", "user_id", "lesson_id"),
        CheckConstraint("total_questions >= 0", name="ck_practice_sessions_total"),
        CheckConstraint("answered_questions >= 0", name="ck_practice_sessions_answered"),
        CheckConstraint("correct_answers >= 0", name="ck_practice_sessions_correct"),
        CheckConstraint(
            "answered_questions <= total_questions",
            name="ck_practice_sessions_answered_total",
        ),
        CheckConstraint(
            "correct_answers <= answered_questions",
            name="ck_practice_sessions_correct_answered",
        ),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_practice_sessions_score"),
        CheckConstraint("time_spent_seconds >= 0", name="ck_practice_sessions_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="RESTRICT"), index=True
    )
    exercise_set_id: Mapped[int] = mapped_column(
        ForeignKey("exercise_sets.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[PracticeSessionStatus] = mapped_column(
        Enum(
            PracticeSessionStatus,
            name="practice_session_status",
            values_callable=enum_values,
        ),
        default=PracticeSessionStatus.IN_PROGRESS,
        server_default=PracticeSessionStatus.IN_PROGRESS.value,
        index=True,
    )
    question_ids: Mapped[list[int]] = mapped_column(JSONB)
    selection_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    total_questions: Mapped[int] = mapped_column(Integer)
    answered_questions: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    correct_answers: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    time_spent_seconds: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    lesson: Mapped[Lesson] = relationship()
    exercise_set: Mapped[ExerciseSet] = relationship()
    attempts: Mapped[list["QuestionAttempt"]] = relationship(
        back_populates="session", order_by="QuestionAttempt.attempted_at"
    )


class QuestionAttempt(Base):
    __tablename__ = "question_attempts"
    __table_args__ = (
        UniqueConstraint(
            "practice_session_id",
            "idempotency_key",
            name="uq_question_attempt_session_idempotency",
        ),
        Index(
            "ix_question_attempts_session_question",
            "practice_session_id",
            "question_id",
        ),
        Index("ix_question_attempts_user_attempted", "user_id", "attempted_at"),
        CheckConstraint("score >= 0", name="ck_question_attempts_score"),
        CheckConstraint("score <= max_score", name="ck_question_attempts_score_max"),
        CheckConstraint("max_score > 0", name="ck_question_attempts_max_score"),
        CheckConstraint("time_spent_seconds >= 0", name="ck_question_attempts_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    practice_session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(80))
    submitted_answer: Mapped[Any] = mapped_column(JSONB)
    normalized_answer: Mapped[Any] = mapped_column(JSONB)
    is_correct: Mapped[bool] = mapped_column(Boolean, index=True)
    score: Mapped[int] = mapped_column(Integer)
    max_score: Mapped[int] = mapped_column(Integer)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    attempt_metadata: Mapped[dict[str, Any]] = mapped_column(
        "attempt_metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    session: Mapped[PracticeSession] = relationship(back_populates="attempts")
    question: Mapped[Question] = relationship()


class SavedWord(Base):
    __tablename__ = "saved_words"
    __table_args__ = (
        UniqueConstraint("user_id", "vocabulary_id", name="uq_saved_words_user_vocabulary"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vocabulary_id: Mapped[int | None] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="CASCADE"), nullable=True, index=True
    )
    hanzi: Mapped[str] = mapped_column(String(40))
    pinyin: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meaning: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hsk_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserVocabularyProgress(TimestampMixin, Base):
    __tablename__ = "user_vocabulary_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "vocabulary_id", name="uq_user_vocabulary_progress"),
        Index("ix_user_vocabulary_progress_user_status", "user_id", "status"),
        CheckConstraint(
            "practiced_count >= 0 AND correct_count >= 0 AND incorrect_count >= 0",
            name="ck_user_vocabulary_progress_counts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vocabulary_id: Mapped[int] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[VocabularyLearningStatus] = mapped_column(
        Enum(
            VocabularyLearningStatus,
            name="vocabulary_learning_status",
            values_callable=enum_values,
        ),
        default=VocabularyLearningStatus.NEW,
        server_default=VocabularyLearningStatus.NEW.value,
    )
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    learned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    practiced_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    correct_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class UserGrammarProgress(TimestampMixin, Base):
    __tablename__ = "user_grammar_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "grammar_point_id", name="uq_user_grammar_progress"),
        Index("ix_user_grammar_progress_user_status", "user_id", "status"),
        CheckConstraint(
            "practiced_count >= 0 AND correct_count >= 0 AND incorrect_count >= 0",
            name="ck_user_grammar_progress_counts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    grammar_point_id: Mapped[int] = mapped_column(
        ForeignKey("grammar_points.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[GrammarLearningStatus] = mapped_column(
        Enum(
            GrammarLearningStatus,
            name="grammar_learning_status",
            values_callable=enum_values,
        ),
        default=GrammarLearningStatus.VIEWED,
        server_default=GrammarLearningStatus.VIEWED.value,
    )
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    practiced_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    correct_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class ImportJob(TimestampMixin, Base):
    __tablename__ = "import_jobs"
    __table_args__ = (Index("ix_import_jobs_entity_status", "entity_type", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requested_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entity_type: Mapped[ImportEntityType] = mapped_column(
        Enum(ImportEntityType, name="import_entity_type", values_callable=enum_values)
    )
    source_format: Mapped[str] = mapped_column(String(10))
    status: Mapped[ImportJobStatus] = mapped_column(
        Enum(ImportJobStatus, name="import_job_status", values_callable=enum_values),
        default=ImportJobStatus.PENDING,
        server_default=ImportJobStatus.PENDING.value,
        index=True,
    )
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    created_records: Mapped[int] = mapped_column(Integer, default=0)
    updated_records: Mapped[int] = mapped_column(Integer, default=0)
    skipped_records: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    achievement_id: Mapped[int] = mapped_column(
        ForeignKey("achievements.id", ondelete="CASCADE"), index=True
    )
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MockTest(Base):
    __tablename__ = "mock_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hsk_level: Mapped[int] = mapped_column(Integer, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    question_count: Mapped[int] = mapped_column(Integer)
    exam_type: Mapped[str] = mapped_column(String(40), default="MOCK", server_default="MOCK")
    status: Mapped[str] = mapped_column(
        String(40), default="PUBLISHED", server_default="PUBLISHED", index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    blueprint: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    scoring_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SpeechRecording(TimestampMixin, Base):
    __tablename__ = "speech_recordings"
    __table_args__ = (
        UniqueConstraint(
            "storage_provider", "storage_key", name="uq_speech_recordings_storage_key"
        ),
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
    recording_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


class SpeakingAttempt(Base):
    __tablename__ = "speaking_attempts"
    __table_args__ = (
        UniqueConstraint(
            "answer_attempt_id", name="uq_speaking_attempts_answer_attempt"
        ),
        Index("ix_speaking_attempts_user_status", "user_id", "processing_status"),
        Index(
            "ix_speaking_attempts_session_question",
            "practice_session_id",
            "question_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    practice_session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    answer_attempt_id: Mapped[int] = mapped_column(
        ForeignKey("question_attempts.id", ondelete="CASCADE"), index=True
    )
    recording_id: Mapped[int] = mapped_column(
        ForeignKey("speech_recordings.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    provider_model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recognized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    pronunciation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fluency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_feedback: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    tone_feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    feedback_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(40), default="PENDING", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewCard(TimestampMixin, Base):
    __tablename__ = "review_cards"
    __table_args__ = (
        CheckConstraint(
            "(card_type = 'VOCABULARY' AND grammar_id IS NULL) "
            "OR (card_type = 'GRAMMAR' AND grammar_id IS NOT NULL AND vocabulary_id IS NULL)",
            name="ck_review_cards_one_content_ref",
        ),
        UniqueConstraint(
            "user_id", "card_type", "content_key", name="uq_review_cards_user_content"
        ),
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
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_days: Mapped[float] = mapped_column(Float, default=0)
    scheduler_version: Mapped[str] = mapped_column(String(40), default="fsrs-5-default")
    content_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    card_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


class ReviewHistory(Base):
    __tablename__ = "review_history"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_review_history_user_key"
        ),
        Index("ix_review_history_card_reviewed", "card_id", "reviewed_at"),
        Index("ix_review_history_user_reviewed", "user_id", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("review_cards.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rating: Mapped[str] = mapped_column(String(20))
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    previous_state: Mapped[str] = mapped_column(String(40))
    new_state: Mapped[str] = mapped_column(String(40))
    previous_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    new_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    previous_stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    review_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


class ExamAttempt(TimestampMixin, Base):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        Index("ix_exam_attempts_user_status", "user_id", "status"),
        Index("ix_exam_attempts_user_created", "user_id", "created_at"),
        Index("ix_exam_attempts_exam_user", "exam_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exam_id: Mapped[int] = mapped_column(
        ForeignKey("mock_tests.id", ondelete="RESTRICT"), index=True
    )
    exam_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="IN_PROGRESS", index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    random_seed: Mapped[int] = mapped_column(Integer)
    current_section: Mapped[str | None] = mapped_column(String(40), nullable=True)
    question_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    section_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


class ExamQuestionResult(Base):
    __tablename__ = "exam_question_results"
    __table_args__ = (
        UniqueConstraint(
            "exam_attempt_id",
            "question_id",
            name="uq_exam_question_results_attempt_question",
        ),
        Index("ix_exam_question_results_attempt", "exam_attempt_id"),
        Index("ix_exam_question_results_question", "question_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_attempt_id: Mapped[int] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    section: Mapped[str] = mapped_column(String(40), index=True)
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    points: Mapped[float] = mapped_column(Float, default=0)
    max_points: Mapped[float] = mapped_column(Float, default=1)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
