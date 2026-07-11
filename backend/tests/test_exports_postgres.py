from __future__ import annotations

import csv
import os
from collections.abc import Generator
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

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
    finally:
        with Session(postgres_engine) as session:
            directory_users = session.scalar(
                select(DataResource).where(DataResource.table_name == "directory_users")
            )
            assert directory_users is not None
            directory_users.is_exportable = False
            session.commit()


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


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
