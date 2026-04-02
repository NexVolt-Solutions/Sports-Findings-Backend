import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Enum as SAEnum, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.enums import MatchPlayerRole, MatchPlayerStatus


class MatchPlayer(Base):
    __tablename__ = "match_players"

    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        index=True,
    )
    role: Mapped[MatchPlayerRole] = mapped_column(
        SAEnum(MatchPlayerRole, name="match_player_role"),
        default=MatchPlayerRole.PLAYER,
        server_default=text("'PLAYER'"),
        nullable=False,
    )
    status: Mapped[MatchPlayerStatus] = mapped_column(
        SAEnum(MatchPlayerStatus, name="match_player_status"),
        default=MatchPlayerStatus.ACTIVE,
        server_default=text("'ACTIVE'"),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    match: Mapped["Match"] = relationship("Match", back_populates="players")
    user: Mapped["User"] = relationship("User", back_populates="match_participations")

    def __repr__(self) -> str:
        return f"<MatchPlayer match={self.match_id} user={self.user_id} role={self.role}>"
