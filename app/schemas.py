from datetime import datetime
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
    learning_goal: str | None
    target_hsk_level: int
    current_hsk_level: int
    daily_goal_minutes: int
    study_streak_days: int
    onboarding_completed: bool


class ProfileUpdate(BaseModel):
    learning_goal: str | None = Field(default=None, max_length=80)
    target_hsk_level: int | None = Field(default=None, ge=1, le=6)
    current_hsk_level: int | None = Field(default=None, ge=1, le=6)
    daily_goal_minutes: int | None = Field(default=None, ge=1, le=240)
    study_streak_days: int | None = Field(default=None, ge=0)
    onboarding_completed: bool | None = None


class HskLevelOut(BaseModel):
    id: int
    level_number: int
    title: str
    description: str | None
    total_characters: int


class LessonListOut(BaseModel):
    id: int
    title: str
    description: str | None
    lesson_type: str
    sort_order: int
    duration_minutes: int
    status: str | None
    score_percent: int | None


class LessonDetailOut(BaseModel):
    id: int
    hsk_level_id: int
    title: str
    description: str | None
    lesson_type: str
    duration_minutes: int
    content: dict[str, Any] | None


class QuestionOut(BaseModel):
    id: int
    question_type: str
    prompt: str
    options: list[str] | None
    sort_order: int


class QuizSubmitIn(BaseModel):
    answers: dict[str, str]


class QuizResultItem(BaseModel):
    question_id: int
    prompt: str | None = None
    correct: bool
    user_answer: str
    correct_answer: str
    explanation: str | None = None


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
    score: int
    finished_at: datetime


class SkillProgressOut(BaseModel):
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
    skill_breakdown: list[SkillProgressOut]
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
    hsk_level: int
    duration_minutes: int
    question_count: int


class MockTestQuestionOut(QuestionOut):
    lesson_id: int
    lesson_title: str


class MistakeOut(BaseModel):
    attempt_id: int
    lesson_id: int
    lesson_title: str | None
    question_id: int
    prompt: str | None
    user_answer: str
    correct_answer: str
    explanation: str | None = None
    finished_at: datetime
