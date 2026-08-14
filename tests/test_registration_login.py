from conftest import bearer, register_user
from jose import jwt

from app.config import settings


def test_valid_registration_returns_access_and_refresh_tokens(client):
    tokens = register_user(client)
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"

    me = client.get("/api/v1/auth/me", headers=bearer(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json() == {
        "id": 1,
        "email": "learner@example.com",
        "display_name": "Learner",
        "is_admin": False,
    }


def test_access_token_is_short_lived_and_contains_only_session_claims(client):
    access_token = register_user(client)["access_token"]
    claims = jwt.decode(
        access_token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    assert claims["type"] == "access"
    assert claims["sub"] == "1"
    assert 30 * 60 <= claims["exp"] - claims["iat"] <= 60 * 60
    assert "email" not in claims
    assert "password" not in claims


def test_duplicate_email_is_rejected_case_insensitively(client):
    register_user(client, email="Learner@Example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "learner@example.com", "password": "StrongPass123"},
    )
    assert response.status_code == 409


def test_registration_rejects_invalid_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "learner@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_registration_rejects_invalid_email(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "StrongPass123"},
    )
    assert response.status_code == 422


def test_valid_login_returns_rotatable_session(client):
    register_user(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "LEARNER@example.com", "password": "StrongPass123"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]


def test_login_rejects_wrong_password(client):
    register_user(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "WrongPass123"},
    )
    assert response.status_code == 401


def test_login_rejects_nonexistent_user(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "StrongPass123"},
    )
    assert response.status_code == 401
