import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.enums import SkillLevel, SportType, UserStatus
from app.schemas.review import UserSummaryResponse, ReviewResponse


class UserSportResponse(BaseModel):
    """Sport with skill level — matches UI badge style."""
    sport: SportType
    skill_level: SkillLevel
    model_config = {"from_attributes": True}


class UserSportRequest(BaseModel):
    sport: SportType
    skill_level: SkillLevel

    @field_validator("sport", mode="before")
    @classmethod
    def normalize_sport(cls, value):
        if isinstance(value, str):
            normalized = value.strip()
            if normalized in SportType.__members__:
                return SportType[normalized]
        return value

    @field_validator("skill_level", mode="before")
    @classmethod
    def normalize_skill_level(cls, value):
        if isinstance(value, str):
            normalized = value.strip()
            if normalized in SkillLevel.__members__:
                return SkillLevel[normalized]
        return value


# ─── Nested Response Models ───────────────────────────────────────────────────

class UserStatsResponse(BaseModel):
    """
    Stats shown in the profile header:
    Followers | Following | Rating
    """
    followers: int = 0
    following: int = 0
    rating: float = 0.0
    matches: int | None = None


class UserActionsResponse(BaseModel):
    """
    Controls which buttons are shown in the UI:
    Follow | Message | Rate Player
    """
    can_follow: bool
    can_message: bool
    can_rate: bool
    is_following: bool = False
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


# ─── Own Profile (Private Profile in UI) ─────────────────────────────────────

class UserResponse(BaseModel):
    """
    Full profile returned to the authenticated user (Private Profile screen).
    Shows: avatar, name, location, bio, stats, sports, reviews
    No Follow/Message/Rate buttons
    """
    id: uuid.UUID
    full_name: str
    email: str
    bio: str | None
    location: str | None
    avatar_url: str | None
    is_admin: bool
    status: UserStatus
    avg_rating: float = 0.0
    total_games_played: int = 0
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
    Public profile returned when viewing another user (Public Profile screen).
    Shows: avatar, name, location, bio, Follow/Message/Rate buttons,
           stats, sports, reviews
    """
    id: uuid.UUID
    full_name: str
    bio: str | None
    location: str | None
    avatar_url: str | None
    is_admin: bool
    avg_rating: float = 0.0
    total_games_played: int = 0
    total_reviews: int
    reviews: list[ReviewResponse]
    sports: list[UserSportResponse]
    stats: UserStatsResponse
    actions: UserActionsResponse
    model_config = {"from_attributes": True}


# ─── User List Item ───────────────────────────────────────────────────────────

class UserListItemResponse(BaseModel):
    """
    Public user card used in browse/search lists.
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


# ─── Update Profile Response ──────────────────────────────────────────────────

class UpdateProfileResponse(BaseModel):
    """
    Focused response for profile update operations.
    """
    id: uuid.UUID
    full_name: str
    bio: str | None
    avatar_url: str | None
    location: str | None = None
    sports: list[UserSportResponse]
    updated_at: datetime
    model_config = {"from_attributes": True}


# ─── Update Profile Request ───────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    """
    Profile update request — only editable fields.
    Use multipart/form-data with optional fields:
    - full_name: string (max 100 chars)
    - bio: string (max 500 chars)
    - sports: JSON array of {sport, skill_level}
    - avatar: file (image)
    """
    full_name: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=500)
    location: str | None = Field(None, max_length=100)
    sports: list[UserSportRequest] | None = None
