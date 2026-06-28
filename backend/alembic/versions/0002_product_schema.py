"""product schema

Revision ID: 0002_product_schema
Revises: 0001_empty_baseline
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002_product_schema"
down_revision: Union[str, None] = "0001_empty_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system_role", sa.Boolean(), server_default="false", nullable=False),
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
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("key"),
    )
    op.create_table(
        "app_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("auth_provider", sa.String(length=32), server_default="demo", nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
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
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('active', 'invited', 'disabled')",
            name="ck_app_users_status",
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "auth_provider",
            "provider_user_id",
            name="uq_app_users_auth_provider_provider_user_id",
        ),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_app_users_department_id", "app_users", ["department_id"])
    op.create_index("ix_app_users_role_id", "app_users", ["role_id"])

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.Column("effect", sa.String(length=16), server_default="allow", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("granted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("effect in ('allow', 'deny')", name="ck_user_permissions_effect"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "permission_id",
            name="uq_user_permissions_user_id_permission_id",
        ),
    )
    op.create_index(
        "ix_user_permissions_granted_by_user_id",
        "user_permissions",
        ["granted_by_user_id"],
    )
    op.create_table(
        "role_upgrade_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requester_user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_role_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_role_upgrade_requests_status",
        ),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_role_upgrade_requests_requested_role_id",
        "role_upgrade_requests",
        ["requested_role_id"],
    )
    op.create_index(
        "ix_role_upgrade_requests_requester_user_id",
        "role_upgrade_requests",
        ["requester_user_id"],
    )
    op.create_index(
        "ix_role_upgrade_requests_status",
        "role_upgrade_requests",
        ["status"],
    )

    op.create_table(
        "dashboards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "visibility_scope",
            sa.String(length=32),
            server_default="personal",
            nullable=False,
        ),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
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
        sa.CheckConstraint(
            "visibility_scope in ('personal', 'department', 'global')",
            name="ck_dashboards_visibility_scope",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dashboards_department_id", "dashboards", ["department_id"])
    op.create_index("ix_dashboards_owner_user_id", "dashboards", ["owner_user_id"])
    op.create_index("ix_dashboards_visibility_scope", "dashboards", ["visibility_scope"])

    op.create_table(
        "saved_queries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("natural_language_question", sa.Text(), nullable=False),
        sa.Column("generated_sql", sa.Text(), nullable=True),
        sa.Column(
            "visibility_scope",
            sa.String(length=32),
            server_default="personal",
            nullable=False,
        ),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("result_schema", sa.JSON(), nullable=True),
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
        sa.CheckConstraint(
            "visibility_scope in ('personal', 'department', 'global')",
            name="ck_saved_queries_visibility_scope",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_queries_department_id", "saved_queries", ["department_id"])
    op.create_index("ix_saved_queries_owner_user_id", "saved_queries", ["owner_user_id"])
    op.create_index("ix_saved_queries_visibility_scope", "saved_queries", ["visibility_scope"])

    op.create_table(
        "query_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("saved_query_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("natural_language_question", sa.Text(), nullable=True),
        sa.Column("generated_sql", sa.Text(), nullable=True),
        sa.Column("executed_sql", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("query_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_query_runs_status",
        ),
        sa.ForeignKeyConstraint(["saved_query_id"], ["saved_queries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_runs_saved_query_id", "query_runs", ["saved_query_id"])
    op.create_index("ix_query_runs_status", "query_runs", ["status"])
    op.create_index("ix_query_runs_user_id", "query_runs", ["user_id"])

    op.create_table(
        "dashboard_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dashboard_id", sa.Uuid(), nullable=False),
        sa.Column("saved_query_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("card_type", sa.String(length=32), server_default="table", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["dashboard_id"], ["dashboards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["saved_query_id"], ["saved_queries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dashboard_cards_dashboard_id_position",
        "dashboard_cards",
        ["dashboard_id", "position"],
    )
    op.create_index("ix_dashboard_cards_saved_query_id", "dashboard_cards", ["saved_query_id"])

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requester_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("query_run_id", sa.Uuid(), nullable=True),
        sa.Column("request_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("policy_snapshot", sa.JSON(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_approval_requests_status",
        ),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["query_run_id"], ["query_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_requests_decided_by_user_id",
        "approval_requests",
        ["decided_by_user_id"],
    )
    op.create_index("ix_approval_requests_query_run_id", "approval_requests", ["query_run_id"])
    op.create_index(
        "ix_approval_requests_requester_user_id",
        "approval_requests",
        ["requester_user_id"],
    )
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="unread", nullable=False),
        sa.Column("related_resource_type", sa.String(length=64), nullable=True),
        sa.Column("related_resource_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('unread', 'read', 'archived')",
            name="ck_notifications_status",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_actor_user_id", "notifications", ["actor_user_id"])
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("run_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_evaluation_runs_status",
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_runs_requested_by_user_id",
        "evaluation_runs",
        ["requested_by_user_id"],
    )
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("query_run_id", sa.Uuid(), nullable=True),
        sa.Column("case_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("expected_output", sa.JSON(), nullable=True),
        sa.Column("actual_output", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('succeeded', 'failed', 'skipped')",
            name="ck_evaluation_results_status",
        ),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_run_id"], ["query_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_results_evaluation_run_id",
        "evaluation_results",
        ["evaluation_run_id"],
    )
    op.create_index("ix_evaluation_results_query_run_id", "evaluation_results", ["query_run_id"])
    op.create_index("ix_evaluation_results_status", "evaluation_results", ["status"])

    op.create_table(
        "app_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("audit_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_audit_logs_actor_user_id", "app_audit_logs", ["actor_user_id"])
    op.create_index("ix_app_audit_logs_entity_type_entity_id", "app_audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_app_audit_logs_event_type", "app_audit_logs", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_app_audit_logs_event_type", table_name="app_audit_logs")
    op.drop_index("ix_app_audit_logs_entity_type_entity_id", table_name="app_audit_logs")
    op.drop_index("ix_app_audit_logs_actor_user_id", table_name="app_audit_logs")
    op.drop_table("app_audit_logs")

    op.drop_index("ix_evaluation_results_status", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_query_run_id", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_evaluation_run_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")

    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_requested_by_user_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")

    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
    op.drop_index("ix_notifications_actor_user_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_requester_user_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_query_run_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_decided_by_user_id", table_name="approval_requests")
    op.drop_table("approval_requests")

    op.drop_index("ix_dashboard_cards_saved_query_id", table_name="dashboard_cards")
    op.drop_index("ix_dashboard_cards_dashboard_id_position", table_name="dashboard_cards")
    op.drop_table("dashboard_cards")

    op.drop_index("ix_query_runs_user_id", table_name="query_runs")
    op.drop_index("ix_query_runs_status", table_name="query_runs")
    op.drop_index("ix_query_runs_saved_query_id", table_name="query_runs")
    op.drop_table("query_runs")

    op.drop_index("ix_saved_queries_visibility_scope", table_name="saved_queries")
    op.drop_index("ix_saved_queries_owner_user_id", table_name="saved_queries")
    op.drop_index("ix_saved_queries_department_id", table_name="saved_queries")
    op.drop_table("saved_queries")

    op.drop_index("ix_dashboards_visibility_scope", table_name="dashboards")
    op.drop_index("ix_dashboards_owner_user_id", table_name="dashboards")
    op.drop_index("ix_dashboards_department_id", table_name="dashboards")
    op.drop_table("dashboards")

    op.drop_index("ix_role_upgrade_requests_status", table_name="role_upgrade_requests")
    op.drop_index(
        "ix_role_upgrade_requests_requester_user_id",
        table_name="role_upgrade_requests",
    )
    op.drop_index(
        "ix_role_upgrade_requests_requested_role_id",
        table_name="role_upgrade_requests",
    )
    op.drop_table("role_upgrade_requests")

    op.drop_index("ix_user_permissions_granted_by_user_id", table_name="user_permissions")
    op.drop_table("user_permissions")
    op.drop_table("role_permissions")

    op.drop_index("ix_app_users_role_id", table_name="app_users")
    op.drop_index("ix_app_users_department_id", table_name="app_users")
    op.drop_table("app_users")

    op.drop_table("permissions")
    op.drop_table("roles")
