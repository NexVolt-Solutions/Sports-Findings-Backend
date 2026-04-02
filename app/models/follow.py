import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (
        CheckConstraint("follower_id <> following_id", name="ck_follow_no_self_follow"),
    )

    follower_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    following_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        index=True,   # Speeds up "who is this user following" queries
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    follower_user: Mapped["User"] = relationship(
        "User", back_populates="following", foreign_keys=[follower_id]
    )
    following_user: Mapped["User"] = relationship(
        "User", back_populates="followers", foreign_keys=[following_id]
    )

    def __repr__(self) -> str:
        return f"<Follow follower={self.follower_id} following={self.following_id}>"
