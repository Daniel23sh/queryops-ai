from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AppUser,
    Dashboard,
    DashboardCard,
    QueryRun,
    RunStatus,
    SavedQuery,
)


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


def test_query_run_export_requires_authentication(client: TestClient) -> None:
    response = client.post(f"/api/v1/query-runs/{uuid.uuid4()}/export-csv", json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf-token"])
def test_query_run_export_requires_valid_csrf(
    client: TestClient,
    csrf_header: str | None,
) -> None:
    _login(client, "demo.analyst@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header is not None else {}

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/export-csv",
        headers=headers,
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert_no_sql_payload(response.json())


def test_query_run_export_rejects_non_object_payload(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json=["not", "an", "object"],
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EXPORT_REQUEST"
    assert_no_sql_payload(response.json())


def test_query_run_export_rejects_unknown_fields(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"filename": "licenses.csv", "generated_sql": "SELECT 1"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EXPORT_REQUEST"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize(
    "filename",
    [
        "../licenses.csv",
        r"reports\licenses.csv",
        "licenses.csv.exe",
        " ",
    ],
)
def test_query_run_export_rejects_invalid_filename(
    client: TestClient,
    filename: str,
) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"filename": filename},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EXPORT_REQUEST"
    assert_no_sql_payload(response.json())


def test_query_run_export_rejects_user_without_export_permission(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    query_run = _add_query_run(db_session, user=manager)
    csrf_token = _login(client, manager.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert_no_sql_payload(response.json())


def test_query_run_export_rejects_another_users_query_run(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    admin = _user_by_email(db_session, "demo.admin@queryops.local")
    query_run = _add_query_run(db_session, user=admin)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_FOUND"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize(
    "status",
    [
        RunStatus.QUEUED.value,
        RunStatus.RUNNING.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    ],
)
def test_query_run_export_rejects_non_succeeded_query_runs(
    client: TestClient,
    db_session: Session,
    status: str,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    query_run = _add_query_run(db_session, user=analyst, status=status)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_EXPORTABLE"
    assert_no_sql_payload(response.json())


def test_query_run_export_returns_controlled_placeholder_without_sql(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"filename": " analyst-export.csv ", "include_headers": False},
    )

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "CSV_EXPORT_NOT_IMPLEMENTED"
    assert body["error"]["details"] == {
        "resource_type": "query_run",
        "resource_id": str(query_run.id),
        "filename": "analyst-export.csv",
        "include_headers": False,
    }
    assert_no_sql_payload(body)


def test_card_export_requires_authentication(client: TestClient) -> None:
    response = client.post(f"/api/v1/cards/{uuid.uuid4()}/export-csv", json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf-token"])
def test_card_export_requires_valid_csrf(
    client: TestClient,
    csrf_header: str | None,
) -> None:
    _login(client, "demo.analyst@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header is not None else {}

    response = client.post(
        f"/api/v1/cards/{uuid.uuid4()}/export-csv",
        headers=headers,
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_non_object_payload(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/cards/{uuid.uuid4()}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json="not-an-object",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EXPORT_REQUEST"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_unknown_fields(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/cards/{uuid.uuid4()}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"filename": "card.csv", "rows": [{"unsafe": "preview"}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EXPORT_REQUEST"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_invalid_filename(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/cards/{uuid.uuid4()}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"filename": "/tmp/card.csv"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EXPORT_REQUEST"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_user_without_export_permission(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Manager Personal",
        visibility_scope="personal",
    )
    card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
    )
    csrf_token = _login(client, manager.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_card_on_non_visible_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    finance = _department_by_name(db_session, "Finance")
    dashboard = _add_dashboard(
        db_session,
        owner=_user_by_email(db_session, "demo.admin@queryops.local"),
        title="Finance Department",
        visibility_scope="department",
        department=finance,
    )
    card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=analyst),
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert_no_sql_payload(response.json())


def test_card_export_returns_controlled_placeholder_without_sql(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=analyst),
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "CSV_EXPORT_NOT_IMPLEMENTED"
    assert body["error"]["details"] == {
        "resource_type": "dashboard_card",
        "resource_id": str(card.id),
        "filename": None,
        "include_headers": True,
    }
    assert_no_sql_payload(body)


def assert_no_sql_payload(payload: Any) -> None:
    serialized = json.dumps(payload)
    assert "SELECT " not in serialized
    _assert_no_forbidden_keys(payload)


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert "generated_sql" not in value
        assert "executed_sql" not in value
        for child in value.values():
            _assert_no_forbidden_keys(child)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_keys(item)


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def _user_by_email(db_session: Session, email: str) -> AppUser:
    user = db_session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _department_by_name(db_session: Session, name: str) -> Department:
    department = db_session.scalar(select(Department).where(Department.name == name))
    assert department is not None
    return department


def _add_dashboard(
    db_session: Session,
    *,
    owner: AppUser,
    title: str,
    visibility_scope: str,
    department: Department | None = None,
    is_archived: bool = False,
) -> Dashboard:
    created_at = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    dashboard = Dashboard(
        owner_user_id=owner.id,
        title=title,
        description=f"{title} description",
        visibility_scope=visibility_scope,
        department_id=department.id if department else None,
        is_archived=is_archived,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(dashboard)
    db_session.commit()
    db_session.refresh(dashboard)
    return dashboard


def _add_saved_query(db_session: Session, *, owner: AppUser) -> SavedQuery:
    saved_query = SavedQuery(
        owner_user_id=owner.id,
        name="Unsafe saved query",
        description="Saved query description",
        natural_language_question="Show unused licenses.",
        generated_sql="SELECT should_not_leak FROM licenses",
        visibility_scope="personal",
        department_id=None,
        parameters={},
        result_schema={"columns": ["product_name"]},
    )
    db_session.add(saved_query)
    db_session.commit()
    db_session.refresh(saved_query)
    return saved_query


def _add_card(
    db_session: Session,
    *,
    dashboard: Dashboard,
    saved_query: SavedQuery,
) -> DashboardCard:
    card = DashboardCard(
        dashboard_id=dashboard.id,
        saved_query_id=saved_query.id,
        title="Saved licenses",
        description="Card description",
        card_type="table",
        position=0,
        layout={"w": 4},
        config={"columns": ["product_name"]},
    )
    db_session.add(card)
    db_session.commit()
    db_session.refresh(card)
    return card


def _add_query_run(
    db_session: Session,
    *,
    user: AppUser,
    status: str = RunStatus.SUCCEEDED.value,
) -> QueryRun:
    query_run = QueryRun(
        user_id=user.id,
        status=status,
        natural_language_question="Show unused licenses.",
        generated_sql="SELECT should_not_leak FROM licenses",
        executed_sql="SELECT should_not_leak FROM licenses WHERE department_id = :id",
        row_count=1 if status == RunStatus.SUCCEEDED.value else None,
        duration_ms=12 if status == RunStatus.SUCCEEDED.value else None,
        error_message=None if status == RunStatus.SUCCEEDED.value else "Query failed.",
        query_metadata={
            "provider": "mock",
            "validation": {"valid": status == RunStatus.SUCCEEDED.value},
            "execution": {"status": status},
        },
    )
    db_session.add(query_run)
    db_session.commit()
    db_session.refresh(query_run)
    return query_run
