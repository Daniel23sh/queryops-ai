from __future__ import annotations

import json
import os
import re
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.routes import dashboards as dashboards_routes
from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AppUser,
    Dashboard,
    DashboardCard,
    Permission,
    PermissionEffect,
    QueryRun,
    RunStatus,
    SavedQuery,
    UserPermission,
)
from app.query_engine.runtime_role import QUERY_RUNTIME_ROLE
from app.query_engine.sql_executor import execute_validated_sql


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"


def test_card_refresh_uses_viewer_context_instead_of_creator_context(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = user_by_email(session, "demo.admin@queryops.local")
        manager = user_by_email(session, "demo.manager@queryops.local")
        finance = department_by_name(session, "Finance")
        card, source_run = add_refresh_card(
            session,
            owner=admin,
            visibility_scope="department",
            department=finance,
            table_name="directory_users",
            executed_sql=(
                "SELECT department_id, email FROM directory_users "
                "ORDER BY email LIMIT 200"
            ),
        )
        card_id = card.id
        saved_query_id = card.saved_query_id
        manager_id = manager.id
        finance_id = finance.id
        source_run_id = source_run.id

    csrf_token = login(client, "demo.manager@queryops.local")
    response = refresh(client, card_id, csrf_token)

    assert response.status_code == 200
    body = response.json()
    rows = body["data"]["rows"]
    assert rows
    assert {row["department_id"] for row in rows} == {str(finance_id)}
    assert_no_sql_payload(body)

    with Session(postgres_engine) as session:
        refresh_run = session.get(
            QueryRun,
            body["data"]["query_run_id"],
        )
        assert refresh_run is not None
        assert refresh_run.user_id == manager_id
        assert refresh_run.saved_query_id == saved_query_id
        assert refresh_run.query_metadata["refreshed_from_query_run_id"] == str(
            source_run_id
        )
        assert "rows" not in refresh_run.query_metadata


def test_card_refresh_uses_runtime_role_read_only_rls_and_preview_limit(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = user_by_email(session, "demo.admin@queryops.local")
        manager = user_by_email(session, "demo.manager@queryops.local")
        finance = department_by_name(session, "Finance")
        card, _ = add_refresh_card(
            session,
            owner=admin,
            visibility_scope="department",
            department=finance,
            table_name="login_events",
            executed_sql=(
                "SELECT id, department_id, occurred_at FROM login_events "
                "ORDER BY occurred_at DESC LIMIT 500"
            ),
        )
        card_id = card.id
        manager_id = manager.id
        finance_id = finance.id

    executor = CapturingRealExecutor()
    app.dependency_overrides[
        dashboards_routes.get_card_refresh_sql_executor
    ] = lambda: executor
    try:
        csrf_token = login(client, "demo.manager@queryops.local")
        response = refresh(client, card_id, csrf_token)
    finally:
        app.dependency_overrides.pop(
            dashboards_routes.get_card_refresh_sql_executor,
            None,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["rows"]) == 100
    assert data["row_count"] == 100
    assert data["truncated"] is True
    assert {row["department_id"] for row in data["rows"]} == {str(finance_id)}
    assert len(executor.calls) == 1
    call = executor.calls[0]
    assert call["access_context"].user_id == manager_id
    assert call["access_context"].has_global_scope is False
    assert call["options"].row_limit == 100
    assert call["options"].query_action == "query:scoped_data"
    assert call["execution_metadata"]["runtime_role"] == QUERY_RUNTIME_ROLE
    assert call["execution_metadata"]["transaction_read_only"] == "on"
    assert call["execution_metadata"]["row_limit"] == 100
    assert_no_sql_payload(response.json())
    assert "runtime_role" not in json.dumps(response.json())


def test_card_refresh_denies_cross_scope_before_sql_execution(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = user_by_email(session, "demo.admin@queryops.local")
        analyst = user_by_email(session, "demo.analyst@queryops.local")
        finance = department_by_name(session, "Finance")
        card, _ = add_refresh_card(
            session,
            owner=admin,
            visibility_scope="department",
            department=finance,
            table_name="directory_users",
            executed_sql=(
                "SELECT department_id, email FROM directory_users "
                "ORDER BY email LIMIT 200"
            ),
        )
        card_id = card.id
        saved_query_id = card.saved_query_id
        analyst_id = analyst.id
        before_count = successful_refresh_count(
            session,
            user_id=analyst_id,
            saved_query_id=saved_query_id,
        )

    executor = FailIfCalledExecutor()
    app.dependency_overrides[
        dashboards_routes.get_card_refresh_sql_executor
    ] = lambda: executor
    try:
        csrf_token = login(client, "demo.analyst@queryops.local")
        response = refresh(client, card_id, csrf_token)
    finally:
        app.dependency_overrides.pop(
            dashboards_routes.get_card_refresh_sql_executor,
            None,
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CARD_REFRESH_NOT_ALLOWED"
    assert executor.calls == 0
    assert_no_sql_payload(response.json())
    with Session(postgres_engine) as session:
        assert successful_refresh_count(
            session,
            user_id=analyst_id,
            saved_query_id=saved_query_id,
        ) == before_count


def test_card_refresh_respects_current_direct_permission_deny(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        analyst = user_by_email(session, "demo.analyst@queryops.local")
        it_department = department_by_name(session, "IT")
        card, _ = add_refresh_card(
            session,
            owner=analyst,
            visibility_scope="department",
            department=it_department,
            table_name="directory_users",
            executed_sql=(
                "SELECT department_id, email FROM directory_users "
                "ORDER BY email LIMIT 200"
            ),
        )
        prior_override = permission_override_snapshot(
            session,
            analyst,
            "can_query_scoped_data",
        )
        set_permission_deny(session, analyst, "can_query_scoped_data")
        card_id = card.id
        saved_query_id = card.saved_query_id
        analyst_id = analyst.id
        before_count = successful_refresh_count(
            session,
            user_id=analyst_id,
            saved_query_id=saved_query_id,
        )

    executor = FailIfCalledExecutor()
    app.dependency_overrides[
        dashboards_routes.get_card_refresh_sql_executor
    ] = lambda: executor
    try:
        csrf_token = login(client, "demo.analyst@queryops.local")
        response = refresh(client, card_id, csrf_token)
    finally:
        app.dependency_overrides.pop(
            dashboards_routes.get_card_refresh_sql_executor,
            None,
        )
        with Session(postgres_engine) as session:
            restore_permission_override(
                session,
                user_id=analyst_id,
                key="can_query_scoped_data",
                snapshot=prior_override,
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CARD_REFRESH_NOT_ALLOWED"
    assert executor.calls == 0
    assert_no_sql_payload(response.json())
    with Session(postgres_engine) as session:
        assert successful_refresh_count(
            session,
            user_id=analyst_id,
            saved_query_id=saved_query_id,
        ) == before_count


def add_refresh_card(
    session: Session,
    *,
    owner: AppUser,
    visibility_scope: str,
    table_name: str,
    executed_sql: str,
    department: Department | None = None,
) -> tuple[DashboardCard, QueryRun]:
    suffix = str(datetime.now(UTC).timestamp()).replace(".", "")
    dashboard = Dashboard(
        owner_user_id=owner.id,
        title=f"Refresh PostgreSQL {suffix}",
        visibility_scope=visibility_scope,
        department_id=department.id if department else None,
    )
    saved_query = SavedQuery(
        owner_user_id=owner.id,
        name=f"Refresh PostgreSQL {suffix}",
        natural_language_question="Show current scoped data.",
        generated_sql=executed_sql,
        visibility_scope=visibility_scope,
        department_id=department.id if department else None,
        parameters={},
    )
    session.add_all([dashboard, saved_query])
    session.flush()
    card = DashboardCard(
        dashboard_id=dashboard.id,
        saved_query_id=saved_query.id,
        title="Scoped refresh",
        card_type="table",
        position=0,
    )
    now = datetime.now(UTC)
    source_run = QueryRun(
        user_id=owner.id,
        saved_query_id=saved_query.id,
        status=RunStatus.SUCCEEDED.value,
        natural_language_question="Show current scoped data.",
        generated_sql="SELECT provider_output_that_must_not_leak",
        executed_sql=executed_sql,
        row_count=1,
        duration_ms=1,
        query_metadata={"referenced_tables": [table_name]},
        started_at=now,
        completed_at=now,
    )
    session.add_all([card, source_run])
    session.commit()
    session.refresh(card)
    session.refresh(source_run)
    return card, source_run


def set_permission_deny(session: Session, user: AppUser, key: str) -> None:
    permission = session.scalar(select(Permission).where(Permission.key == key))
    assert permission is not None
    existing = session.scalar(
        select(UserPermission).where(
            UserPermission.user_id == user.id,
            UserPermission.permission_id == permission.id,
        )
    )
    if existing is None:
        session.add(
            UserPermission(
                user_id=user.id,
                permission_id=permission.id,
                effect=PermissionEffect.DENY.value,
                reason="PostgreSQL refresh permission test",
            )
        )
    else:
        existing.effect = PermissionEffect.DENY.value
    session.commit()


def permission_override_snapshot(
    session: Session,
    user: AppUser,
    key: str,
) -> tuple[str, str | None] | None:
    permission = session.scalar(select(Permission).where(Permission.key == key))
    assert permission is not None
    existing = session.scalar(
        select(UserPermission).where(
            UserPermission.user_id == user.id,
            UserPermission.permission_id == permission.id,
        )
    )
    if existing is None:
        return None
    return existing.effect, existing.reason


def restore_permission_override(
    session: Session,
    *,
    user_id: Any,
    key: str,
    snapshot: tuple[str, str | None] | None,
) -> None:
    permission = session.scalar(select(Permission).where(Permission.key == key))
    assert permission is not None
    existing = session.scalar(
        select(UserPermission).where(
            UserPermission.user_id == user_id,
            UserPermission.permission_id == permission.id,
        )
    )
    if snapshot is None:
        if existing is not None:
            session.delete(existing)
    else:
        assert existing is not None
        existing.effect, existing.reason = snapshot
    session.commit()


def successful_refresh_count(
    session: Session,
    *,
    user_id: Any,
    saved_query_id: Any,
) -> int:
    count = session.scalar(
        select(func.count(QueryRun.id)).where(
            QueryRun.user_id == user_id,
            QueryRun.saved_query_id == saved_query_id,
            QueryRun.status == RunStatus.SUCCEEDED.value,
            QueryRun.query_metadata["source"].as_string()
            == "dashboard_card_refresh",
        )
    )
    return int(count or 0)


def refresh(client: TestClient, card_id: Any, csrf_token: str):
    return client.post(
        f"/api/v1/cards/{card_id}/refresh",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def department_by_name(session: Session, name: str) -> Department:
    department = session.scalar(select(Department).where(Department.name == name))
    assert department is not None
    return department


def assert_no_sql_payload(payload: Any) -> None:
    serialized = json.dumps(payload)
    normalized = serialized.lower()
    for sql_syntax in (
        r"\bselect\s+[a-z_\"*(]",
        r"\bwith\s+[a-z_][a-z0-9_]*\s+as\s*\(",
        r"\bupdate\s+[a-z_\"]+\s+set\b",
        r"\bdelete\s+from\b",
    ):
        assert re.search(sql_syntax, normalized) is None
    for source_fragment in (
        "provider_output_that_must_not_leak",
        "directory_users",
        "login_events",
    ):
        assert source_fragment not in normalized
    for forbidden_key in ("generated_sql", "executed_sql", "sanitized_sql"):
        assert forbidden_key not in normalized


class CapturingRealExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        db: Session,
        access_context: Any,
        validation_result: Any,
        *,
        options: Any = None,
    ):
        result = execute_validated_sql(
            db,
            access_context,
            validation_result,
            options=options,
        )
        self.calls.append(
            {
                "access_context": access_context,
                "options": options,
                "execution_metadata": result.execution_metadata,
            }
        )
        return result


class FailIfCalledExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("SQL executor must not be called for denied refresh.")


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
        pytest.skip("PostgreSQL card refresh tests require PostgreSQL DATABASE_URL.")

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
            "Destructive card refresh tests require POSTGRES_TEST_DATABASE_URL "
            "or the local queryops PostgreSQL database."
        )
    return database_url


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
