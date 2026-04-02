import uuid

from sqlalchemy import ForeignKey, String, Text, Enum as SAEnum, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin
from app.models.enums import SupportRequestStatus


class SupportRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "support_requests"
    __table_args__ = (
        Index("ix_support_requests_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SupportRequestStatus] = mapped_column(
        SAEnum(SupportRequestStatus, name="support_request_status"),
        default=SupportRequestStatus.OPEN,
        server_default=text("'OPEN'"),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="support_requests")

    def __repr__(self) -> str:
        return f"<SupportRequest id={self.id} user={self.user_id} status={self.status}>"
