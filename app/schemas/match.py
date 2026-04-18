import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, field_validator, model_validator

from app.models.enums import MatchStatus, SkillLevel, SportType
from app.schemas.user import UserSummaryResponse


class CreateMatchRequest(BaseModel):
    title: str
    description: str | None = None
    sport: SportType
    facility_address: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    scheduled_at: datetime | None = None
    date: str | None = None
    time: str | None = None
    duration_minutes: int | None = None
    max_players: int
    skill_level: SkillLevel = SkillLevel.INTERMEDIATE

    @model_validator(mode="after")
    def normalize_ui_fields(self) -> "CreateMatchRequest":
        if not self.facility_address and self.location:
            self.facility_address = self.location.strip()

        if self.scheduled_at is None:
            if not self.date or not self.time:
                raise ValueError("Provide either scheduled_at or both date and time")

            try:
                parsed = datetime.fromisoformat(f"{self.date.strip()}T{self.time.strip()}")
            except ValueError as exc:
                raise ValueError("Invalid date/time format. Use YYYY-MM-DD and HH:MM") from exc

            self.scheduled_at = parsed.replace(tzinfo=timezone.utc)

        if self.duration_minutes is None:
            raise ValueError("duration_minutes is required")

        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")

        return self

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Title must be at least 3 characters")
        if len(value) > 150:
            raise ValueError("Title must be at most 150 characters")
        return value

    @field_validator("max_players")
    @classmethod
    def validate_max_players(cls, value: int) -> int:
        if value < 2:
            raise ValueError("A match must allow at least 2 players")
        if value > 50:
            raise ValueError("Maximum player limit is 50")
        return value

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, value: int) -> int:
        if value < 10:
            raise ValueError("Match duration must be at least 10 minutes")
        if value > 480:
            raise ValueError("Match duration cannot exceed 8 hours")
        return value

    @field_validator("facility_address")
    @classmethod
    def validate_address(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Please enter a valid facility address")
        return value

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, value: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value <= now:
            raise ValueError("Match must be scheduled in the future")
        return value


class UpdateMatchRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    sport: SportType | None = None
    facility_address: str | None = None
    location: str | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    max_players: int | None = None
    skill_level: SkillLevel | None = None

    @model_validator(mode="after")
    def normalize_location_fields(self) -> "UpdateMatchRequest":
        if self.facility_address is None and self.location is not None:
            self.facility_address = self.location.strip()

        if self.location_name is None and self.location is not None:
            self.location_name = self.location.strip()

        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")

        return self

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Title must be at least 3 characters")
        if len(value) > 150:
            raise ValueError("Title must be at most 150 characters")
        return value

    @field_validator("max_players")
    @classmethod
    def validate_max_players(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 2:
            raise ValueError("A match must allow at least 2 players")
        if value > 50:
            raise ValueError("Maximum player limit is 50")
        return value

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 10:
            raise ValueError("Match duration must be at least 10 minutes")
        if value > 480:
            raise ValueError("Match duration cannot exceed 8 hours")
        return value

    @field_validator("facility_address")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Please enter a valid facility address")
        return value

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        now = datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value <= now:
            raise ValueError("Match must be scheduled in the future")
        return value


class MatchStatusUpdateRequest(BaseModel):
    status: MatchStatus


class MatchSummaryResponse(BaseModel):
    id: uuid.UUID
    title: str
    sport: SportType
    skill_level: SkillLevel
    status: MatchStatus
    scheduled_at: datetime
    duration_minutes: int
    scheduled_date: str
    scheduled_time: str
    location_name: str | None
    location: str
    facility_address: str
    latitude: float | None
    longitude: float | None
    max_players: int
    current_players: int = 0
    distance_km: float | None = None
    host: UserSummaryResponse

    model_config = {"from_attributes": True}


class MatchDetailResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    sport: SportType
    skill_level: SkillLevel
    status: MatchStatus
    scheduled_at: datetime
    duration_minutes: int
    scheduled_date: str
    scheduled_time: str
    facility_address: str
    location: str
    latitude: float | None
    longitude: float | None
    max_players: int
    current_players: int = 0
    host: UserSummaryResponse
    host_games_played: int = 0  # Number of matches the host has played
    participants: list["MatchPlayerResponse"] = []  # List of all participating players
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchPlayerResponse(BaseModel):
    user: UserSummaryResponse
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}
