from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings


class GoogleTokenError(ValueError):
    pass


class GoogleConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    display_name: str | None


class GoogleTokenVerifier:
    def verify(self, raw_token: str) -> GoogleIdentity:
        if not settings.google_client_id:
            raise GoogleConfigurationError("Google OAuth is not configured")
        try:
            claims = google_id_token.verify_oauth2_token(
                raw_token,
                google_requests.Request(),
                audience=settings.google_client_id,
            )
        except ValueError as exc:
            raise GoogleTokenError("Invalid Google ID token") from exc

        issuer = claims.get("iss")
        subject = claims.get("sub")
        email = claims.get("email")
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise GoogleTokenError("Invalid Google ID token")
        if not subject or not email or claims.get("email_verified") is not True:
            raise GoogleTokenError("Invalid Google ID token")

        display_name = claims.get("name")
        return GoogleIdentity(
            subject=str(subject),
            email=str(email).strip().lower(),
            display_name=str(display_name)[:120] if display_name else None,
        )


_google_token_verifier = GoogleTokenVerifier()


def get_google_token_verifier() -> GoogleTokenVerifier:
    return _google_token_verifier
