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


class RoleUpgradeRequest(Base):
    __tablename__ = "role_upgrade_requests"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_role_upgrade_requests_status",
        ),
        Index("ix_role_upgrade_requests_requester_user_id", "requester_user_id"),
        Index("ix_role_upgrade_requests_requested_role_id", "requested_role_id"),
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
    evaluation_results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="query_run",
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_approval_requests_status",
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
    request_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RequestStatus.PENDING.value,
        server_default=RequestStatus.PENDING.value,
    )
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    policy_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
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
    created_at: Mapped[datetime] = created_at_column()

    actor: Mapped[AppUser | None] = relationship(back_populates="audit_logs")
