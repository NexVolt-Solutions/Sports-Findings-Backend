import uuid
from sqlalchemy import Boolean, ForeignKey, Enum as SAEnum, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin
from app.models.enums import NotificationType


class Notification(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # Index to quickly fetch unread notifications for a user
        Index("ix_notification_user_read", "user_id", "is_read"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type"),
        nullable=False,
    )
    # JSONB allows flexible payload per notification type
    # e.g. { "match_id": "uuid", "match_title": "Evening Basketball" }
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification id={self.id} type={self.type} user={self.user_id} read={self.is_read}>"
