import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.enums import UserStatus, SportType, SkillLevel


# ─── Sport Schemas ────────────────────────────────────────────────────────────
class UserSportResponse(BaseModel):
    sport: SportType
    skill_level: SkillLevel

    model_config = {"from_attributes": True}


class UserSportRequest(BaseModel):
    sport: SportType
    skill_level: SkillLevel


# ─── User Summary (used in nested responses) ─────────────────────────────────
class UserSummaryResponse(BaseModel):
    """
    Lightweight user object — used inside match responses,
    review responses, etc. Never exposes sensitive fields.
    """
    id: uuid.UUID
    full_name: str
    avatar_url: str | None
    avg_rating: float

    model_config = {"from_attributes": True}


# ─── Full User Response (own profile) ────────────────────────────────────────
class UserResponse(BaseModel):
    """
    Full profile returned to the authenticated user themselves (GET /users/me).
    """
    id: uuid.UUID
    full_name: str
    email: str
    phone_number: str | None
    bio: str | None
    location: str | None
    avatar_url: str | None
    avg_rating: float
    total_games_played: int
    status: UserStatus
    sports: list[UserSportResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Public Profile Response (other users) ───────────────────────────────────
class UserProfileResponse(BaseModel):
    """
    Public profile — returned when viewing another user's profile.
    Does NOT expose email or account status.
    """
    id: uuid.UUID
    full_name: str
    bio: str | None
    location: str | None
    avatar_url: str | None
    avg_rating: float
    total_games_played: int
    sports: list[UserSportResponse]
    followers_count: int = 0
    following_count: int = 0
    is_following: bool = False       # Whether the current user follows this profile

    model_config = {"from_attributes": True}


# ─── Update Profile Request ───────────────────────────────────────────────────
class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    bio: str | None = None
    location: str | None = None
    phone_number: str | None = None
    avatar_url: str | None = None
    sports: list[UserSportRequest] | None = None


# ─── User Stats ───────────────────────────────────────────────────────────────
class UserStatsResponse(BaseModel):
    user_id: uuid.UUID
    total_games_played: int
    avg_rating: float
    total_reviews: int
