from fastapi import APIRouter, Depends, BackgroundTasks, Form, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import re
from pydantic import EmailStr

from app.database import get_db
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    GoogleAuthRequest,
    TokenResponse,
    RefreshTokenRequest,
    VerifyEmailRequest,
    ResendVerificationOtpRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.schemas.common import MessageResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=MessageResponse, status_code=201)
async def register(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    full_name: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    accept_terms: bool = Form(...),
    avatar: Optional[UploadFile] = File(None),
):
    """
    Register a new user with multipart/form-data.
    Optionally accepts an avatar image file.
    Sends a verification email as a background task.
    """
    # ─── Validate full_name ───────────────────────────────────────
    full_name = full_name.strip()
    if len(full_name) < 2:
        raise HTTPException(
            status_code=422,
            detail="Full name must be at least 2 characters"
        )

    # ─── Validate password ────────────────────────────────────────
    if len(password) < 8:
        raise HTTPException(
            status_code=422,
            detail="Password must be at least 8 characters long"
        )
    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=422,
            detail="Password must contain at least one uppercase letter"
        )
    if not re.search(r"\d", password):
        raise HTTPException(
            status_code=422,
            detail="Password must contain at least one number"
        )

    # ─── Validate confirm_password ────────────────────────────────
    if password != confirm_password:
        raise HTTPException(
            status_code=422,
            detail="Password and confirm password must match"
        )

    # ─── Validate accept_terms ────────────────────────────────────
    if not accept_terms:
        raise HTTPException(
            status_code=422,
            detail="You must accept the Terms of Service and Privacy Policy"
        )

    # ─── Upload avatar to S3 if provided ──────────────────────────
    avatar_url = None
    if avatar and avatar.filename:
        from app.utils.s3 import upload_avatar_to_s3
        avatar_url = await upload_avatar_to_s3("registration", avatar)

    # ─── Build payload and register ───────────────────────────────
    payload = RegisterRequest(
        full_name=full_name,
        email=email,
        password=password,
        confirm_password=confirm_password,
        accept_terms=accept_terms,
        avatar_url=avatar_url,
    )

    return await auth_service.register_user(payload, db, background_tasks)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Login with email and password.
    Returns access and refresh JWT tokens.
    """
    return await auth_service.login_user(payload, db)


@router.post("/google", response_model=TokenResponse)
async def google_auth(
    payload: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with a Google ID token.
    Creates a new account if the user does not exist.
    """
    return await auth_service.google_login(payload, db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    return await auth_service.refresh_access_token(payload.refresh_token, db)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: RefreshTokenRequest,
):
    """
    Logout the user.
    In a stateless JWT setup, the client discards the tokens.
    Token blacklisting can be added in Phase 2 via Redis.
    """
    return MessageResponse(message="Logged out successfully.")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify a user's email address using a 6-digit OTP."""
    return await auth_service.verify_email(payload.email, payload.otp, db)


@router.post("/resend-verification-otp", response_model=MessageResponse)
async def resend_verification_otp(
    payload: ResendVerificationOtpRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Resend a fresh 6-digit email verification OTP."""
    return await auth_service.resend_verification_otp(
        payload.email, db, background_tasks
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Request a password reset email.
    Always returns the same response — never reveals if email exists.
    """
    return await auth_service.forgot_password(payload.email, db, background_tasks)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset the user's password using a valid reset OTP."""
    return await auth_service.reset_password(payload.email, payload.otp, payload.new_password, db)