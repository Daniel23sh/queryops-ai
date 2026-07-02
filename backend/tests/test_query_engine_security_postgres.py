from __future__ import annotations

import os
from collections.abc import Generator, Mapping
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.routes.queries import get_query_engine_service
from app.auth.access_context import build_user_access_context
from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import AppUser, QueryRun
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import SQLGenerationResult
from app.query_engine.runtime_role import QUERY_RUNTIME_ROLE
from app.query_engine.service import QueryEngineRequest, QueryEngineService


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"
PUBLIC_SQL_ERROR = "SQL is not allowed for safe read-only querying."
EVALUATION_TEMPLATE_IDS = (
    "high_severity_security_events_by_department",
    "inactive_users_by_department",
    "non_compliant_devices_by_department",
    "open_support_tickets_by_department",
    "privileged_group_memberships_by_department",
    "unused_licenses_by_department",
)


def test_service_path_executes_as_runtime_role_not_table_owner(
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    with Session(postgres_engine) as session:
        admin = user_by_email(session, "demo.admin@queryops.local")

        result = QueryEngineService(
            provider=StaticSQLProvider(
                "SELECT current_user AS runtime_user, id, name "
                "FROM departments ORDER BY name LIMIT 1"
            )
        ).run(
            session,
            admin,
            QueryEngineRequest(question="Which runtime role executes queries?"),
        )
        query_run = latest_query_run(session, admin)

    assert result.status == "succeeded"
    assert result.rows[0]["runtime_user"] == QUERY_RUNTIME_ROLE
    assert query_run.status == "succeeded"
    assert query_run.query_metadata["execution"]["status"] == "succeeded"


def test_analyst_cross_department_filter_still_returns_no_rows_under_rls(
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    with Session(postgres_engine) as session:
        analyst = user_by_email(session, "demo.analyst@queryops.local")
        finance_id = session.scalar(select(Department.id).where(Department.name == "Finance"))
        assert finance_id is not None

        result = QueryEngineService(
            provider=StaticSQLProvider(
                "SELECT id, department_id, email "
                f"FROM directory_users WHERE department_id = '{finance_id}' "
                "ORDER BY email"
            )
        ).run(
            session,
            analyst,
            QueryEngineRequest(question="Show finance users even though I am IT."),
        )
        query_run = latest_query_run(session, analyst)

    assert result.status == "succeeded"
    assert result.rows == []
    assert result.row_count == 0
    assert query_run.status == "succeeded"
    assert query_run.row_count == 0


def test_manager_api_audit_table_failure_does_not_leak_sql_or_table_name(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    clear_query_runs(postgres_engine)
    app.dependency_overrides[get_query_engine_service] = lambda: QueryEngineService(
        provider=StaticSQLProvider("SELECT id, event_type FROM it_audit_events")
    )
    try:
        csrf_token = login(client, "demo.manager@queryops.local")
        response = client.post(
            "/api/v1/queries/run",
            headers={"X-CSRF-Token": csrf_token},
            json={"question": "Show audit events."},
        )
    finally:
        app.dependency_overrides.pop(get_query_engine_service, None)

    assert response.status_code == 200
    data = response.json()["data"]
    serialized = str(response.json())
    assert data["status"] == "failed"
    assert data["error_code"] == "validation_failed"
    assert data["message"] == PUBLIC_SQL_ERROR
    assert "generated_sql" not in data
    assert "executed_sql" not in data
    assert "it_audit_events" not in serialized
    assert "forbidden_table" in serialized

    with Session(postgres_engine) as session:
        manager = user_by_email(session, "demo.manager@queryops.local")
        query_run = latest_query_run(session, manager)
        assert query_run.status == "failed"
        assert query_run.generated_sql == "SELECT id, event_type FROM it_audit_events"
        assert query_run.executed_sql is None
        assert query_run.error_message == PUBLIC_SQL_ERROR
        assert query_run.query_metadata["validation"]["error_code"] == "forbidden_table"
        assert "execution" not in query_run.query_metadata


@pytest.mark.parametrize("template_id", EVALUATION_TEMPLATE_IDS)
def test_template_evaluation_cases_execute_deterministically_against_seeded_postgres(
    postgres_engine: Engine,
    template_id: str,
) -> None:
    clear_query_runs(postgres_engine)
    domain_pack = load_it_operations_domain_pack()
    template = domain_pack.templates_by_id[template_id]
    with Session(postgres_engine) as session:
        manager = user_by_email(session, "demo.manager@queryops.local")
        service = QueryEngineService()

        first = service.run(
            session,
            manager,
            QueryEngineRequest(
                question=template.natural_language_question,
                template_id=template.id,
            ),
        )
        second = service.run(
            session,
            manager,
            QueryEngineRequest(
                question=template.natural_language_question,
                template_id=template.id,
            ),
        )

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert first.columns == second.columns
    assert first.rows == second.rows
    assert first.row_count == second.row_count
    assert first.metadata["template_id"] == template_id
    assert set(first.metadata["referenced_tables"]) == set(template.referenced_tables)


class StaticSQLProvider:
    provider_name = "static-security-postgres-provider"
    model_name = "static-security-postgres-model"

    def __init__(self, generated_sql: str) -> None:
        self.generated_sql = generated_sql

    def generate_sql(
        self,
        _question: str,
        _schema_context: Mapping[str, Any],
        _user_context: Mapping[str, Any],
        _options: Mapping[str, Any],
    ) -> SQLGenerationResult:
        return SQLGenerationResult(
            generated_sql=self.generated_sql,
            provider_name=self.provider_name,
            model_name=self.model_name,
            generation_metadata={"source": "security_postgres_test"},
            clarification_required=False,
        )


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return response.json()["data"]["csrf_token"]


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
        pytest.skip("PostgreSQL query engine security tests require a PostgreSQL DATABASE_URL.")

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
