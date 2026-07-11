from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

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
from app.query_engine.sql_executor import SQLExecutionResult


SAFE_SQL = "SELECT product_name, monthly_cost_usd FROM licenses"


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
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
    seed_database(session, profile_name="small", reset=True)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def refresh_executor_override() -> Generator[Any, None, None]:
    def apply(executor: FakeRefreshExecutor) -> FakeRefreshExecutor:
        app.dependency_overrides[
            dashboards_routes.get_card_refresh_sql_executor
        ] = lambda: executor
        return executor

    try:
        yield apply
    finally:
        app.dependency_overrides.pop(
            dashboards_routes.get_card_refresh_sql_executor,
            None,
        )


def test_card_refresh_requires_authentication(client: TestClient) -> None:
    response = client.post(f"/api/v1/cards/{uuid.uuid4()}/refresh", json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("csrf_header", [None, "wrong-token"])
def test_card_refresh_requires_valid_csrf(
    client: TestClient,
    csrf_header: str | None,
) -> None:
    _login(client, "demo.manager@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header else {}

    response = client.post(
        f"/api/v1/cards/{uuid.uuid4()}/refresh",
        headers=headers,
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize("payload", [None, [], "invalid", {"limit": 100}])
def test_card_refresh_accepts_only_an_empty_object(
    client: TestClient,
    payload: Any,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        f"/api/v1/cards/{uuid.uuid4()}/refresh",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CARD_REFRESH_REQUEST"
    assert_no_sql_payload(response.json())


def test_card_refresh_rejects_missing_card(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = _refresh(client, uuid.uuid4(), csrf_token)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CARD_NOT_FOUND"


def test_card_refresh_rejects_archived_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    card, _ = _add_refreshable_card(
        db_session,
        owner=manager,
        archived=True,
    )
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CARD_NOT_FOUND"


def test_card_refresh_enforces_personal_dashboard_ownership(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user(db_session, "demo.analyst@queryops.local")
    manager = _user(db_session, "demo.manager@queryops.local")
    card, _ = _add_refreshable_card(db_session, owner=analyst)
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CARD_REFRESH_NOT_ALLOWED"


def test_card_refresh_allows_matching_department_dashboard(
    client: TestClient,
    db_session: Session,
    refresh_executor_override: Any,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    finance = _department(db_session, "Finance")
    card, _ = _add_refreshable_card(
        db_session,
        owner=_user(db_session, "demo.admin@queryops.local"),
        visibility_scope="department",
        department=finance,
    )
    refresh_executor_override(FakeRefreshExecutor(_success_result()))
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 200
    assert response.json()["data"]["card_id"] == str(card.id)


def test_card_refresh_rejects_wrong_department_scope(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    it = _department(db_session, "IT")
    card, _ = _add_refreshable_card(
        db_session,
        owner=_user(db_session, "demo.admin@queryops.local"),
        visibility_scope="department",
        department=it,
    )
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CARD_REFRESH_NOT_ALLOWED"


def test_card_refresh_allows_global_dashboard_for_global_user(
    client: TestClient,
    db_session: Session,
    refresh_executor_override: Any,
) -> None:
    admin = _user(db_session, "demo.admin@queryops.local")
    card, _ = _add_refreshable_card(
        db_session,
        owner=admin,
        visibility_scope="global",
    )
    refresh_executor_override(FakeRefreshExecutor(_success_result()))
    csrf_token = _login(client, admin.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 200


def test_card_refresh_rejects_global_dashboard_without_global_scope(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _user(db_session, "demo.admin@queryops.local")
    manager = _user(db_session, "demo.manager@queryops.local")
    card, _ = _add_refreshable_card(
        db_session,
        owner=admin,
        visibility_scope="global",
    )
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CARD_REFRESH_NOT_ALLOWED"


def test_card_refresh_rejects_card_without_saved_query(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    dashboard = _add_dashboard(db_session, owner=manager)
    card = DashboardCard(
        dashboard_id=dashboard.id,
        saved_query_id=None,
        title="Metadata only",
        card_type="table",
        position=0,
    )
    db_session.add(card)
    db_session.commit()
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CARD_NOT_REFRESHABLE"


def test_card_refresh_requires_successful_source_run(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    card, source_run = _add_refreshable_card(db_session, owner=manager)
    source_run.status = RunStatus.FAILED.value
    db_session.commit()
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CARD_NOT_REFRESHABLE"


@pytest.mark.parametrize(
    ("executed_sql", "metadata"),
    [
        (" ", {"referenced_tables": ["licenses"]}),
        (SAFE_SQL, {}),
        (SAFE_SQL, {"referenced_tables": ["devices"]}),
        (
            "UPDATE licenses SET product_name = 'unsafe'",
            {"referenced_tables": ["licenses"]},
        ),
    ],
)
def test_card_refresh_rejects_unsafe_or_untrusted_source_query(
    client: TestClient,
    db_session: Session,
    executed_sql: str,
    metadata: dict[str, Any],
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    card, source_run = _add_refreshable_card(db_session, owner=manager)
    source_run.executed_sql = executed_sql
    source_run.query_metadata = metadata
    db_session.commit()
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CARD_NOT_REFRESHABLE"
    assert_no_sql_payload(response.json())


def test_card_refresh_honors_current_query_permission_override(
    client: TestClient,
    db_session: Session,
    refresh_executor_override: Any,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    _set_permission_deny(db_session, manager, "can_query_scoped_data")
    card, _ = _add_refreshable_card(db_session, owner=manager)
    executor = refresh_executor_override(FakeRefreshExecutor(_success_result()))
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CARD_REFRESH_NOT_ALLOWED"
    assert executor.calls == []


def test_card_refresh_returns_safe_preview_and_persists_viewer_query_run(
    client: TestClient,
    db_session: Session,
    refresh_executor_override: Any,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    admin = _user(db_session, "demo.admin@queryops.local")
    card, source_run = _add_refreshable_card(
        db_session,
        owner=manager,
        source_user=admin,
    )
    executor = refresh_executor_override(
        FakeRefreshExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["product_name", "monthly_cost_usd"],
                rows=[{"product_name": "Jira", "monthly_cost_usd": 8.5}],
                row_count=1,
                duration_ms=7.6,
                truncated=False,
                execution_metadata={
                    "runtime_role": "queryops_query_runtime",
                    "private": "must-not-leak",
                },
                referenced_tables=["licenses"],
            )
        )
    )
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data == {
        "card_id": str(card.id),
        "dashboard_id": str(card.dashboard_id),
        "saved_query_id": str(card.saved_query_id),
        "query_run_id": data["query_run_id"],
        "status": "succeeded",
        "columns": ["product_name", "monthly_cost_usd"],
        "rows": [{"product_name": "Jira", "monthly_cost_usd": 8.5}],
        "row_count": 1,
        "duration_ms": 8,
        "truncated": False,
        "refreshed_at": data["refreshed_at"],
        "message": "Dashboard card refreshed successfully.",
        "warnings": [],
    }
    assert body["meta"]["request_id"]
    assert body["meta"]["timestamp"]
    assert executor.calls[0]["access_context"].user_id == manager.id
    assert executor.calls[0]["options"].row_limit == 100
    assert executor.calls[0]["options"].query_action == "query:scoped_data"
    assert_no_sql_payload(body)
    assert "runtime_role" not in json.dumps(body)
    assert "referenced_tables" not in json.dumps(body)

    refresh_run = db_session.get(QueryRun, uuid.UUID(data["query_run_id"]))
    assert refresh_run is not None
    assert refresh_run.id != source_run.id
    assert refresh_run.user_id == manager.id
    assert refresh_run.saved_query_id == card.saved_query_id
    assert refresh_run.generated_sql is None
    assert refresh_run.executed_sql == f"{SAFE_SQL} LIMIT 100"
    assert refresh_run.row_count == 1
    assert refresh_run.duration_ms == 8
    assert refresh_run.error_message is None
    assert refresh_run.query_metadata == {
        "source": "dashboard_card_refresh",
        "card_id": str(card.id),
        "dashboard_id": str(card.dashboard_id),
        "saved_query_id": str(card.saved_query_id),
        "refreshed_from_query_run_id": str(source_run.id),
        "referenced_tables": ["licenses"],
        "validation": {"valid": True, "error_code": None},
        "execution": {
            "status": "succeeded",
            "error_code": None,
            "row_count": 1,
            "duration_ms": 8,
            "truncated": False,
            "row_limit": 100,
        },
    }
    assert "rows" not in refresh_run.query_metadata


def test_card_refresh_enforces_preview_limit_and_truncation(
    client: TestClient,
    db_session: Session,
    refresh_executor_override: Any,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    card, _ = _add_refreshable_card(db_session, owner=manager)
    rows = [{"row_number": index} for index in range(100)]
    executor = refresh_executor_override(
        FakeRefreshExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["row_number"],
                rows=rows,
                row_count=100,
                duration_ms=4,
                truncated=True,
                referenced_tables=["licenses"],
            )
        )
    )
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 200
    assert len(response.json()["data"]["rows"]) == 100
    assert response.json()["data"]["row_count"] == 100
    assert response.json()["data"]["truncated"] is True
    assert executor.calls[0]["options"].row_limit == 100


def test_failed_card_refresh_does_not_create_successful_query_run(
    client: TestClient,
    db_session: Session,
    refresh_executor_override: Any,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    card, source_run = _add_refreshable_card(db_session, owner=manager)
    executor = refresh_executor_override(
        FakeRefreshExecutor(
            SQLExecutionResult(
                status="failed",
                columns=[],
                rows=[],
                row_count=0,
                duration_ms=3,
                truncated=False,
                referenced_tables=["licenses"],
                error_code="database_error",
                public_error="private database detail",
            )
        )
    )
    before_ids = set(db_session.scalars(select(QueryRun.id)).all())
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "CARD_REFRESH_FAILED"
    assert "private database detail" not in response.text
    assert_no_sql_payload(response.json())
    assert set(db_session.scalars(select(QueryRun.id)).all()) == before_ids
    assert db_session.get(QueryRun, source_run.id) is not None
    assert executor.calls


def test_card_refresh_uses_latest_successful_source_deterministically(
    client: TestClient,
    db_session: Session,
    refresh_executor_override: Any,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    card, older_run = _add_refreshable_card(db_session, owner=manager)
    newer_run = _add_source_run(
        db_session,
        saved_query_id=card.saved_query_id,
        user=manager,
        executed_sql="SELECT product_name FROM licenses",
        completed_at=older_run.completed_at + timedelta(minutes=1),
    )
    executor = refresh_executor_override(FakeRefreshExecutor(_success_result()))
    csrf_token = _login(client, manager.email)

    response = _refresh(client, card.id, csrf_token)

    assert response.status_code == 200
    refresh_run = db_session.get(
        QueryRun,
        uuid.UUID(response.json()["data"]["query_run_id"]),
    )
    assert refresh_run is not None
    assert refresh_run.query_metadata["refreshed_from_query_run_id"] == str(
        newer_run.id
    )
    assert executor.calls[0]["validation_result"].sanitized_sql == (
        "SELECT product_name FROM licenses LIMIT 100"
    )


def _refresh(client: TestClient, card_id: uuid.UUID, csrf_token: str):
    return client.post(
        f"/api/v1/cards/{card_id}/refresh",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def _user(db: Session, email: str) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _department(db: Session, name: str) -> Department:
    department = db.scalar(select(Department).where(Department.name == name))
    assert department is not None
    return department


def _add_dashboard(
    db: Session,
    *,
    owner: AppUser,
    visibility_scope: str = "personal",
    department: Department | None = None,
    archived: bool = False,
) -> Dashboard:
    dashboard = Dashboard(
        owner_user_id=owner.id,
        title="Refresh dashboard",
        visibility_scope=visibility_scope,
        department_id=department.id if department else None,
        is_archived=archived,
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return dashboard


def _add_refreshable_card(
    db: Session,
    *,
    owner: AppUser,
    source_user: AppUser | None = None,
    visibility_scope: str = "personal",
    department: Department | None = None,
    archived: bool = False,
) -> tuple[DashboardCard, QueryRun]:
    dashboard = _add_dashboard(
        db,
        owner=owner,
        visibility_scope=visibility_scope,
        department=department,
        archived=archived,
    )
    saved_query = SavedQuery(
        owner_user_id=owner.id,
        name="Unused licenses",
        natural_language_question="Show unused licenses.",
        generated_sql=SAFE_SQL,
        visibility_scope=visibility_scope,
        department_id=department.id if department else None,
        parameters={},
    )
    db.add(saved_query)
    db.flush()
    card = DashboardCard(
        dashboard_id=dashboard.id,
        saved_query_id=saved_query.id,
        title="Unused licenses",
        card_type="table",
        position=0,
    )
    db.add(card)
    db.flush()
    source_run = _add_source_run(
        db,
        saved_query_id=saved_query.id,
        user=source_user or owner,
        commit=False,
    )
    db.commit()
    db.refresh(card)
    db.refresh(source_run)
    return card, source_run


def _add_source_run(
    db: Session,
    *,
    saved_query_id: uuid.UUID,
    user: AppUser,
    executed_sql: str = SAFE_SQL,
    completed_at: datetime | None = None,
    commit: bool = True,
) -> QueryRun:
    finished_at = completed_at or datetime(2026, 7, 11, 15, 0, tzinfo=UTC)
    query_run = QueryRun(
        user_id=user.id,
        saved_query_id=saved_query_id,
        status=RunStatus.SUCCEEDED.value,
        natural_language_question="Show unused licenses.",
        generated_sql=executed_sql,
        executed_sql=executed_sql,
        row_count=1,
        duration_ms=4,
        query_metadata={"referenced_tables": ["licenses"]},
        started_at=finished_at,
        completed_at=finished_at,
    )
    db.add(query_run)
    if commit:
        db.commit()
        db.refresh(query_run)
    return query_run


def _set_permission_deny(db: Session, user: AppUser, key: str) -> None:
    permission = db.scalar(select(Permission).where(Permission.key == key))
    assert permission is not None
    db.add(
        UserPermission(
            user_id=user.id,
            permission_id=permission.id,
            effect=PermissionEffect.DENY.value,
            reason="Test deny",
        )
    )
    db.commit()


def _success_result() -> SQLExecutionResult:
    return SQLExecutionResult(
        status="succeeded",
        columns=["product_name"],
        rows=[{"product_name": "Jira"}],
        row_count=1,
        duration_ms=4,
        truncated=False,
        referenced_tables=["licenses"],
    )


def assert_no_sql_payload(payload: Any) -> None:
    serialized = json.dumps(payload)
    assert "SELECT " not in serialized
    _assert_no_forbidden_keys(payload)


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert "generated_sql" not in value
        assert "executed_sql" not in value
        assert "sanitized_sql" not in value
        for child in value.values():
            _assert_no_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_keys(child)


class FakeRefreshExecutor:
    def __init__(self, result: SQLExecutionResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        db: Session,
        access_context: Any,
        validation_result: Any,
        *,
        options: Any = None,
    ) -> SQLExecutionResult:
        self.calls.append(
            {
                "db": db,
                "access_context": access_context,
                "validation_result": validation_result,
                "options": options,
            }
        )
        return self.result
