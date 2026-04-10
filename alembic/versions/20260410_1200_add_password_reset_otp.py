"""add password reset otp fields

Revision ID: 20260410_1200_add_password_reset_otp
Revises: 20260409_1200_remove_phone_number_from_users
Create Date: 2026-04-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260410_1200_add_password_reset_otp'
down_revision: Union[str, None] = '20260409_1200_remove_phone_number_from_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add password reset OTP fields
    op.add_column('users', sa.Column('password_reset_otp', sa.String(6), nullable=True))
    op.add_column('users', sa.Column('password_reset_otp_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove password reset OTP fields
    op.drop_column('users', 'password_reset_otp_expires_at')
    op.drop_column('users', 'password_reset_otp')