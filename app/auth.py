import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import RefreshToken, User

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return password_context.verify(password, password_hash)


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "type": "access", "iat": now, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token(db: Session, user_id: int) -> str:
    raw_token = secrets.token_urlsafe(64)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_opaque_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    return raw_token


def issue_token_pair(db: Session, user_id: int) -> tuple[str, str]:
    return create_access_token(user_id), create_refresh_token(db, user_id)


def revoke_user_refresh_tokens(db: Session, user_id: int) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_opaque_token(raw_token))
    )
    if token and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[int, str, str]:
    token = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_opaque_token(raw_token))
        .with_for_update()
    )
    if not token:
        raise _unauthorized()

    now = datetime.now(UTC)
    if token.revoked_at is not None:
        # A rotated token being presented again indicates possible theft. Revoke
        # every session for that user without exposing whether the token existed.
        revoke_user_refresh_tokens(db, token.user_id)
        db.commit()
        raise _unauthorized()
    if token.expires_at <= now:
        token.revoked_at = now
        db.commit()
        raise _unauthorized()

    user = db.get(User, token.user_id)
    if not user or not user.is_active:
        token.revoked_at = now
        db.commit()
        raise _unauthorized()

    token.revoked_at = now
    access_token, refresh_token = issue_token_pair(db, user.id)
    db.commit()
    return user.id, access_token, refresh_token


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized()
    return _user_from_access_token(credentials.credentials, db)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    return _user_from_access_token(credentials.credentials, db)


def _user_from_access_token(token: str, db: Session) -> User:
    unauthorized = _unauthorized()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "access":
            raise unauthorized
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError):
        raise unauthorized from None

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
