from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def _create_token(
    *,
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra: dict | None = None,
    jti: str | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": subject,
        "exp": expire,
        "token_type": token_type,
        "jti": jti or str(uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str,
    extra: dict | None = None,
    jti: str | None = None,
) -> str:
    """Create a JWT access token."""
    return _create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.jwt_expiration_minutes),
        extra=extra,
        jti=jti,
    )


def create_refresh_token(
    subject: str,
    extra: dict | None = None,
    jti: str | None = None,
) -> str:
    """Create a JWT refresh token."""
    return _create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expiration_days),
        extra=extra,
        jti=jti,
    )


def decode_token(token: str) -> dict | None:
    """Decode and verify a JWT token. Returns None if invalid."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None
