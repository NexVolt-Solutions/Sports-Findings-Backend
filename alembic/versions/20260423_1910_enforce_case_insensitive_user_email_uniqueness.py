"""enforce case insensitive user email uniqueness

Revision ID: a7b1f9d92c4e
Revises: 4f2d0bb2f3b1
Create Date: 2026-04-23 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b1f9d92c4e"
down_revision: Union[str, None] = "4f2d0bb2f3b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    duplicate_rows = conn.execute(
        sa.text(
            """
            SELECT lower(email) AS normalized_email, COUNT(*) AS duplicates
            FROM users
            GROUP BY lower(email)
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    if duplicate_rows:
        duplicate_list = ", ".join(row.normalized_email for row in duplicate_rows)
        raise RuntimeError(
            "Cannot enforce case-insensitive unique emails until duplicates are cleaned up: "
            f"{duplicate_list}"
        )

    conn.execute(sa.text("UPDATE users SET email = lower(btrim(email))"))
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
