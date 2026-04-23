"""make review match optional

Revision ID: 4f2d0bb2f3b1
Revises: 20260416_1030_add_password_reset_otp_verified
Create Date: 2026-04-23 18:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4f2d0bb2f3b1"
down_revision: Union[str, None] = "20260416_1030_add_password_reset_otp_verified"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("reviews", "match_id", existing_type=sa.UUID(), nullable=True)
    op.create_index(
        "uq_profile_review_per_user_pair",
        "reviews",
        ["reviewer_id", "reviewee_id"],
        unique=True,
        postgresql_where=sa.text("match_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_profile_review_per_user_pair", table_name="reviews")
    op.execute("DELETE FROM reviews WHERE match_id IS NULL")
    op.alter_column("reviews", "match_id", existing_type=sa.UUID(), nullable=False)
