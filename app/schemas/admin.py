import uuid
import re
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from app.models.enums import SportType, SupportRequestStatus


class MonthlyUserCount(BaseModel):
    month: str
    count: int


class DailyMatchCount(BaseModel):
    day: str
    count: int


class SportDistribution(BaseModel):
    sport: SportType
    count: int
    percentage: float


class DashboardStatsResponse(BaseModel):
    generated_at: datetime
    total_users: int
    total_matches: int
    active_matches: int
    new_users_today: int
    total_users_by_month: list[MonthlyUserCount]
    matches_per_day: list[DailyMatchCount]
    most_popular_sports: list[SportDistribution]


class CreateUserRequest(BaseModel):
    full_name: str
    email: str
    password: str
    is_admin: bool = False

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Full name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Full name must be at most 100 characters")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v:
            raise ValueError("Please enter a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v


class AdminUserListItemResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    location: str | None
    matches: int
    status: str


class AdminUserDetailResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    location: str | None
    status: str
    matches: int


class AdminMatchListItemResponse(BaseModel):
    id: uuid.UUID
    title: str
    host_name: str
    host_email: str
    location: str
    scheduled_at: datetime


class ReviewModerationUserItemResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    avatar_url: str | None
    reviews_count: int


class ReviewModerationReviewItemResponse(BaseModel):
    id: uuid.UUID
    reviewer_name: str
    rating: int
    comment: str | None
    created_at: datetime


class ReviewModerationUserReviewsResponse(BaseModel):
    user: ReviewModerationUserItemResponse
    items: list[ReviewModerationReviewItemResponse]
    total: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool


class ContentPageResponse(BaseModel):
    section: str
    title: str
    content: str


class UpdateContentPageRequest(BaseModel):
    title: str
    content: str

    @field_validator("title", "content")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("This field is required")
        return v


class SupportRequestListItemResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    subject: str
    submitted_at: datetime
    status: SupportRequestStatus


class SupportRequestDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    subject: str
    message: str
    submitted_at: datetime
    status: SupportRequestStatus


class AdminAccountResponse(BaseModel):
    full_name: str
    email: str
    phone: str | None


class UpdateAdminAccountRequest(BaseModel):
    full_name: str
    email: str
    phone: str | None = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v:
            raise ValueError("Please enter a valid email address")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if v and len(v) < 7:
            raise ValueError("Phone number must be at least 7 characters")
        return v or None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str

    @field_validator("current_password", "new_password", "confirm_new_password")
    @classmethod
    def validate_password_present(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Password is required")
        return v

    @model_validator(mode="after")
    def validate_confirmation(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("New password and confirm password must match")
        return self
