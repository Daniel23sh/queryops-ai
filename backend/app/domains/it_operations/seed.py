from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Iterable

from faker import Faker
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.it_operations.models import (
    Department,
    Device,
    DirectoryUser,
    Group,
    ItAuditEvent,
    License,
    LicenseAssignment,
    LoginEvent,
    SecurityEvent,
    SoftwareInstall,
    SupportTicket,
    UserGroupMembership,
)
from app.domains.it_operations.seed_profiles import SeedProfile, get_seed_profile
from app.models.product import (
    AccessScope,
    AppAuditLog,
    AppUser,
    ApprovalRequest,
    Dashboard,
    DashboardCard,
    DataResource,
    EvaluationResult,
    EvaluationRun,
    Notification,
    Permission,
    QueryRun,
    Role,
    RolePermission,
    RoleUpgradeRequest,
    SavedQuery,
    UserAccessScope,
    UserPermission,
)


NAMESPACE = uuid.UUID("64a29730-04d5-4dc4-b9a1-8d4f721a7c29")
REFERENCE_NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)

DEPARTMENT_NAMES = [
    "IT",
    "Finance",
    "HR",
    "Sales",
    "Engineering",
    "Operations",
    "Support",
    "Legal",
]

LICENSE_PRODUCTS = [
    ("Microsoft 365 E3", "Microsoft", Decimal("32.00"), True),
    ("Microsoft 365 E5", "Microsoft", Decimal("57.00"), True),
    ("Salesforce", "Salesforce", Decimal("165.00"), False),
    ("Jira", "Atlassian", Decimal("8.50"), False),
    ("GitHub Enterprise", "GitHub", Decimal("21.00"), False),
    ("Zoom", "Zoom", Decimal("15.99"), False),
    ("Adobe Creative Cloud", "Adobe", Decimal("89.99"), False),
    ("Slack", "Salesforce", Decimal("12.50"), False),
]

PERMISSIONS = [
    ("can_use_query_templates", "query", "Use approved query templates"),
    ("can_run_free_query", "query", "Ask free-form data questions"),
    ("can_query_department_data", "query", "Query department-scoped data"),
    ("can_query_scoped_data", "query", "Query assigned-scope data"),
    ("can_query_global_data", "query", "Query global data"),
    ("can_query_product_tables", "query", "Query product tables in admin mode"),
    ("can_view_sql", "query", "View generated SQL"),
    ("can_view_query_history_department", "query", "View department query history"),
    ("can_view_query_history_scope", "query", "View assigned-scope query history"),
    ("can_star_dashboard", "dashboard", "Star dashboards and cards"),
    ("can_create_personal_dashboard", "dashboard", "Create personal dashboards"),
    ("can_create_department_dashboard", "dashboard", "Create department dashboards"),
    ("can_create_scope_dashboard", "dashboard", "Create assigned-scope dashboards"),
    ("can_create_global_dashboard", "dashboard", "Create global dashboards"),
    (
        "can_manage_department_dashboard",
        "dashboard",
        "Manage department dashboards",
    ),
    ("can_manage_scope_dashboard", "dashboard", "Manage assigned-scope dashboards"),
    ("can_manage_global_dashboard", "dashboard", "Manage global dashboards"),
    ("can_create_card", "dashboard", "Create dashboard cards"),
    ("can_export_results", "export", "Export query and dashboard card results as CSV"),
    ("can_request_action", "action", "Request controlled actions"),
    ("can_approve_department_action", "action", "Approve department actions"),
    ("can_approve_scoped_action", "action", "Approve assigned-scope actions"),
    ("can_approve_global_action", "action", "Approve global actions"),
    ("can_approve_policy_override", "action", "Approve policy override actions"),
    (
        "can_self_approve_admin_action",
        "action",
        "Self-approve admin actions with audit marking",
    ),
    ("can_manage_users", "admin", "Manage application users"),
    ("can_disable_app_user", "admin", "Disable application users"),
    ("can_downgrade_user_role", "admin", "Downgrade application user roles"),
    ("can_approve_role_requests", "admin", "Approve role upgrade requests"),
    ("can_view_department_audit", "audit", "View department audit data"),
    ("can_view_scope_audit", "audit", "View assigned-scope audit data"),
    ("can_view_global_audit", "audit", "View global audit data"),
    ("can_view_department_evaluation", "evaluation", "View department evaluation data"),
    ("can_view_scope_evaluation", "evaluation", "View assigned-scope evaluation data"),
    ("can_view_global_evaluation", "evaluation", "View global evaluation data"),
    ("can_view_own_data", "data", "View own scoped data"),
    ("can_view_department_data", "data", "View department-scoped data"),
    ("can_view_scoped_data", "data", "View assigned-scope data"),
    ("can_view_global_data", "data", "View global data"),
]

ROLE_PERMISSION_KEYS = {
    "user": [
        "can_use_query_templates",
        "can_view_own_data",
        "can_star_dashboard",
    ],
    "manager": [
        "can_use_query_templates",
        "can_view_own_data",
        "can_star_dashboard",
        "can_run_free_query",
        "can_query_department_data",
        "can_query_scoped_data",
        "can_view_department_data",
        "can_view_scoped_data",
        "can_create_personal_dashboard",
        "can_request_action",
        "can_view_department_evaluation",
        "can_view_scope_evaluation",
    ],
    "analyst": [
        "can_use_query_templates",
        "can_view_own_data",
        "can_star_dashboard",
        "can_run_free_query",
        "can_query_department_data",
        "can_query_scoped_data",
        "can_view_department_data",
        "can_view_scoped_data",
        "can_create_personal_dashboard",
        "can_request_action",
        "can_view_department_evaluation",
        "can_view_scope_evaluation",
        "can_view_sql",
        "can_create_department_dashboard",
        "can_create_scope_dashboard",
        "can_manage_department_dashboard",
        "can_manage_scope_dashboard",
        "can_create_card",
        "can_export_results",
        "can_approve_department_action",
        "can_approve_scoped_action",
        "can_view_query_history_department",
        "can_view_query_history_scope",
        "can_view_department_audit",
        "can_view_scope_audit",
    ],
    "admin": [key for key, _category, _description in PERMISSIONS],
}

DEMO_USERS = [
    ("demo.admin@queryops.local", "Demo Admin", "admin", "IT"),
    ("demo.analyst@queryops.local", "Demo Analyst", "analyst", "IT"),
    ("demo.manager@queryops.local", "Demo Manager", "manager", "Finance"),
    ("demo.user@queryops.local", "Demo User", "user", "Sales"),
]

DATA_RESOURCE_SPECS = [
    (
        "departments",
        "Departments",
        "internal",
        None,
        None,
        True,
        False,
        "schema_only",
    ),
    (
        "directory_users",
        "Directory Users",
        "scoped_restricted",
        "department",
        "department_id",
        True,
        False,
        "aggregate_safe",
    ),
    (
        "login_events",
        "Login Events",
        "sensitive",
        "department",
        "department_id",
        True,
        False,
        "aggregate_safe",
    ),
    (
        "licenses",
        "Licenses",
        "internal",
        None,
        None,
        True,
        False,
        "result_safe",
    ),
    (
        "license_assignments",
        "License Assignments",
        "scoped_restricted",
        "department",
        "department_id",
        True,
        False,
        "aggregate_safe",
    ),
    (
        "devices",
        "Devices",
        "scoped_restricted",
        "department",
        "department_id",
        True,
        False,
        "aggregate_safe",
    ),
    (
        "software_installs",
        "Software Installs",
        "sensitive",
        "department",
        "department_id",
        True,
        False,
        "aggregate_safe",
    ),
    (
        "support_tickets",
        "Support Tickets",
        "scoped_restricted",
        "department",
        "department_id",
        True,
        False,
        "aggregate_safe",
    ),
    (
        "groups",
        "Groups",
        "sensitive",
        "department",
        "department_id",
        True,
        False,
        "aggregate_safe",
    ),
    (
        "user_group_memberships",
        "User Group Memberships",
        "sensitive",
        "department",
        "department_id",
        True,
        False,
        "aggregate_safe",
    ),
    (
        "security_events",
        "Security Events",
        "highly_sensitive",
        "department",
        "department_id",
        True,
        False,
        "aggregate_safe",
    ),
    (
        "it_audit_events",
        "IT Audit Events",
        "sensitive",
        "department",
        "department_id",
        False,
        False,
        "none",
    ),
]

GROUP_SPECS = [
    ("Domain Admins", "admin", None, True, "critical"),
    ("Security Admins", "admin", None, True, "critical"),
    ("IT Admins", "admin", "IT", True, "high"),
    ("Finance Approvers", "security", "Finance", True, "high"),
    ("HR Managers", "security", "HR", True, "medium"),
    ("Engineering Deployers", "application", "Engineering", True, "high"),
    ("Support Operators", "application", "Support", False, "medium"),
    ("Sales Analytics", "application", "Sales", False, "medium"),
    ("Operations Coordinators", "distribution", "Operations", False, "low"),
    ("Legal Reviewers", "security", "Legal", False, "medium"),
    ("VPN Users", "security", None, False, "medium"),
    ("MFA Exemptions", "security", None, True, "critical"),
    ("Device Admins", "admin", "IT", True, "high"),
    ("License Managers", "application", "Finance", True, "medium"),
    ("Production Access", "security", "Engineering", True, "critical"),
    ("Payroll Operators", "application", "HR", True, "high"),
    ("Regional Sales Leads", "distribution", "Sales", False, "low"),
    ("Warehouse Systems", "application", "Operations", False, "medium"),
    ("Support Escalation", "security", "Support", True, "high"),
    ("Contract Review", "distribution", "Legal", False, "low"),
    ("Privileged Breakglass", "admin", None, True, "critical"),
    ("Audit Readers", "security", None, True, "high"),
    ("Endpoint Pilot", "application", "IT", False, "low"),
    ("All Employees", "distribution", None, False, "low"),
]

SOFTWARE_CATALOG = [
    ("Chrome", "Google"),
    ("Microsoft Teams", "Microsoft"),
    ("Zoom", "Zoom"),
    ("Slack", "Salesforce"),
    ("Jira Cloud", "Atlassian"),
    ("Adobe Acrobat", "Adobe"),
    ("Docker Desktop", "Docker"),
    ("Node.js", "OpenJS"),
    ("Python", "Python Software Foundation"),
    ("Endpoint Protect", "QueryOps Synthetic"),
    ("Legacy VPN Client", "Contoso"),
    ("Old Java Runtime", "Oracle"),
]

DEPARTMENT_WEIGHTS = [18, 14, 11, 13, 17, 9, 10, 8]
LICENSE_ASSIGNMENT_WEIGHTS = [32, 18, 15, 12, 9, 6, 5, 3]
LOGIN_COUNTRY_WEIGHTS = [41, 18, 16, 14, 11]
OS_PROFILES = [
    ("Windows", "11"),
    ("macOS", "14.5"),
    ("Ubuntu", "22.04"),
    ("iOS", "17.4"),
    ("Android", "14"),
]
OS_WEIGHTS = [34, 25, 18, 13, 10]
DEVICE_TYPE_WEIGHTS = [52, 24, 18, 6]

TICKET_CATEGORIES = [
    "access_request",
    "license_issue",
    "device_issue",
    "security_alert",
    "software_install",
    "general_support",
]

SECURITY_EVENT_TYPES = [
    "failed_login_spike",
    "suspicious_login",
    "impossible_travel",
    "malware_detected",
    "privilege_escalation",
    "inactive_privileged_user",
    "device_non_compliance",
]

IT_AUDIT_EVENT_TYPES = [
    "user_disabled",
    "user_enabled",
    "license_assigned",
    "license_removed",
    "group_membership_added",
    "group_membership_removed",
    "device_assigned",
    "ticket_status_changed",
]

SEEDED_MODELS = [
    ItAuditEvent,
    SecurityEvent,
    UserGroupMembership,
    SupportTicket,
    SoftwareInstall,
    LoginEvent,
    LicenseAssignment,
    Group,
    Device,
    DirectoryUser,
    License,
    UserAccessScope,
    AccessScope,
    DataResource,
    Department,
    AppAuditLog,
    EvaluationResult,
    EvaluationRun,
    Notification,
    ApprovalRequest,
    DashboardCard,
    QueryRun,
    SavedQuery,
    Dashboard,
    RoleUpgradeRequest,
    UserPermission,
    RolePermission,
    AppUser,
    Permission,
    Role,
]

COUNT_MODELS = {
    "app_users": AppUser,
    "access_scopes": AccessScope,
    "data_resources": DataResource,
    "roles": Role,
    "permissions": Permission,
    "role_permissions": RolePermission,
    "user_access_scopes": UserAccessScope,
    "departments": Department,
    "directory_users": DirectoryUser,
    "login_events": LoginEvent,
    "licenses": License,
    "license_assignments": LicenseAssignment,
    "devices": Device,
    "software_installs": SoftwareInstall,
    "support_tickets": SupportTicket,
    "groups": Group,
    "user_group_memberships": UserGroupMembership,
    "security_events": SecurityEvent,
    "it_audit_events": ItAuditEvent,
}


@dataclass(frozen=True)
class SeedSummary:
    profile_name: str
    table_counts: dict[str, int]
    anomaly_counts: dict[str, int]

    def format(self) -> str:
        lines = [f"profile: {self.profile_name}", "row counts:"]
        lines.extend(
            f"  {table_name}: {count}"
            for table_name, count in sorted(self.table_counts.items())
        )
        lines.append("anomalies:")
        lines.extend(
            f"  {name}: {count}" for name, count in sorted(self.anomaly_counts.items())
        )
        return "\n".join(lines)


@dataclass
class SeedState:
    profile: SeedProfile
    rng: random.Random
    fake: Faker
    departments: list[Department]
    roles: dict[str, Role]
    permissions: dict[str, Permission]
    app_users: dict[str, AppUser]
    access_scopes: dict[tuple[str, str], AccessScope]
    directory_users: list[DirectoryUser]
    human_users: list[DirectoryUser]
    service_accounts: list[DirectoryUser]
    directory_user_positions: dict[uuid.UUID, int]
    groups: list[Group]
    devices: list[Device]
    devices_by_user: dict[uuid.UUID, list[Device]]
    licenses: list[License]
    license_assignments: list[LicenseAssignment]
    latest_success_login_by_user: dict[uuid.UUID, datetime]


def seed_database(
    session: Session,
    profile_name: str = "medium",
    *,
    reset: bool = False,
) -> SeedSummary:
    profile = get_seed_profile(profile_name)
    if reset:
        reset_seeded_data(session)
    elif _has_existing_seed_data(session):
        raise RuntimeError(
            "Seed target tables already contain data. Re-run with --reset to replace "
            "development seed rows."
        )

    random.seed(profile.seed)
    fake = Faker("en_US")
    Faker.seed(profile.seed)
    fake.seed_instance(profile.seed)
    state = SeedState(
        profile=profile,
        rng=random.Random(profile.seed),
        fake=fake,
        departments=[],
        roles={},
        permissions={},
        app_users={},
        access_scopes={},
        directory_users=[],
        human_users=[],
        service_accounts=[],
        directory_user_positions={},
        groups=[],
        devices=[],
        devices_by_user={},
        licenses=[],
        license_assignments=[],
        latest_success_login_by_user={},
    )

    _seed_departments(session, state)
    session.flush()
    _seed_product_core(session, state)
    session.flush()
    _seed_directory_users(session, state)
    session.flush()
    _seed_groups(session, state)
    session.flush()
    _seed_user_group_memberships(session, state)
    session.flush()
    _seed_devices(session, state)
    session.flush()
    _seed_licenses(session, state)
    session.flush()
    _seed_license_assignments(session, state)
    session.flush()
    _seed_login_events(session, state)
    _seed_software_installs(session, state)
    _seed_support_tickets(session, state)
    session.flush()
    _seed_security_events(session, state)
    _seed_it_audit_events(session, state)
    session.flush()

    return SeedSummary(
        profile_name=profile.name,
        table_counts=table_counts(session),
        anomaly_counts=anomaly_counts(session),
    )


def reset_seeded_data(session: Session) -> None:
    for model in SEEDED_MODELS:
        session.query(model).delete(synchronize_session=False)
    session.flush()


def table_counts(session: Session) -> dict[str, int]:
    return {
        table_name: int(session.scalar(select(func.count()).select_from(model)) or 0)
        for table_name, model in COUNT_MODELS.items()
    }


def anomaly_counts(session: Session) -> dict[str, int]:
    cutoff_60 = REFERENCE_NOW - timedelta(days=60)
    cutoff_90 = REFERENCE_NOW - timedelta(days=90)
    cutoff_30 = REFERENCE_NOW - timedelta(days=30)
    privileged_user_ids = select(UserGroupMembership.user_id).join(Group).where(
        Group.is_privileged.is_(True)
    )

    return {
        "inactive_licensed_users": _count(
            session,
            select(DirectoryUser.id)
            .join(LicenseAssignment, LicenseAssignment.user_id == DirectoryUser.id)
            .where(
                DirectoryUser.account_type == "human",
                DirectoryUser.last_login_at < cutoff_60,
                LicenseAssignment.status == "active",
            )
            .distinct(),
        ),
        "terminated_active_accounts": _count(
            session,
            select(DirectoryUser.id).where(
                DirectoryUser.employee_status == "terminated",
                DirectoryUser.account_status == "active",
            ),
        ),
        "terminated_users_with_devices": _count(
            session,
            select(DirectoryUser.id)
            .join(Device, Device.assigned_user_id == DirectoryUser.id)
            .where(DirectoryUser.employee_status == "terminated")
            .distinct(),
        ),
        "inactive_privileged_users": _count(
            session,
            select(DirectoryUser.id).where(
                DirectoryUser.id.in_(privileged_user_ids),
                DirectoryUser.last_login_at < cutoff_60,
            ),
        ),
        "unused_licenses_over_90_days": _count(
            session,
            select(LicenseAssignment.id).where(
                LicenseAssignment.status == "active",
                LicenseAssignment.last_used_at < cutoff_90,
            ),
        ),
        "mandatory_license_assignments": _count(
            session,
            select(LicenseAssignment.id).where(LicenseAssignment.is_mandatory.is_(True)),
        ),
        "exception_license_assignments": _count(
            session,
            select(LicenseAssignment.id).where(LicenseAssignment.is_exception.is_(True)),
        ),
        "stale_devices": _count(
            session,
            select(Device.id).where(Device.last_seen_at < cutoff_30),
        ),
        "risky_software_installs": _count(
            session,
            select(SoftwareInstall.id).where(
                (SoftwareInstall.is_outdated.is_(True))
                | (SoftwareInstall.is_unsupported.is_(True))
                | (SoftwareInstall.risk_level.in_(["high", "critical"]))
            ),
        ),
        "high_priority_open_tickets": _count(
            session,
            select(SupportTicket.id).where(
                SupportTicket.priority.in_(["high", "critical"]),
                SupportTicket.status.in_(["open", "in_progress"]),
            ),
        ),
        "failed_login_clusters": _count(
            session,
            select(LoginEvent.user_id)
            .where(LoginEvent.event_type == "failed")
            .group_by(LoginEvent.user_id)
            .having(func.count(LoginEvent.id) >= 5),
        ),
        "high_severity_open_security_events": _count(
            session,
            select(SecurityEvent.id).where(
                SecurityEvent.severity.in_(["high", "critical"]),
                SecurityEvent.status.in_(["open", "investigating"]),
            ),
        ),
    }


def seed_fingerprint(session: Session) -> dict[str, object]:
    return {
        "counts": table_counts(session),
        "anomalies": anomaly_counts(session),
        "users": [
            (str(row.id), row.employee_number, row.email, row.last_login_at)
            for row in session.scalars(
                select(DirectoryUser).order_by(DirectoryUser.employee_number).limit(12)
            )
        ],
        "devices": [
            (str(row.id), row.hostname, row.compliance_status, row.antivirus_status)
            for row in session.scalars(select(Device).order_by(Device.hostname).limit(12))
        ],
        "licenses": [
            (str(row.id), str(row.user_id), str(row.license_id), row.last_used_at)
            for row in session.scalars(
                select(LicenseAssignment)
                .order_by(LicenseAssignment.assigned_at, LicenseAssignment.id)
                .limit(12)
            )
        ],
    }


def _seed_product_core(session: Session, state: SeedState) -> None:
    for role_name, description in [
        ("user", "Regular read-only QueryOps user"),
        ("manager", "Department-level business user"),
        ("analyst", "Technical department analyst"),
        ("admin", "Global QueryOps administrator"),
    ]:
        role = Role(
            id=_id(state.profile, "role", role_name),
            name=role_name,
            description=description,
            is_system_role=True,
        )
        state.roles[role_name] = role
        session.add(role)

    for key, category, description in PERMISSIONS:
        permission = Permission(
            id=_id(state.profile, "permission", key),
            key=key,
            category=category,
            description=description,
        )
        state.permissions[key] = permission
        session.add(permission)

    for role_name, permission_keys in ROLE_PERMISSION_KEYS.items():
        for permission_key in permission_keys:
            session.add(
                RolePermission(
                    role_id=state.roles[role_name].id,
                    permission_id=state.permissions[permission_key].id,
                )
            )

    department_ids_by_name = {
        department.name: department.id for department in state.departments
    }
    for email, full_name, role_name, department_name in DEMO_USERS:
        department_id = department_ids_by_name.get(department_name)
        if department_id is None:
            raise RuntimeError(
                f"Demo app user {email} references missing department {department_name!r} "
                f"in {state.profile.name!r} seed profile."
            )
        app_user = AppUser(
            id=_id(state.profile, "app-user", email),
            auth_provider="demo",
            provider_user_id=email,
            email=email,
            full_name=full_name,
            role_id=state.roles[role_name].id,
            department_id=department_id,
            status="active",
            created_at=REFERENCE_NOW,
            updated_at=REFERENCE_NOW,
            last_login_at=REFERENCE_NOW - timedelta(hours=2),
        )
        state.app_users[email] = app_user
        session.add(app_user)

    _seed_access_scopes(session, state)
    _seed_data_resources(session, state)


def _seed_access_scopes(session: Session, state: SeedState) -> None:
    global_scope = AccessScope(
        id=_id(state.profile, "access-scope", "global", "global"),
        scope_type="global",
        scope_key="global",
        display_name="Global",
        domain=None,
        department_id=None,
        is_system_scope=True,
        created_at=REFERENCE_NOW,
        updated_at=REFERENCE_NOW,
    )
    state.access_scopes[("global", "global")] = global_scope
    session.add(global_scope)

    for department in state.departments:
        scope_key = _scope_key(department.name)
        department_scope = AccessScope(
            id=_id(state.profile, "access-scope", "department", scope_key),
            scope_type="department",
            scope_key=scope_key,
            display_name=department.name,
            domain="it_operations",
            department_id=department.id,
            is_system_scope=True,
            created_at=REFERENCE_NOW,
            updated_at=REFERENCE_NOW,
        )
        state.access_scopes[("department", scope_key)] = department_scope
        session.add(department_scope)

    demo_assignments = {
        "demo.admin@queryops.local": ("global", "global", "manage"),
        "demo.analyst@queryops.local": ("department", "it", "manage"),
        "demo.manager@queryops.local": ("department", "finance", "read"),
        "demo.user@queryops.local": ("department", "sales", "read"),
    }
    for email, (scope_type, scope_key, access_level) in demo_assignments.items():
        user = state.app_users[email]
        scope = state.access_scopes[(scope_type, scope_key)]
        session.add(
            UserAccessScope(
                user_id=user.id,
                scope_id=scope.id,
                access_level=access_level,
                is_default=True,
                created_at=REFERENCE_NOW,
            )
        )


def _seed_data_resources(session: Session, state: SeedState) -> None:
    for (
        table_name,
        display_name,
        sensitivity_level,
        scope_type,
        scope_column,
        is_queryable,
        is_exportable,
        llm_exposure_level,
    ) in DATA_RESOURCE_SPECS:
        session.add(
            DataResource(
                id=_id(state.profile, "data-resource", table_name),
                resource_type="table",
                domain="it_operations",
                schema_name="public",
                table_name=table_name,
                column_name=None,
                display_name=display_name,
                sensitivity_level=sensitivity_level,
                scope_type=scope_type,
                scope_column=scope_column,
                is_queryable=is_queryable,
                is_exportable=is_exportable,
                llm_exposure_level=llm_exposure_level,
                resource_metadata=None,
                created_at=REFERENCE_NOW,
                updated_at=REFERENCE_NOW,
            )
        )


def _seed_departments(session: Session, state: SeedState) -> None:
    for name in DEPARTMENT_NAMES[: state.profile.departments]:
        department = Department(
            id=_id(state.profile, "department", name),
            name=name,
            description=f"{name} department",
            created_at=REFERENCE_NOW,
            updated_at=REFERENCE_NOW,
        )
        state.departments.append(department)
        session.add(department)


def _seed_directory_users(session: Session, state: SeedState) -> None:
    inactive_count = max(8, state.profile.human_directory_users // 10)
    terminated_count = max(4, state.profile.human_directory_users // 20)
    managers_by_department: dict[uuid.UUID, uuid.UUID] = {}

    for index in range(state.profile.human_directory_users):
        department = state.departments[
            _weighted_index(index, len(state.departments), DEPARTMENT_WEIGHTS)
        ]
        manager_id = managers_by_department.get(department.id)
        user_id = _id(state.profile, "directory-user-human", str(index))
        if manager_id is None:
            managers_by_department[department.id] = user_id

        first_name = state.fake.first_name()
        last_name = state.fake.last_name()
        is_terminated = index < terminated_count
        is_inactive = index < inactive_count
        planned_last_login_at = _planned_last_login_at(
            index,
            is_service=False,
            is_inactive=is_inactive,
            is_terminated=is_terminated,
        )
        user = DirectoryUser(
            id=user_id,
            employee_number=f"E{index + 1:06d}",
            email=f"{first_name}.{last_name}.{index + 1:04d}@queryops.example".lower(),
            full_name=f"{first_name} {last_name}",
            department_id=department.id,
            manager_id=None if manager_id == user_id else manager_id,
            job_title=_job_title(index),
            account_type="human",
            employee_status="terminated" if is_terminated else "active",
            account_status="active" if index < terminated_count else "disabled" if index % 19 == 0 else "active",
            last_login_at=planned_last_login_at,
            created_at=REFERENCE_NOW - timedelta(days=900 - index % 365),
            updated_at=REFERENCE_NOW,
        )
        state.directory_user_positions[user.id] = index
        state.human_users.append(user)
        state.directory_users.append(user)
        session.add(user)

    for index in range(state.profile.service_accounts):
        directory_index = state.profile.human_directory_users + index
        department = state.departments[
            _weighted_index(directory_index, len(state.departments), DEPARTMENT_WEIGHTS)
        ]
        planned_last_login_at = _planned_last_login_at(
            directory_index,
            is_service=True,
            is_inactive=True,
            is_terminated=False,
        )
        user = DirectoryUser(
            id=_id(state.profile, "directory-user-service", str(index)),
            employee_number=f"SVC{index + 1:04d}",
            email=f"svc-{department.name.lower()}-{index + 1:03d}@queryops.example",
            full_name=f"{department.name} Service Account {index + 1}",
            department_id=department.id,
            manager_id=None,
            job_title="Service Account",
            account_type="service",
            employee_status="active",
            account_status="active",
            last_login_at=planned_last_login_at,
            created_at=REFERENCE_NOW - timedelta(days=500 - index),
            updated_at=REFERENCE_NOW,
        )
        state.directory_user_positions[user.id] = directory_index
        state.service_accounts.append(user)
        state.directory_users.append(user)
        session.add(user)


def _seed_groups(session: Session, state: SeedState) -> None:
    department_by_name = {department.name: department for department in state.departments}
    for index, spec in enumerate(GROUP_SPECS[: state.profile.groups]):
        name, group_type, department_name, is_privileged, risk_level = spec
        department = department_by_name.get(department_name or "")
        group = Group(
            id=_id(state.profile, "group", str(index), name),
            name=name,
            description=f"Synthetic {name} group",
            group_type=group_type,
            department_id=department.id if department is not None else None,
            is_privileged=is_privileged,
            risk_level=risk_level,
            created_at=REFERENCE_NOW,
            updated_at=REFERENCE_NOW,
        )
        state.groups.append(group)
        session.add(group)


def _seed_user_group_memberships(session: Session, state: SeedState) -> None:
    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    privileged_groups = [group for group in state.groups if group.is_privileged]
    regular_groups = [group for group in state.groups if not group.is_privileged] or state.groups
    actor_users = state.human_users[: max(1, min(8, len(state.human_users)))]

    def add_membership(user: DirectoryUser, group: Group, index: int) -> None:
        key = (user.id, group.id)
        if key in pairs or len(pairs) >= state.profile.user_group_memberships:
            return
        pairs.add(key)
        session.add(
            UserGroupMembership(
                user_id=user.id,
                group_id=group.id,
                department_id=user.department_id,
                added_at=REFERENCE_NOW - timedelta(days=index % 120),
                added_by_user_id=actor_users[index % len(actor_users)].id,
            )
        )

    for index, user in enumerate(state.human_users[: max(6, len(state.human_users) // 12)]):
        add_membership(user, privileged_groups[index % len(privileged_groups)], index)

    index = 0
    while len(pairs) < state.profile.user_group_memberships:
        user = state.directory_users[index % len(state.directory_users)]
        group_pool = regular_groups if index % 3 else state.groups
        group = group_pool[index % len(group_pool)]
        add_membership(user, group, index)
        index += 1


def _seed_devices(session: Session, state: SeedState) -> None:
    for index in range(state.profile.devices):
        if index < len(state.directory_users):
            assigned_user = state.directory_users[index]
        else:
            user_index = _weighted_index(
                index * 3,
                len(state.directory_users),
                _directory_user_weights(state),
            )
            assigned_user = state.directory_users[user_index]
        os_name, os_version = OS_PROFILES[
            _weighted_index(index, len(OS_PROFILES), OS_WEIGHTS)
        ]
        device_type = ["laptop", "desktop", "mobile", "server"][
            _weighted_index(index, 4, DEVICE_TYPE_WEIGHTS)
        ]
        stale = index < max(8, state.profile.devices // 8)
        non_compliant = index % 7 == 0 or stale
        device = Device(
            id=_id(state.profile, "device", str(index)),
            assigned_user_id=assigned_user.id,
            department_id=assigned_user.department_id,
            hostname=f"QOPS-{index + 1:05d}",
            os=os_name,
            os_version=os_version,
            device_type=device_type,
            last_seen_at=(
                REFERENCE_NOW - timedelta(days=45 + index % 40)
                if stale
                else REFERENCE_NOW - timedelta(days=index % 20)
            ),
            compliance_status="non_compliant" if non_compliant else "compliant",
            encryption_enabled=index % 11 != 0,
            antivirus_status=(
                "missing" if index % 13 == 0 else "outdated" if index % 7 == 0 else "healthy"
            ),
            created_at=REFERENCE_NOW - timedelta(days=500 - index % 300),
            updated_at=REFERENCE_NOW,
        )
        state.devices.append(device)
        state.devices_by_user.setdefault(assigned_user.id, []).append(device)
        session.add(device)


def _seed_licenses(session: Session, state: SeedState) -> None:
    for index, (product_name, vendor, monthly_cost, is_mandatory) in enumerate(
        LICENSE_PRODUCTS[: state.profile.licenses]
    ):
        license_record = License(
            id=_id(state.profile, "license", product_name),
            product_name=product_name,
            vendor=vendor,
            monthly_cost_usd=monthly_cost,
            is_mandatory_default=is_mandatory,
            created_at=REFERENCE_NOW,
            updated_at=REFERENCE_NOW,
        )
        state.licenses.append(license_record)
        session.add(license_record)


def _seed_license_assignments(session: Session, state: SeedState) -> None:
    inactive_users = [
        user
        for user in state.human_users
        if user.last_login_at is not None
        and user.last_login_at < REFERENCE_NOW - timedelta(days=90)
    ]
    users_for_assignments = inactive_users + state.directory_users
    admin_user = state.app_users["demo.admin@queryops.local"]

    for index in range(state.profile.license_assignments):
        user = users_for_assignments[(index * 17) % len(users_for_assignments)]
        license_record = state.licenses[
            _weighted_index(index, len(state.licenses), LICENSE_ASSIGNMENT_WEIGHTS)
        ]
        old_unused = index < max(12, state.profile.license_assignments // 8)
        status = "reclaimed" if index % 29 == 0 else "suspended" if index % 37 == 0 else "active"
        if old_unused:
            last_used_at = REFERENCE_NOW - timedelta(days=120 + index % 60)
            assigned_at = last_used_at - timedelta(days=30 + index % 90)
        else:
            assigned_at = REFERENCE_NOW - timedelta(days=20 + (index * 7) % 240)
            last_used_at = REFERENCE_NOW - timedelta(days=(index * 11) % 55)
            if last_used_at < assigned_at:
                days_after_assignment = max(1, min(14, (REFERENCE_NOW - assigned_at).days))
                last_used_at = min(
                    assigned_at + timedelta(days=days_after_assignment),
                    REFERENCE_NOW,
                )
        reclaimed_at = None
        if status == "reclaimed":
            reclaimed_at = max(
                assigned_at + timedelta(days=1),
                REFERENCE_NOW - timedelta(days=index % 30),
            )
            reclaimed_at = min(reclaimed_at, REFERENCE_NOW)
            if last_used_at > reclaimed_at:
                last_used_at = reclaimed_at
        assignment = LicenseAssignment(
            id=_id(state.profile, "license-assignment", str(index)),
            user_id=user.id,
            license_id=license_record.id,
            department_id=user.department_id,
            assigned_at=assigned_at,
            last_used_at=last_used_at,
            last_checked_at=REFERENCE_NOW - timedelta(days=index % 7),
            status=status,
            is_mandatory=license_record.is_mandatory_default or index % 17 == 0,
            is_exception=index % 23 == 0,
            reclaimed_at=reclaimed_at,
            reclaimed_by_app_user_id=admin_user.id if status == "reclaimed" else None,
        )
        state.license_assignments.append(assignment)
        session.add(assignment)


def _seed_login_events(session: Session, state: SeedState) -> None:
    cluster_users = state.human_users[: max(3, min(10, len(state.human_users) // 8))]
    event_index = 0

    for user in state.directory_users:
        _add_login_event(
            session,
            state,
            event_index,
            user,
            event_type="success",
            occurred_at=user.last_login_at or REFERENCE_NOW,
            failure_reason=None,
        )
        event_index += 1

    cluster_event_count = min(
        state.profile.login_events - event_index,
        len(cluster_users) * 6,
    )
    for cluster_index in range(cluster_event_count):
        user = cluster_users[cluster_index // 6]
        _add_login_event(
            session,
            state,
            event_index,
            user,
            event_type="failed",
            occurred_at=REFERENCE_NOW - timedelta(days=2, minutes=cluster_index),
            failure_reason="invalid_password",
        )
        event_index += 1

    while event_index < state.profile.login_events:
        user = state.directory_users[(event_index * 19) % len(state.directory_users)]
        event_type = "failed" if event_index % 11 == 0 else "success"
        if event_type == "success":
            latest_success_at = state.latest_success_login_by_user[user.id]
            occurred_at = latest_success_at - timedelta(
                days=1 + event_index % 45,
                minutes=event_index % 1440,
            )
            failure_reason = None
        else:
            occurred_at = REFERENCE_NOW - timedelta(
                days=(event_index * 7) % 120,
                minutes=event_index % 1440,
            )
            failure_reason = "mfa_failed"
        _add_login_event(
            session,
            state,
            event_index,
            user,
            event_type=event_type,
            occurred_at=occurred_at,
            failure_reason=failure_reason,
        )
        event_index += 1

    _sync_last_login_at_from_success_events(state)


def _seed_software_installs(session: Session, state: SeedState) -> None:
    for index in range(state.profile.software_installs):
        device_index = (index * 37) % len(state.devices)
        device = state.devices[device_index]
        software_index = (index // len(state.devices) + device_index * 5) % len(
            SOFTWARE_CATALOG
        )
        software_name, vendor = SOFTWARE_CATALOG[software_index]
        risky = index < max(20, state.profile.software_installs // 10)
        session.add(
            SoftwareInstall(
                id=_id(state.profile, "software-install", str(index)),
                device_id=device.id,
                department_id=device.department_id,
                software_name=software_name,
                vendor=vendor,
                version=f"{1 + index % 12}.{index % 10}.{index % 20}",
                installed_at=REFERENCE_NOW - timedelta(days=300 - index % 250),
                is_outdated=risky or index % 9 == 0,
                is_unsupported=(index % 17 == 0) or (risky and index % 3 == 0),
                risk_level="critical" if risky and index % 5 == 0 else "high" if risky else "low",
            )
        )


def _seed_support_tickets(session: Session, state: SeedState) -> None:
    for index in range(state.profile.support_tickets):
        requester = state.directory_users[index % len(state.directory_users)]
        assignee = state.human_users[(index + 3) % len(state.human_users)]
        high_open = index < max(5, state.profile.support_tickets // 10)
        status = "open" if high_open else ["open", "in_progress", "resolved", "closed"][index % 4]
        opened_at = REFERENCE_NOW - timedelta(days=45 + index % 30) if high_open else REFERENCE_NOW - timedelta(days=index % 25)
        resolved_at = None
        if status not in ["open", "in_progress"]:
            resolved_at = min(
                opened_at + timedelta(days=2 + index % 5),
                REFERENCE_NOW,
            )
        session.add(
            SupportTicket(
                id=_id(state.profile, "support-ticket", str(index)),
                requester_user_id=requester.id,
                assignee_user_id=assignee.id,
                department_id=requester.department_id,
                title=f"{TICKET_CATEGORIES[index % len(TICKET_CATEGORIES)].replace('_', ' ').title()} #{index + 1}",
                description="Synthetic IT support ticket",
                category=TICKET_CATEGORIES[index % len(TICKET_CATEGORIES)],
                priority="critical" if high_open and index % 2 == 0 else "high" if high_open else ["low", "medium", "high"][index % 3],
                status=status,
                opened_at=opened_at,
                resolved_at=resolved_at,
                created_at=opened_at,
                updated_at=REFERENCE_NOW,
            )
        )


def _seed_security_events(session: Session, state: SeedState) -> None:
    for index in range(state.profile.security_events):
        user = state.directory_users[index % len(state.directory_users)] if index % 4 != 0 else None
        device = state.devices[index % len(state.devices)] if index % 3 != 0 else None
        department_id = (
            user.department_id
            if user is not None
            else device.department_id
            if device is not None
            else state.departments[index % len(state.departments)].id
        )
        high_open = index < max(6, state.profile.security_events // 8)
        session.add(
            SecurityEvent(
                id=_id(state.profile, "security-event", str(index)),
                user_id=user.id if user is not None else None,
                device_id=device.id if device is not None else None,
                department_id=department_id,
                event_type=SECURITY_EVENT_TYPES[index % len(SECURITY_EVENT_TYPES)],
                severity="critical" if high_open and index % 2 == 0 else "high" if high_open else ["low", "medium", "high"][index % 3],
                description="Synthetic security event",
                occurred_at=REFERENCE_NOW - timedelta(days=index % 90),
                status="open" if high_open else ["open", "investigating", "resolved", "false_positive"][index % 4],
                event_metadata={"source": "seed", "sequence": index},
            )
        )


def _seed_it_audit_events(session: Session, state: SeedState) -> None:
    for index in range(state.profile.it_audit_events):
        actor = state.human_users[index % len(state.human_users)] if index % 5 else None
        target = state.directory_users[(index + 7) % len(state.directory_users)]
        resource_type = ["directory_user", "device", "license_assignment", "support_ticket"][index % 4]
        resource_id = _resource_id_for_audit(resource_type, index, state)
        session.add(
            ItAuditEvent(
                id=_id(state.profile, "it-audit-event", str(index)),
                actor_user_id=actor.id if actor is not None else None,
                target_user_id=target.id,
                department_id=target.department_id,
                event_type=IT_AUDIT_EVENT_TYPES[index % len(IT_AUDIT_EVENT_TYPES)],
                resource_type=resource_type,
                resource_id=resource_id,
                description="Synthetic IT audit event",
                occurred_at=REFERENCE_NOW - timedelta(days=index % 180, minutes=index % 1440),
                event_metadata={"source": "seed", "sequence": index},
            )
        )


def _resource_id_for_audit(resource_type: str, index: int, state: SeedState) -> uuid.UUID:
    if resource_type == "directory_user":
        return state.directory_users[index % len(state.directory_users)].id
    if resource_type == "device":
        return state.devices[index % len(state.devices)].id
    if resource_type == "license_assignment":
        return state.license_assignments[index % len(state.license_assignments)].id
    return _id(state.profile, "support-ticket", str(index % state.profile.support_tickets))


def _add_login_event(
    session: Session,
    state: SeedState,
    index: int,
    user: DirectoryUser,
    *,
    event_type: str,
    occurred_at: datetime,
    failure_reason: str | None,
) -> None:
    device = _device_for_login_event(user, index, state)
    session.add(
        LoginEvent(
            id=_id(state.profile, "login-event", str(index)),
            user_id=user.id,
            department_id=user.department_id,
            event_type=event_type,
            source_ip=f"10.{index % 250}.{(index * 7) % 250}.{(index * 13) % 250}",
            country=_login_country(index),
            device_id=device.id if device is not None else None,
            occurred_at=occurred_at,
            failure_reason=failure_reason,
        )
    )
    if event_type == "success":
        existing = state.latest_success_login_by_user.get(user.id)
        if existing is None or occurred_at > existing:
            state.latest_success_login_by_user[user.id] = occurred_at


def _device_for_login_event(
    user: DirectoryUser,
    index: int,
    state: SeedState,
) -> Device | None:
    if index % 5 == 0:
        return None

    if index % 20 == 1:
        for offset in range(len(state.devices)):
            device = state.devices[(index * 7 + offset) % len(state.devices)]
            if device.assigned_user_id != user.id:
                return device

    own_devices = state.devices_by_user.get(user.id, [])
    if not own_devices:
        return None
    return own_devices[(index // 5) % len(own_devices)]


def _sync_last_login_at_from_success_events(state: SeedState) -> None:
    for user in state.directory_users:
        user.last_login_at = state.latest_success_login_by_user[user.id]
        user.updated_at = REFERENCE_NOW


def _planned_last_login_at(
    index: int,
    *,
    is_service: bool,
    is_inactive: bool,
    is_terminated: bool,
) -> datetime:
    if is_service:
        return REFERENCE_NOW - timedelta(days=120 + index % 45)
    if is_terminated:
        return REFERENCE_NOW - timedelta(days=125 + index % 35)
    if is_inactive:
        return REFERENCE_NOW - timedelta(days=100 + index % 40)
    return REFERENCE_NOW - timedelta(days=(index * 7) % 45, minutes=index % 240)


def _login_country(index: int) -> str:
    countries = ["US", "IL", "GB", "DE", "CA"]
    return countries[_weighted_index(index, len(countries), LOGIN_COUNTRY_WEIGHTS)]


def _directory_user_weights(state: SeedState) -> list[int]:
    weights = []
    for user in state.directory_users:
        position = state.directory_user_positions[user.id]
        if user.account_type == "service":
            weights.append(1)
        elif user.employee_status == "terminated":
            weights.append(2)
        else:
            weights.append(4 + position % 5)
    return weights


def _weighted_index(index: int, item_count: int, weights: list[int]) -> int:
    active_weights = weights[:item_count]
    total_weight = sum(active_weights)
    bucket = (index * 37) % total_weight
    running_total = 0
    for item_index, weight in enumerate(active_weights):
        running_total += weight
        if bucket < running_total:
            return item_index
    return item_count - 1


def _has_existing_seed_data(session: Session) -> bool:
    return any(count > 0 for count in table_counts(session).values())


def _count(session: Session, statement) -> int:
    return len(session.scalars(statement).all())


def _id(profile: SeedProfile, *parts: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, ":".join((profile.name, *parts)))


def _scope_key(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _job_title(index: int) -> str:
    titles = [
        "Systems Analyst",
        "Finance Manager",
        "HR Specialist",
        "Sales Representative",
        "Software Engineer",
        "Operations Coordinator",
        "Support Engineer",
        "Legal Counsel",
    ]
    return titles[index % len(titles)]
