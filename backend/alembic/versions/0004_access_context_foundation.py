"""access context foundation

Revision ID: 0004_access_context_foundation
Revises: 0003_it_operations_domain_schema
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0004_access_context_foundation"
down_revision: Union[str, None] = "0003_it_operations_domain_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=128), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("is_system_scope", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_type", "scope_key", name="uq_access_scopes_type_key"),
    )
    op.create_index("ix_access_scopes_department_id", "access_scopes", ["department_id"])
    op.create_index("ix_access_scopes_scope_type", "access_scopes", ["scope_type"])

    op.create_table(
        "user_access_scopes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("access_level", sa.String(length=32), server_default="read", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["scope_id"], ["access_scopes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "scope_id"),
    )
    op.create_index("ix_user_access_scopes_scope_id", "user_access_scopes", ["scope_id"])
    op.create_index("ix_user_access_scopes_user_id", "user_access_scopes", ["user_id"])

    op.create_table(
        "data_resources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=128), nullable=False),
        sa.Column("schema_name", sa.String(length=128), nullable=True),
        sa.Column("table_name", sa.String(length=128), nullable=False),
        sa.Column("column_name", sa.String(length=128), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("sensitivity_level", sa.String(length=64), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=True),
        sa.Column("scope_column", sa.String(length=128), nullable=True),
        sa.Column("is_queryable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_exportable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("llm_exposure_level", sa.String(length=64), nullable=False),
        sa.Column("resource_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_resources_domain", "data_resources", ["domain"])
    op.create_index("ix_data_resources_scope_type", "data_resources", ["scope_type"])
    op.create_index("ix_data_resources_table_name", "data_resources", ["table_name"])

    with op.batch_alter_table("role_upgrade_requests") as batch_op:
        batch_op.add_column(sa.Column("requested_scope_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("requested_scope_type", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("requested_scope_key", sa.String(length=128), nullable=True))
        batch_op.create_foreign_key(
            "fk_role_upgrade_requests_requested_scope_id_access_scopes",
            "access_scopes",
            ["requested_scope_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_role_upgrade_requests_requested_scope_id",
            ["requested_scope_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("role_upgrade_requests") as batch_op:
        batch_op.drop_index("ix_role_upgrade_requests_requested_scope_id")
        batch_op.drop_constraint(
            "fk_role_upgrade_requests_requested_scope_id_access_scopes",
            type_="foreignkey",
        )
        batch_op.drop_column("requested_scope_key")
        batch_op.drop_column("requested_scope_type")
        batch_op.drop_column("requested_scope_id")

    op.drop_index("ix_data_resources_table_name", table_name="data_resources")
    op.drop_index("ix_data_resources_scope_type", table_name="data_resources")
    op.drop_index("ix_data_resources_domain", table_name="data_resources")
    op.drop_table("data_resources")

    op.drop_index("ix_user_access_scopes_user_id", table_name="user_access_scopes")
    op.drop_index("ix_user_access_scopes_scope_id", table_name="user_access_scopes")
    op.drop_table("user_access_scopes")

    op.drop_index("ix_access_scopes_scope_type", table_name="access_scopes")
    op.drop_index("ix_access_scopes_department_id", table_name="access_scopes")
    op.drop_table("access_scopes")
