"""merge heads

Revision ID: 2b3b8dcebf93
Revises: b8e2a1c4d9f0, 20260409_1200
Create Date: 2026-04-09 11:44:00.000000
"""
from typing import Sequence, Union

revision: str = '2b3b8dcebf93'
down_revision: Union[str, Sequence[str], None] = ('b8e2a1c4d9f0', '20260409_1200')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
