import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin


class DirectMessage(UUIDMixin, Base):
    __tablename__ = "direct_messages"
    __table_args__ = (
        Index("ix_direct_message_sender_recipient_sent", "sender_id", "recipient_id", "sent_at"),
        Index("ix_direct_message_recipient_sender_sent", "recipient_id", "sender_id", "sent_at"),
        CheckConstraint(
            "length(btrim(content)) > 0",
            name="ck_direct_messages_content_not_blank",
        ),
        CheckConstraint(
            "sender_id <> recipient_id",
            name="ck_direct_messages_no_self_message",
        ),
    )

    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    sender: Mapped["User"] = relationship(
        "User",
        back_populates="direct_messages_sent",
        foreign_keys=[sender_id],
    )
    recipient: Mapped["User"] = relationship(
        "User",
        back_populates="direct_messages_received",
        foreign_keys=[recipient_id],
    )

    def __repr__(self) -> str:
        return (
            f"<DirectMessage id={self.id} sender={self.sender_id} "
            f"recipient={self.recipient_id}>"
        )
