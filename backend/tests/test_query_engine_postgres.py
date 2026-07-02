from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth.access_context import build_user_access_context
from app.db.base import Base
from app.domains.it_operations.models import Device, SupportTicket
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser, QueryRun
from app.query_engine.llm_provider import SQLGenerationResult
from app.query_engine.service import QueryEngineRequest, QueryEngineService


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"


def test_manager_scoped_template_query_returns_only_assigned_department_rows(
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    with Session(postgres_engine) as session:
        manager = user_by_email(session, "demo.manager@queryops.local")
        access_context = build_user_access_context(manager, session)
        expected_rows = expected_support_ticket_rows(
            session,
            department_id=access_context.default_scope.department_id,
        )

        result = QueryEngineService().run(
            session,
            manager,
            QueryEngineRequest(
                question="How many open support tickets exist in my department by priority?",
                template_id="open_support_tickets_by_department",
            ),
        )
        query_run = latest_query_run(session, manager)

    assert result.status == "succeeded"
    assert result.rows == expected_rows
    assert result.row_count == len(expected_rows)
    assert query_run.status == "succeeded"
    assert query_run.generated_sql is not None
    assert query_run.executed_sql is not None
    assert "LIMIT" in query_run.executed_sql
    assert query_run.query_metadata["template_id"] == "open_support_tickets_by_department"
    assert query_run.query_metadata["scope_type"] == "department"
    assert query_run.query_metadata["validation"]["valid"] is True
    assert query_run.query_metadata["execution"]["status"] == "succeeded"


def test_analyst_scoped_free_text_query_works_for_assigned_it_scope(
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    with Session(postgres_engine) as session:
        analyst = user_by_email(session, "demo.analyst@queryops.local")
        access_context = build_user_access_context(analyst, session)
        expected_count = expected_non_compliant_device_count(
            session,
            department_id=access_context.default_scope.department_id,
        )

        result = QueryEngineService().run(
            session,
            analyst,
            QueryEngineRequest(question="Show non-compliant devices in my department."),
        )
        query_run = latest_query_run(session, analyst)

    assert result.status == "succeeded"
    assert result.row_count == expected_count
    assert result.row_count > 0
    assert query_run.status == "succeeded"
    assert query_run.query_metadata["provider"] == "mock"
    assert query_run.query_metadata["template_id"] == "non_compliant_devices_by_department"
    assert query_run.query_metadata["scope_type"] == "department"


def test_admin_global_template_query_returns_allowed_global_data(
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    with Session(postgres_engine) as session:
        admin = user_by_email(session, "demo.admin@queryops.local")
        expected_rows = expected_support_ticket_rows(session)

        result = QueryEngineService().run(
            session,
            admin,
            QueryEngineRequest(
                question="How many open support tickets exist in my department by priority?",
                template_id="open_support_tickets_by_department",
            ),
        )
        query_run = latest_query_run(session, admin)

    assert result.status == "succeeded"
    assert result.rows == expected_rows
    assert result.row_count == len(expected_rows)
    assert result.row_count > 0
    assert query_run.status == "succeeded"
    assert query_run.query_metadata["scope_type"] == "global"
    assert query_run.query_metadata["execution"]["status"] == "succeeded"


def test_non_queryable_resource_is_denied_through_service(
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    with Session(postgres_engine) as session:
        admin = user_by_email(session, "demo.admin@queryops.local")

        result = QueryEngineService(provider=AuditSqlProvider()).run(
            session,
            admin,
            QueryEngineRequest(question="Show audit events."),
        )
        query_run = latest_query_run(session, admin)

    assert result.status == "failed"
    assert result.error_code == "validation_failed"
    assert result.public_error == "SQL is not allowed for safe read-only querying."
    assert query_run.status == "failed"
    assert query_run.generated_sql == "SELECT id, event_type FROM it_audit_events"
    assert query_run.executed_sql is None
    assert query_run.error_message == "SQL is not allowed for safe read-only querying."
    assert query_run.query_metadata["validation"]["error_code"] == "forbidden_table"


def expected_support_ticket_rows(
    session: Session,
    *,
    department_id: Any | None = None,
) -> list[dict[str, Any]]:
    query = (
        select(
            SupportTicket.priority,
            SupportTicket.status,
            func.count().label("ticket_count"),
        )
        .where(SupportTicket.status.in_(["open", "in_progress"]))
        .group_by(SupportTicket.priority, SupportTicket.status)
        .order_by(SupportTicket.priority, SupportTicket.status)
    )
    if department_id is not None:
        query = query.where(SupportTicket.department_id == department_id)

    return [
        {
            "priority": row.priority,
            "status": row.status,
            "ticket_count": row.ticket_count,
        }
        for row in session.execute(query)
    ]


def expected_non_compliant_device_count(
    session: Session,
    *,
    department_id: Any,
) -> int:
    count = session.scalar(
        select(func.count(Device.id)).where(
            Device.department_id == department_id,
            or_(
                Device.compliance_status == "non_compliant",
                Device.antivirus_status.in_(["outdated", "missing"]),
                Device.encryption_enabled.is_(False),
            ),
        )
    )
    assert count is not None
    return count


def clear_query_runs(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM query_runs"))


def user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def latest_query_run(session: Session, user: AppUser) -> QueryRun:
    query_run = session.scalar(
        select(QueryRun)
        .where(QueryRun.user_id == user.id)
        .order_by(QueryRun.created_at.desc(), QueryRun.id.desc())
        .limit(1)
    )
    assert query_run is not None
    return query_run


class AuditSqlProvider:
    provider_name = "audit-test-provider"
    model_name = "audit-test-model"

    def generate_sql(
        self,
        _question: str,
        _schema_context: dict[str, Any],
        _user_context: dict[str, Any],
        _options: dict[str, Any],
    ) -> SQLGenerationResult:
        return SQLGenerationResult(
            generated_sql="SELECT id, event_type FROM it_audit_events",
            provider_name=self.provider_name,
            model_name=self.model_name,
            generation_metadata={"referenced_tables": ["it_audit_events"]},
            clarification_required=False,
        )


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = postgres_database_url()
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL query engine tests require a PostgreSQL DATABASE_URL.")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    run_alembic_upgrade(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, profile_name="small", reset=True)
        session.commit()

    try:
        yield engine
    finally:
        engine.dispose()


def postgres_database_url() -> str:
    return (
        os.environ.get("POSTGRES_TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or LOCAL_POSTGRES_URL
    )


def run_alembic_upgrade(database_url: str) -> None:
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
