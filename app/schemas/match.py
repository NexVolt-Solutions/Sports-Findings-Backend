import uuid
from datetime import datetime
from datetime import timezone
from pydantic import BaseModel, field_validator, model_validator
from app.models.enums import SportType, SkillLevel, MatchStatus
from app.schemas.user import UserSummaryResponse


# ─── Create Match ─────────────────────────────────────────────────────────────
class CreateMatchRequest(BaseModel):
    title: str
    description: str
    sport: SportType
    facility_address: str
    scheduled_at: datetime
    duration_minutes: int
    max_players: int
    skill_level: SkillLevel

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Title must be at least 3 characters")
        if len(v) > 150:
            raise ValueError("Title must be at most 150 characters")
        return v

    @field_validator("max_players")
    @classmethod
    def validate_max_players(cls, v: int) -> int:
        if v < 2:
            raise ValueError("A match must allow at least 2 players")
        if v > 50:
            raise ValueError("Maximum player limit is 50")
        return v

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v < 10:
            raise ValueError("Match duration must be at least 10 minutes")
        if v > 480:
            raise ValueError("Match duration cannot exceed 8 hours")
        return v

    @field_validator("facility_address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Please enter a valid facility address")
        return v

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, v: datetime) -> datetime:
        # Use module-level datetime/timezone imports (not inner import which shadows them)
        now = datetime.now(timezone.utc)
        # Make timezone-aware if naive
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= now:
            raise ValueError("Match must be scheduled in the future")
        return v


# ─── Update Match ─────────────────────────────────────────────────────────────
class UpdateMatchRequest(BaseModel):
    """All fields are optional — only provided fields are updated."""
    title: str | None = None
    description: str | None = None
    facility_address: str | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    max_players: int | None = None
    skill_level: SkillLevel | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Title must be at least 3 characters")
        if len(v) > 150:
            raise ValueError("Title must be at most 150 characters")
        return v

    @field_validator("max_players")
    @classmethod
    def validate_max_players(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < 2:
            raise ValueError("A match must allow at least 2 players")
        if v > 50:
            raise ValueError("Maximum player limit is 50")
        return v

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < 10:
            raise ValueError("Match duration must be at least 10 minutes")
        if v > 480:
            raise ValueError("Match duration cannot exceed 8 hours")
        return v

    @field_validator("facility_address")
    @classmethod
    def validate_address(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Please enter a valid facility address")
        return v

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= now:
            raise ValueError("Match must be scheduled in the future")
        return v


# ─── Match Status Update ──────────────────────────────────────────────────────
class MatchStatusUpdateRequest(BaseModel):
    """
    Used by the host to update match status.
    Valid transitions:
      OPEN / FULL → ONGOING  (Start Game)
      ONGOING     → COMPLETED
      OPEN / FULL → CANCELLED
    """
    status: MatchStatus


# ─── Match Summary (used in list/discovery responses) ────────────────────────
class MatchSummaryResponse(BaseModel):
    """
    Lightweight match object returned in list and discovery results.
    Does not include full player list or messages.
    """
    id: uuid.UUID
    title: str
    sport: SportType
    skill_level: SkillLevel
    status: MatchStatus
    scheduled_at: datetime
    duration_minutes: int
    location_name: str | None
    facility_address: str
    latitude: float | None
    longitude: float | None
    max_players: int
    current_players: int = 0           # Computed from active MatchPlayer records
    distance_km: float | None = None   # Populated in discovery responses only
    host: UserSummaryResponse

    model_config = {"from_attributes": True}


# ─── Match Detail (full single match view) ───────────────────────────────────
class MatchDetailResponse(BaseModel):
    """
    Full match detail — returned when viewing a single match.
    Includes host info and participant list.
    """
    id: uuid.UUID
    title: str
    description: str | None
    sport: SportType
    skill_level: SkillLevel
    status: MatchStatus
    scheduled_at: datetime
    duration_minutes: int
    facility_address: str
    location_name: str | None
    latitude: float | None
    longitude: float | None
    max_players: int
    current_players: int = 0
    host: UserSummaryResponse
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Match Player Response ────────────────────────────────────────────────────
class MatchPlayerResponse(BaseModel):
    """Represents a participant in a match."""
    user: UserSummaryResponse
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}
