"""allow multiple profile reviews

Revision ID: b2c6a4f18d7e
Revises: a7b1f9d92c4e
Create Date: 2026-04-24 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b2c6a4f18d7e"
down_revision: Union[str, None] = "a7b1f9d92c4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_profile_review_per_user_pair", table_name="reviews")


def downgrade() -> None:
    op.create_index(
        "uq_profile_review_per_user_pair",
        "reviews",
        ["reviewer_id", "reviewee_id"],
        unique=True,
        postgresql_where="match_id IS NULL",
    )
