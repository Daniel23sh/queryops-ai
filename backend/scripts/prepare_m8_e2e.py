from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.domains.it_operations.models import DirectoryUser, LicenseAssignment
from app.models.product import AccessScope, AppUser, UserAccessScope


ANALYST_EMAIL = "demo.analyst@queryops.local"
FINANCE_SCOPE_TYPE = "department"
FINANCE_SCOPE_KEY = "finance"
_SAFE_DATABASE_MARKER = re.compile(
    r"(?:^|[_-])(?:test|dev|e2e)(?:$|[_-])",
    re.IGNORECASE,
)
_ENDPOINT_QUERY_KEYS = frozenset(
    {"database", "dbname", "host", "hostaddr", "port", "service", "servicefile"}
)


class UnsafeE2EDatabaseError(ValueError):
    """Raised before any connection is opened for an unsafe E2E target."""


@dataclass(frozen=True)
class PreparationResult:
    analyst_user_id: str
    finance_scope_id: str
    created: bool
    stabilized_service_assignments: int


def validated_e2e_database_url(
    target_url: str,
    *,
    disposable_opt_in: str | None,
    application_url: str | None,
    application_database_name: str,
) -> str:
    if disposable_opt_in != "1":
        raise UnsafeE2EDatabaseError(
            "Set M8_E2E_DATABASE_DISPOSABLE=1 to permit E2E preparation."
        )

    target = _parse_explicit_postgres_url(target_url, label="M8_E2E_DATABASE_URL")
    if _ENDPOINT_QUERY_KEYS.intersection(target.query):
        raise UnsafeE2EDatabaseError(
            "E2E database URLs cannot override endpoint identity in query parameters."
        )
    if not _is_local_endpoint(target):
        raise UnsafeE2EDatabaseError(
            "M8 E2E preparation requires a loopback local or CI PostgreSQL endpoint."
        )

    database_name = target.database
    assert database_name is not None
    if database_name.lower() == application_database_name.lower():
        raise UnsafeE2EDatabaseError(
            "Refusing to prepare the configured normal application database."
        )
    if _SAFE_DATABASE_MARKER.search(database_name) is None:
        raise UnsafeE2EDatabaseError(
            "The E2E database name must include a test, dev, or e2e marker."
        )

    if application_url:
        application = _parse_explicit_postgres_url(
            application_url,
            label="DATABASE_URL",
        )
        if _ENDPOINT_QUERY_KEYS.intersection(application.query):
            raise UnsafeE2EDatabaseError(
                "Cannot safely compare DATABASE_URL with endpoint query overrides."
            )
        if _database_identity(application) == _database_identity(target):
            raise UnsafeE2EDatabaseError(
                "Refusing to prepare the configured normal application database."
            )

    return target_url


def prepare_e2e_state(session: Session, *, now: datetime) -> PreparationResult:
    analyst = session.scalar(select(AppUser).where(AppUser.email == ANALYST_EMAIL))
    finance = session.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == FINANCE_SCOPE_TYPE,
            AccessScope.scope_key == FINANCE_SCOPE_KEY,
        )
    )
    if analyst is None or finance is None:
        raise RuntimeError(
            "Run the deterministic small seed before M8 E2E scope preparation."
        )

    assignment = session.get(
        UserAccessScope,
        {"user_id": analyst.id, "scope_id": finance.id},
    )
    created = assignment is None
    if assignment is None:
        session.add(
            UserAccessScope(
                user_id=analyst.id,
                scope_id=finance.id,
                access_level="manage",
                is_default=False,
            )
        )
    else:
        assignment.access_level = "manage"

    service_assignments = session.scalars(
        select(LicenseAssignment)
        .join(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
        .where(
            LicenseAssignment.department_id == finance.department_id,
            LicenseAssignment.status == "active",
            LicenseAssignment.is_mandatory.is_(False),
            DirectoryUser.account_type == "service",
            or_(
                LicenseAssignment.last_used_at.is_(None),
                LicenseAssignment.last_used_at < now - timedelta(days=60),
            ),
        )
    ).all()
    for service_assignment in service_assignments:
        service_assignment.last_used_at = now

    session.flush()
    return PreparationResult(
        analyst_user_id=str(analyst.id),
        finance_scope_id=str(finance.id),
        created=created,
        stabilized_service_assignments=len(service_assignments),
    )


def _parse_explicit_postgres_url(value: str, *, label: str) -> URL:
    if not value or value.strip() != value:
        raise UnsafeE2EDatabaseError(f"{label} must be an unambiguous explicit URL.")
    try:
        parsed = make_url(value)
    except Exception as exc:
        raise UnsafeE2EDatabaseError(f"{label} is not a valid database URL.") from exc
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        raise UnsafeE2EDatabaseError(
            f"{label} must identify an explicit PostgreSQL database."
        )
    return parsed


def _is_local_endpoint(database_url: URL) -> bool:
    host = (database_url.host or "localhost").rstrip(".").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _database_identity(database_url: URL) -> tuple[str, int, str | None]:
    host = (database_url.host or "localhost").rstrip(".").lower()
    try:
        if ipaddress.ip_address(host).is_loopback:
            host = "localhost"
    except ValueError:
        pass
    return host, database_url.port or 5432, database_url.database


def main() -> None:
    target_url = validated_e2e_database_url(
        os.environ.get("M8_E2E_DATABASE_URL", ""),
        disposable_opt_in=os.environ.get("M8_E2E_DATABASE_DISPOSABLE"),
        application_url=os.environ.get("DATABASE_URL"),
        application_database_name=os.environ.get("POSTGRES_DB", "queryops"),
    )
    engine = create_engine(target_url)
    try:
        with Session(engine) as session:
            now = session.scalar(select(func.now()))
            assert now is not None
            result = prepare_e2e_state(session, now=now)
            session.commit()
    finally:
        engine.dispose()

    status = "created" if result.created else "already present"
    print(
        "M8 E2E Finance scope for Demo Analyst: "
        f"{status} (user={result.analyst_user_id}, scope={result.finance_scope_id}); "
        "Finance service-account reclaim candidates stabilized: "
        f"{result.stabilized_service_assignments}."
    )


if __name__ == "__main__":
    main()
