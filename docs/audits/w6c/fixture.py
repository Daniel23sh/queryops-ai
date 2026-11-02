"""Disposable synthetic contrasts only; never used by production or frozen V2."""
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.domains.it_operations.models import (
    Department, Device, DirectoryUser, Group, License, LicenseAssignment,
    LoginEvent, SecurityEvent, SoftwareInstall, SupportTicket, UserGroupMembership,
)


REFERENCE = datetime.fromisoformat("2026-11-02T09:00:00+00:00")


def key(name):
    return uuid5(NAMESPACE_URL, "queryops-w6c-offline-v1/" + name)


def add_contrasts(db):
    departments = {d.name: d.id for d in db.scalars(select(Department))}
    for scope in ("IT", "Finance"):
        department = departments[scope]
        users = (
            ("null-human", "human", "on_leave", "active", None),
            ("old-service", "service", "terminated", "active", REFERENCE - timedelta(days=150)),
            ("old-disabled", "human", "active", "disabled", REFERENCE - timedelta(days=150)),
            ("recent-human", "human", "active", "active", REFERENCE - timedelta(days=2)),
            ("group-only", "human", "on_leave", "active", None),
            ("event-only", "human", "on_leave", "active", None),
            ("neither", "human", "on_leave", "active", None),
        )
        for name, account_type, employee, account, login in users:
            label = scope + "/" + name
            db.add(DirectoryUser(
                id=key(label), employee_number="w6c-" + scope + "-" + name,
                email="w6c-" + scope.lower() + "-" + name + "@example.test",
                full_name="Synthetic W6c " + name, department_id=department,
                account_type=account_type, employee_status=employee,
                account_status=account, last_login_at=login,
            ))
        db.flush()
        devices = (
            ("compliance-only", "non_compliant", "healthy", True, "null-human"),
            ("antivirus-only", "compliant", "missing", True, "old-service"),
            ("encryption-only", "compliant", "healthy", False, "old-disabled"),
            ("all", "non_compliant", "outdated", False, "recent-human"),
            ("none", "compliant", "healthy", True, "null-human"),
            ("no-outdated", "non_compliant", "healthy", True, "null-human"),
        )
        for name, compliance, antivirus, encryption, user in devices:
            label = scope + "/device/" + name
            db.add(Device(
                id=key(label), department_id=department,
                assigned_user_id=key(scope + "/" + user), hostname="w6c-" + scope + "-" + name,
                os="Synthetic", os_version="1", device_type="desktop",
                compliance_status=compliance, antivirus_status=antivirus,
                encryption_enabled=encryption, last_seen_at=REFERENCE - timedelta(days=50),
            ))
            db.flush()
            for index in range(2):
                db.add(SoftwareInstall(
                    id=key(label + "/install/" + str(index)), device_id=key(label),
                    department_id=department, software_name="Synthetic W6c application",
                    version="1", installed_at=REFERENCE - timedelta(days=100),
                    is_outdated=name != "no-outdated", is_unsupported=True, risk_level="high",
                ))
        db.flush()
        for index in range(2):
            db.add(SecurityEvent(
                id=key(scope + "/device-event/" + str(index)),
                device_id=key(scope + "/device/compliance-only"), department_id=department,
                user_id=key(scope + "/null-human"), event_type="synthetic",
                severity="critical", status="open", occurred_at=REFERENCE - timedelta(days=2),
            ))
        db.add(SecurityEvent(
            id=key(scope + "/user-event"), user_id=key(scope + "/event-only"),
            department_id=department, event_type="synthetic", severity="critical",
            status="investigating", occurred_at=REFERENCE - timedelta(days=2),
        ))
        for privileged in (True, False):
            group_id = key(scope + "/group/" + str(privileged))
            db.add(Group(id=group_id, name="w6c-" + scope + str(privileged),
                         group_type="security", department_id=department,
                         is_privileged=privileged, risk_level="low"))
            db.flush()
            for name in ("null-human", "group-only"):
                db.add(UserGroupMembership(user_id=key(scope + "/" + name),
                    group_id=group_id, department_id=department,
                    added_at=REFERENCE - timedelta(days=5)))
        license_id = key(scope + "/license")
        db.add(License(id=license_id, product_name="W6c product " + scope,
                       vendor="Synthetic", monthly_cost_usd=10))
        db.flush()
        for index, mandatory, exception, age in (
            (0, True, True, 1), (1, True, False, 150),
            (2, False, False, 150), (3, False, False, 75),
            (4, False, True, 150), (5, False, False, 1),
        ):
            db.add(LicenseAssignment(
                id=key(scope + "/assignment/" + str(index)),
                user_id=key(scope + "/null-human"), license_id=license_id,
                department_id=department, assigned_at=REFERENCE - timedelta(days=200),
                last_used_at=REFERENCE - timedelta(days=age), status="active",
                is_mandatory=mandatory, is_exception=exception,
            ))
        db.add(LoginEvent(id=key(scope + "/failed-login"), user_id=key(scope + "/null-human"),
                          department_id=department, event_type="failed",
                          occurred_at=REFERENCE - timedelta(days=2)))
        for status, age in (("open", 50), ("in_progress", 50), ("open", 2), ("closed", 50)):
            db.add(SupportTicket(id=key(scope + "/ticket/" + status + str(age)),
                department_id=department, title="Synthetic W6c ticket", category="synthetic",
                priority="low", status=status, opened_at=REFERENCE - timedelta(days=age)))
    db.flush()
