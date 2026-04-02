import uuid
from datetime import datetime, timezone
from sqlalchemy import Text, DateTime, ForeignKey, Index, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin


class Message(UUIDMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_message_match_sent", "match_id", "sent_at"),
        CheckConstraint("length(btrim(content)) > 0", name="ck_messages_content_not_blank"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
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

    # ─── Relationships ────────────────────────────────────────────────────────
    match: Mapped["Match"] = relationship("Match", back_populates="messages")
    sender: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Message id={self.id} match={self.match_id} sender={self.sender_id}>"
