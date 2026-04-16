import uuid
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

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

EMAIL_OTP_EXPIRE_MINUTES = 2
PASSWORD_RESET_OTP_EXPIRE_MINUTES = 2


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _generate_otp(expire_minutes: int) -> tuple[str, datetime]:
    """
    Generate a cryptographically secure 6-digit OTP and its expiry timestamp.
    Single implementation shared by email verification and password reset flows.
    """
    otp = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    return otp, expires_at


async def register_user(
    payload: RegisterRequest,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    normalized_email = _normalize_email(payload.email)
    result = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.status == UserStatus.PENDING_VERIFICATION:
            verification_otp, otp_expires_at = _generate_otp(EMAIL_OTP_EXPIRE_MINUTES)
            # full_name is already stripped by the Pydantic validator
            existing.full_name = payload.full_name
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
    verification_otp, otp_expires_at = _generate_otp(EMAIL_OTP_EXPIRE_MINUTES)

    user = User(
        email=normalized_email,
        hashed_password=hashed,
        # full_name is already stripped by the Pydantic validator
        full_name=payload.full_name,
        avatar_url=payload.avatar_url,
        status=UserStatus.PENDING_VERIFICATION,
        terms_accepted_at=datetime.now(timezone.utc),
        email_verification_otp=verification_otp,
        email_verification_otp_expires_at=otp_expires_at,
    )
    db.add(user)

    # flush() to get user.id before passing it to the background task.
    # BackgroundTasks runs post-response (after commit), so the user row
    # will exist by the time the task executes — this ordering is safe.
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
    normalized_email = _normalize_email(payload.email)
    result = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
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
    google_data = await _verify_google_token(payload.id_token)

    google_id = google_data.get("sub")
    email = _normalize_email(google_data.get("email", ""))
    full_name = google_data.get("name", email.split("@")[0])
    avatar_url = google_data.get("picture")

    if not google_id or not email:
        raise bad_request("Invalid Google token — missing required fields")

    result = await db.execute(
        select(User).where(
            (User.google_id == google_id) | (func.lower(User.email) == email)
        )
    )
    user = result.scalar_one_or_none()

    if user:
        if user.status == UserStatus.BLOCKED:
            raise AccountBlocked()

        # Google has verified ownership of this email, so a PENDING_VERIFICATION
        # account can be safely activated — no need to complete the OTP flow.
        if user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.ACTIVE
            user.email_verification_otp = None
            user.email_verification_otp_expires_at = None
            logger.info(
                f"PENDING_VERIFICATION account activated via Google OAuth: "
                f"{user.email} (id={user.id})"
            )

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
    normalized_email = _normalize_email(email)
    result = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
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

    expires_at = user.email_verification_otp_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        user.email_verification_otp = None
        user.email_verification_otp_expires_at = None
        await db.commit()
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
    normalized_email = _normalize_email(email)
    result = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    user = result.scalar_one_or_none()

    if not user:
        return MessageResponse(
            message="If an account with that email exists and is pending verification, a new OTP has been sent."
        )

    if user.status == UserStatus.ACTIVE:
        return MessageResponse(message="Email is already verified. You can log in.")

    if user.status == UserStatus.BLOCKED:
        raise AccountBlocked()

    verification_otp, otp_expires_at = _generate_otp(EMAIL_OTP_EXPIRE_MINUTES)
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
    Send a password reset OTP via email.
    Always returns the same message — never reveals whether the email exists.
    Each call generates a NEW OTP, invalidating the previous one.
    Only works for password-based accounts (hashed_password is not None).
    """
    generic_message = MessageResponse(
        message="If an account with that email exists, a password reset OTP has been sent."
    )

    normalized_email = _normalize_email(email)
    result = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    user = result.scalar_one_or_none()

    if not user or user.status == UserStatus.BLOCKED or not user.hashed_password:
        return generic_message

    reset_otp, otp_expires_at = _generate_otp(PASSWORD_RESET_OTP_EXPIRE_MINUTES)
    user.password_reset_otp = reset_otp
    user.password_reset_otp_expires_at = otp_expires_at
    # Clear any previously verified flag so a new OTP cycle must be completed.
    user.password_reset_otp_verified = False
    await db.commit()

    background_tasks.add_task(
        send_password_reset_email,
        user.id,
        user.email,
        reset_otp,
    )

    return generic_message


async def resend_reset_password_otp(
    email: str,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """
    Resend a fresh password reset OTP.
    Intentionally delegates to forgot_password — each call issues a new OTP
    and invalidates the previous one.
    """
    return await forgot_password(email, db, background_tasks)


async def verify_reset_password_otp(
    email: str,
    otp: str,
    db: AsyncSession,
) -> MessageResponse:
    """
    Step 2 of 3 — verify the password reset OTP.
    Sets password_reset_otp_verified=True so reset_password() knows step 2
    was completed and the client didn't skip straight to step 3.
    """
    user = await _get_user_for_password_reset(email, db)

    if user.password_reset_otp != otp:
        raise bad_request("Invalid OTP")

    await _ensure_password_reset_otp_not_expired(user, db)

    # Mark OTP as verified — required by reset_password() before it will proceed.
    user.password_reset_otp_verified = True
    await db.commit()

    return MessageResponse(message="OTP verified successfully. You can now set a new password.")


async def reset_password(
    email: str,
    otp: str,
    new_password: str,
    db: AsyncSession,
) -> MessageResponse:
    """
    Step 3 of 3 — reset the password.
    Requires that step 2 (verify_reset_password_otp) was completed first.
    Re-validates the OTP and expiry as a defence-in-depth measure.
    """
    user = await _get_user_for_password_reset(email, db)

    # Guard: step 2 must have been completed — prevents skipping OTP verification.
    if not getattr(user, "password_reset_otp_verified", False):
        raise bad_request("OTP not verified. Please complete the OTP verification step first.")

    if user.password_reset_otp != otp:
        raise bad_request("Invalid OTP")

    await _ensure_password_reset_otp_not_expired(user, db)

    user.hashed_password = hash_password(new_password)
    user.password_reset_otp = None
    user.password_reset_otp_expires_at = None
    user.password_reset_otp_verified = False
    await db.commit()

    logger.info(f"Password reset for user: {user.email} (id={user.id})")
    return MessageResponse(message="Password reset successfully. You can now log in.")


# ─── Internal Helpers ─────────────────────────────────────────────────────────

async def _get_user_for_password_reset(email: str, db: AsyncSession) -> User:
    """
    Fetch and validate a user for any step of the password reset flow.
    Raises bad_request for missing users, blocked accounts, or missing OTP state.
    """
    normalized_email = _normalize_email(email)
    result = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    user = result.scalar_one_or_none()

    if not user or user.status == UserStatus.BLOCKED:
        raise bad_request("Invalid email or OTP")

    if not user.password_reset_otp or not user.password_reset_otp_expires_at:
        raise bad_request("No password reset request found. Please request a new OTP.")

    return user


async def _ensure_password_reset_otp_not_expired(user: User, db: AsyncSession) -> None:
    """
    Check OTP expiry, ensuring timezone-aware comparison.
    Clears the OTP fields and raises bad_request if expired.
    """
    expires_at = user.password_reset_otp_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        user.password_reset_otp = None
        user.password_reset_otp_expires_at = None
        user.password_reset_otp_verified = False
        await db.commit()
        raise bad_request("OTP has expired. Please request a new OTP.")


async def _verify_google_token(id_token: str) -> dict:
    """Verify a Google ID token against Google's tokeninfo endpoint."""
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

    
