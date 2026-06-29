from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
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
from app.domains.it_operations.seed import (
    REFERENCE_NOW,
    reset_seeded_data,
    seed_database,
    seed_fingerprint,
)
from app.domains.it_operations.seed_profiles import get_seed_profile
from app.models.product import AppUser, Permission, Role, RolePermission


DEMO_USER_DEPARTMENTS = {
    "demo.admin@queryops.local": "IT",
    "demo.analyst@queryops.local": "IT",
    "demo.manager@queryops.local": "Finance",
    "demo.user@queryops.local": "Sales",
}

DEMO_USER_ROLES = {
    "demo.admin@queryops.local": "admin",
    "demo.analyst@queryops.local": "analyst",
    "demo.manager@queryops.local": "manager",
    "demo.user@queryops.local": "user",
}

REQUIRED_PERMISSION_KEYS = {
    "can_use_query_templates",
    "can_run_free_query",
    "can_query_department_data",
    "can_query_global_data",
    "can_query_product_tables",
    "can_view_sql",
    "can_view_query_history_department",
    "can_star_dashboard",
    "can_create_personal_dashboard",
    "can_create_department_dashboard",
    "can_create_global_dashboard",
    "can_manage_department_dashboard",
    "can_manage_global_dashboard",
    "can_create_card",
    "can_request_action",
    "can_approve_department_action",
    "can_approve_global_action",
    "can_approve_policy_override",
    "can_self_approve_admin_action",
    "can_manage_users",
    "can_disable_app_user",
    "can_downgrade_user_role",
    "can_approve_role_requests",
    "can_view_department_audit",
    "can_view_global_audit",
    "can_view_department_evaluation",
    "can_view_global_evaluation",
    "can_view_own_data",
    "can_view_department_data",
    "can_view_global_data",
}

EXPECTED_ROLE_PERMISSIONS = {
    "user": {
        "can_use_query_templates",
        "can_star_dashboard",
        "can_view_own_data",
    },
    "manager": {
        "can_use_query_templates",
        "can_star_dashboard",
        "can_view_own_data",
        "can_run_free_query",
        "can_query_department_data",
        "can_view_department_data",
        "can_create_personal_dashboard",
        "can_request_action",
        "can_view_department_evaluation",
    },
    "analyst": {
        "can_use_query_templates",
        "can_star_dashboard",
        "can_view_own_data",
        "can_run_free_query",
        "can_query_department_data",
        "can_view_department_data",
        "can_create_personal_dashboard",
        "can_request_action",
        "can_view_department_evaluation",
        "can_view_sql",
        "can_create_card",
        "can_create_department_dashboard",
        "can_manage_department_dashboard",
        "can_view_query_history_department",
        "can_view_department_audit",
        "can_approve_department_action",
    },
    "admin": REQUIRED_PERMISSION_KEYS,
}

COUNT_MODELS = {
    "app_users": AppUser,
    "roles": Role,
    "permissions": Permission,
    "role_permissions": RolePermission,
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


def test_seed_profiles_define_expected_target_counts() -> None:
    small = get_seed_profile("small")
    medium = get_seed_profile("medium")

    assert small.departments == 4
    assert small.human_directory_users == 40
    assert small.service_accounts == 8
    assert small.total_directory_users == 48
    assert small.devices == 60
    assert small.licenses == 8
    assert small.license_assignments == 100
    assert small.login_events == 500
    assert small.support_tickets == 50
    assert small.groups == 10
    assert small.user_group_memberships == 90
    assert small.security_events == 40
    assert small.software_installs == 160
    assert small.it_audit_events == 120
    assert small.app_users == 4

    assert medium.departments == 8
    assert medium.human_directory_users == 600
    assert medium.service_accounts == 80
    assert medium.total_directory_users == 680
    assert medium.devices == 900
    assert medium.license_assignments == 1200
    assert medium.login_events == 10000
    assert medium.software_installs == 2000
    assert medium.it_audit_events == 1000


def test_small_seed_creates_expected_counts() -> None:
    with session_scope() as session:
        summary = seed_database(session, profile_name="small", reset=True)

        assert summary.table_counts == expected_counts("small")
        assert table_counts(session) == expected_counts("small")


def test_medium_seed_creates_expected_counts() -> None:
    with session_scope() as session:
        summary = seed_database(session, profile_name="medium", reset=True)

        assert summary.table_counts == expected_counts("medium")
        assert table_counts(session) == expected_counts("medium")


def test_small_seed_is_deterministic_across_reset() -> None:
    with session_scope() as session:
        first_summary = seed_database(session, profile_name="small", reset=True)
        first_fingerprint = seed_fingerprint(session)

        second_summary = seed_database(session, profile_name="small", reset=True)
        second_fingerprint = seed_fingerprint(session)

        assert second_summary.table_counts == first_summary.table_counts
        assert second_summary.anomaly_counts == first_summary.anomaly_counts
        assert second_fingerprint == first_fingerprint


def test_seed_rows_have_valid_relationships() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)

        department_ids = set(session.scalars(select(Department.id)))
        directory_user_ids = set(session.scalars(select(DirectoryUser.id)))
        device_ids = set(session.scalars(select(Device.id)))
        license_ids = set(session.scalars(select(License.id)))
        group_ids = set(session.scalars(select(Group.id)))
        app_user_ids = set(session.scalars(select(AppUser.id)))

        for user in session.scalars(select(DirectoryUser)):
            assert user.department_id in department_ids
            assert user.manager_id is None or user.manager_id in directory_user_ids

        for assignment in session.scalars(select(LicenseAssignment)):
            assert assignment.user_id in directory_user_ids
            assert assignment.license_id in license_ids
            assert assignment.department_id in department_ids
            assert (
                assignment.reclaimed_by_app_user_id is None
                or assignment.reclaimed_by_app_user_id in app_user_ids
            )

        for event in session.scalars(select(LoginEvent)):
            assert event.user_id in directory_user_ids
            assert event.department_id in department_ids
            assert event.device_id is None or event.device_id in device_ids

        for install in session.scalars(select(SoftwareInstall)):
            assert install.device_id in device_ids
            assert install.department_id in department_ids

        for membership in session.scalars(select(UserGroupMembership)):
            assert membership.user_id in directory_user_ids
            assert membership.group_id in group_ids
            assert membership.department_id in department_ids
            assert (
                membership.added_by_user_id is None
                or membership.added_by_user_id in directory_user_ids
            )

        for audit_event in session.scalars(select(ItAuditEvent)):
            assert audit_event.actor_user_id is None or audit_event.actor_user_id in directory_user_ids
            assert audit_event.target_user_id is None or audit_event.target_user_id in directory_user_ids
            assert audit_event.department_id is None or audit_event.department_id in department_ids


def test_demo_app_users_reference_valid_departments_in_small_and_medium_seed() -> None:
    for profile_name in ("small", "medium"):
        with session_scope() as session:
            seed_database(session, profile_name=profile_name, reset=True)

            departments_by_id = {
                department.id: department.name
                for department in session.scalars(select(Department))
            }
            demo_users = session.scalars(
                select(AppUser).where(AppUser.email.in_(DEMO_USER_DEPARTMENTS))
            ).all()

            assert {user.email for user in demo_users} == set(DEMO_USER_DEPARTMENTS)
            for user in demo_users:
                assert user.department_id in departments_by_id
                assert departments_by_id[user.department_id] == DEMO_USER_DEPARTMENTS[user.email]


def test_seed_creates_required_roles_permissions_and_role_permissions() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)

        roles = {role.name: role for role in session.scalars(select(Role))}
        assert set(roles) == set(EXPECTED_ROLE_PERMISSIONS)
        assert all(role.is_system_role for role in roles.values())
        assert all(role.description for role in roles.values())

        permissions = {
            permission.key: permission
            for permission in session.scalars(select(Permission))
        }
        assert set(permissions) == REQUIRED_PERMISSION_KEYS
        assert all(permission.category for permission in permissions.values())
        assert all(permission.description for permission in permissions.values())

        rows = session.execute(
            select(Role.name, Permission.key)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
        ).all()
        actual_mapping: dict[str, set[str]] = {
            role_name: set() for role_name in EXPECTED_ROLE_PERMISSIONS
        }
        for role_name, permission_key in rows:
            actual_mapping[role_name].add(permission_key)

        assert actual_mapping == EXPECTED_ROLE_PERMISSIONS


def test_demo_app_users_are_assigned_expected_roles() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)

        rows = session.execute(
            select(AppUser.email, Role.name)
            .join(Role, Role.id == AppUser.role_id)
            .where(AppUser.email.in_(DEMO_USER_ROLES))
        ).all()

        assert dict(rows) == DEMO_USER_ROLES


def test_directory_user_last_login_matches_latest_successful_login() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)

        latest_success = (
            select(
                LoginEvent.user_id.label("user_id"),
                func.max(LoginEvent.occurred_at).label("latest_success_at"),
            )
            .where(LoginEvent.event_type == "success")
            .group_by(LoginEvent.user_id)
            .subquery()
        )
        rows = session.execute(
            select(
                DirectoryUser.id,
                DirectoryUser.last_login_at,
                latest_success.c.latest_success_at,
            ).join(latest_success, latest_success.c.user_id == DirectoryUser.id)
        ).all()

        assert len(rows) == get_seed_profile("small").total_directory_users
        assert all(last_login_at == latest_success_at for _id, last_login_at, latest_success_at in rows)


def test_login_events_mostly_use_assigned_user_devices() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)

        with_device_count = session.scalar(
            select(func.count()).select_from(LoginEvent).where(LoginEvent.device_id.is_not(None))
        )
        foreign_device_count = session.scalar(
            select(func.count())
            .select_from(LoginEvent)
            .join(Device, LoginEvent.device_id == Device.id)
            .where(LoginEvent.user_id != Device.assigned_user_id)
        )

        assert with_device_count and with_device_count > 0
        assert foreign_device_count and foreign_device_count > 0
        foreign_ratio = foreign_device_count / with_device_count
        assert 0.02 <= foreign_ratio <= 0.08


def test_seed_dates_are_chronologically_valid() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)

        license_last_used_before_assignment = session.scalar(
            select(func.count())
            .select_from(LicenseAssignment)
            .where(
                LicenseAssignment.last_used_at.is_not(None),
                LicenseAssignment.last_used_at < LicenseAssignment.assigned_at,
            )
        )
        future_resolved_tickets = session.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.resolved_at > REFERENCE_NOW)
        )
        resolved_before_opened = session.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(
                SupportTicket.resolved_at.is_not(None),
                SupportTicket.resolved_at < SupportTicket.opened_at,
            )
        )

        assert license_last_used_before_assignment == 0
        assert future_resolved_tickets == 0
        assert resolved_before_opened == 0


def test_software_installs_are_current_inventory_without_duplicate_packages() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)

        duplicate_groups = session.execute(
            select(
                SoftwareInstall.device_id,
                SoftwareInstall.software_name,
                SoftwareInstall.vendor,
                func.count().label("install_count"),
            )
            .group_by(
                SoftwareInstall.device_id,
                SoftwareInstall.software_name,
                SoftwareInstall.vendor,
            )
            .having(func.count() > 1)
        ).all()

        assert duplicate_groups == []


def test_seed_includes_required_anomalies() -> None:
    with session_scope() as session:
        summary = seed_database(session, profile_name="small", reset=True)

        assert summary.anomaly_counts["inactive_licensed_users"] > 0
        assert summary.anomaly_counts["terminated_active_accounts"] > 0
        assert summary.anomaly_counts["terminated_users_with_devices"] > 0
        assert summary.anomaly_counts["inactive_privileged_users"] > 0
        assert summary.anomaly_counts["unused_licenses_over_90_days"] > 0
        assert summary.anomaly_counts["mandatory_license_assignments"] > 0
        assert summary.anomaly_counts["exception_license_assignments"] > 0
        assert summary.anomaly_counts["stale_devices"] > 0
        assert summary.anomaly_counts["risky_software_installs"] > 0
        assert summary.anomaly_counts["high_priority_open_tickets"] > 0
        assert summary.anomaly_counts["failed_login_clusters"] > 0
        assert summary.anomaly_counts["high_severity_open_security_events"] > 0


def test_seed_requires_reset_when_data_already_exists() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)

        try:
            seed_database(session, profile_name="small", reset=False)
        except RuntimeError as exc:
            assert "--reset" in str(exc)
        else:
            raise AssertionError("Expected seed_database to fail without reset")


def test_reset_seeded_data_clears_seeded_tables() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)

        reset_seeded_data(session)
        session.commit()

        assert table_counts(session) == {table_name: 0 for table_name in COUNT_MODELS}


def test_seed_code_has_no_llm_or_network_dependency() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    seed_sources = [
        backend_dir / "app" / "domains" / "it_operations" / "seed.py",
        backend_dir / "app" / "domains" / "it_operations" / "seed_profiles.py",
        backend_dir / "scripts" / "seed_it_operations.py",
    ]
    banned_imports = [
        "import openai",
        "from openai",
        "import anthropic",
        "from anthropic",
        "import groq",
        "from groq",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "import urllib",
        "from urllib",
        "import socket",
        "from socket",
        "import subprocess",
        "from subprocess",
    ]

    for source in seed_sources:
        text = source.read_text().lower()
        assert all(token not in text for token in banned_imports)


@contextmanager
def session_scope():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def table_counts(session: Session) -> dict[str, int]:
    return {
        table_name: session.scalar(select(func.count()).select_from(model))
        for table_name, model in COUNT_MODELS.items()
    }


def expected_counts(profile_name: str) -> dict[str, int]:
    profile = get_seed_profile(profile_name)
    return {
        "app_users": profile.app_users,
        "roles": 4,
        "permissions": 30,
        "role_permissions": 58,
        "departments": profile.departments,
        "directory_users": profile.total_directory_users,
        "login_events": profile.login_events,
        "licenses": profile.licenses,
        "license_assignments": profile.license_assignments,
        "devices": profile.devices,
        "software_installs": profile.software_installs,
        "support_tickets": profile.support_tickets,
        "groups": profile.groups,
        "user_group_memberships": profile.user_group_memberships,
        "security_events": profile.security_events,
        "it_audit_events": profile.it_audit_events,
    }
