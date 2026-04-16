"""add password reset otp verified flag

Revision ID: 20260416_1030_add_password_reset_otp_verified
Revises: 20260410_1200_add_password_reset_otp
Create Date: 2026-04-16 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260416_1030_add_password_reset_otp_verified"
down_revision: Union[str, None] = "20260410_1200_add_password_reset_otp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_reset_otp_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "password_reset_otp_verified")
