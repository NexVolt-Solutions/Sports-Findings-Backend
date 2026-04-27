import uuid
from sqlalchemy import Integer, Text, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin


class Review(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # Legacy match-era uniqueness rule. Current profile reviews are stored
        # with match_id=NULL, so repeated profile reviews remain allowed.
        UniqueConstraint("reviewer_id", "reviewee_id", "match_id", name="uq_review_per_match"),
        # Rating must be between 1 and 5
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_rating_range"),
        CheckConstraint("reviewer_id <> reviewee_id", name="ck_review_no_self_review"),
        CheckConstraint(
            "comment IS NULL OR length(btrim(comment)) <= 500",
            name="ck_review_comment_length",
        ),
    )

    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,   # Speeds up "reviews I have written" queries
    )
    reviewee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    reviewer: Mapped["User"] = relationship(
        "User", back_populates="reviews_given", foreign_keys=[reviewer_id]
    )
    reviewee: Mapped["User"] = relationship(
        "User", back_populates="reviews_received", foreign_keys=[reviewee_id]
    )
    match: Mapped["Match | None"] = relationship("Match", back_populates="reviews")

    def __repr__(self) -> str:
        return f"<Review id={self.id} rating={self.rating} reviewer={self.reviewer_id}>"
