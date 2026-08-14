import os

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://hsk:hsk@localhost:5432/hsk_test",
)
os.environ.setdefault("JWT_SECRET", "test-only-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")

from app.database import Base, engine  # noqa: E402
from app.email import get_email_sender  # noqa: E402
from app.google_auth import get_google_token_verifier  # noqa: E402
from app.main import app  # noqa: E402


class FakeEmailSender:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def send_password_reset(self, email: str, token: str, expires_at: object) -> None:
        self.messages.append({"email": email, "token": token, "expires_at": expires_at})


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def fake_email_sender() -> FakeEmailSender:
    sender = FakeEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    return sender


@pytest.fixture
def override_google_verifier():
    def apply(verifier: object) -> None:
        app.dependency_overrides[get_google_token_verifier] = lambda: verifier

    return apply


def register_user(
    client: TestClient,
    email: str = "learner@example.com",
    password: str = "StrongPass123",
    display_name: str = "Learner",
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}
