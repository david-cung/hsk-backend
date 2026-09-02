from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://hsk:hsk@postgres:5432/hsk"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 45
    refresh_token_expire_days: int = 30
    password_reset_expire_minutes: int = 30
    password_reset_url: str = "hsk://reset-password"
    google_client_id: str | None = None
    cors_origins: list[str] = ["*"]

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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
