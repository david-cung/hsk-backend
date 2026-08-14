import pytest
from conftest import bearer, register_user
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import HskLevel, RefreshToken, SavedWord, User


def test_unauthenticated_request_returns_401(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_authenticated_user_can_access_own_profile(client):
    session = register_user(client)
    response = client.get(
        "/api/v1/auth/me/profile",
        headers=bearer(session["access_token"]),
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "forbidden_field",
    ["user_id", "is_admin", "study_streak_days", "score_percent", "created_at"],
)
def test_profile_rejects_system_managed_fields(client, forbidden_field):
    session = register_user(client)
    response = client.patch(
        "/api/v1/profile",
        json={forbidden_field: 99},
        headers=bearer(session["access_token"]),
    )
    assert response.status_code == 422


def test_admin_only_endpoint_rejects_user_and_accepts_admin(client):
    session = register_user(client)
    assert client.get(
        "/api/v1/admin/status",
        headers=bearer(session["access_token"]),
    ).status_code == 403

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "learner@example.com"))
        user.is_admin = True
        db.commit()

    response = client.get(
        "/api/v1/admin/status",
        headers=bearer(session["access_token"]),
    )
    assert response.status_code == 200


def test_user_cannot_delete_another_users_saved_word(client):
    owner = register_user(client, email="owner@example.com")
    other = register_user(client, email="other@example.com")
    created = client.post(
        "/api/v1/learning/saved-words",
        json={"hanzi": "你好", "pinyin": "nǐ hǎo", "meaning": "hello"},
        headers=bearer(owner["access_token"]),
    )
    word_id = created.json()["id"]

    response = client.delete(
        f"/api/v1/learning/saved-words/{word_id}",
        headers=bearer(other["access_token"]),
    )
    assert response.status_code == 404


def test_account_deletion_removes_owned_data_but_keeps_shared_content(client):
    session = register_user(client)
    client.post(
        "/api/v1/learning/saved-words",
        json={"hanzi": "你好", "pinyin": "nǐ hǎo", "meaning": "hello"},
        headers=bearer(session["access_token"]),
    )
    with SessionLocal() as db:
        db.add(
            HskLevel(
                level_number=1,
                title="HSK 1",
                description="Shared curriculum",
                total_characters=150,
            )
        )
        db.commit()

    response = client.delete(
        "/api/v1/auth/me",
        headers=bearer(session["access_token"]),
    )
    assert response.status_code == 204

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(SavedWord)) == 0
        assert db.scalar(select(func.count()).select_from(RefreshToken)) == 0
        assert db.scalar(select(func.count()).select_from(HskLevel)) == 1

    assert client.get(
        "/api/v1/auth/me",
        headers=bearer(session["access_token"]),
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": session["refresh_token"]},
    ).status_code == 401
