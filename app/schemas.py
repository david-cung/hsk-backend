from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import ContentStatus
from app.practice_engine import canonical_exercise_type, validate_question_configuration


class UserOut(BaseModel):
    id: int
    email: EmailStr
    display_name: str | None
    is_admin: bool


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RegisterIn(AuthIn):
    password: str = Field(min_length=8, max_length=72)
    display_name: str | None = None


class RefreshTokenIn(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class GoogleAuthIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=4096)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    new_password: str = Field(min_length=8, max_length=72)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class MessageOut(BaseModel):
    message: str


class AdminStatusOut(BaseModel):
    status: str


class ProfileOut(BaseModel):
    learning_goal: str | None
    target_hsk_level: int
    current_hsk_level: int
    daily_goal_minutes: int
    study_streak_days: int
    onboarding_completed: bool


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learning_goal: str | None = Field(default=None, max_length=80)
    target_hsk_level: int | None = Field(default=None, ge=1, le=6)
    current_hsk_level: int | None = Field(default=None, ge=1, le=6)
    daily_goal_minutes: int | None = Field(default=None, ge=1, le=240)
    onboarding_completed: bool | None = None


class HskLevelOut(BaseModel):
    id: int
    level_number: int
    name: str | None = None
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None
    description_translations: dict[str, str] | None = None
    total_characters: int
    display_order: int = 0
    status: str = "published"
    metadata: dict[str, Any] | None = None
    course_count: int = 0


class CourseOut(BaseModel):
    id: int
    hsk_level_id: int
    hsk_level: int
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None
    description_translations: dict[str, str] | None = None
    thumbnail_url: str | None
    course_type: str
    order: int
    status: str
    metadata: dict[str, Any] | None = None
    lesson_count: int = 0


class LessonListOut(BaseModel):
    id: int
    hsk_level_id: int | None = None
    course_id: int | None = None
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None
    description_translations: dict[str, str] | None = None
    lesson_type: str
    sort_order: int
    duration_minutes: int
    status: str | None
    score_percent: int | None
    lesson_number: int | None = None
    difficulty: int | None = None
    content_status: str = "published"


class AudioAssetOut(BaseModel):
    id: int
    url: str | None
    storage_provider: str
    storage_key: str
    duration_ms: int | None
    format: str | None
    locale: str | None


class ExampleSentenceOut(BaseModel):
    id: int
    chinese: str
    pinyin: str | None
    translations: dict[str, str]
    audio: AudioAssetOut | None = None


class VocabularyListItemOut(BaseModel):
    id: int
    simplified: str
    traditional: str | None
    pinyin: str | None
    meaning_translations: dict[str, str]
    part_of_speech: str
    hsk_level: int
    difficulty: int | None
    display_order: int
    audio: AudioAssetOut | None = None
    learning_status: str = "new"
    is_favorite: bool = False


class LessonReferenceOut(BaseModel):
    id: int
    course_id: int
    title: str
    lesson_number: int


class VocabularyDetailOut(VocabularyListItemOut):
    hsk_level_id: int
    category: str | None
    examples: list[ExampleSentenceOut]
    lessons: list[LessonReferenceOut]
    status: str
    metadata: dict[str, Any] | None = None


class VocabularyPageOut(BaseModel):
    items: list[VocabularyListItemOut]
    page: int
    page_size: int
    total: int
    pages: int


class GrammarListItemOut(BaseModel):
    id: int
    title: str
    title_translations: dict[str, str] | None = None
    explanation_translations: dict[str, str]
    pattern: str | None
    hsk_level: int
    difficulty: int | None
    display_order: int
    learning_status: str | None = None


class GrammarDetailOut(GrammarListItemOut):
    hsk_level_id: int
    examples: list[ExampleSentenceOut]
    lessons: list[LessonReferenceOut]
    status: str
    metadata: dict[str, Any] | None = None


class LessonDetailOut(BaseModel):
    id: int
    hsk_level_id: int
    course_id: int | None = None
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None
    description_translations: dict[str, str] | None = None
    lesson_type: str
    lesson_number: int | None = None
    duration_minutes: int
    difficulty: int | None = None
    content_status: str = "published"
    content: dict[str, Any] | None
    vocabulary: list[VocabularyListItemOut] = Field(default_factory=list)
    grammar: list[GrammarListItemOut] = Field(default_factory=list)
    reading: Any | None = None
    listening: Any | None = None
    listening_audio: AudioAssetOut | None = None
    practice: Any | None = None


class ContentStatusUpdate(BaseModel):
    status: Literal["draft", "published", "archived"]


class HskLevelCreate(BaseModel):
    level_number: int = Field(ge=1, le=6)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    display_order: int = Field(ge=0)
    total_characters: int = Field(default=0, ge=0)
    status: Literal["draft", "published", "archived"] = "published"
    metadata: dict[str, Any] | None = None


class HskLevelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    display_order: int | None = Field(default=None, ge=0)
    total_characters: int | None = Field(default=None, ge=0)
    status: Literal["draft", "published", "archived"] | None = None
    metadata: dict[str, Any] | None = None


class CourseCreate(BaseModel):
    hsk_level_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=180)
    title_translations: dict[str, str] | None = None
    description: str | None = None
    description_translations: dict[str, str] | None = None
    thumbnail_url: str | None = Field(default=None, max_length=500)
    course_type: str = Field(min_length=1, max_length=40)
    order: int = Field(ge=0)
    status: Literal["draft", "published", "archived"] = "published"
    metadata: dict[str, Any] | None = None


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    title_translations: dict[str, str] | None = None
    description: str | None = None
    description_translations: dict[str, str] | None = None
    thumbnail_url: str | None = Field(default=None, max_length=500)
    course_type: str | None = Field(default=None, min_length=1, max_length=40)
    order: int | None = Field(default=None, ge=0)
    status: Literal["draft", "published", "archived"] | None = None
    metadata: dict[str, Any] | None = None


class LessonCreate(BaseModel):
    course_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    lesson_type: str = Field(min_length=1, max_length=40)
    order: int = Field(ge=0)
    estimated_duration: int = Field(default=10, ge=1, le=600)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    listening_audio_asset_id: int | None = Field(default=None, ge=1)
    status: Literal["draft", "published", "archived"] = "published"
    metadata: dict[str, Any] | None = None
    content: dict[str, Any] | None = None


class LessonUpdate(BaseModel):
    course_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    lesson_type: str | None = Field(default=None, min_length=1, max_length=40)
    order: int | None = Field(default=None, ge=0)
    estimated_duration: int | None = Field(default=None, ge=1, le=600)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    listening_audio_asset_id: int | None = Field(default=None, ge=1)
    status: Literal["draft", "published", "archived"] | None = None
    metadata: dict[str, Any] | None = None
    content: dict[str, Any] | None = None


class VocabularyCreate(BaseModel):
    hsk_level_id: int = Field(ge=1)
    simplified: str = Field(min_length=1, max_length=80)
    traditional: str | None = Field(default=None, max_length=80)
    pinyin: str | None = Field(default=None, max_length=160)
    meaning_translations: dict[str, str]
    part_of_speech: str = Field(default="other", min_length=1, max_length=40)
    category: str | None = Field(default=None, max_length=120)
    audio_asset_id: int | None = Field(default=None, ge=1)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    display_order: int = Field(default=0, ge=0)
    status: Literal["draft", "published", "archived"] = "published"
    metadata: dict[str, Any] | None = None
    lesson_ids: list[int] = Field(default_factory=list)
    example_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_pinyin_or_legacy_exception(self) -> "VocabularyCreate":
        if not (self.pinyin or "").strip() and not (
            self.metadata or {}
        ).get("pinyin_not_available"):
            raise ValueError(
                "pinyin is required unless metadata.pinyin_not_available is true"
            )
        if not any(str(value).strip() for value in self.meaning_translations.values()):
            raise ValueError("meaning_translations must contain a value")
        return self


class VocabularyUpdate(BaseModel):
    simplified: str | None = Field(default=None, min_length=1, max_length=80)
    traditional: str | None = Field(default=None, max_length=80)
    pinyin: str | None = Field(default=None, max_length=160)
    meaning_translations: dict[str, str] | None = None
    part_of_speech: str | None = Field(default=None, min_length=1, max_length=40)
    category: str | None = Field(default=None, max_length=120)
    audio_asset_id: int | None = Field(default=None, ge=1)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    display_order: int | None = Field(default=None, ge=0)
    status: Literal["draft", "published", "archived"] | None = None
    metadata: dict[str, Any] | None = None
    lesson_ids: list[int] | None = None
    example_ids: list[int] | None = None


class GrammarCreate(BaseModel):
    hsk_level_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=180)
    title_translations: dict[str, str] | None = None
    explanation_translations: dict[str, str]
    pattern: str | None = Field(default=None, max_length=500)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    display_order: int = Field(default=0, ge=0)
    status: Literal["draft", "published", "archived"] = "published"
    metadata: dict[str, Any] | None = None
    lesson_ids: list[int] = Field(default_factory=list)
    example_ids: list[int] = Field(default_factory=list)


class GrammarUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    title_translations: dict[str, str] | None = None
    explanation_translations: dict[str, str] | None = None
    pattern: str | None = Field(default=None, max_length=500)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    display_order: int | None = Field(default=None, ge=0)
    status: Literal["draft", "published", "archived"] | None = None
    metadata: dict[str, Any] | None = None
    lesson_ids: list[int] | None = None
    example_ids: list[int] | None = None


class ExampleSentenceCreate(BaseModel):
    chinese: str = Field(min_length=1)
    pinyin: str | None = None
    translations: dict[str, str]
    audio_asset_id: int | None = Field(default=None, ge=1)
    status: Literal["draft", "published", "archived"] = "published"
    metadata: dict[str, Any] | None = None


class ExampleSentenceUpdate(BaseModel):
    chinese: str | None = Field(default=None, min_length=1)
    pinyin: str | None = None
    translations: dict[str, str] | None = None
    audio_asset_id: int | None = Field(default=None, ge=1)
    status: Literal["draft", "published", "archived"] | None = None
    metadata: dict[str, Any] | None = None


class VocabularyStatusIn(BaseModel):
    status: Literal["new", "learning", "learned", "mastered"]


class LearningProgressOut(BaseModel):
    item_id: int
    status: str
    first_viewed_at: datetime | None = None
    last_viewed_at: datetime | None = None
    completed_at: datetime | None = None


class ImportRequest(BaseModel):
    entity_type: Literal[
        "hsk_levels",
        "courses",
        "lessons",
        "vocabulary",
        "grammar",
        "example_sentences",
        "exercises",
    ]
    source_format: Literal["json", "csv"]
    data: Any


class ImportJobOut(BaseModel):
    id: int
    entity_type: str
    source_format: str
    status: str
    total_records: int
    created_records: int
    updated_records: int
    skipped_records: int
    errors: list[dict[str, Any]] | None


class PracticeQuestionOut(BaseModel):
    id: int
    exercise_id: int
    question_type: str
    prompt: str
    prompt_translations: dict[str, str] | None = None
    instruction: str | None = None
    explanation_available: bool = False
    difficulty: int | None = None
    points: int
    order: int
    configuration: dict[str, Any]


class ExerciseSummaryOut(BaseModel):
    id: int
    exercise_set_id: int
    exercise_type: str
    title: str
    instruction: str | None = None
    skill: str | None = None
    vocabulary_id: int | None = None
    grammar_point_id: int | None = None
    difficulty: int | None = None
    order: int
    question_count: int
    status: str


class ExerciseSetSummaryOut(BaseModel):
    id: int
    lesson_id: int
    title: str
    description: str | None = None
    skill: str | None = None
    difficulty: int | None = None
    question_count: int
    exercises: list[ExerciseSummaryOut]


class LessonPracticeOut(BaseModel):
    lesson_id: int
    lesson_title: str
    exercise_sets: list[ExerciseSetSummaryOut]
    total_questions: int


class PracticeSessionCreate(BaseModel):
    lesson_id: int = Field(ge=1)
    exercise_set_id: int | None = Field(default=None, ge=1)
    question_count: int | None = Field(default=None, ge=1, le=50)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    skill: str | None = Field(default=None, min_length=1, max_length=40)
    resume: bool = True


class PracticeSessionOut(BaseModel):
    id: int
    lesson_id: int
    exercise_set_id: int
    status: str
    questions: list[PracticeQuestionOut]
    total_questions: int
    answered_questions: int
    answered_question_ids: list[int] = Field(default_factory=list)
    correct_answers: int
    score: int
    time_spent_seconds: int
    started_at: datetime
    completed_at: datetime | None = None


class PracticeAnswerIn(BaseModel):
    question_id: int = Field(ge=1)
    answer: Any
    idempotency_key: str = Field(min_length=8, max_length=80)
    time_spent_seconds: int = Field(default=0, ge=0, le=86_400)


class PracticeAnswerOut(BaseModel):
    attempt_id: int
    question_id: int
    correct: bool
    score: int
    max_score: int
    submitted_answer: Any
    normalized_answer: Any
    correct_answer: Any
    explanation: str | None = None
    explanation_translations: dict[str, str] | None = None
    answered_questions: int
    correct_answers: int
    session_score: int


class PracticeReviewItemOut(BaseModel):
    question_id: int
    prompt: str
    prompt_translations: dict[str, str] | None = None
    submitted_answer: Any
    correct_answer: Any
    correct: bool
    score: int
    max_score: int
    explanation: str | None = None
    explanation_translations: dict[str, str] | None = None


class PracticeResultsOut(BaseModel):
    session_id: int
    status: str
    total_questions: int
    answered_questions: int
    correct_answers: int
    incorrect_answers: int
    score: int
    accuracy: int
    time_spent_seconds: int
    review: list[PracticeReviewItemOut]


class ExerciseCreate(BaseModel):
    lesson_id: int = Field(ge=1)
    exercise_set_id: int | None = Field(default=None, ge=1)
    exercise_set_title: str | None = Field(default=None, min_length=1, max_length=180)
    external_id: str = Field(min_length=1, max_length=180)
    exercise_type: str
    title: str = Field(min_length=1, max_length=180)
    instruction: str | None = None
    skill: str | None = Field(default=None, max_length=40)
    vocabulary_id: int | None = Field(default=None, ge=1)
    grammar_point_id: int | None = Field(default=None, ge=1)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    order: int = Field(ge=0)
    status: ContentStatus = ContentStatus.PUBLISHED
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_type(self) -> "ExerciseCreate":
        self.exercise_type = canonical_exercise_type(self.exercise_type).value
        return self


class ExerciseUpdate(BaseModel):
    exercise_type: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=180)
    instruction: str | None = None
    skill: str | None = Field(default=None, max_length=40)
    vocabulary_id: int | None = Field(default=None, ge=1)
    grammar_point_id: int | None = Field(default=None, ge=1)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    order: int | None = Field(default=None, ge=0)
    status: ContentStatus | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_type(self) -> "ExerciseUpdate":
        if self.exercise_type is not None:
            self.exercise_type = canonical_exercise_type(self.exercise_type).value
        return self


class QuestionCreate(BaseModel):
    external_id: str | None = Field(default=None, min_length=1, max_length=180)
    question_type: str
    prompt: str = Field(min_length=1)
    instruction: str | None = None
    explanation: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=6)
    points: int = Field(default=1, ge=1, le=100)
    order: int = Field(ge=0)
    configuration: dict[str, Any]
    status: ContentStatus = ContentStatus.PUBLISHED
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_configuration(self) -> "QuestionCreate":
        question_type = canonical_exercise_type(self.question_type)
        self.question_type = question_type.value
        self.configuration = validate_question_configuration(
            question_type, self.configuration
        ).model_dump()
        return self


class QuestionUpdate(BaseModel):
    external_id: str | None = Field(default=None, min_length=1, max_length=180)
    question_type: str | None = None
    prompt: str | None = Field(default=None, min_length=1)
    instruction: str | None = None
    explanation: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=6)
    points: int | None = Field(default=None, ge=1, le=100)
    order: int | None = Field(default=None, ge=0)
    configuration: dict[str, Any] | None = None
    status: ContentStatus | None = None
    metadata: dict[str, Any] | None = None


class QuestionReorderIn(BaseModel):
    question_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_question_ids(self) -> "QuestionReorderIn":
        if len(self.question_ids) != len(set(self.question_ids)):
            raise ValueError("question ids must be unique")
        return self


class AdminQuestionOut(BaseModel):
    id: int
    exercise_id: int | None
    lesson_id: int
    external_id: str | None = None
    question_type: str
    prompt: str
    instruction: str | None = None
    explanation: str | None = None
    difficulty: int | None = None
    points: int
    order: int
    configuration: dict[str, Any]
    status: str
    metadata: dict[str, Any] | None = None


class AdminExerciseOut(ExerciseSummaryOut):
    external_id: str
    metadata: dict[str, Any] | None = None
    questions: list[AdminQuestionOut] = Field(default_factory=list)


class QuestionOut(BaseModel):
    id: int
    question_type: str
    prompt: str
    prompt_translations: dict[str, str] | None = None
    options: list[str] | None
    options_translations: dict[str, list[str]] | None = None
    sort_order: int


class QuizSubmitIn(BaseModel):
    answers: dict[str, str]


class QuizResultItem(BaseModel):
    question_id: int
    prompt: str | None = None
    prompt_translations: dict[str, str] | None = None
    correct: bool
    user_answer: str
    correct_answer: str
    explanation: str | None = None
    explanation_translations: dict[str, str] | None = None


class QuizSubmitOut(BaseModel):
    attempt_id: int
    score: int
    total_questions: int
    correct_count: int
    results: list[QuizResultItem]


class RecentAttemptOut(BaseModel):
    attempt_id: int
    lesson_id: int
    lesson_title: str | None = None
    lesson_title_translations: dict[str, str] | None = None
    score: int
    finished_at: datetime


class SkillBreakdownOut(BaseModel):
    lesson_type: str
    completed: int
    total: int
    average_score: int | None


class ProgressDashboardOut(BaseModel):
    current_hsk_level: int
    target_hsk_level: int
    daily_goal_minutes: int
    minutes_studied_today: int
    study_streak_days: int
    lessons_completed: int
    lessons_in_progress: int
    total_lessons: int
    current_level_total_lessons: int
    current_level_completed_lessons: int
    current_level_progress_percent: int
    exam_readiness_percent: int
    skill_breakdown: list[SkillBreakdownOut]
    recent_attempts: list[RecentAttemptOut]


class SavedWordIn(BaseModel):
    hanzi: str = Field(min_length=1, max_length=40)
    pinyin: str | None = None
    meaning: str | None = None
    hsk_level: int | None = Field(default=None, ge=1, le=6)


class SavedWordOut(SavedWordIn):
    id: int
    saved_at: datetime


class AchievementOut(BaseModel):
    id: int
    code: str
    title: str
    description: str | None
    icon: str | None
    earned: bool
    earned_at: datetime | None


class MockTestOut(BaseModel):
    id: int
    title: str
    title_translations: dict[str, str] | None = None
    hsk_level: int
    duration_minutes: int
    question_count: int


class MockTestQuestionOut(QuestionOut):
    lesson_id: int
    lesson_title: str
    lesson_title_translations: dict[str, str] | None = None


class MistakeOut(BaseModel):
    attempt_id: int
    lesson_id: int
    lesson_title: str | None
    lesson_title_translations: dict[str, str] | None = None
    question_id: int
    prompt: str | None
    prompt_translations: dict[str, str] | None = None
    user_answer: str
    correct_answer: str
    explanation: str | None = None
    explanation_translations: dict[str, str] | None = None
    finished_at: datetime
