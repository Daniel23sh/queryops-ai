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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AccountType(StrEnum):
    HUMAN = "human"
    SERVICE = "service"


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    TERMINATED = "terminated"
    ON_LEAVE = "on_leave"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


class LoginEventType(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class AssignmentStatus(StrEnum):
    ACTIVE = "active"
    RECLAIMED = "reclaimed"
    SUSPENDED = "suspended"


class DeviceType(StrEnum):
    LAPTOP = "laptop"
    DESKTOP = "desktop"
    MOBILE = "mobile"
    SERVER = "server"


class ComplianceStatus(StrEnum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    UNKNOWN = "unknown"


class AntivirusStatus(StrEnum):
    HEALTHY = "healthy"
    OUTDATED = "outdated"
    MISSING = "missing"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class GroupType(StrEnum):
    SECURITY = "security"
    DISTRIBUTION = "distribution"
    APPLICATION = "application"
    ADMIN = "admin"


class SecurityEventStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


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


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    directory_users: Mapped[list[DirectoryUser]] = relationship(
        back_populates="department",
    )
    devices: Mapped[list[Device]] = relationship(back_populates="department")
    groups: Mapped[list[Group]] = relationship(back_populates="department")


class License(Base):
    __tablename__ = "licenses"
    __table_args__ = (
        UniqueConstraint("vendor", "product_name", name="uq_licenses_vendor_product_name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    monthly_cost_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_mandatory_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    assignments: Mapped[list[LicenseAssignment]] = relationship(
        back_populates="license",
    )


class DirectoryUser(Base):
    __tablename__ = "directory_users"
    __table_args__ = (
        CheckConstraint(
            "account_type in ('human', 'service')",
            name="ck_directory_users_account_type",
        ),
        CheckConstraint(
            "employee_status in ('active', 'terminated', 'on_leave')",
            name="ck_directory_users_employee_status",
        ),
        CheckConstraint(
            "account_status in ('active', 'disabled', 'locked')",
            name="ck_directory_users_account_status",
        ),
        Index("ix_directory_users_department_id", "department_id"),
        Index("ix_directory_users_manager_id", "manager_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="SET NULL"),
    )
    job_title: Mapped[str | None] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AccountType.HUMAN.value,
        server_default=AccountType.HUMAN.value,
    )
    employee_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=EmployeeStatus.ACTIVE.value,
        server_default=EmployeeStatus.ACTIVE.value,
    )
    account_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AccountStatus.ACTIVE.value,
        server_default=AccountStatus.ACTIVE.value,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    department: Mapped[Department] = relationship(back_populates="directory_users")
    manager: Mapped[DirectoryUser | None] = relationship(
        "DirectoryUser",
        back_populates="direct_reports",
        remote_side="DirectoryUser.id",
        foreign_keys=[manager_id],
    )
    direct_reports: Mapped[list[DirectoryUser]] = relationship(
        "DirectoryUser",
        back_populates="manager",
        foreign_keys=[manager_id],
    )
    login_events: Mapped[list[LoginEvent]] = relationship(back_populates="user")
    devices: Mapped[list[Device]] = relationship(back_populates="assigned_user")
    license_assignments: Mapped[list[LicenseAssignment]] = relationship(
        back_populates="user",
    )


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            "device_type in ('laptop', 'desktop', 'mobile', 'server')",
            name="ck_devices_device_type",
        ),
        CheckConstraint(
            "compliance_status in ('compliant', 'non_compliant', 'unknown')",
            name="ck_devices_compliance_status",
        ),
        CheckConstraint(
            "antivirus_status in ('healthy', 'outdated', 'missing', 'unknown')",
            name="ck_devices_antivirus_status",
        ),
        Index("ix_devices_assigned_user_id", "assigned_user_id"),
        Index("ix_devices_department_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="SET NULL"),
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    os: Mapped[str] = mapped_column(String(128), nullable=False)
    os_version: Mapped[str] = mapped_column(String(128), nullable=False)
    device_type: Mapped[str] = mapped_column(String(32), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    compliance_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ComplianceStatus.UNKNOWN.value,
        server_default=ComplianceStatus.UNKNOWN.value,
    )
    encryption_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    antivirus_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AntivirusStatus.UNKNOWN.value,
        server_default=AntivirusStatus.UNKNOWN.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    assigned_user: Mapped[DirectoryUser | None] = relationship(back_populates="devices")
    department: Mapped[Department] = relationship(back_populates="devices")
    software_installs: Mapped[list[SoftwareInstall]] = relationship(
        back_populates="device",
    )


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint(
            "group_type in ('security', 'distribution', 'application', 'admin')",
            name="ck_groups_group_type",
        ),
        CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_groups_risk_level",
        ),
        Index("ix_groups_department_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    group_type: Mapped[str] = mapped_column(String(64), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
    )
    is_privileged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    risk_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RiskLevel.LOW.value,
        server_default=RiskLevel.LOW.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    department: Mapped[Department | None] = relationship(back_populates="groups")
    memberships: Mapped[list[UserGroupMembership]] = relationship(back_populates="group")


class LicenseAssignment(Base):
    __tablename__ = "license_assignments"
    __table_args__ = (
        CheckConstraint(
            "status in ('active', 'reclaimed', 'suspended')",
            name="ck_license_assignments_status",
        ),
        Index("ix_license_assignments_user_id", "user_id"),
        Index("ix_license_assignments_license_id", "license_id"),
        Index("ix_license_assignments_department_id", "department_id"),
        Index("ix_license_assignments_reclaimed_by_app_user_id", "reclaimed_by_app_user_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    license_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("licenses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AssignmentStatus.ACTIVE.value,
        server_default=AssignmentStatus.ACTIVE.value,
    )
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_exception: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    reclaimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reclaimed_by_app_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )

    user: Mapped[DirectoryUser] = relationship(back_populates="license_assignments")
    license: Mapped[License] = relationship(back_populates="assignments")


class LoginEvent(Base):
    __tablename__ = "login_events"
    __table_args__ = (
        CheckConstraint(
            "event_type in ('success', 'failed')",
            name="ck_login_events_event_type",
        ),
        Index("ix_login_events_user_id", "user_id"),
        Index("ix_login_events_department_id", "department_id"),
        Index("ix_login_events_device_id", "device_id"),
        Index("ix_login_events_occurred_at", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(128))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)

    user: Mapped[DirectoryUser] = relationship(back_populates="login_events")


class SoftwareInstall(Base):
    __tablename__ = "software_installs"
    __table_args__ = (
        CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_software_installs_risk_level",
        ),
        Index("ix_software_installs_device_id", "device_id"),
        Index("ix_software_installs_department_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    software_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str | None] = mapped_column(String(128))
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_outdated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_unsupported: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    risk_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RiskLevel.LOW.value,
        server_default=RiskLevel.LOW.value,
    )

    device: Mapped[Device] = relationship(back_populates="software_installs")


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint(
            "priority in ('low', 'medium', 'high', 'critical')",
            name="ck_support_tickets_priority",
        ),
        CheckConstraint(
            "status in ('open', 'in_progress', 'resolved', 'closed')",
            name="ck_support_tickets_status",
        ),
        Index("ix_support_tickets_requester_user_id", "requester_user_id"),
        Index("ix_support_tickets_assignee_user_id", "assignee_user_id"),
        Index("ix_support_tickets_department_id", "department_id"),
        Index("ix_support_tickets_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    requester_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="SET NULL"),
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="SET NULL"),
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TicketStatus.OPEN.value,
        server_default=TicketStatus.OPEN.value,
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class UserGroupMembership(Base):
    __tablename__ = "user_group_memberships"
    __table_args__ = (
        Index("ix_user_group_memberships_department_id", "department_id"),
        Index("ix_user_group_memberships_group_id", "group_id"),
        Index("ix_user_group_memberships_added_by_user_id", "added_by_user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="SET NULL"),
    )

    user: Mapped[DirectoryUser] = relationship(foreign_keys=[user_id])
    group: Mapped[Group] = relationship(back_populates="memberships")
    added_by_user: Mapped[DirectoryUser | None] = relationship(
        foreign_keys=[added_by_user_id],
    )


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (
        CheckConstraint(
            "severity in ('low', 'medium', 'high', 'critical')",
            name="ck_security_events_severity",
        ),
        CheckConstraint(
            "status in ('open', 'investigating', 'resolved', 'false_positive')",
            name="ck_security_events_status",
        ),
        Index("ix_security_events_user_id", "user_id"),
        Index("ix_security_events_device_id", "device_id"),
        Index("ix_security_events_department_id", "department_id"),
        Index("ix_security_events_occurred_at", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="SET NULL"),
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SecurityEventStatus.OPEN.value,
        server_default=SecurityEventStatus.OPEN.value,
    )
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)


class ItAuditEvent(Base):
    __tablename__ = "it_audit_events"
    __table_args__ = (
        Index("ix_it_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_it_audit_events_target_user_id", "target_user_id"),
        Index("ix_it_audit_events_department_id", "department_id"),
        Index("ix_it_audit_events_occurred_at", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="SET NULL"),
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("directory_users.id", ondelete="SET NULL"),
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    description: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
