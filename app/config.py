from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "postgresql+psycopg://hsk:hsk@postgres:5432/hsk"
    public_api_url: str = "http://localhost:8000"
    release: str = "dev"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 45
    refresh_token_expire_days: int = 30
    password_reset_expire_minutes: int = 30
    password_reset_url: str = "hsk://reset-password"
    google_client_id: str | None = None
    cors_origins: list[str] = ["*"]
    sentry_dsn: str | None = None

    # Phase 6 — Listening / audio delivery
    audio_url_expire_minutes: int = 15
    # Phase 7 — Speaking / pronunciation
    speech_provider: str = "mock"
    speech_upload_url_expire_minutes: int = 10
    speech_recording_retention_days: int = 30
    speech_max_upload_bytes: int = 10 * 1024 * 1024
    speech_minimum_acceptable_score: float = 70
    speech_feedback_excellent_threshold: float = 90
    speech_feedback_good_threshold: float = 80
    speech_feedback_needs_improvement_threshold: float = 70
    # Phase 8 — Progress analytics
    progress_min_daily_study_minutes: int = 5
    progress_weak_accuracy_threshold: float = 70
    progress_weak_speaking_threshold: float = 70
    progress_min_attempts_for_weak_area: int = 5
    progress_trend_min_attempts: int = 3
    # Phase 9 — SRS / FSRS
    review_new_cards_per_day: int = 10
    review_cards_per_day: int = 50
    review_default_timezone: str = "Asia/Ho_Chi_Minh"
    review_desired_retention: float = 0.9
    review_learning_again_minutes: int = 10
    review_speaking_again_threshold: float = 60
    review_speaking_hard_threshold: float = 75
    review_speaking_good_threshold: float = 90
    # Phase 12 — AI tutor
    ai_provider: str = "mock"
    ai_model: str = "openai/gpt-4o-mini"
    ai_api_key: str | None = None
    ai_base_url: str = "https://openrouter.ai/api/v1"
    ai_max_tokens: int = 800
    ai_temperature: float = 0.7
    ai_timeout: float = 30
    ai_max_history_messages: int = 12
    ai_max_input_characters: int = 2000
    ai_rate_limit_per_minute: int = 20
    ai_retry_attempts: int = 2
    ai_tutor_prompt_version: str = "v1"
    ai_writing_feedback_enabled: bool = False
    # Phase 13 — gamification
    xp_lesson_completed: int = 20
    xp_practice_completed: int = 10
    xp_exam_completed: int = 50
    xp_srs_review_completed: int = 2
    xp_writing_completed: int = 0
    xp_listening_completed: int = 0
    xp_speaking_completed: int = 0
    xp_ai_conversation_completed: int = 5
    xp_question_correct: int = 0
    xp_daily_goal_bonus: int = 15
    xp_level_base: int = 100
    xp_level_step: int = 50
    notification_provider: str = "mock"
    # Phase 4 - PDF/audio exam import
    exam_import_storage_dir: str = "/tmp/hsk-exam-imports"
    exam_import_max_bytes: int = 25 * 1024 * 1024
    exam_import_ai_enabled: bool = False
    media_storage_provider: str = "local"
    media_storage_dir: str = "/tmp/hsk-media"
    media_public_base_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment.lower() in {"production", "prod"}:
            if self.jwt_secret in {"change-me-in-production", "dev-hsk-mobile-secret"}:
                raise ValueError("JWT_SECRET must be set to a non-development value in production")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must list explicit origins in production")
            if not self.public_api_url.startswith("https://") or any(
                host in self.public_api_url.lower() for host in ("localhost", "127.0.0.1")
            ):
                raise ValueError("PUBLIC_API_URL must be a public HTTPS URL in production")
            if self.media_storage_provider.lower() != "s3":
                raise ValueError("MEDIA_STORAGE_PROVIDER must be s3 in production")
            if not self.s3_bucket:
                raise ValueError("S3_BUCKET must be set in production")
            if not self.sentry_dsn:
                raise ValueError("SENTRY_DSN must be set in production")
        return self


settings = Settings()
