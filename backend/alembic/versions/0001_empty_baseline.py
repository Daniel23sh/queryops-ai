"""empty baseline

Revision ID: 0001_empty_baseline
Revises:
Create Date: 2026-06-28
"""

from typing import Sequence, Union


revision: str = "0001_empty_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
