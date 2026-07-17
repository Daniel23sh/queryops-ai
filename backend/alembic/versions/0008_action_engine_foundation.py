"""action engine foundation

Revision ID: 0008_action_engine_foundation
Revises: 0007_dashboard_layout_version
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008_action_engine_foundation"
down_revision: Union[str, None] = "0007_dashboard_layout_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTION_REQUEST_STATUSES = (
    "draft_preview",
    "pending_approval",
    "approved_executing",
    "completed",
    "rejected",
    "failed",
    "cancelled",
    "expired",
)
ACTION_PRIORITIES = ("normal", "high", "urgent")
SUPPORTED_ACTION_TYPES = ("reclaim_unused_license", "disable_inactive_user")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "cancelled", "expired")


def upgrade() -> None:
    op.create_table(
        "action_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("requested_by_app_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_query_run_id", sa.Uuid(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("scope_type", sa.String(length=64), nullable=True),
        sa.Column("scope_key", sa.String(length=128), nullable=True),
        sa.Column("access_context_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("access_decision_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("preview_json", sa.JSON(), nullable=False),
        sa.Column("policy_flags_json", sa.JSON(), nullable=False),
        sa.Column("skipped_records_json", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="draft_preview",
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.String(length=16),
            server_default="normal",
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "requires_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("record_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("failure_reason_user_safe", sa.Text(), nullable=True),
        sa.Column("failure_reason_internal", sa.Text(), nullable=True),
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
        sa.Column("preview_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preview_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action_type in (" + ", ".join(f"'{value}'" for value in SUPPORTED_ACTION_TYPES) + ")",
            name="ck_action_requests_action_type",
        ),
        sa.CheckConstraint(
            "status in (" + ", ".join(f"'{value}'" for value in ACTION_REQUEST_STATUSES) + ")",
            name="ck_action_requests_status",
        ),
        sa.CheckConstraint(
            "priority in (" + ", ".join(f"'{value}'" for value in ACTION_PRIORITIES) + ")",
            name="ck_action_requests_priority",
        ),
        sa.CheckConstraint("record_count >= 0", name="ck_action_requests_record_count"),
        sa.CheckConstraint("skipped_count >= 0", name="ck_action_requests_skipped_count"),
        sa.ForeignKeyConstraint(
            ["requested_by_app_user_id"],
            ["app_users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_query_run_id"],
            ["query_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["scope_id"],
            ["access_scopes.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_action_requests_idempotency_key"),
    )
    op.create_index(
        "ix_action_requests_requested_by_app_user_id",
        "action_requests",
        ["requested_by_app_user_id"],
    )
    op.create_index("ix_action_requests_status", "action_requests", ["status"])
    op.create_index(
        "ix_action_requests_scope_type_scope_key",
        "action_requests",
        ["scope_type", "scope_key"],
    )
    op.create_index("ix_action_requests_expires_at", "action_requests", ["expires_at"])

    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.add_column(sa.Column("action_request_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("required_approver_role", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.drop_constraint("ck_approval_requests_status", type_="check")
        batch_op.create_check_constraint(
            "ck_approval_requests_status",
            "status in (" + ", ".join(f"'{value}'" for value in APPROVAL_STATUSES) + ")",
        )
        batch_op.create_foreign_key(
            "fk_approval_requests_action_request_id_action_requests",
            "action_requests",
            ["action_request_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_approval_requests_action_request_id",
            ["action_request_id"],
        )

    with op.batch_alter_table("app_audit_logs") as batch_op:
        batch_op.add_column(sa.Column("action_request_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("approval_request_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("department_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("scope_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("scope_type", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("scope_key", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("severity", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("before_state_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("after_state_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("self_approved", sa.Boolean(), nullable=True))
        batch_op.create_foreign_key(
            "fk_app_audit_logs_action_request_id_action_requests",
            "action_requests",
            ["action_request_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_app_audit_logs_approval_request_id_approval_requests",
            "approval_requests",
            ["approval_request_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_app_audit_logs_department_id_departments",
            "departments",
            ["department_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_app_audit_logs_scope_id_access_scopes",
            "access_scopes",
            ["scope_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_app_audit_logs_action_request_id",
        "app_audit_logs",
        ["action_request_id"],
    )
    op.create_index(
        "ix_app_audit_logs_approval_request_id",
        "app_audit_logs",
        ["approval_request_id"],
    )
    op.create_index(
        "ix_app_audit_logs_department_id",
        "app_audit_logs",
        ["department_id"],
    )
    op.create_index("ix_app_audit_logs_scope_id", "app_audit_logs", ["scope_id"])
    op.create_index(
        "ix_app_audit_logs_scope_type_scope_key",
        "app_audit_logs",
        ["scope_type", "scope_key"],
    )

    with op.batch_alter_table("it_audit_events") as batch_op:
        batch_op.add_column(sa.Column("actor_app_user_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_it_audit_events_actor_app_user_id_app_users",
            "app_users",
            ["actor_app_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_it_audit_events_actor_app_user_id",
        "it_audit_events",
        ["actor_app_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_it_audit_events_actor_app_user_id", table_name="it_audit_events")
    with op.batch_alter_table("it_audit_events") as batch_op:
        batch_op.drop_constraint(
            "fk_it_audit_events_actor_app_user_id_app_users",
            type_="foreignkey",
        )
        batch_op.drop_column("actor_app_user_id")

    op.drop_index("ix_app_audit_logs_scope_type_scope_key", table_name="app_audit_logs")
    op.drop_index("ix_app_audit_logs_scope_id", table_name="app_audit_logs")
    op.drop_index("ix_app_audit_logs_department_id", table_name="app_audit_logs")
    op.drop_index("ix_app_audit_logs_approval_request_id", table_name="app_audit_logs")
    op.drop_index("ix_app_audit_logs_action_request_id", table_name="app_audit_logs")
    with op.batch_alter_table("app_audit_logs") as batch_op:
        batch_op.drop_constraint(
            "fk_app_audit_logs_scope_id_access_scopes",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_app_audit_logs_department_id_departments",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_app_audit_logs_approval_request_id_approval_requests",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_app_audit_logs_action_request_id_action_requests",
            type_="foreignkey",
        )
        batch_op.drop_column("self_approved")
        batch_op.drop_column("after_state_json")
        batch_op.drop_column("before_state_json")
        batch_op.drop_column("severity")
        batch_op.drop_column("scope_key")
        batch_op.drop_column("scope_type")
        batch_op.drop_column("scope_id")
        batch_op.drop_column("department_id")
        batch_op.drop_column("approval_request_id")
        batch_op.drop_column("action_request_id")

    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.drop_constraint(
            "uq_approval_requests_action_request_id",
            type_="unique",
        )
        batch_op.drop_constraint(
            "fk_approval_requests_action_request_id_action_requests",
            type_="foreignkey",
        )
        batch_op.drop_constraint("ck_approval_requests_status", type_="check")
        batch_op.create_check_constraint(
            "ck_approval_requests_status",
            "status in ('pending', 'approved', 'rejected', 'cancelled')",
        )
        batch_op.drop_column("expires_at")
        batch_op.drop_column("required_approver_role")
        batch_op.drop_column("action_request_id")

    op.drop_index("ix_action_requests_expires_at", table_name="action_requests")
    op.drop_index("ix_action_requests_scope_type_scope_key", table_name="action_requests")
    op.drop_index("ix_action_requests_status", table_name="action_requests")
    op.drop_index(
        "ix_action_requests_requested_by_app_user_id",
        table_name="action_requests",
    )
    op.drop_table("action_requests")
