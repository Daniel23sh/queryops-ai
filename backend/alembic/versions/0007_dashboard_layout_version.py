"""dashboard layout version

Revision ID: 0007_dashboard_layout_version
Revises: 0006_query_runtime_role
Create Date: 2026-07-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0007_dashboard_layout_version"
down_revision: Union[str, None] = "0006_query_runtime_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dashboards",
        sa.Column(
            "layout_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("dashboards", "layout_version")
