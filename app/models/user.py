import uuid
from sqlalchemy import (
    String,
    Boolean,
    Float,
    Integer,
    ForeignKey,
    Enum as SAEnum,
    CheckConstraint,
    UniqueConstraint,
    text,
    DateTime,
)
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin
from app.models.enums import UserStatus, SportType, SkillLevel


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("avg_rating >= 0 AND avg_rating <= 5", name="ck_users_avg_rating_range"),
        CheckConstraint("total_games_played >= 0", name="ck_users_total_games_played_non_negative"),
        CheckConstraint("length(btrim(full_name)) >= 2", name="ck_users_full_name_not_blank"),
    )

    # ─── Identity ─────────────────────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    hashed_password: Mapped[str | None] = mapped_column(
        String, nullable=True  # Null for Google OAuth users
    )
    google_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True
    )

    # ─── Profile ──────────────────────────────────────────────────────────────
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)

    # ─── Stats ────────────────────────────────────────────────────────────────
    avg_rating: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        server_default=text("0"),
        nullable=False,
    )
    total_games_played: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )

    # ─── Account Status ───────────────────────────────────────────────────────
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"),
        default=UserStatus.PENDING_VERIFICATION,
        server_default=text("'PENDING_VERIFICATION'"),
        nullable=False,
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    terms_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    email_verification_otp: Mapped[str | None] = mapped_column(
        String(6),
        nullable=True,
    )
    email_verification_otp_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    password_reset_otp: Mapped[str | None] = mapped_column(
        String(6),
        nullable=True,
    )
    password_reset_otp_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    sports: Mapped[list["UserSport"]] = relationship(
        "UserSport", back_populates="user", cascade="all, delete-orphan"
    )
    hosted_matches: Mapped[list["Match"]] = relationship(
        "Match", back_populates="host", foreign_keys="Match.host_id"
    )
    match_participations: Mapped[list["MatchPlayer"]] = relationship(
        "MatchPlayer", back_populates="user", cascade="all, delete-orphan"
    )
    reviews_given: Mapped[list["Review"]] = relationship(
        "Review", back_populates="reviewer", foreign_keys="Review.reviewer_id"
    )
    reviews_received: Mapped[list["Review"]] = relationship(
        "Review", back_populates="reviewee", foreign_keys="Review.reviewee_id"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    support_requests: Mapped[list["SupportRequest"]] = relationship(
        "SupportRequest", back_populates="user", cascade="all, delete-orphan"
    )
    followers: Mapped[list["Follow"]] = relationship(
        "Follow", back_populates="following_user", foreign_keys="Follow.following_id"
    )
    following: Mapped[list["Follow"]] = relationship(
        "Follow", back_populates="follower_user", foreign_keys="Follow.follower_id"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


class UserSport(UUIDMixin, Base):
    __tablename__ = "user_sports"
    __table_args__ = (
        UniqueConstraint("user_id", "sport", name="uq_user_sport"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sport: Mapped[SportType] = mapped_column(
        SAEnum(SportType, name="sport_type"), nullable=False
    )
    skill_level: Mapped[SkillLevel] = mapped_column(
        SAEnum(SkillLevel, name="skill_level"), nullable=False
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="sports")

    def __repr__(self) -> str:
        return f"<UserSport user_id={self.user_id} sport={self.sport} level={self.skill_level}>"