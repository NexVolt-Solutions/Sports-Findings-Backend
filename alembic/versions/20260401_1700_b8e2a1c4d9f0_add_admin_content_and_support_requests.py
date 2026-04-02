"""add admin content pages and support requests

Revision ID: b8e2a1c4d9f0
Revises: 7d2b5c1c3a41
Create Date: 2026-04-01 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e2a1c4d9f0"
down_revision: Union[str, None] = "7d2b5c1c3a41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_pages",
        sa.Column("section", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("section", name="uq_content_pages_section"),
    )
    op.create_index(op.f("ix_content_pages_section"), "content_pages", ["section"], unique=False)

    op.create_table(
        "support_requests",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("OPEN", "RESOLVED", name="support_request_status"),
            server_default=sa.text("'OPEN'"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_requests_user_status", "support_requests", ["user_id", "status"], unique=False)
    op.create_index(op.f("ix_support_requests_user_id"), "support_requests", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_support_requests_user_id"), table_name="support_requests")
    op.drop_index("ix_support_requests_user_status", table_name="support_requests")
    op.drop_table("support_requests")
    op.drop_index(op.f("ix_content_pages_section"), table_name="content_pages")
    op.drop_table("content_pages")
    op.execute("DROP TYPE support_request_status")
