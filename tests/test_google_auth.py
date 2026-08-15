import pytest
from conftest import register_user
from sqlalchemy import func, select

import app.google_auth as google_auth_module
from app.database import SessionLocal
from app.google_auth import GoogleIdentity, GoogleTokenError, GoogleTokenVerifier
from app.models import OAuthAccount, User


class StaticGoogleVerifier:
    def __init__(self, identity: GoogleIdentity | None = None, error: Exception | None = None):
        self.identity = identity
        self.error = error

    def verify(self, _: str) -> GoogleIdentity:
        if self.error:
            raise self.error
        assert self.identity is not None
        return self.identity


def _identity(subject: str = "google-sub-1", email: str = "google@example.com"):
    return GoogleIdentity(subject=subject, email=email, display_name="Google Learner")


def test_valid_google_token_creates_new_user_and_oauth_account(
    client, override_google_verifier
):
    override_google_verifier(StaticGoogleVerifier(identity=_identity()))
    response = client.post("/api/v1/auth/google", json={"id_token": "valid-token-value-123"})

    assert response.status_code == 200
    assert response.json()["refresh_token"]
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "google@example.com"))
        assert user is not None
        assert user.password_hash is None
        assert db.scalar(select(func.count()).select_from(OAuthAccount)) == 1


def test_existing_oauth_account_logs_into_same_user_without_duplicate(
    client, override_google_verifier
):
    override_google_verifier(StaticGoogleVerifier(identity=_identity()))
    first = client.post("/api/v1/auth/google", json={"id_token": "valid-token-value-123"})
    second = client.post("/api/v1/auth/google", json={"id_token": "valid-token-value-123"})

    assert first.status_code == 200
    assert second.status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(OAuthAccount)) == 1


def test_existing_verified_email_is_linked_instead_of_duplicated(
    client, override_google_verifier
):
    register_user(client, email="google@example.com")
    override_google_verifier(StaticGoogleVerifier(identity=_identity()))
    response = client.post("/api/v1/auth/google", json={"id_token": "valid-token-value-123"})

    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(OAuthAccount)) == 1


@pytest.mark.parametrize("reason", ["invalid", "expired", "wrong audience"])
def test_invalid_google_tokens_are_rejected(client, override_google_verifier, reason):
    override_google_verifier(
        StaticGoogleVerifier(error=GoogleTokenError(f"{reason} Google token"))
    )
    response = client.post(
        "/api/v1/auth/google",
        json={"id_token": "invalid-google-token-value"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Google ID token"


def test_google_verifier_rejects_wrong_issuer(monkeypatch):
    monkeypatch.setattr(
        google_auth_module.google_id_token,
        "verify_oauth2_token",
        lambda *args, **kwargs: {
            "iss": "https://evil.example",
            "sub": "sub",
            "email": "learner@example.com",
            "email_verified": True,
        },
    )
    with pytest.raises(GoogleTokenError):
        GoogleTokenVerifier().verify("token")


def test_google_verifier_rejects_unverified_email(monkeypatch):
    monkeypatch.setattr(
        google_auth_module.google_id_token,
        "verify_oauth2_token",
        lambda *args, **kwargs: {
            "iss": "https://accounts.google.com",
            "sub": "sub",
            "email": "learner@example.com",
            "email_verified": False,
        },
    )
    with pytest.raises(GoogleTokenError):
        GoogleTokenVerifier().verify("token")
