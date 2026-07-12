from __future__ import annotations

import csv
import os
from collections.abc import Generator
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.routes import exports as exports_routes
from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AppAuditLog,
    AppUser,
    Dashboard,
    DashboardCard,
    DataResource,
    QueryRun,
    RunStatus,
    SavedQuery,
)
from app.query_engine.runtime_role import QUERY_RUNTIME_ROLE
from app.query_engine.sql_executor import execute_validated_sql


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"


def test_query_run_export_uses_runtime_role_read_only_transaction_and_audit(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        analyst = user_by_email(session, "demo.analyst@queryops.local")
        query_run = QueryRun(
            user_id=analyst.id,
            status=RunStatus.SUCCEEDED.value,
            natural_language_question="Show runtime export evidence.",
            generated_sql="SELECT provider_output_that_must_not_leak",
            executed_sql=(
                "SELECT current_user AS runtime_user, "
                "current_setting('transaction_read_only') AS read_only, "
                "product_name FROM licenses ORDER BY product_name LIMIT 2"
            ),
            row_count=2,
            duration_ms=1,
            query_metadata={"referenced_tables": ["licenses"]},
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        session.add(query_run)
        session.commit()
        query_run_id = query_run.id
        analyst_id = analyst.id

    csrf_token = login(client, "demo.analyst@queryops.local")
    response = client.post(
        f"/api/v1/query-runs/{query_run_id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"filename": "runtime-proof.csv"},
    )

    assert response.status_code == 200
    rows = list(csv.DictReader(StringIO(response.text)))
    assert len(rows) == 2
    assert {row["runtime_user"] for row in rows} == {QUERY_RUNTIME_ROLE}
    assert {row["read_only"] for row in rows} == {"on"}
    assert all(row["product_name"] for row in rows)
    assert "provider_output_that_must_not_leak" not in response.text

    with Session(postgres_engine) as session:
        audit_logs = list(
            session.scalars(
                select(AppAuditLog).where(
                    AppAuditLog.entity_type == "query_run_export",
                    AppAuditLog.entity_id == query_run_id,
                )
            )
        )
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        assert audit_log.actor_user_id == analyst_id
        assert audit_log.status == "succeeded"
        assert audit_log.audit_metadata["query_run_id"] == str(query_run_id)
        assert audit_log.audit_metadata["referenced_tables"] == ["licenses"]
        assert audit_log.audit_metadata["export_policy_override"] is False
        assert audit_log.audit_metadata["restricted_tables"] == []


def test_card_export_reexecutes_admin_query_under_analyst_rls_context(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = user_by_email(session, "demo.admin@queryops.local")
        analyst = user_by_email(session, "demo.analyst@queryops.local")
        it_department = session.scalar(
            select(Department).where(Department.name == "IT")
        )
        directory_users = session.scalar(
            select(DataResource).where(DataResource.table_name == "directory_users")
        )
        assert it_department is not None
        assert directory_users is not None
        directory_users.is_exportable = True

        dashboard = Dashboard(
            owner_user_id=admin.id,
            title="IT Viewer Context Export",
            visibility_scope="department",
            department_id=it_department.id,
        )
        saved_query = SavedQuery(
            owner_user_id=admin.id,
            name="All directory users",
            natural_language_question="Show all directory users.",
            generated_sql="SELECT provider_output_that_must_not_leak",
            visibility_scope="department",
            department_id=it_department.id,
            parameters={},
        )
        session.add_all([dashboard, saved_query])
        session.flush()

        card = DashboardCard(
            dashboard_id=dashboard.id,
            saved_query_id=saved_query.id,
            title="Directory users",
            card_type="table",
            position=0,
        )
        query_run = QueryRun(
            user_id=admin.id,
            saved_query_id=saved_query.id,
            status=RunStatus.SUCCEEDED.value,
            natural_language_question="Show all directory users.",
            generated_sql="SELECT provider_output_that_must_not_leak",
            executed_sql=(
                "SELECT department_id, email FROM directory_users "
                "ORDER BY email LIMIT 200"
            ),
            row_count=48,
            duration_ms=1,
            query_metadata={"referenced_tables": ["directory_users"]},
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        session.add_all([card, query_run])
        session.commit()
        card_id = card.id
        dashboard_id = dashboard.id
        saved_query_id = saved_query.id
        query_run_id = query_run.id
        analyst_id = analyst.id
        it_department_id = it_department.id

    try:
        csrf_token = login(client, "demo.analyst@queryops.local")
        response = client.post(
            f"/api/v1/cards/{card_id}/export-csv",
            headers={"X-CSRF-Token": csrf_token},
            json={"filename": "it-directory-users.csv"},
        )

        assert response.status_code == 200
        rows = list(csv.DictReader(StringIO(response.text)))
        assert rows
        assert {row["department_id"] for row in rows} == {str(it_department_id)}
        assert "provider_output_that_must_not_leak" not in response.text

        with Session(postgres_engine) as session:
            audit_logs = list(
                session.scalars(
                    select(AppAuditLog).where(
                        AppAuditLog.entity_type == "dashboard_card_export",
                        AppAuditLog.entity_id == card_id,
                    )
                )
            )
            assert len(audit_logs) == 1
            audit_log = audit_logs[0]
            assert audit_log.actor_user_id == analyst_id
            assert audit_log.audit_metadata["dashboard_id"] == str(dashboard_id)
            assert audit_log.audit_metadata["saved_query_id"] == str(saved_query_id)
            assert audit_log.audit_metadata["query_run_id"] == str(query_run_id)
            assert audit_log.audit_metadata["referenced_tables"] == ["directory_users"]
            assert audit_log.audit_metadata["export_policy_override"] is False
            assert audit_log.audit_metadata["restricted_tables"] == []
    finally:
        with Session(postgres_engine) as session:
            directory_users = session.scalar(
                select(DataResource).where(DataResource.table_name == "directory_users")
            )
            assert directory_users is not None
            directory_users.is_exportable = False
            session.commit()


def test_admin_restricted_query_and_card_exports_use_public_safe_flow(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    csrf_token = login(client, "demo.admin@queryops.local")
    query_response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "question": "Show unused paid licenses in my department.",
            "template_id": "unused_licenses_by_department",
        },
    )
    assert query_response.status_code == 200
    query_data = query_response.json()["data"]
    assert query_data["status"] == "succeeded"
    assert query_data["row_count"] > 0
    query_run_id = query_data["query_run_id"]

    executor = CapturingRealExportExecutor()
    app.dependency_overrides[exports_routes.get_export_sql_executor] = lambda: executor
    try:
        query_export_response = client.post(
            f"/api/v1/query-runs/{query_run_id}/export-csv",
            headers={"X-CSRF-Token": csrf_token},
            json={"filename": "admin-unused-licenses.csv"},
        )
    finally:
        app.dependency_overrides.pop(exports_routes.get_export_sql_executor, None)

    assert query_export_response.status_code == 200
    query_export_rows = list(csv.DictReader(StringIO(query_export_response.text)))
    assert query_export_rows
    assert len(executor.calls) == 1
    assert executor.calls[0]["access_context"].has_global_scope is True
    assert executor.calls[0]["options"].row_limit == exports_routes.EXPORT_ROW_LIMIT

    dashboard_response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Admin restricted export QA"},
    )
    assert dashboard_response.status_code == 201
    dashboard_id = dashboard_response.json()["data"]["id"]

    save_card_response = client.post(
        f"/api/v1/query-runs/{query_run_id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "dashboard_id": dashboard_id,
            "title": "Unused licenses",
        },
    )
    assert save_card_response.status_code == 201
    card_id = save_card_response.json()["data"]["id"]

    refresh_response = client.post(
        f"/api/v1/cards/{card_id}/refresh",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )
    assert refresh_response.status_code == 200
    refresh_data = refresh_response.json()["data"]
    refresh_query_run_id = refresh_data["query_run_id"]
    assert refresh_data["status"] == "succeeded"
    assert "executed_sql" not in refresh_data
    assert "generated_sql" not in refresh_data

    app.dependency_overrides[exports_routes.get_export_sql_executor] = lambda: executor
    try:
        card_export_response = client.post(
            f"/api/v1/cards/{card_id}/export-csv",
            headers={"X-CSRF-Token": csrf_token},
            json={"filename": "admin-card-unused-licenses.csv"},
        )
    finally:
        app.dependency_overrides.pop(exports_routes.get_export_sql_executor, None)
    assert card_export_response.status_code == 200
    assert list(csv.DictReader(StringIO(card_export_response.text)))
    assert "SELECT " not in card_export_response.text.upper()
    assert len(executor.calls) == 2
    assert executor.calls[1]["access_context"].has_global_scope is True
    assert executor.calls[1]["options"].row_limit == exports_routes.EXPORT_ROW_LIMIT

    with Session(postgres_engine) as session:
        query_audit = single_export_audit(
            session,
            entity_type="query_run_export",
            entity_id=query_run_id,
        )
        card_audit = single_export_audit(
            session,
            entity_type="dashboard_card_export",
            entity_id=card_id,
        )
        for audit_log in (query_audit, card_audit):
            assert audit_log.audit_metadata["export_policy_override"] is True
            assert audit_log.audit_metadata["restricted_tables"] == [
                "license_assignments"
            ]
            assert (
                audit_log.audit_metadata["override_permission"]
                == "can_export_restricted_results"
            )
            assert "executed_sql" not in audit_log.audit_metadata
            assert "generated_sql" not in audit_log.audit_metadata
            assert "rows" not in audit_log.audit_metadata
        assert card_audit.audit_metadata["query_run_id"] == refresh_query_run_id

        refresh_query_run = session.get(QueryRun, refresh_query_run_id)
        assert refresh_query_run is not None
        assert "rows" not in refresh_query_run.query_metadata


def test_analyst_restricted_query_and_card_exports_are_denied_before_execution(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    csrf_token = login(client, "demo.analyst@queryops.local")
    query_response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "question": "Show unused paid licenses in my department.",
            "template_id": "unused_licenses_by_department",
        },
    )
    assert query_response.status_code == 200
    query_data = query_response.json()["data"]
    assert query_data["status"] == "succeeded"
    query_run_id = query_data["query_run_id"]

    dashboard_response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Analyst restricted export QA"},
    )
    assert dashboard_response.status_code == 201
    dashboard_id = dashboard_response.json()["data"]["id"]
    save_card_response = client.post(
        f"/api/v1/query-runs/{query_run_id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": dashboard_id, "title": "Unused licenses"},
    )
    assert save_card_response.status_code == 201
    card_id = save_card_response.json()["data"]["id"]
    refresh_response = client.post(
        f"/api/v1/cards/{card_id}/refresh",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )
    assert refresh_response.status_code == 200

    executor = FailIfCalledExportExecutor()
    app.dependency_overrides[exports_routes.get_export_sql_executor] = lambda: executor
    try:
        query_export_response = client.post(
            f"/api/v1/query-runs/{query_run_id}/export-csv",
            headers={"X-CSRF-Token": csrf_token},
            json={},
        )
        card_export_response = client.post(
            f"/api/v1/cards/{card_id}/export-csv",
            headers={"X-CSRF-Token": csrf_token},
            json={},
        )
    finally:
        app.dependency_overrides.pop(exports_routes.get_export_sql_executor, None)

    for response in (query_export_response, card_export_response):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSV_EXPORT_NOT_ALLOWED"
    assert executor.calls == 0

    with Session(postgres_engine) as session:
        assert export_audits(
            session,
            entity_type="query_run_export",
            entity_id=query_run_id,
        ) == []
        assert export_audits(
            session,
            entity_type="dashboard_card_export",
            entity_id=card_id,
        ) == []


def test_admin_restricted_permission_does_not_override_non_queryable_resource(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = user_by_email(session, "demo.admin@queryops.local")
        query_run = QueryRun(
            user_id=admin.id,
            status=RunStatus.SUCCEEDED.value,
            natural_language_question="Show audit data.",
            generated_sql="SELECT provider_output_that_must_not_leak",
            executed_sql="SELECT id FROM it_audit_events",
            row_count=1,
            duration_ms=1,
            query_metadata={"referenced_tables": ["it_audit_events"]},
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        session.add(query_run)
        session.commit()
        query_run_id = query_run.id

    executor = FailIfCalledExportExecutor()
    app.dependency_overrides[exports_routes.get_export_sql_executor] = lambda: executor
    try:
        csrf_token = login(client, "demo.admin@queryops.local")
        response = client.post(
            f"/api/v1/query-runs/{query_run_id}/export-csv",
            headers={"X-CSRF-Token": csrf_token},
            json={},
        )
    finally:
        app.dependency_overrides.pop(exports_routes.get_export_sql_executor, None)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSV_EXPORT_NOT_ALLOWED"
    assert executor.calls == 0
    with Session(postgres_engine) as session:
        assert export_audits(
            session,
            entity_type="query_run_export",
            entity_id=query_run_id,
        ) == []


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def export_audits(
    session: Session,
    *,
    entity_type: str,
    entity_id: UUID | str,
) -> list[AppAuditLog]:
    return list(
        session.scalars(
            select(AppAuditLog).where(
                AppAuditLog.entity_type == entity_type,
                AppAuditLog.entity_id == UUID(str(entity_id)),
            )
        )
    )


def single_export_audit(
    session: Session,
    *,
    entity_type: str,
    entity_id: UUID | str,
) -> AppAuditLog:
    audit_logs = export_audits(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    assert len(audit_logs) == 1
    return audit_logs[0]


class CapturingRealExportExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, db, access_context, validation_result, *, options=None):
        self.calls.append(
            {
                "access_context": access_context,
                "validation_result": validation_result,
                "options": options,
            }
        )
        return execute_validated_sql(
            db,
            access_context,
            validation_result,
            options=options,
        )


class FailIfCalledExportExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("Export SQL executor must not run for denied export.")


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


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = postgres_database_url()
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL export tests require a PostgreSQL DATABASE_URL.")

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
