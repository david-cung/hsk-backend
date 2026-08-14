from datetime import UTC, datetime, timedelta

from conftest import register_user
from sqlalchemy import select

from app.auth import hash_opaque_token
from app.database import SessionLocal
from app.models import RefreshToken


def test_valid_refresh_rotates_token(client):
    original = register_user(client)["refresh_token"]
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": original})

    assert response.status_code == 200
    rotated = response.json()["refresh_token"]
    assert rotated != original

    with SessionLocal() as db:
        old_row = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_opaque_token(original))
        )
        assert old_row is not None
        assert old_row.revoked_at is not None


def test_expired_refresh_is_rejected(client):
    refresh_token = register_user(client)["refresh_token"]
    with SessionLocal() as db:
        row = db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_opaque_token(refresh_token)
            )
        )
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 401


def test_revoked_refresh_is_rejected(client):
    refresh_token = register_user(client)["refresh_token"]
    client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 401


def test_reuse_of_rotated_token_revokes_successor(client):
    original = register_user(client)["refresh_token"]
    first_rotation = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original},
    )
    successor = first_rotation.json()["refresh_token"]

    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert reused.status_code == 401
    successor_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": successor},
    )
    assert successor_response.status_code == 401


def test_invalid_refresh_does_not_leak_token_existence(client):
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "x" * 64},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired credentials"


def test_logout_revokes_token_and_is_idempotent(client):
    refresh_token = register_user(client)["refresh_token"]
    first = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    second = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})

    assert first.status_code == 204
    assert second.status_code == 204
