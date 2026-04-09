import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import SkillLevel, SportType, UserStatus


class UserSportResponse(BaseModel):
    sport: SportType
    skill_level: SkillLevel

    model_config = {"from_attributes": True}


class UserSportRequest(BaseModel):
    sport: SportType
    skill_level: SkillLevel


class UserSummaryResponse(BaseModel):
    """
    Lightweight user object used inside nested responses.
    """
    id: uuid.UUID
    full_name: str
    avatar_url: str | None
    avg_rating: float

    model_config = {"from_attributes": True}


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
    avg_rating: float
    total_games_played: int
    status: UserStatus
    sports: list[UserSportResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfileResponse(BaseModel):
    """
    Public profile returned when viewing another user's profile.
    """
    id: uuid.UUID
    full_name: str
    bio: str | None
    location: str | None
    avatar_url: str | None
    avg_rating: float
    total_games_played: int
    total_reviews: int
    sports: list[UserSportResponse]
    followers_count: int = 0
    following_count: int = 0
    is_following: bool = False

    model_config = {"from_attributes": True}


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


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    bio: str | None = None
    location: str | None = None
    avatar_url: str | None = None
    sports: list[UserSportRequest] | None = None

