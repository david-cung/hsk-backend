import pytest

from app.config import Settings
from app.exam_import_service import validate_audio_bytes
from app.request_safety import FixedWindowLimiter, rate_limit_for


def test_production_settings_reject_unsafe_defaults() -> None:
    with pytest.raises(ValueError):
        Settings(environment="production", cors_origins=["https://app.example.com"])


def test_production_settings_accept_explicit_services() -> None:
    configured = Settings(
        environment="production",
        public_api_url="https://api.example.com",
        jwt_secret="a" * 64,
        cors_origins=["https://app.example.com"],
        sentry_dsn="https://public@example.ingest.sentry.io/1",
        media_storage_provider="s3",
        s3_bucket="hsk-production",
    )
    assert configured.public_api_url == "https://api.example.com"


def test_import_audio_signature_is_validated() -> None:
    validate_audio_bytes(b"ID3 test audio", ".mp3")
    validate_audio_bytes(b"\x00\x00\x00\x18ftypM4A ", ".m4a")
    with pytest.raises(Exception, match="supported audio format"):
        validate_audio_bytes(b"not audio", ".mp3")


def test_release_rate_limit_rules_are_scoped() -> None:
    limiter = FixedWindowLimiter()
    assert limiter.allow("test", "auth", 1)[0]
    assert not limiter.allow("test", "auth", 1)[0]
    assert rate_limit_for("/api/v1/auth/login", "POST") == ("auth", 60)
    assert rate_limit_for("/api/v1/content", "GET") is None
