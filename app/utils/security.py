import hashlib
import base64
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status

from app.config import settings

# ─── Password Hashing ─────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _prepare_password(plain_password: str) -> str:
    """
    Pre-hash the password with SHA-256 before passing to bcrypt.

    Why: bcrypt silently truncates passwords longer than 72 bytes.
    bcrypt 4.x raises ValueError instead of silently truncating.
    Pre-hashing with SHA-256 produces a fixed 44-character base64 string
    (well under the 72-byte limit) while preserving full password entropy.

    This approach is recommended by passlib and used in production systems.
    """
    digest = hashlib.sha256(plain_password.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("utf-8")


def hash_password(plain_password: str) -> str:
    """
    Hash a plain text password using SHA-256 pre-hash + bcrypt.
    Safe for passwords of any length.
    """
    return pwd_context.hash(_prepare_password(plain_password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against its bcrypt hash.
    Must use the same SHA-256 pre-hash as hash_password().
    """
    return pwd_context.verify(_prepare_password(plain_password), hashed_password)


# ─── JWT Token Utilities ──────────────────────────────────────────────────────

def create_access_token(subject: str | Any) -> str:
    """
    Creates a JWT access token.
    Expires after ACCESS_TOKEN_EXPIRE_MINUTES (default: 15 minutes).
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str | Any) -> str:
    """
    Creates a JWT refresh token.
    Expires after REFRESH_TOKEN_EXPIRE_DAYS (default: 30 days).
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str, token_type: str = "access") -> str:
    """
    Decodes and validates a JWT token.
    Returns the subject (user ID) if valid.
    Raises HTTP 401 if invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        subject: str = payload.get("sub")
        t_type: str = payload.get("type")

        if subject is None or t_type != token_type:
            raise credentials_exception

        return subject

    except JWTError:
        raise credentials_exception
