import uuid
from datetime import datetime
from sqlalchemy import (
    String,
    Integer,
    Float,
    ForeignKey,
    Enum as SAEnum,
    DateTime,
    Text,
    Index,
    CheckConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin
from app.models.enums import SportType, SkillLevel, MatchStatus


class Match(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "matches"
    __table_args__ = (
        # Composite index for discovery queries (sport + status + scheduled_at)
        Index("ix_match_discovery", "sport", "status", "scheduled_at"),
        # Spatial index for lat/lng proximity queries
        Index("ix_match_location", "latitude", "longitude"),
        CheckConstraint("max_players >= 2 AND max_players <= 50", name="ck_matches_max_players"),
        CheckConstraint(
            "duration_minutes >= 10 AND duration_minutes <= 480",
            name="ck_matches_duration_minutes",
        ),
        CheckConstraint("length(btrim(title)) >= 3", name="ck_matches_title_not_blank"),
        CheckConstraint(
            "length(btrim(facility_address)) >= 5",
            name="ck_matches_facility_address_not_blank",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_matches_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_matches_longitude_range",
        ),
    )

    # ─── Host ─────────────────────────────────────────────────────────────────
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ─── Match Info ───────────────────────────────────────────────────────────
    sport: Mapped[SportType] = mapped_column(
        SAEnum(SportType, name="sport_type"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Location ─────────────────────────────────────────────────────────────
    facility_address: Mapped[str] = mapped_column(
        String(255), nullable=False  # Raw address entered by user
    )
    location_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True   # Resolved label from geocoding
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ─── Schedule ─────────────────────────────────────────────────────────────
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    # ─── Capacity & Skill ─────────────────────────────────────────────────────
    max_players: Mapped[int] = mapped_column(Integer, nullable=False)
    skill_level: Mapped[SkillLevel] = mapped_column(
        SAEnum(SkillLevel, name="skill_level"),
        nullable=False,
        index=True,
    )

    # ─── Status ───────────────────────────────────────────────────────────────
    status: Mapped[MatchStatus] = mapped_column(
        SAEnum(MatchStatus, name="match_status"),
        default=MatchStatus.OPEN,
        server_default=text("'OPEN'"),
        nullable=False,
        index=True,
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    host: Mapped["User"] = relationship(
        "User", back_populates="hosted_matches", foreign_keys=[host_id]
    )
    players: Mapped[list["MatchPlayer"]] = relationship(
        "MatchPlayer", back_populates="match", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="match", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(
        "Review", back_populates="match", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Match id={self.id} title={self.title} status={self.status}>"
