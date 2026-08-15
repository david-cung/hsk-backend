import logging
from datetime import datetime
from typing import Protocol

from app.config import settings

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    def send_password_reset(self, email: str, token: str, expires_at: datetime) -> None:
        """Send a password-reset message without exposing provider details."""


class LoggingEmailSender:
    """Development-only sender.

    Production deployments must replace this dependency with a provider adapter.
    """

    def send_password_reset(self, email: str, token: str, expires_at: datetime) -> None:
        logger.warning(
            "Development password reset for %s: %s?token=%s (expires %s)",
            email,
            settings.password_reset_url,
            token,
            expires_at.isoformat(),
        )


_email_sender: EmailSender = LoggingEmailSender()


def get_email_sender() -> EmailSender:
    return _email_sender
