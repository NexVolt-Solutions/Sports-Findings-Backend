from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin


class ContentPage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "content_pages"
    __table_args__ = (
        UniqueConstraint("section", name="uq_content_pages_section"),
    )

    section: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<ContentPage section={self.section}>"
