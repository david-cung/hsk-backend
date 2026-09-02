from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class UserOut(BaseModel):
    id: int
    email: EmailStr
    display_name: str | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class RegisterIn(AuthIn):
    display_name: str | None = None


class ProfileOut(BaseModel):
    target_hsk_level: int
    current_hsk_level: int
    daily_goal_minutes: int
    study_streak_days: int
    longest_streak_days: int = 0
    last_active_date: date | None = None
    timezone: str = "Asia/Ho_Chi_Minh"
    daily_new_cards_limit: int = 10
    daily_review_cards_limit: int = 50
    onboarding_completed: bool


class ProfileUpdate(BaseModel):
    target_hsk_level: int | None = Field(default=None, ge=1, le=6)
    current_hsk_level: int | None = Field(default=None, ge=1, le=6)
    daily_goal_minutes: int | None = Field(default=None, ge=1, le=240)
    study_streak_days: int | None = Field(default=None, ge=0)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    daily_new_cards_limit: int | None = Field(default=None, ge=0, le=200)
    daily_review_cards_limit: int | None = Field(default=None, ge=0, le=500)
    onboarding_completed: bool | None = None


class HskLevelOut(BaseModel):
    id: int
    level_number: int
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None
    description_translations: dict[str, str] | None = None
    total_characters: int


class LessonListOut(BaseModel):
    id: int
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None
    description_translations: dict[str, str] | None = None
    lesson_type: str
    sort_order: int
    duration_minutes: int
    status: str | None
    score_percent: int | None


class LessonDetailOut(BaseModel):
    id: int
    hsk_level_id: int
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None
    description_translations: dict[str, str] | None = None
    lesson_type: str
    duration_minutes: int
    content: dict[str, Any] | None


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
    hsk_level: int
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
    hsk_level: int
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
    overall_progress_percent: float = 0
    today_questions: int = 0
    today_accuracy: float | None = None
    longest_streak_days: int = 0
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
    recommended_practice: list[RecommendationOut] = Field(default_factory=list)
    weak_areas: list[WeakAreaOut] = Field(default_factory=list)
    skill_overview: list[SkillPerformanceOut] = Field(default_factory=list)


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


class PracticeQuestionOut(BaseModel):
    id: int
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


class ExamListOut(BaseModel):
    id: int
    title: str
    title_translations: dict[str, str] | None = None
    description: str | None = None
    hsk_level: int
    exam_type: str
    duration_minutes: int
    question_count: int
    sections: list[ExamSectionOut] = Field(default_factory=list)
    attempt_count: int = 0
    best_percentage: float | None = None
    status: str


class ExamDetailOut(ExamListOut):
    instructions: str | None = None
    availability: str = "AVAILABLE"
    latest_attempt_id: int | None = None


class ExamQuestionOut(PracticeQuestionOut):
    section: str
    section_index: int
    question_index: int
    lesson_title: str | None = None
    lesson_title_translations: dict[str, str] | None = None


class ExamAttemptOut(BaseModel):
    attempt_id: int
    exam_id: int
    exam_version: int
    status: str
    title: str
    title_translations: dict[str, str] | None = None
    hsk_level: int
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
    hsk_level: int
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
    hsk_level: int
    status: str
    score: float | None = None
    percentage: float | None = None
    passed: bool | None = None
    started_at: datetime
    submitted_at: datetime | None = None


class AdminExamIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    hsk_level: int = Field(ge=1, le=6)
    duration_minutes: int = Field(ge=1, le=240)
    question_count: int = Field(ge=1, le=200)
    sections: list[ExamSectionOut] = Field(default_factory=list)
    scoring_config: dict[str, Any] = Field(default_factory=dict)
    instructions: str | None = None
    status: str = Field(default="DRAFT", pattern="^(DRAFT|PUBLISHED|ARCHIVED)$")


class PracticeLessonOut(BaseModel):
    lesson_id: int
    exercise_set_id: int | None
    title: str
    total_questions: int
    questions: list[PracticeQuestionOut]


class PracticeSessionCreateIn(BaseModel):
    lesson_id: int
    exercise_set_id: int | None = None
    question_count: int | None = Field(default=None, ge=1, le=100)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    skill: str | None = None
    resume: bool = True


class PracticeSessionOut(BaseModel):
    id: int
    lesson_id: int | None
    exercise_set_id: int | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    total_questions: int
    answered_questions: int
    correct_answers: int
    score: float
    time_spent_seconds: int
    questions: list[PracticeQuestionOut]


class PracticeAnswerIn(BaseModel):
    question_id: int
    answer: Any
    time_spent_seconds: int = Field(default=0, ge=0, le=86400)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)
    playback: dict[str, Any] | None = None


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


class PracticeAnswerOut(BaseModel):
    attempt_id: int
    question_id: int
    correct: bool
    score: float
    max_score: float
    correct_answer: Any
    explanation: str | None = None
    normalized_answer: dict[str, Any]
    transcript: str | None = None
    pinyin: str | None = None
    translation: str | None = None
    processing_status: str | None = None
    speech_analysis: SpeechAnalysisOut | None = None
    writing_evaluation: dict[str, Any] | None = None
    session: PracticeSessionOut


class PracticeReviewItemOut(BaseModel):
    question: PracticeQuestionOut
    user_answer: Any
    correct_answer: Any
    correct: bool
    score: float
    explanation: str | None = None
    transcript: str | None = None
    pinyin: str | None = None
    translation: str | None = None
    processing_status: str | None = None
    speech_analysis: SpeechAnalysisOut | None = None
    writing_evaluation: dict[str, Any] | None = None
    attempted_at: datetime | None = None


class PracticeResultsOut(BaseModel):
    session_id: int
    total_questions: int
    answered_questions: int
    correct_answers: int
    incorrect_answers: int
    score: float
    accuracy: float
    time_spent_seconds: int
    review: list[PracticeReviewItemOut]


class AdminQuestionIn(BaseModel):
    prompt: str = Field(min_length=1)
    question_type: str
    instruction: str | None = None
    explanation: str | None = None
    difficulty: int = Field(default=1, ge=1, le=5)
    points: int = Field(default=1, ge=1, le=100)
    order: int = Field(default=0, ge=0)
    config: dict[str, Any]
    reference_type: str | None = None
    reference_id: str | None = None


class AdminExerciseIn(BaseModel):
    lesson_id: int
    exercise_set_id: int | None = None
    slug: str
    title: str
    exercise_type: str
    skill: str | None = None
    order: int = 0
    config: dict[str, Any] = Field(default_factory=dict)
    questions: list[AdminQuestionIn] = Field(default_factory=list)


class AdminExerciseOut(BaseModel):
    id: int
    exercise_set_id: int
    lesson_id: int | None
    slug: str
    title: str
    exercise_type: str
    skill: str | None
    order: int
    is_archived: bool
    questions: list[PracticeQuestionOut]


class ExerciseImportIn(BaseModel):
    lesson_id: int | None = None
    lesson: str | None = None
    exercise: AdminExerciseIn | dict[str, Any]
    upsert: bool = True


class ExerciseImportOut(BaseModel):
    imported: bool
    exercise_id: int
    question_count: int
    warnings: list[str] = Field(default_factory=list)


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
