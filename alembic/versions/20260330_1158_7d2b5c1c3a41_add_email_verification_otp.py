"""add email verification otp fields

Revision ID: 7d2b5c1c3a41
Revises: fff7e3f6c1a6
Create Date: 2026-03-30 11:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7d2b5c1c3a41"
down_revision: Union[str, None] = "fff7e3f6c1a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verification_otp", sa.String(length=6), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verification_otp_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verification_otp_expires_at")
    op.drop_column("users", "email_verification_otp")
