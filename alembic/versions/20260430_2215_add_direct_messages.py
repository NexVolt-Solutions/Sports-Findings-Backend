"""add direct messages

Revision ID: c4d91aa3ef20
Revises: b2c6a4f18d7e
Create Date: 2026-04-30 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4d91aa3ef20"
down_revision: Union[str, None] = "b2c6a4f18d7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "direct_messages",
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "length(btrim(content)) > 0",
            name="ck_direct_messages_content_not_blank",
        ),
        sa.CheckConstraint(
            "sender_id <> recipient_id",
            name="ck_direct_messages_no_self_message",
        ),
    )
    op.create_index(
        "ix_direct_message_sender_recipient_sent",
        "direct_messages",
        ["sender_id", "recipient_id", "sent_at"],
        unique=False,
    )
    op.create_index(
        "ix_direct_message_recipient_sender_sent",
        "direct_messages",
        ["recipient_id", "sender_id", "sent_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_direct_messages_sender_id"),
        "direct_messages",
        ["sender_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_direct_messages_recipient_id"),
        "direct_messages",
        ["recipient_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_direct_messages_recipient_id"), table_name="direct_messages")
    op.drop_index(op.f("ix_direct_messages_sender_id"), table_name="direct_messages")
    op.drop_index("ix_direct_message_recipient_sender_sent", table_name="direct_messages")
    op.drop_index("ix_direct_message_sender_recipient_sent", table_name="direct_messages")
    op.drop_table("direct_messages")
