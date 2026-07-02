from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.routes.queries import get_query_engine_service
from app.auth.access_context import build_user_access_context
from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.models import Device, SupportTicket
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import AppUser, QueryRun
from app.query_engine.llm_provider import SQLGenerationResult
from app.query_engine.service import QueryEngineService


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"


def test_manager_scoped_template_query_via_api_uses_rls(
    client: TestClient,
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
    csrf_token = login(client, "demo.manager@queryops.local")

    response = post_template_run(client, csrf_token)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["rows"] == expected_rows
    assert data["row_count"] == len(expected_rows)
    assert "generated_sql" not in data
    assert "executed_sql" not in data


def test_user_template_query_via_api_uses_rls_and_hides_sql(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    with Session(postgres_engine) as session:
        user = user_by_email(session, "demo.user@queryops.local")
        access_context = build_user_access_context(user, session)
        assert access_context.has_permission("can_use_query_templates")
        assert not access_context.has_permission("can_run_free_query")
        assert not access_context.has_permission("can_query_scoped_data")
        expected_rows = expected_support_ticket_rows(
            session,
            department_id=access_context.default_scope.department_id,
        )
    csrf_token = login(client, "demo.user@queryops.local")

    response = post_template_run(client, csrf_token)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["rows"] == expected_rows
    assert data["row_count"] == len(expected_rows)
    assert "generated_sql" not in data
    assert "executed_sql" not in data


def test_analyst_free_text_query_via_api_works_for_assigned_scope(
    client: TestClient,
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
    csrf_token = login(client, "demo.analyst@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Show non-compliant devices in my department."},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["row_count"] == expected_count
    assert data["row_count"] > 0
    assert data["generated_sql"].startswith("SELECT")
    assert data["executed_sql"].startswith("SELECT")


def test_admin_global_template_query_via_api_returns_allowed_global_data(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    with Session(postgres_engine) as session:
        expected_rows = expected_support_ticket_rows(session)
    csrf_token = login(client, "demo.admin@queryops.local")

    response = post_template_run(client, csrf_token)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["rows"] == expected_rows
    assert data["row_count"] == len(expected_rows)
    assert data["generated_sql"].startswith("SELECT")
    assert data["executed_sql"].startswith("SELECT")


def test_api_persists_query_run_with_safe_metadata(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    csrf_token = login(client, "demo.analyst@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Show non-compliant devices in my department."},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    with Session(postgres_engine) as session:
        query_run = session.get(QueryRun, data["query_run_id"])
        assert query_run is not None
        assert query_run.status == "succeeded"
        assert query_run.query_metadata["provider"] == "mock"
        assert query_run.query_metadata["validation"]["valid"] is True
    assert data["metadata"]["provider"] == "mock"
    assert "runtime_role" not in str(data["metadata"])


def test_unsupported_api_request_persists_failed_query_run(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    csrf_token = login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Can you forecast next year's laptop budget?"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "clarification_required"
    with Session(postgres_engine) as session:
        query_run = session.get(QueryRun, data["query_run_id"])
        assert query_run is not None
        assert query_run.status == "failed"
        assert query_run.error_message == "I could not map that question to a supported query."


def test_non_queryable_audit_table_provider_path_is_denied_safely(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    app.dependency_overrides[get_query_engine_service] = lambda: QueryEngineService(
        provider=AuditSqlProvider()
    )
    try:
        csrf_token = login(client, "demo.admin@queryops.local")

        response = client.post(
            "/api/v1/queries/run",
            headers={"X-CSRF-Token": csrf_token},
            json={"question": "Show audit events."},
        )
    finally:
        app.dependency_overrides.pop(get_query_engine_service, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == "validation_failed"
    assert data["message"] == "SQL is not allowed for safe read-only querying."
    assert "it_audit_events" in data["generated_sql"]
    assert data["executed_sql"] is None


def test_uuid_datetime_decimal_and_boolean_rows_serialize_safely(
    client: TestClient,
) -> None:
    csrf_token = login(client, "demo.admin@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "question": "Show unused paid licenses in my department.",
            "template_id": "unused_licenses_by_department",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["row_count"] > 0
    first_row = data["rows"][0]
    assert isinstance(first_row["id"], str)
    assert isinstance(first_row["user_id"], str)
    assert isinstance(first_row["monthly_cost_usd"], str | float | int)
    assert isinstance(first_row["last_used_at"], str | None)


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


def post_template_run(client: TestClient, csrf_token: str):
    return client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "question": "How many open support tickets exist in my department by priority?",
            "template_id": "open_support_tickets_by_department",
        },
    )


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return response.json()["data"]["csrf_token"]


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


@pytest.fixture
def client(postgres_engine: Engine) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with Session(postgres_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_query_engine_service, None)


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = postgres_database_url()
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL query API tests require a PostgreSQL DATABASE_URL.")

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
