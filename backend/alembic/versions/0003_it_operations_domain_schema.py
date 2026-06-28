"""it operations domain schema

Revision ID: 0003_it_operations_domain_schema
Revises: 0002_product_schema
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_it_operations_domain_schema"
down_revision: Union[str, None] = "0002_product_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
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
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "licenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("vendor", sa.String(length=255), nullable=False),
        sa.Column("monthly_cost_usd", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("is_mandatory_default", sa.Boolean(), server_default="false", nullable=False),
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
        sa.UniqueConstraint("vendor", "product_name", name="uq_licenses_vendor_product_name"),
    )
    op.create_table(
        "directory_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_number", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("account_type", sa.String(length=32), server_default="human", nullable=False),
        sa.Column(
            "employee_status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "account_status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
            "account_status in ('active', 'disabled', 'locked')",
            name="ck_directory_users_account_status",
        ),
        sa.CheckConstraint(
            "account_type in ('human', 'service')",
            name="ck_directory_users_account_type",
        ),
        sa.CheckConstraint(
            "employee_status in ('active', 'terminated', 'on_leave')",
            name="ck_directory_users_employee_status",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["manager_id"], ["directory_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("employee_number"),
    )
    op.create_index("ix_directory_users_department_id", "directory_users", ["department_id"])
    op.create_index("ix_directory_users_manager_id", "directory_users", ["manager_id"])

    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("os", sa.String(length=128), nullable=False),
        sa.Column("os_version", sa.String(length=128), nullable=False),
        sa.Column("device_type", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "compliance_status",
            sa.String(length=32),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("encryption_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "antivirus_status",
            sa.String(length=32),
            server_default="unknown",
            nullable=False,
        ),
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
            "antivirus_status in ('healthy', 'outdated', 'missing', 'unknown')",
            name="ck_devices_antivirus_status",
        ),
        sa.CheckConstraint(
            "compliance_status in ('compliant', 'non_compliant', 'unknown')",
            name="ck_devices_compliance_status",
        ),
        sa.CheckConstraint(
            "device_type in ('laptop', 'desktop', 'mobile', 'server')",
            name="ck_devices_device_type",
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["directory_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hostname"),
    )
    op.create_index("ix_devices_assigned_user_id", "devices", ["assigned_user_id"])
    op.create_index("ix_devices_department_id", "devices", ["department_id"])

    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("group_type", sa.String(length=64), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("is_privileged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("risk_level", sa.String(length=32), server_default="low", nullable=False),
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
            "group_type in ('security', 'distribution', 'application', 'admin')",
            name="ck_groups_group_type",
        ),
        sa.CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_groups_risk_level",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_groups_department_id", "groups", ["department_id"])

    op.create_table(
        "license_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("license_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_exception", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("reclaimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reclaimed_by_app_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status in ('active', 'reclaimed', 'suspended')",
            name="ck_license_assignments_status",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["license_id"], ["licenses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reclaimed_by_app_user_id"],
            ["app_users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["directory_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_license_assignments_department_id", "license_assignments", ["department_id"])
    op.create_index("ix_license_assignments_license_id", "license_assignments", ["license_id"])
    op.create_index(
        "ix_license_assignments_reclaimed_by_app_user_id",
        "license_assignments",
        ["reclaimed_by_app_user_id"],
    )
    op.create_index("ix_license_assignments_user_id", "license_assignments", ["user_id"])

    op.create_table(
        "login_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "event_type in ('success', 'failed')",
            name="ck_login_events_event_type",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["directory_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_events_department_id", "login_events", ["department_id"])
    op.create_index("ix_login_events_device_id", "login_events", ["device_id"])
    op.create_index("ix_login_events_occurred_at", "login_events", ["occurred_at"])
    op.create_index("ix_login_events_user_id", "login_events", ["user_id"])

    op.create_table(
        "software_installs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("software_name", sa.String(length=255), nullable=False),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column("version", sa.String(length=128), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_outdated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_unsupported", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("risk_level", sa.String(length=32), server_default="low", nullable=False),
        sa.CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_software_installs_risk_level",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_software_installs_department_id", "software_installs", ["department_id"])
    op.create_index("ix_software_installs_device_id", "software_installs", ["device_id"])

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requester_user_id", sa.Uuid(), nullable=True),
        sa.Column("assignee_user_id", sa.Uuid(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
            "priority in ('low', 'medium', 'high', 'critical')",
            name="ck_support_tickets_priority",
        ),
        sa.CheckConstraint(
            "status in ('open', 'in_progress', 'resolved', 'closed')",
            name="ck_support_tickets_status",
        ),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["directory_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["directory_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_tickets_assignee_user_id", "support_tickets", ["assignee_user_id"])
    op.create_index("ix_support_tickets_department_id", "support_tickets", ["department_id"])
    op.create_index("ix_support_tickets_requester_user_id", "support_tickets", ["requester_user_id"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])

    op.create_table(
        "user_group_memberships",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("added_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["added_by_user_id"], ["directory_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["directory_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "group_id"),
    )
    op.create_index(
        "ix_user_group_memberships_added_by_user_id",
        "user_group_memberships",
        ["added_by_user_id"],
    )
    op.create_index(
        "ix_user_group_memberships_department_id",
        "user_group_memberships",
        ["department_id"],
    )
    op.create_index("ix_user_group_memberships_group_id", "user_group_memberships", ["group_id"])

    op.create_table(
        "security_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "severity in ('low', 'medium', 'high', 'critical')",
            name="ck_security_events_severity",
        ),
        sa.CheckConstraint(
            "status in ('open', 'investigating', 'resolved', 'false_positive')",
            name="ck_security_events_status",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["directory_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_events_department_id", "security_events", ["department_id"])
    op.create_index("ix_security_events_device_id", "security_events", ["device_id"])
    op.create_index("ix_security_events_occurred_at", "security_events", ["occurred_at"])
    op.create_index("ix_security_events_user_id", "security_events", ["user_id"])

    op.create_table(
        "it_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("target_user_id", sa.Uuid(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["directory_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["directory_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_it_audit_events_actor_user_id", "it_audit_events", ["actor_user_id"])
    op.create_index("ix_it_audit_events_department_id", "it_audit_events", ["department_id"])
    op.create_index("ix_it_audit_events_occurred_at", "it_audit_events", ["occurred_at"])
    op.create_index("ix_it_audit_events_target_user_id", "it_audit_events", ["target_user_id"])


def downgrade() -> None:
    op.drop_index("ix_it_audit_events_target_user_id", table_name="it_audit_events")
    op.drop_index("ix_it_audit_events_occurred_at", table_name="it_audit_events")
    op.drop_index("ix_it_audit_events_department_id", table_name="it_audit_events")
    op.drop_index("ix_it_audit_events_actor_user_id", table_name="it_audit_events")
    op.drop_table("it_audit_events")

    op.drop_index("ix_security_events_user_id", table_name="security_events")
    op.drop_index("ix_security_events_occurred_at", table_name="security_events")
    op.drop_index("ix_security_events_device_id", table_name="security_events")
    op.drop_index("ix_security_events_department_id", table_name="security_events")
    op.drop_table("security_events")

    op.drop_index("ix_user_group_memberships_group_id", table_name="user_group_memberships")
    op.drop_index(
        "ix_user_group_memberships_department_id",
        table_name="user_group_memberships",
    )
    op.drop_index(
        "ix_user_group_memberships_added_by_user_id",
        table_name="user_group_memberships",
    )
    op.drop_table("user_group_memberships")

    op.drop_index("ix_support_tickets_status", table_name="support_tickets")
    op.drop_index("ix_support_tickets_requester_user_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_department_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_assignee_user_id", table_name="support_tickets")
    op.drop_table("support_tickets")

    op.drop_index("ix_software_installs_device_id", table_name="software_installs")
    op.drop_index("ix_software_installs_department_id", table_name="software_installs")
    op.drop_table("software_installs")

    op.drop_index("ix_login_events_user_id", table_name="login_events")
    op.drop_index("ix_login_events_occurred_at", table_name="login_events")
    op.drop_index("ix_login_events_device_id", table_name="login_events")
    op.drop_index("ix_login_events_department_id", table_name="login_events")
    op.drop_table("login_events")

    op.drop_index("ix_license_assignments_user_id", table_name="license_assignments")
    op.drop_index(
        "ix_license_assignments_reclaimed_by_app_user_id",
        table_name="license_assignments",
    )
    op.drop_index("ix_license_assignments_license_id", table_name="license_assignments")
    op.drop_index("ix_license_assignments_department_id", table_name="license_assignments")
    op.drop_table("license_assignments")

    op.drop_index("ix_groups_department_id", table_name="groups")
    op.drop_table("groups")

    op.drop_index("ix_devices_department_id", table_name="devices")
    op.drop_index("ix_devices_assigned_user_id", table_name="devices")
    op.drop_table("devices")

    op.drop_index("ix_directory_users_manager_id", table_name="directory_users")
    op.drop_index("ix_directory_users_department_id", table_name="directory_users")
    op.drop_table("directory_users")

    op.drop_table("licenses")
    op.drop_table("departments")
