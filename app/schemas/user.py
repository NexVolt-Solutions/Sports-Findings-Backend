import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.enums import SkillLevel, SportType, UserStatus
from app.schemas.review import UserSummaryResponse, ReviewResponse


class UserSportResponse(BaseModel):
    sport: SportType
    skill_level: SkillLevel
    model_config = {"from_attributes": True}


class UserSportRequest(BaseModel):
    sport: SportType
    skill_level: SkillLevel


# ─── Nested Response Models ───────────────────────────────────────────────────

class UserStatsResponse(BaseModel):
    followers: int = 0
    following: int = 0
    matches: int | None = None
    rating: float | None = None


class UserActionsResponse(BaseModel):
    can_follow: bool
    can_message: bool
    can_rate: bool
    is_following: bool | None = None
    is_own_profile: bool


class UserSettingsResponse(BaseModel):
    notifications_enabled: bool = True


class UserNavigationResponse(BaseModel):
    public_profile_enabled: bool = True
    private_profile_enabled: bool = False
    terms_url: str = "https://sportfinding.com/terms"
    privacy_url: str = "https://sportfinding.com/privacy"


class UserCtaResponse(BaseModel):
    edit_profile: bool = True
    share_profile: bool = True


# ─── Own Profile ──────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    """
    Full profile returned to the authenticated user themselves.
    """
    id: uuid.UUID
    full_name: str
    email: str
    bio: str | None
    location: str | None
    avatar_url: str | None
    is_admin: bool
    status: UserStatus
    sports: list[UserSportResponse]
    total_reviews: int = 0
    reviews: list[ReviewResponse] = []
    stats: UserStatsResponse
    actions: UserActionsResponse
    settings: UserSettingsResponse
    navigation: UserNavigationResponse
    cta: UserCtaResponse
    created_at: datetime
    model_config = {"from_attributes": True}


# ─── Public Profile ───────────────────────────────────────────────────────────

class UserProfileResponse(BaseModel):
    """
    Public profile returned when viewing another user's profile.
    """
    id: uuid.UUID
    full_name: str
    bio: str | None
    location: str | None
    avatar_url: str | None
    is_admin: bool
    total_reviews: int
    reviews: list[ReviewResponse]
    sports: list[UserSportResponse]
    stats: UserStatsResponse
    actions: UserActionsResponse
    model_config = {"from_attributes": True}


# ─── User List Item ───────────────────────────────────────────────────────────

class UserListItemResponse(BaseModel):
    """
    Public user card used in frontend browse/search user lists.
    """
    id: uuid.UUID
    full_name: str
    bio: str | None
    location: str | None
    avatar_url: str | None
    avg_rating: float
    total_games_played: int
    sports: list[UserSportResponse]
    is_following: bool = False
    model_config = {"from_attributes": True}


# ─── Update Profile Request ───────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    bio: str | None = None
    location: str | None = None
    avatar_url: str | None = None
    sports: list[UserSportRequest] | None = None

    