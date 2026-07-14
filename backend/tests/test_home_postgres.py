from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, or_, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth.access_context import build_user_access_context
from app.db.base import Base
from app.domains.it_operations.models import (
    AccountStatus,
    AccountType,
    AssignmentStatus,
    ComplianceStatus,
    Device,
    DirectoryUser,
    EmployeeStatus,
    License,
    LicenseAssignment,
    SecurityEvent,
    SupportTicket,
    TicketStatus,
)
from app.domains.it_operations.seed import seed_database
from app.models.product import AccessScope, AppUser, UserAccessScope
from app.services.home_overview import (
    OPERATIONAL_METRIC_DEPENDENCIES,
    read_operational_metrics,
)


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"
ALL_OPERATIONAL_METRICS = frozenset(OPERATIONAL_METRIC_DEPENDENCIES)


def test_scoped_home_aggregates_match_only_the_viewers_department_rows(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine) as session:
        manager = _user_by_email(session, "demo.manager@queryops.local")
        access_context = build_user_access_context(manager, session)
        department_ids = {
            scope.department_id
            for scope in access_context.scopes
            if scope.department_id is not None
        }
        expected = _expected_metrics(session, department_ids, now)

        result = read_operational_metrics(
            session,
            access_context,
            ALL_OPERATIONAL_METRICS,
            now,
        )

    assert result.runtime_role == "queryops_query_runtime"
    assert result.transaction_read_only is True
    assert result.row_security_enabled is True
    assert result.metrics == expected


def test_multiple_scopes_aggregate_without_leaking_other_departments(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine) as session:
        manager = _user_by_email(session, "demo.manager@queryops.local")
        sales_scope = session.scalar(
            select(AccessScope).where(
                AccessScope.scope_type == "department",
                AccessScope.scope_key == "sales",
            )
        )
        assert sales_scope is not None
        session.add(
            UserAccessScope(
                user_id=manager.id,
                scope_id=sales_scope.id,
                access_level="read",
                is_default=False,
            )
        )
        session.commit()
        access_context = build_user_access_context(manager, session)
        department_ids = {
            scope.department_id
            for scope in access_context.scopes
            if scope.department_id is not None
        }
        expected = _expected_metrics(session, department_ids, now)

        result = read_operational_metrics(
            session,
            access_context,
            ALL_OPERATIONAL_METRICS,
            now,
        )

    assert len(department_ids) == 2
    assert result.metrics == expected


def test_global_home_aggregates_and_transaction_local_context_do_not_leak(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine) as session:
        admin = _user_by_email(session, "demo.admin@queryops.local")
        access_context = build_user_access_context(admin, session)
        expected = _expected_metrics(session, None, now)

        result = read_operational_metrics(
            session,
            access_context,
            ALL_OPERATIONAL_METRICS,
            now,
        )

    assert result.metrics == expected
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT current_user")) == "queryops"
        assert connection.scalar(
            text("SELECT current_setting('app.current_scope_keys', true)")
        ) in {None, ""}
        assert connection.scalar(
            text("SELECT current_setting('app.has_global_scope', true)")
        ) in {None, ""}


def _expected_metrics(
    session: Session,
    department_ids: set | None,
    now: datetime,
):
    from app.services.home_overview import OperationalMetrics

    def scoped(statement, column):
        if department_ids is None:
            return statement
        return statement.where(column.in_(department_ids))

    active_users = session.scalar(
        scoped(
            select(func.count(DirectoryUser.id)).where(
                DirectoryUser.account_type == AccountType.HUMAN.value,
                DirectoryUser.employee_status == EmployeeStatus.ACTIVE.value,
                DirectoryUser.account_status == AccountStatus.ACTIVE.value,
            ),
            DirectoryUser.department_id,
        )
    )
    device_row = session.execute(
        scoped(
            select(
                func.count(Device.id),
                func.count(Device.id).filter(
                    Device.compliance_status == ComplianceStatus.COMPLIANT.value
                ),
            ),
            Device.department_id,
        )
    ).one()
    device_total = int(device_row[0])
    compliant_devices = int(device_row[1])
    compliance_rate = None
    if device_total:
        compliance_rate = (
            Decimal(compliant_devices) * Decimal("100") / Decimal(device_total)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    license_cost = session.scalar(
        scoped(
            select(func.coalesce(func.sum(License.monthly_cost_usd), Decimal("0.00")))
            .select_from(LicenseAssignment)
            .join(License, License.id == LicenseAssignment.license_id)
            .where(LicenseAssignment.status == AssignmentStatus.ACTIVE.value),
            LicenseAssignment.department_id,
        )
    )
    unused_cutoff = now - timedelta(days=60)
    unused = session.scalar(
        scoped(
            select(func.count(LicenseAssignment.id)).where(
                LicenseAssignment.status == AssignmentStatus.ACTIVE.value,
                LicenseAssignment.is_mandatory.is_(False),
                or_(
                    LicenseAssignment.last_used_at.is_(None),
                    LicenseAssignment.last_used_at < unused_cutoff,
                ),
            ),
            LicenseAssignment.department_id,
        )
    )
    open_tickets = session.scalar(
        scoped(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.status.in_(
                    [TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value]
                )
            ),
            SupportTicket.department_id,
        )
    )
    recent_events = session.scalar(
        scoped(
            select(func.count(SecurityEvent.id)).where(
                SecurityEvent.occurred_at >= now - timedelta(days=30)
            ),
            SecurityEvent.department_id,
        )
    )
    return OperationalMetrics(
        active_human_users=int(active_users or 0),
        device_total=device_total,
        compliant_device_count=compliant_devices,
        device_compliance_rate=compliance_rate,
        monthly_license_cost_usd=Decimal(license_cost or 0).quantize(Decimal("0.01")),
        unused_license_assignments=int(unused or 0),
        open_support_tickets=int(open_tickets or 0),
        security_events_last_30_days=int(recent_events or 0),
    )


def _user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = _postgres_database_url()
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL Home tests require PostgreSQL DATABASE_URL.")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    _run_alembic_upgrade(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, profile_name="small", reset=True)
        session.commit()
    try:
        yield engine
    finally:
        engine.dispose()


def _postgres_database_url() -> str:
    explicit_test_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if explicit_test_url:
        return explicit_test_url
    database_url = os.environ.get("DATABASE_URL") or LOCAL_POSTGRES_URL
    parsed_url = make_url(database_url)
    if (
        not parsed_url.drivername.startswith("postgresql")
        or parsed_url.host not in {"localhost", "127.0.0.1", "::1"}
        or parsed_url.database != "queryops"
    ):
        raise pytest.UsageError(
            "Destructive Home tests require POSTGRES_TEST_DATABASE_URL or the "
            "local queryops PostgreSQL database."
        )
    return database_url


def _run_alembic_upgrade(database_url: str) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(alembic_config, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
