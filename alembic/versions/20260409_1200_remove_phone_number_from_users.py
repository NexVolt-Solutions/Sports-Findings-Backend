"""remove phone number from users

Revision ID: 20260409_1200
Revises: fff7e3f6c1a6
Create Date: 2026-04-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260409_1200"
down_revision: Union[str, None] = "fff7e3f6c1a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("phone_number")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("phone_number", sa.String(length=20), nullable=True))
        batch_op.create_check_constraint(
            "ck_users_phone_number_length",
            "phone_number IS NULL OR length(btrim(phone_number)) >= 7",
        )
        batch_op.create_unique_constraint("uq_users_phone_number", ["phone_number"])
