import uuid
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.user import User
from app.models.enums import UserStatus
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    GoogleAuthRequest,
    TokenResponse,
)
from app.schemas.common import MessageResponse
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.utils.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    AccountNotVerified,
    AccountBlocked,
    bad_request,
    external_service_error,
)
from app.background.tasks import (
    send_verification_email,
    send_password_reset_email,
)

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
EMAIL_OTP_EXPIRE_MINUTES = 10


async def register_user(
    payload: RegisterRequest,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """
    Register a new user with email and password.
    Steps:
    1. Check if email already exists
    2. Hash the password
    3. Create user with status PENDING_VERIFICATION
    4. Generate 6-digit email verification OTP
    5. Queue verification email as background task
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    existing = result.scalar_one_or_none()

    if existing:
        if existing.status == UserStatus.PENDING_VERIFICATION:
            verification_otp, otp_expires_at = _generate_email_otp()
            existing.full_name = payload.full_name.strip()
            existing.avatar_url = payload.avatar_url
            existing.hashed_password = hash_password(payload.password)
            existing.terms_accepted_at = datetime.now(timezone.utc)
            existing.email_verification_otp = verification_otp
            existing.email_verification_otp_expires_at = otp_expires_at

            await db.commit()

            background_tasks.add_task(
                send_verification_email,
                existing.id,
                existing.email,
                verification_otp,
            )

            return MessageResponse(
                message="Account already exists but is not verified. A new 6-digit verification OTP has been sent."
            )

        raise EmailAlreadyRegistered()

    hashed = hash_password(payload.password)
    verification_otp, otp_expires_at = _generate_email_otp()

    user = User(
        email=payload.email,
        hashed_password=hashed,
        full_name=payload.full_name.strip(),
        avatar_url=payload.avatar_url,
        status=UserStatus.PENDING_VERIFICATION,
        terms_accepted_at=datetime.now(timezone.utc),
        email_verification_otp=verification_otp,
        email_verification_otp_expires_at=otp_expires_at,
    )
    db.add(user)
    await db.flush()

    background_tasks.add_task(
        send_verification_email,
        user.id,
        user.email,
        verification_otp,
    )

    await db.commit()
    logger.info(f"New user registered: {user.email} (id={user.id})")

    return MessageResponse(
        message="Registration successful. Please check your email for the 6-digit verification OTP."
    )


async def login_user(
    payload: LoginRequest,
    db: AsyncSession,
) -> TokenResponse:
    """
    Authenticate a user with email and password.
    Returns access + refresh tokens on success.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise InvalidCredentials()
    if not verify_password(payload.password, user.hashed_password):
        raise InvalidCredentials()

    if user.status == UserStatus.PENDING_VERIFICATION:
        raise AccountNotVerified()
    if user.status == UserStatus.BLOCKED:
        raise AccountBlocked()

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    logger.info(f"User logged in: {user.email} (id={user.id})")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


async def google_login(
    payload: GoogleAuthRequest,
    db: AsyncSession,
) -> TokenResponse:
    """
    Authenticate or register a user via Google ID token.
    Steps:
    1. Verify token with Google
    2. Look up user by google_id or email
    3. If exists: check not blocked, return tokens
    4. If new: auto-create account (Google emails are pre-verified)
    """
    google_data = await _verify_google_token(payload.id_token)

    google_id = google_data.get("sub")
    email = google_data.get("email")
    full_name = google_data.get("name", email.split("@")[0])
    avatar_url = google_data.get("picture")

    if not google_id or not email:
        raise bad_request("Invalid Google token — missing required fields")

    result = await db.execute(
        select(User).where(
            (User.google_id == google_id) | (User.email == email)
        )
    )
    user = result.scalar_one_or_none()

    if user:
        if user.status == UserStatus.BLOCKED:
            raise AccountBlocked()
        if not user.google_id:
            user.google_id = google_id
            await db.commit()
    else:
        user = User(
            email=email,
            full_name=full_name,
            google_id=google_id,
            hashed_password=None,
            avatar_url=avatar_url,
            terms_accepted_at=datetime.now(timezone.utc),
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"New Google user registered: {email} (id={user.id})")

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


async def refresh_access_token(
    refresh_token: str,
    db: AsyncSession,
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    user_id_str = decode_token(refresh_token, token_type="refresh")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise bad_request("Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise bad_request("User not found")
    if user.status == UserStatus.BLOCKED:
        raise AccountBlocked()

    new_access = create_access_token(str(user.id))
    new_refresh = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
    )


async def verify_email(
    email: str,
    otp: str,
    db: AsyncSession,
) -> MessageResponse:
    """Verify a user's email using a 6-digit OTP."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise bad_request("Invalid email or OTP")

    if user.status == UserStatus.ACTIVE:
        return MessageResponse(message="Email is already verified. You can log in.")

    if user.status == UserStatus.BLOCKED:
        raise AccountBlocked()

    if not user.email_verification_otp or not user.email_verification_otp_expires_at:
        raise bad_request("No verification OTP found. Please request a new OTP.")

    if user.email_verification_otp != otp:
        raise bad_request("Invalid email or OTP")

    if user.email_verification_otp_expires_at < datetime.now(timezone.utc):
        raise bad_request("Verification OTP has expired. Please request a new OTP.")

    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db.commit()

    logger.info(f"Email verified for user: {user.email} (id={user.id})")
    return MessageResponse(message="Email verified successfully. You can now log in.")


async def resend_verification_otp(
    email: str,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """Resend a fresh email verification OTP for a pending account."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        return MessageResponse(
            message="If an account with that email exists and is pending verification, a new OTP has been sent."
        )

    if user.status == UserStatus.ACTIVE:
        return MessageResponse(message="Email is already verified. You can log in.")

    if user.status == UserStatus.BLOCKED:
        raise AccountBlocked()

    verification_otp, otp_expires_at = _generate_email_otp()
    user.email_verification_otp = verification_otp
    user.email_verification_otp_expires_at = otp_expires_at
    await db.commit()

    background_tasks.add_task(
        send_verification_email,
        user.id,
        user.email,
        verification_otp,
    )

    return MessageResponse(
        message="If an account with that email exists and is pending verification, a new OTP has been sent."
    )


async def forgot_password(
    email: str,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """
    Send a password reset email.
    Always returns the same message — never reveals whether email exists.
    """
    generic_message = MessageResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or user.status == UserStatus.BLOCKED or not user.hashed_password:
        return generic_message

    reset_token = _create_email_token(
        str(user.id), token_type="reset", expire_minutes=15
    )

    background_tasks.add_task(
        send_password_reset_email,
        user.id,
        user.email,
        reset_token,
    )

    return generic_message


async def reset_password(
    token: str,
    new_password: str,
    db: AsyncSession,
) -> MessageResponse:
    """Reset the user password using a valid reset token."""
    user_id_str = decode_token(token, token_type="reset")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise bad_request("Invalid or expired reset token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or user.status == UserStatus.BLOCKED:
        raise bad_request("Invalid or expired reset token")

    user.hashed_password = hash_password(new_password)
    await db.commit()

    logger.info(f"Password reset for user: {user.email} (id={user.id})")
    return MessageResponse(message="Password reset successfully. You can now log in.")


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _create_email_token(
    subject: str,
    token_type: str,
    expire_minutes: int = 60 * 24,
) -> str:
    """Creates a short-lived signed JWT for email verification or password reset."""
    from jose import jwt
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {
        "sub": subject,
        "exp": expire,
        "type": token_type,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _generate_email_otp() -> tuple[str, datetime]:
    otp = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=EMAIL_OTP_EXPIRE_MINUTES)
    return otp, expires_at


async def _verify_google_token(id_token: str) -> dict:
    """
    Verify a Google ID token using Google's tokeninfo endpoint.
    Returns decoded payload on success, raises HTTP 400 on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                GOOGLE_TOKEN_INFO_URL,
                params={"id_token": id_token},
            )

        if response.status_code != 200:
            raise bad_request("Invalid Google ID token")

        data = response.json()

        if settings.google_client_id and data.get("aud") != settings.google_client_id:
            raise bad_request("Google token audience mismatch")

        return data

    except httpx.HTTPError as e:
        logger.error(f"Google token verification HTTP error: {e}")
        raise external_service_error("Google authentication")
        
        