from datetime import UTC, datetime, timedelta

from conftest import bearer, register_user
from sqlalchemy import select

from app.auth import hash_opaque_token
from app.database import SessionLocal
from app.models import PasswordResetToken


def _request_reset(client, fake_email_sender) -> str:
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "learner@example.com"},
    )
    assert response.status_code == 202
    assert len(fake_email_sender.messages) == 1
    return str(fake_email_sender.messages[0]["token"])


def test_forgot_password_does_not_reveal_account_existence(client, fake_email_sender):
    missing = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "missing@example.com"},
    )
    register_user(client)
    existing = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "learner@example.com"},
    )
    assert missing.status_code == existing.status_code == 202
    assert missing.json() == existing.json()


def test_valid_password_reset_changes_password_and_revokes_sessions(
    client, fake_email_sender
):
    session = register_user(client)
    reset_token = _request_reset(client, fake_email_sender)

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "NewStrongPass123"},
    )
    assert reset.status_code == 204
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "NewStrongPass123"},
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": session["refresh_token"]},
    ).status_code == 401


def test_expired_reset_token_is_rejected(client, fake_email_sender):
    register_user(client)
    reset_token = _request_reset(client, fake_email_sender)
    with SessionLocal() as db:
        row = db.scalar(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == hash_opaque_token(reset_token)
            )
        )
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "NewStrongPass123"},
    )
    assert response.status_code == 400


def test_invalid_reset_token_is_rejected(client):
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "x" * 64, "new_password": "NewStrongPass123"},
    )
    assert response.status_code == 400


def test_reset_token_is_single_use(client, fake_email_sender):
    register_user(client)
    reset_token = _request_reset(client, fake_email_sender)
    payload = {"token": reset_token, "new_password": "NewStrongPass123"}
    assert client.post("/api/v1/auth/reset-password", json=payload).status_code == 204
    assert client.post("/api/v1/auth/reset-password", json=payload).status_code == 400


def test_new_reset_request_invalidates_previous_token(client, fake_email_sender):
    register_user(client)
    first_token = _request_reset(client, fake_email_sender)
    second_response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "learner@example.com"},
    )
    assert second_response.status_code == 202

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": first_token, "new_password": "NewStrongPass123"},
    )
    assert response.status_code == 400


def test_authenticated_password_change_revokes_refresh_tokens(client):
    session = register_user(client)
    response = client.patch(
        "/api/v1/auth/password",
        json={
            "current_password": "StrongPass123",
            "new_password": "ChangedPass123",
        },
        headers=bearer(session["access_token"]),
    )
    assert response.status_code == 204
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": session["refresh_token"]},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "ChangedPass123"},
    ).status_code == 200
