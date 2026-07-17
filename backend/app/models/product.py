from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class SupportedActionType(StrEnum):
    RECLAIM_UNUSED_LICENSE = "reclaim_unused_license"
    DISABLE_INACTIVE_USER = "disable_inactive_user"


class ActionRequestStatus(StrEnum):
    DRAFT_PREVIEW = "draft_preview"
    PENDING_APPROVAL = "pending_approval"
    APPROVED_EXECUTING = "approved_executing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ActionPriority(StrEnum):
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VisibilityScope(StrEnum):
    PERSONAL = "personal"
    DEPARTMENT = "department"
    GLOBAL = "global"


class PermissionEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class NotificationStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_system_role: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    users: Mapped[list[AppUser]] = relationship(back_populates="role")
    role_permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
    role_upgrade_requests: Mapped[list[RoleUpgradeRequest]] = relationship(
        back_populates="requested_role",
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    role_permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="permission",
        cascade="all, delete-orphan",
    )
    user_permissions: Mapped[list[UserPermission]] = relationship(
        back_populates="permission",
        cascade="all, delete-orphan",
    )


class AccessScope(Base):
    __tablename__ = "access_scopes"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_key", name="uq_access_scopes_type_key"),
        Index("ix_access_scopes_scope_type", "scope_type"),
        Index("ix_access_scopes_department_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(128))
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
    )
    is_system_scope: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    user_access_scopes: Mapped[list[UserAccessScope]] = relationship(
        back_populates="scope",
        cascade="all, delete-orphan",
    )
    department: Mapped[Any | None] = relationship(
        "Department",
        back_populates="access_scopes",
    )
    role_upgrade_requests: Mapped[list[RoleUpgradeRequest]] = relationship(
        back_populates="requested_scope",
    )
    action_requests: Mapped[list[ActionRequest]] = relationship(
        back_populates="scope",
    )
    action_audit_logs: Mapped[list[AppAuditLog]] = relationship(
        back_populates="scope",
    )


class AppUser(Base):
    __tablename__ = "app_users"
    __table_args__ = (
        UniqueConstraint(
            "auth_provider",
            "provider_user_id",
            name="uq_app_users_auth_provider_provider_user_id",
        ),
        CheckConstraint(
            "status in ('active', 'invited', 'disabled')",
            name="ck_app_users_status",
        ),
        Index("ix_app_users_role_id", "role_id"),
        Index("ix_app_users_department_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    auth_provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="demo",
        server_default="demo",
    )
    provider_user_id: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=UserStatus.ACTIVE.value,
        server_default=UserStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped[Role | None] = relationship(back_populates="users")
    user_permissions: Mapped[list[UserPermission]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserPermission.user_id",
    )
    user_access_scopes: Mapped[list[UserAccessScope]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    granted_user_permissions: Mapped[list[UserPermission]] = relationship(
        back_populates="granted_by_user",
        foreign_keys="UserPermission.granted_by_user_id",
    )
    role_upgrade_requests: Mapped[list[RoleUpgradeRequest]] = relationship(
        back_populates="requester",
        foreign_keys="RoleUpgradeRequest.requester_user_id",
    )
    decided_role_upgrade_requests: Mapped[list[RoleUpgradeRequest]] = relationship(
        back_populates="decided_by_user",
        foreign_keys="RoleUpgradeRequest.decided_by_user_id",
    )
    dashboards: Mapped[list[Dashboard]] = relationship(back_populates="owner")
    saved_queries: Mapped[list[SavedQuery]] = relationship(back_populates="owner")
    query_runs: Mapped[list[QueryRun]] = relationship(back_populates="user")
    requested_actions: Mapped[list[ActionRequest]] = relationship(
        back_populates="requester",
        foreign_keys="ActionRequest.requested_by_app_user_id",
    )
    requested_approvals: Mapped[list[ApprovalRequest]] = relationship(
        back_populates="requester",
        foreign_keys="ApprovalRequest.requester_user_id",
    )
    decided_approvals: Mapped[list[ApprovalRequest]] = relationship(
        back_populates="decided_by_user",
        foreign_keys="ApprovalRequest.decided_by_user_id",
    )
    received_notifications: Mapped[list[Notification]] = relationship(
        back_populates="recipient",
        foreign_keys="Notification.recipient_user_id",
    )
    acted_notifications: Mapped[list[Notification]] = relationship(
        back_populates="actor",
        foreign_keys="Notification.actor_user_id",
    )
    evaluation_runs: Mapped[list[EvaluationRun]] = relationship(
        back_populates="requested_by_user",
    )
    audit_logs: Mapped[list[AppAuditLog]] = relationship(back_populates="actor")
    operational_audit_events: Mapped[list[Any]] = relationship(
        "ItAuditEvent",
        back_populates="actor_app_user",
        foreign_keys="ItAuditEvent.actor_app_user_id",
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = created_at_column()

    role: Mapped[Role] = relationship(back_populates="role_permissions")
    permission: Mapped[Permission] = relationship(back_populates="role_permissions")


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "permission_id",
            name="uq_user_permissions_user_id_permission_id",
        ),
        CheckConstraint("effect in ('allow', 'deny')", name="ck_user_permissions_effect"),
        Index("ix_user_permissions_granted_by_user_id", "granted_by_user_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    effect: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PermissionEffect.ALLOW.value,
        server_default=PermissionEffect.ALLOW.value,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = created_at_column()

    user: Mapped[AppUser] = relationship(
        back_populates="user_permissions",
        foreign_keys=[user_id],
    )
    permission: Mapped[Permission] = relationship(back_populates="user_permissions")
    granted_by_user: Mapped[AppUser | None] = relationship(
        back_populates="granted_user_permissions",
        foreign_keys=[granted_by_user_id],
    )


class UserAccessScope(Base):
    __tablename__ = "user_access_scopes"
    __table_args__ = (
        Index("ix_user_access_scopes_user_id", "user_id"),
        Index("ix_user_access_scopes_scope_id", "scope_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_scopes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    access_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="read",
        server_default="read",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = created_at_column()

    user: Mapped[AppUser] = relationship(back_populates="user_access_scopes")
    scope: Mapped[AccessScope] = relationship(back_populates="user_access_scopes")


class DataResource(Base):
    __tablename__ = "data_resources"
    __table_args__ = (
        Index("ix_data_resources_domain", "domain"),
        Index("ix_data_resources_table_name", "table_name"),
        Index("ix_data_resources_scope_type", "scope_type"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    domain: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_name: Mapped[str | None] = mapped_column(String(128))
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sensitivity_level: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str | None] = mapped_column(String(64))
    scope_column: Mapped[str | None] = mapped_column(String(128))
    is_queryable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    is_exportable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    llm_exposure_level: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class RoleUpgradeRequest(Base):
    __tablename__ = "role_upgrade_requests"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_role_upgrade_requests_status",
        ),
        Index("ix_role_upgrade_requests_requester_user_id", "requester_user_id"),
        Index("ix_role_upgrade_requests_requested_role_id", "requested_role_id"),
        Index("ix_role_upgrade_requests_requested_scope_id", "requested_scope_id"),
        Index("ix_role_upgrade_requests_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    requester_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_scope_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_scopes.id", ondelete="SET NULL"),
    )
    requested_scope_type: Mapped[str | None] = mapped_column(String(64))
    requested_scope_key: Mapped[str | None] = mapped_column(String(128))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RequestStatus.PENDING.value,
        server_default=RequestStatus.PENDING.value,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    requester: Mapped[AppUser] = relationship(
        back_populates="role_upgrade_requests",
        foreign_keys=[requester_user_id],
    )
    requested_role: Mapped[Role] = relationship(back_populates="role_upgrade_requests")
    requested_scope: Mapped[AccessScope | None] = relationship(
        back_populates="role_upgrade_requests",
    )
    decided_by_user: Mapped[AppUser | None] = relationship(
        back_populates="decided_role_upgrade_requests",
        foreign_keys=[decided_by_user_id],
    )


class Dashboard(Base):
    __tablename__ = "dashboards"
    __table_args__ = (
        CheckConstraint(
            "visibility_scope in ('personal', 'department', 'global')",
            name="ck_dashboards_visibility_scope",
        ),
        Index("ix_dashboards_owner_user_id", "owner_user_id"),
        Index("ix_dashboards_visibility_scope", "visibility_scope"),
        Index("ix_dashboards_department_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    visibility_scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=VisibilityScope.PERSONAL.value,
        server_default=VisibilityScope.PERSONAL.value,
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    layout_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    owner: Mapped[AppUser | None] = relationship(back_populates="dashboards")
    cards: Mapped[list[DashboardCard]] = relationship(
        back_populates="dashboard",
        cascade="all, delete-orphan",
    )


class SavedQuery(Base):
    __tablename__ = "saved_queries"
    __table_args__ = (
        CheckConstraint(
            "visibility_scope in ('personal', 'department', 'global')",
            name="ck_saved_queries_visibility_scope",
        ),
        Index("ix_saved_queries_owner_user_id", "owner_user_id"),
        Index("ix_saved_queries_visibility_scope", "visibility_scope"),
        Index("ix_saved_queries_department_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    natural_language_question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    visibility_scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=VisibilityScope.PERSONAL.value,
        server_default=VisibilityScope.PERSONAL.value,
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    owner: Mapped[AppUser | None] = relationship(back_populates="saved_queries")
    dashboard_cards: Mapped[list[DashboardCard]] = relationship(
        back_populates="saved_query",
    )
    query_runs: Mapped[list[QueryRun]] = relationship(back_populates="saved_query")


class DashboardCard(Base):
    __tablename__ = "dashboard_cards"
    __table_args__ = (
        Index("ix_dashboard_cards_dashboard_id_position", "dashboard_id", "position"),
        Index("ix_dashboard_cards_saved_query_id", "saved_query_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    saved_query_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("saved_queries.id", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    card_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="table",
        server_default="table",
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    layout: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    dashboard: Mapped[Dashboard] = relationship(back_populates="cards")
    saved_query: Mapped[SavedQuery | None] = relationship(
        back_populates="dashboard_cards",
    )


class QueryRun(Base):
    __tablename__ = "query_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_query_runs_status",
        ),
        Index("ix_query_runs_user_id", "user_id"),
        Index("ix_query_runs_saved_query_id", "saved_query_id"),
        Index("ix_query_runs_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    saved_query_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("saved_queries.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RunStatus.QUEUED.value,
        server_default=RunStatus.QUEUED.value,
    )
    natural_language_question: Mapped[str | None] = mapped_column(Text)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    executed_sql: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    query_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[AppUser | None] = relationship(back_populates="query_runs")
    saved_query: Mapped[SavedQuery | None] = relationship(back_populates="query_runs")
    approval_requests: Mapped[list[ApprovalRequest]] = relationship(
        back_populates="query_run",
    )
    source_action_requests: Mapped[list[ActionRequest]] = relationship(
        back_populates="source_query_run",
    )
    evaluation_results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="query_run",
    )


class ActionRequest(Base):
    __tablename__ = "action_requests"
    __table_args__ = (
        CheckConstraint(
            "action_type in ('reclaim_unused_license', 'disable_inactive_user')",
            name="ck_action_requests_action_type",
        ),
        CheckConstraint(
            "status in ('draft_preview', 'pending_approval', 'approved_executing', "
            "'completed', 'rejected', 'failed', 'cancelled', 'expired')",
            name="ck_action_requests_status",
        ),
        CheckConstraint(
            "priority in ('normal', 'high', 'urgent')",
            name="ck_action_requests_priority",
        ),
        CheckConstraint(
            "record_count >= 0",
            name="ck_action_requests_record_count",
        ),
        CheckConstraint(
            "skipped_count >= 0",
            name="ck_action_requests_skipped_count",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_action_requests_idempotency_key",
        ),
        Index(
            "ix_action_requests_requested_by_app_user_id",
            "requested_by_app_user_id",
        ),
        Index("ix_action_requests_status", "status"),
        Index("ix_action_requests_scope_type_scope_key", "scope_type", "scope_key"),
        Index("ix_action_requests_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by_app_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_query_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("query_runs.id", ondelete="SET NULL"),
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
    )
    scope_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_scopes.id", ondelete="SET NULL"),
    )
    scope_type: Mapped[str | None] = mapped_column(String(64))
    scope_key: Mapped[str | None] = mapped_column(String(128))
    access_context_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    access_decision_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    preview_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    policy_flags_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    skipped_records_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ActionRequestStatus.DRAFT_PREVIEW.value,
        server_default=ActionRequestStatus.DRAFT_PREVIEW.value,
    )
    priority: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ActionPriority.NORMAL.value,
        server_default=ActionPriority.NORMAL.value,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    requires_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    record_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    failure_reason_user_safe: Mapped[str | None] = mapped_column(Text)
    failure_reason_internal: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    preview_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preview_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requester: Mapped[AppUser] = relationship(
        back_populates="requested_actions",
        foreign_keys=[requested_by_app_user_id],
    )
    source_query_run: Mapped[QueryRun | None] = relationship(
        back_populates="source_action_requests",
    )
    scope: Mapped[AccessScope | None] = relationship(back_populates="action_requests")
    department: Mapped[Any | None] = relationship(
        "Department",
        back_populates="action_requests",
    )
    approval_request: Mapped[ApprovalRequest | None] = relationship(
        back_populates="action_request",
        uselist=False,
    )
    audit_logs: Mapped[list[AppAuditLog]] = relationship(
        back_populates="action_request",
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'cancelled', 'expired')",
            name="ck_approval_requests_status",
        ),
        UniqueConstraint(
            "action_request_id",
            name="uq_approval_requests_action_request_id",
        ),
        Index("ix_approval_requests_requester_user_id", "requester_user_id"),
        Index("ix_approval_requests_decided_by_user_id", "decided_by_user_id"),
        Index("ix_approval_requests_query_run_id", "query_run_id"),
        Index("ix_approval_requests_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    requester_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    query_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("query_runs.id", ondelete="SET NULL"),
    )
    action_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("action_requests.id", ondelete="CASCADE"),
    )
    request_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ApprovalStatus.PENDING.value,
        server_default=ApprovalStatus.PENDING.value,
    )
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    policy_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    required_approver_role: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    requester: Mapped[AppUser | None] = relationship(
        back_populates="requested_approvals",
        foreign_keys=[requester_user_id],
    )
    decided_by_user: Mapped[AppUser | None] = relationship(
        back_populates="decided_approvals",
        foreign_keys=[decided_by_user_id],
    )
    query_run: Mapped[QueryRun | None] = relationship(
        back_populates="approval_requests",
    )
    action_request: Mapped[ActionRequest | None] = relationship(
        back_populates="approval_request",
    )
    audit_logs: Mapped[list[AppAuditLog]] = relationship(
        back_populates="approval_request",
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "status in ('unread', 'read', 'archived')",
            name="ck_notifications_status",
        ),
        Index("ix_notifications_recipient_user_id", "recipient_user_id"),
        Index("ix_notifications_actor_user_id", "actor_user_id"),
        Index("ix_notifications_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=NotificationStatus.UNREAD.value,
        server_default=NotificationStatus.UNREAD.value,
    )
    related_resource_type: Mapped[str | None] = mapped_column(String(64))
    related_resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recipient: Mapped[AppUser] = relationship(
        back_populates="received_notifications",
        foreign_keys=[recipient_user_id],
    )
    actor: Mapped[AppUser | None] = relationship(
        back_populates="acted_notifications",
        foreign_keys=[actor_user_id],
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_evaluation_runs_status",
        ),
        Index("ix_evaluation_runs_requested_by_user_id", "requested_by_user_id"),
        Index("ix_evaluation_runs_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    run_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RunStatus.QUEUED.value,
        server_default=RunStatus.QUEUED.value,
    )
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requested_by_user: Mapped[AppUser | None] = relationship(
        back_populates="evaluation_runs",
    )
    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="evaluation_run",
        cascade="all, delete-orphan",
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        CheckConstraint(
            "status in ('succeeded', 'failed', 'skipped')",
            name="ck_evaluation_results_status",
        ),
        Index("ix_evaluation_results_evaluation_run_id", "evaluation_run_id"),
        Index("ix_evaluation_results_query_run_id", "query_run_id"),
        Index("ix_evaluation_results_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    query_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("query_runs.id", ondelete="SET NULL"),
    )
    case_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    expected_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    actual_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    evaluation_run: Mapped[EvaluationRun] = relationship(back_populates="results")
    query_run: Mapped[QueryRun | None] = relationship(
        back_populates="evaluation_results",
    )


class AppAuditLog(Base):
    __tablename__ = "app_audit_logs"
    __table_args__ = (
        Index("ix_app_audit_logs_actor_user_id", "actor_user_id"),
        Index("ix_app_audit_logs_event_type", "event_type"),
        Index("ix_app_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_app_audit_logs_action_request_id", "action_request_id"),
        Index("ix_app_audit_logs_approval_request_id", "approval_request_id"),
        Index("ix_app_audit_logs_department_id", "department_id"),
        Index("ix_app_audit_logs_scope_id", "scope_id"),
        Index("ix_app_audit_logs_scope_type_scope_key", "scope_type", "scope_key"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    action_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("action_requests.id", ondelete="SET NULL"),
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approval_requests.id", ondelete="SET NULL"),
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
    )
    scope_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_scopes.id", ondelete="SET NULL"),
    )
    scope_type: Mapped[str | None] = mapped_column(String(64))
    scope_key: Mapped[str | None] = mapped_column(String(128))
    severity: Mapped[str | None] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(32))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    summary: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    audit_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    before_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    self_approved: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = created_at_column()

    actor: Mapped[AppUser | None] = relationship(back_populates="audit_logs")
    action_request: Mapped[ActionRequest | None] = relationship(
        back_populates="audit_logs",
    )
    approval_request: Mapped[ApprovalRequest | None] = relationship(
        back_populates="audit_logs",
    )
    department: Mapped[Any | None] = relationship(
        "Department",
        back_populates="app_audit_logs",
    )
    scope: Mapped[AccessScope | None] = relationship(
        back_populates="action_audit_logs",
    )
