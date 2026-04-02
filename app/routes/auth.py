from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

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
    payload: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with email and password.
    Sends a verification email as a background task.
    """
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
    return await auth_service.resend_verification_otp(payload.email, db, background_tasks)


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
    """Reset the user's password using a valid reset token."""
    return await auth_service.reset_password(payload.token, payload.new_password, db)
