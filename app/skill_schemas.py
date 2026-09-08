"""Pydantic schemas for Phase 6-11 skill systems.

Kept separate from ``app.schemas`` so the ported listening/speaking/progress/
SRS/exam routers can reuse the codex response contracts (which use a ``config``
field name) without clashing with main's normalized content schemas
(which use ``configuration``).
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Progress analytics (Phase 8)
# ---------------------------------------------------------------------------
class ProgressMetricOut(BaseModel):
    total: int = 0
    completed: int = 0
    percent: float | None = None


class AccuracyMetricOut(BaseModel):
    attempts: int = 0
    correct: int = 0
    accuracy: float | None = None
    average_score: float | None = None


class SkillPerformanceOut(BaseModel):
    skill: str
    attempts: int = 0
    correct: int = 0
    accuracy: float | None = None
    average_score: float | None = None
    study_minutes: int = 0
    practiced: bool = False
    trend: str | None = None
    trend_delta: float | None = None


class WeakAreaOut(BaseModel):
    type: str
    label: str
    skill: str | None = None
    target_id: int | str | None = None
    metric: float | None = None
    attempts: int = 0
    reason: str


class RecommendationOut(BaseModel):
    type: str
    target_id: int | str | None = None
    target_label: str | None = None
    reason: str
    activity_type: str


class ContinueLearningOut(BaseModel):
    lesson_id: int | None = None
    lesson_title: str | None = None
    lesson_title_translations: dict[str, str] | None = None
    hsk_level: int | None = None
    lesson_type: str | None = None


class DailyActivityOut(BaseModel):
    date: str
    study_minutes: int = 0
    practice_attempts: int = 0
    questions: int = 0
    correct: int = 0
    accuracy: float | None = None
    lessons_studied: int = 0
    vocabulary_practiced: int = 0
    grammar_practiced: int = 0
    listening_practiced: int = 0
    speaking_practiced: int = 0
    writing_practiced: int = 0


class ProgressSummaryOut(BaseModel):
    current_hsk_level: int
    target_hsk_level: int
    overall_progress_percent: float
    today_study_minutes: int
    today_questions: int
    today_accuracy: float | None = None
    current_streak_days: int
    longest_streak_days: int
    last_active_date: str | None = None
    cards_due: int = 0
    cards_overdue: int = 0
    cards_reviewed_today: int = 0
    review_retention: float | None = None
    review_streak_days: int = 0
    exams_attempted: int = 0
    exams_completed: int = 0
    exam_best_score: float | None = None
    exam_latest_score: float | None = None
    exam_average_score: float | None = None
    exam_section_performance: list[dict[str, Any]] = Field(default_factory=list)
    writing_exercises_attempted: int = 0
    writing_exercises_completed: int = 0
    writing_accuracy: float | None = None
    writing_average_score: float | None = None
    guided_writing_count: int = 0
    translation_accuracy: float | None = None
    word_order_accuracy: float | None = None
    weak_skills: list[WeakAreaOut] = Field(default_factory=list)
    recommended_practice: list[RecommendationOut] = Field(default_factory=list)
    continue_learning: ContinueLearningOut | None = None
    skill_overview: list[SkillPerformanceOut] = Field(default_factory=list)
    ai_conversations: int = 0
    ai_messages: int = 0
    ai_corrections: int = 0


class HskProgressOut(BaseModel):
    level: int
    level_id: int
    title: str
    title_translations: dict[str, str] | None = None
    vocabulary: ProgressMetricOut
    grammar: ProgressMetricOut
    lessons: ProgressMetricOut
    practice: AccuracyMetricOut
    listening: AccuracyMetricOut | None = None
    speaking: AccuracyMetricOut | None = None
    skill_performance: list[SkillPerformanceOut] = Field(default_factory=list)
    study_minutes: int = 0


class CourseProgressOut(BaseModel):
    course_id: int
    title: str
    title_translations: dict[str, str] | None = None
    hsk_level: int | None
    total_lessons: int
    completed_lessons: int
    progress_percent: float
    practice_attempts: int
    accuracy: float | None = None
    last_studied: datetime | None = None
    total_study_minutes: int = 0
    lessons: list[dict[str, Any]] = Field(default_factory=list)


class LessonProgressAnalyticsOut(BaseModel):
    lesson_id: int
    title: str
    title_translations: dict[str, str] | None = None
    hsk_level: int | None
    lesson_type: str
    started: bool
    completed: bool
    completion_percent: float
    vocabulary: ProgressMetricOut
    grammar: ProgressMetricOut
    practice: AccuracyMetricOut
    listening: AccuracyMetricOut | None = None
    speaking: AccuracyMetricOut | None = None
    study_minutes: int = 0
    last_practiced: datetime | None = None
    completion_rule: str


# ---------------------------------------------------------------------------
# Spaced repetition (Phase 9)
# ---------------------------------------------------------------------------
class ReviewRatingPreviewOut(BaseModel):
    rating: str
    due_at: datetime
    interval_days: float
    interval_label: str


class ReviewCardOut(BaseModel):
    id: int
    card_type: str
    state: str
    due_at: datetime
    last_reviewed_at: datetime | None = None
    overdue_seconds: int = 0
    content: dict[str, Any]
    rating_previews: list[ReviewRatingPreviewOut] = Field(default_factory=list)


class ReviewDueOut(BaseModel):
    items: list[ReviewCardOut] = Field(default_factory=list)
    due_count: int = 0
    overdue_count: int = 0
    new_count: int = 0
    review_limit: int
    new_limit: int
    next_review_at: datetime | None = None


class ReviewSubmitIn(BaseModel):
    rating: str = Field(pattern="^(AGAIN|HARD|GOOD|EASY)$")
    idempotency_key: str = Field(min_length=1, max_length=160)


class ReviewSubmitOut(BaseModel):
    card: ReviewCardOut
    reviewed_today: int
    next_review_at: datetime | None = None


class ReviewSummaryOut(BaseModel):
    due_count: int = 0
    overdue_count: int = 0
    new_count: int = 0
    reviewed_today: int = 0
    retention: float | None = None
    review_streak_days: int = 0
    next_review_at: datetime | None = None


class ReviewHistoryOut(BaseModel):
    id: int
    card_id: int
    card_type: str
    rating: str
    reviewed_at: datetime
    previous_state: str
    new_state: str
    previous_due_at: datetime | None = None
    new_due_at: datetime
    source: str


class ReviewEnrollIn(BaseModel):
    card_type: str = Field(pattern="^(VOCABULARY|GRAMMAR)$")
    vocabulary_id: int | None = None
    grammar_id: str | None = None
    content_key: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)


class ReviewCardStatusOut(BaseModel):
    id: int
    card_type: str
    vocabulary_id: int | None = None
    grammar_id: str | None = None
    content_key: str
    state: str
    due_at: datetime
    last_reviewed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Listening / audio (Phase 6)
# ---------------------------------------------------------------------------
class AudioAssetIn(BaseModel):
    storage_key: str = Field(min_length=1, max_length=500)
    provider: str = "tts"
    mime_type: str = "audio/mpeg"
    duration_seconds: float | None = Field(default=None, ge=0)
    language: str = "zh-CN"
    transcript: str | None = None
    pinyin: str | None = None
    translation: str | None = None
    status: str = "READY"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioAssetOut(AudioAssetIn):
    id: int
    created_at: datetime
    updated_at: datetime


class AudioUrlOut(BaseModel):
    audio_asset_id: int
    url: str
    provider: str
    mime_type: str
    expires_at: datetime | str


# ---------------------------------------------------------------------------
# Speaking / pronunciation (Phase 7)
# ---------------------------------------------------------------------------
class SpeechUploadRequestIn(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    mime_type: str = "audio/mp4"
    size_bytes: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    language: str = "zh-CN"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeechUploadOut(BaseModel):
    recording_id: int
    storage_key: str
    upload_url: str
    headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime | str
    max_size_bytes: int
    status: str


class SpeechUploadCompleteIn(BaseModel):
    size_bytes: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeechRecordingOut(BaseModel):
    id: int
    storage_key: str
    mime_type: str
    size_bytes: int | None = None
    duration_seconds: float | None = None
    language: str
    status: str
    upload_expires_at: datetime
    uploaded_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SpeechWordFeedbackOut(BaseModel):
    expected: str
    recognized: str | None = None
    pronunciation_score: float | None = None
    accuracy_score: float | None = None
    expected_pinyin: str | None = None
    recognized_pinyin: str | None = None
    tone_score: float | None = None


class SpeechAnalysisOut(BaseModel):
    recognized_text: str | None = None
    confidence: float | None = None
    pronunciation_score: float | None = None
    accuracy_score: float | None = None
    fluency_score: float | None = None
    completeness_score: float | None = None
    words: list[SpeechWordFeedbackOut] = Field(default_factory=list)
    feedback_label: str | None = None
    provider: str | None = None
    provider_model_version: str | None = None
    tone_feedback: dict[str, Any] | None = None


class SpeakingAttemptOut(BaseModel):
    id: int
    answer_attempt_id: int
    recording_id: int
    practice_session_id: int
    question_id: int
    provider: str
    provider_model_version: str | None = None
    recognized_text: str | None = None
    pronunciation_score: float | None = None
    accuracy_score: float | None = None
    fluency_score: float | None = None
    completeness_score: float | None = None
    processing_status: str
    error_code: str | None = None
    error_message: str | None = None
    speech_analysis: SpeechAnalysisOut | None = None


# ---------------------------------------------------------------------------
# Mock exam (Phase 10)
# ---------------------------------------------------------------------------
class SkillQuestionOut(BaseModel):
    id: int
    question_version_id: int | None = None
    exercise_id: int | None = None
    question_type: str
    prompt: str
    instruction: str | None = None
    explanation: str | None = None
    difficulty: int
    points: int
    order: int
    config: dict[str, Any]


class ExamSectionOut(BaseModel):
    type: str
    title: str
    duration_minutes: int
    question_count: int
    allow_previous: bool = True
    code: str | None = None
    skill: str | None = None
    duration_seconds: int | None = None
    instructions: str | None = None
    parts: list["ExamPartOut"] = Field(default_factory=list)


class ExamPartOut(BaseModel):
    id: int | None = None
    code: str | None = None
    title: str
    instructions: str | None = None
    sort_order: int = 0
    questions: list["ExamQuestionOut"] = Field(default_factory=list)


class ExamListOut(BaseModel):
    id: int
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None = None
    hsk_level: int | None
    exam_revision_id: int | None = None
    exam_level_id: int | None = None
    scoring_policy_id: int | None = None
    blueprint_schema_version: int = 1
    exam_type: str
    duration_minutes: int
    question_count: int
    sections: list[ExamSectionOut] = Field(min_length=1)
    attempt_count: int = 0
    best_percentage: float | None = None
    status: str


class ExamDetailOut(ExamListOut):
    instructions: str | None = None
    availability: str = "AVAILABLE"
    latest_attempt_id: int | None = None


class ExamQuestionOut(SkillQuestionOut):
    section: str
    section_index: int
    question_index: int
    part_id: int | None = None
    part_code: str | None = None
    part_title: str | None = None
    lesson_title: str | None = None
    lesson_title_translations: dict[str, str] | None = None


class ExamAttemptOut(BaseModel):
    attempt_id: int
    exam_id: int
    exam_version: int
    exam_version_id: int | None = None
    status: str
    title: str
    title_translations: dict[str, str] | None = None
    hsk_level: int | None
    exam_revision_id: int | None = None
    exam_level_id: int | None = None
    scoring_policy_id: int | None = None
    blueprint_schema_version: int = 1
    duration_minutes: int
    sections: list[ExamSectionOut] = Field(default_factory=list)
    questions: list[ExamQuestionOut] = Field(default_factory=list)
    answers: dict[str, Any] = Field(default_factory=dict)
    server_time: datetime
    started_at: datetime
    expires_at: datetime
    submitted_at: datetime | None = None
    remaining_seconds: int = 0
    current_section: str | None = None
    allow_previous_section: bool = True


class ExamAnswerIn(BaseModel):
    answer: Any
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)


class ExamQuestionResultOut(BaseModel):
    question_id: int
    question_version_id: int | None = None
    section: str
    prompt: str | None = None
    user_answer: Any = None
    correct_answer: Any = None
    correct: bool | None = None
    points: float = 0
    max_points: float = 1
    explanation: str | None = None
    evaluation_source: str | None = None
    writing_evaluation: dict[str, Any] | None = None


class ExamSectionResultOut(BaseModel):
    section: str
    total_questions: int
    answered: int
    correct: int
    incorrect: int
    skipped: int
    raw_score: float
    percentage: float
    time_used_seconds: int = 0


class ExamResultOut(BaseModel):
    attempt_id: int
    exam_id: int
    title: str
    hsk_level: int | None
    exam_revision_id: int | None = None
    exam_level_id: int | None = None
    scoring_policy_id: int | None = None
    status: str
    score_label: str = "Estimated Practice Score"
    raw_score: float
    total_points: float
    percentage: float
    passed: bool | None = None
    started_at: datetime
    submitted_at: datetime | None = None
    expires_at: datetime
    time_used_seconds: int
    sections: list[ExamSectionResultOut] = Field(default_factory=list)
    questions: list[ExamQuestionResultOut] = Field(default_factory=list)
    weak_areas: list[WeakAreaOut] = Field(default_factory=list)
    recommended_practice: list[RecommendationOut] = Field(default_factory=list)


class ExamAttemptHistoryOut(BaseModel):
    attempt_id: int
    exam_id: int
    title: str
    hsk_level: int | None
    exam_revision_id: int | None = None
    exam_level_id: int | None = None
    scoring_policy_id: int | None = None
    status: str
    score: float | None = None
    percentage: float | None = None
    passed: bool | None = None
    started_at: datetime
    submitted_at: datetime | None = None


class AdminExamIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    hsk_level: int | None = Field(default=None, ge=1, le=6)
    exam_revision_id: int | None = Field(default=None, ge=1)
    exam_level_id: int | None = Field(default=None, ge=1)
    scoring_policy_id: int | None = Field(default=None, ge=1)
    duration_minutes: int = Field(ge=1, le=240)
    question_count: int = Field(ge=1, le=200)
    sections: list[ExamSectionOut] = Field(default_factory=list)
    scoring_config: dict[str, Any] = Field(default_factory=dict)
    instructions: str | None = None
    status: str = Field(default="DRAFT", pattern="^(DRAFT|PUBLISHED|ARCHIVED)$")

    @model_validator(mode="after")
    def validate_scope(self) -> "AdminExamIn":
        if self.hsk_level is None and not self.exam_level_id:
            raise ValueError("An exam level or legacy HSK level is required")
        if (self.exam_revision_id is None) != (self.exam_level_id is None):
            raise ValueError("Both exam revision and exam level are required")
        return self


# ---------------------------------------------------------------------------
# Versioned exam builder (Phase 3)
# ---------------------------------------------------------------------------
class AdminExamQuestionIn(BaseModel):
    question_version_id: int = Field(ge=1)
    sort_order: int = Field(default=0, ge=0)
    points: int = Field(default=1, ge=1)
    required: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)


class AdminExamPartIn(BaseModel):
    code: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=180)
    instructions: str | None = None
    sort_order: int = Field(default=0, ge=0)
    configuration: dict[str, Any] = Field(default_factory=dict)
    questions: list[AdminExamQuestionIn] = Field(default_factory=list)


class AdminExamSectionIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=180)
    skill: str | None = Field(default=None, max_length=40)
    sort_order: int = Field(default=0, ge=0)
    duration_seconds: int = Field(default=0, ge=0)
    instructions: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    parts: list[AdminExamPartIn] = Field(default_factory=list)


class AdminExamDocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    exam_revision_id: int = Field(ge=1)
    exam_level_id: int = Field(ge=1)
    scoring_policy_id: int = Field(ge=1)
    duration_seconds: int = Field(ge=1, le=86400)
    instructions: str | None = None
    blueprint_schema_version: int = Field(default=1, ge=1)
    configuration: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    sections: list[AdminExamSectionIn] = Field(default_factory=list)


class AdminExamQuestionOut(BaseModel):
    id: int
    question_version_id: int
    sort_order: int
    points: int
    required: bool
    question_id: int
    question_type: str
    skill: str | None = None
    prompt: str
    instruction: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)


class AdminExamPartOut(BaseModel):
    id: int
    code: str | None = None
    title: str
    instructions: str | None = None
    sort_order: int
    configuration: dict[str, Any] = Field(default_factory=dict)
    questions: list[AdminExamQuestionOut] = Field(default_factory=list)


class AdminExamSectionOut(BaseModel):
    id: int
    code: str
    title: str
    skill: str | None = None
    sort_order: int
    duration_seconds: int
    instructions: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    parts: list[AdminExamPartOut] = Field(default_factory=list)


class ExamValidationIssue(BaseModel):
    code: str
    field: str
    message: str


class ExamValidationOut(BaseModel):
    valid: bool
    errors: list[ExamValidationIssue] = Field(default_factory=list)


class AdminExamVersionOut(BaseModel):
    id: int
    exam_id: int
    version_number: int
    status: str
    title: str
    description: str | None = None
    exam_revision_id: int | None = None
    exam_level_id: int | None = None
    scoring_policy_id: int | None = None
    duration_seconds: int
    instructions: str | None = None
    blueprint_schema_version: int
    configuration: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    sections: list[AdminExamSectionOut] = Field(default_factory=list)


class AdminExamListItem(BaseModel):
    id: int
    title: str
    description: str | None = None
    exam_revision_id: int | None = None
    exam_level_id: int | None = None
    scoring_policy_id: int | None = None
    version_number: int
    version_id: int
    status: str
    duration_seconds: int
    question_count: int


class AdminExamListOut(BaseModel):
    items: list[AdminExamListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    pages: int


# ---------------------------------------------------------------------------
# AI tutor (Phase 12)
# ---------------------------------------------------------------------------
class RolePlayScenarioOut(BaseModel):
    id: str
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None = None
    description_translations: dict[str, str] | None = None


class ConversationCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    lesson_id: int | None = None
    course_id: int | None = None
    hsk_level: int | None = Field(default=None, ge=1, le=6)
    scenario_id: str | None = None
    explanation_language: str = "zh"
    title: str | None = Field(default=None, max_length=180)


class ConversationMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
    action: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=160)


class ConversationMessageOut(BaseModel):
    id: int
    role: str
    content: str
    chinese_text: str | None = None
    pinyin: str | None = None
    translation: str | None = None
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    vocabulary_notes: list[dict[str, Any]] = Field(default_factory=list)
    grammar_notes: list[dict[str, Any]] = Field(default_factory=list)
    prompt_version: str | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    mode: str
    hsk_level: int
    course_id: int | None = None
    lesson_id: int | None = None
    title: str
    scenario_id: str | None = None
    explanation_language: str
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageOut] = Field(default_factory=list)


class ConversationListOut(BaseModel):
    items: list[ConversationOut]
    total: int
    limit: int
    offset: int


class ConversationMessageResultOut(BaseModel):
    conversation: ConversationOut
    user_message: ConversationMessageOut
    assistant_message: ConversationMessageOut


class SentenceCheckIn(BaseModel):
    sentence: str = Field(min_length=1, max_length=2000)
    lesson_id: int | None = None


class SentenceCheckOut(BaseModel):
    corrected_sentence: str
    is_correct: bool
    explanation: str
    alternatives: list[str] = Field(default_factory=list)
    vocabulary_notes: list[dict[str, Any]] = Field(default_factory=list)
    grammar_notes: list[dict[str, Any]] = Field(default_factory=list)


class GrammarExplainIn(BaseModel):
    grammar_point: str = Field(min_length=1, max_length=200)
    sentence: str | None = Field(default=None, max_length=2000)
    lesson_id: int | None = None


class GrammarExplainOut(BaseModel):
    is_correct: bool | None = None
    corrected_sentence: str | None = None
    explanation: str
    examples: list[str] = Field(default_factory=list)
    difficulty: str | None = None


class WritingFeedbackIn(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)
    prompt: str | None = None
    lesson_id: int | None = None


class WritingFeedbackOut(BaseModel):
    label: str = "AI Feedback"
    score: int | None = None
    corrected_answer: str | None = None
    strengths: list[str] = Field(default_factory=list)
    mistakes: list[str] = Field(default_factory=list)
    grammar_feedback: list[str] = Field(default_factory=list)
    vocabulary_feedback: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Gamification & notifications (Phase 13)
# ---------------------------------------------------------------------------
class GamificationProfileOut(BaseModel):
    xp: int
    level: int
    xp_into_level: int
    xp_to_next_level: int
    level_xp_required: int
    progress_percent: float
    streak_days: int
    longest_streak_days: int
    timezone: str
    daily_goal_type: str
    daily_goal_target: int
    daily_goal_current: int
    daily_goal_completed: bool
    today_xp: int
    today_minutes: int
    today_exercises: int
    today_lessons: int
    today_reviews: int
    today: str


class XPHistoryItemOut(BaseModel):
    id: int
    event_type: str
    source_id: str
    xp: int
    created_at: datetime


class XPHistoryOut(BaseModel):
    items: list[XPHistoryItemOut]
    total: int
    limit: int
    offset: int


class DailyGoalOut(BaseModel):
    date: str
    timezone: str
    xp: int
    minutes: int
    exercises: int
    lessons: int
    reviews: int
    goal_type: str
    goal_target: int
    goal_current: int
    goal_completed: bool
    streak_days: int


class DailyGoalUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_type: str | None = None
    target: int | None = Field(default=None, ge=1, le=500)


class GamificationAchievementOut(BaseModel):
    id: int
    code: str
    title: str
    description: str | None
    icon: str | None
    earned: bool
    earned_at: datetime | None
    progress: dict[str, int] | None = None


class DeviceTokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=8, max_length=255)
    platform: str = "local"


class DeviceTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    token: str
    platform: str
    active: bool


class NotificationPreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    daily_reminder: bool
    streak_reminder: bool
    srs_reminder: bool
    exam_reminder: bool
    achievement_notification: bool


class NotificationPreferencesUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_reminder: bool | None = None
    streak_reminder: bool | None = None
    srs_reminder: bool | None = None
    exam_reminder: bool | None = None
    achievement_notification: bool | None = None


# ---------------------------------------------------------------------------
# Admin CMS (Phase 14)
# ---------------------------------------------------------------------------
class AdminDashboardMetricOut(BaseModel):
    key: str
    label: str
    value: int | float


class AdminDashboardOut(BaseModel):
    metrics: list[AdminDashboardMetricOut]
    content_status: dict[str, int]
    import_errors: int
    audio_coverage: dict[str, int | float]


class AdminSearchItemOut(BaseModel):
    id: str
    entity_type: str
    title: str
    subtitle: str | None = None
    hsk_level: int | None = None
    exam_revision_id: int | None = None
    exam_level_id: int | None = None
    status: str | None = None
    updated_at: datetime | None = None


class AdminSearchOut(BaseModel):
    items: list[AdminSearchItemOut]
    total: int
    page: int
    page_size: int
    pages: int


class AdminValidationIssueOut(BaseModel):
    severity: str = "error"
    field: str
    message: str


class AdminValidationOut(BaseModel):
    entity_type: str
    entity_id: str | None = None
    valid: bool
    issues: list[AdminValidationIssueOut]


class AdminStatusChangeIn(BaseModel):
    expected_updated_at: datetime | None = None


class AdminAuditOut(BaseModel):
    id: int
    admin_user_id: int | None
    action: str
    entity_type: str
    entity_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class AdminAuditListOut(BaseModel):
    items: list[AdminAuditOut]
    total: int
    limit: int
    offset: int


class AdminImportPreviewIn(BaseModel):
    entity_type: str
    source_format: str
    data: Any


class AdminImportPreviewOut(BaseModel):
    entity_type: str
    source_format: str
    total_records: int
    records_to_create: int
    records_to_update: int
    duplicates: int
    invalid_records: int
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]


class ExamImportSummaryOut(BaseModel):
    sections: int = 0
    questions: int = 0
    answers_matched: int = 0
    warnings: int = 0
    review_required: bool = False


class ExamImportJobOut(BaseModel):
    id: int
    status: str
    exam_revision_id: int
    exam_level_id: int
    exam_name: str
    created_exam_id: int | None = None
    created_exam_version_id: int | None = None
    progress: int = 0
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    summary: ExamImportSummaryOut = Field(default_factory=ExamImportSummaryOut)
    parsed_document: dict[str, Any] | None = None


# Exam questions reuse the skill question contract (codex ``config`` naming).
PracticeQuestionOut = SkillQuestionOut

# Speech analysis output shared with practice router writing/speaking payloads.
_ = date  # re-exported convenience for callers importing date-based schemas
