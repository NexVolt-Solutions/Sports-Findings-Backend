from pydantic import BaseModel, EmailStr, field_validator, model_validator
import re


class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    confirm_password: str
    avatar_url: str | None = None
    accept_terms: bool

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v

    @model_validator(mode="after")
    def validate_confirmation(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password and confirm password must match")
        if not self.accept_terms:
            raise ValueError("You must accept the Terms of Service and Privacy Policy")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    """Google ID token received from the mobile Google Sign-In SDK."""
    id_token: str


class TokenResponse(BaseModel):
    """Returned after successful login or token refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        otp = v.strip()
        if not re.fullmatch(r"\d{6}", otp):
            raise ValueError("OTP must be exactly 6 digits")
        return otp


class ResendVerificationOtpRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResendResetPasswordOtpRequest(BaseModel):
    email: EmailStr


class VerifyResetPasswordOtpRequest(BaseModel):
    email: EmailStr
    otp: str

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        otp = v.strip()
        if not re.fullmatch(r"\d{6}", otp):
            raise ValueError("OTP must be exactly 6 digits")
        return otp


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str
    # confirm_password is validated here by Pydantic but not forwarded to the
    # service — the service only needs new_password once the match is confirmed.
    confirm_password: str

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        otp = v.strip()
        if not re.fullmatch(r"\d{6}", otp):
            raise ValueError("OTP must be exactly 6 digits")
        return otp

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v

    @model_validator(mode="after")
    def validate_confirmation(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Password and confirm password must match")
        return self

