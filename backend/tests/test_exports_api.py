from __future__ import annotations

import csv
import json
import uuid
from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import exports as exports_routes
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
from app.query_engine.sql_executor import SQLExecutionResult


_OMIT_REFERENCED_TABLES = object()


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
def export_executor_override() -> Generator[Any, None, None]:
    def apply(executor: FakeExportExecutor) -> FakeExportExecutor:
        dependency = exports_routes.get_export_sql_executor
        app.dependency_overrides[dependency] = lambda: executor
        return executor

    try:
        yield apply
    finally:
        dependency = getattr(exports_routes, "get_export_sql_executor", None)
        if dependency is not None:
            app.dependency_overrides.pop(dependency, None)


def test_csv_exporter_serializes_safe_deterministic_values() -> None:
    from app.exports.csv_exporter import rows_to_csv

    exported = rows_to_csv(
        [
            "name",
            "empty",
            "amount",
            "day",
            "timestamp",
            "identifier",
            "payload",
            "items",
        ],
        [
            {
                "name": "Acme, Inc.",
                "empty": None,
                "amount": Decimal("12.30"),
                "day": date(2026, 7, 5),
                "timestamp": datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
                "identifier": uuid.UUID("00000000-0000-4000-8000-000000000123"),
                "payload": {"b": 2, "a": 1},
                "items": ["x", {"z": 1}],
            }
        ],
        include_headers=True,
    )

    assert exported.startswith("name,empty,amount,day,timestamp,identifier,payload,items\n")
    parsed = list(csv.reader(StringIO(exported)))
    assert parsed == [
        [
            "name",
            "empty",
            "amount",
            "day",
            "timestamp",
            "identifier",
            "payload",
            "items",
        ],
        [
            "Acme, Inc.",
            "",
            "12.30",
            "2026-07-05",
            "2026-07-05T12:30:00+00:00",
            "00000000-0000-4000-8000-000000000123",
            '{"a":1,"b":2}',
            '["x",{"z":1}]',
        ],
    ]


def test_csv_exporter_quotes_values_when_needed() -> None:
    from app.exports.csv_exporter import rows_to_csv

    exported = rows_to_csv(
        ["plain", "comma", "quote"],
        [{"plain": "alpha", "comma": "beta,gamma", "quote": 'say "hi"'}],
        include_headers=False,
    )

    assert exported == 'alpha,"beta,gamma","say ""hi"""\n'


@pytest.mark.parametrize(
    "value",
    ["=cmd", "+cmd", "-cmd", "@cmd", "\tcmd", "\rcmd", "\ncmd"],
)
def test_csv_exporter_sanitizes_formula_like_cells(value: str) -> None:
    from app.exports.csv_exporter import rows_to_csv

    exported = rows_to_csv(["value"], [{"value": value}], include_headers=False)

    parsed = list(csv.reader(StringIO(exported)))
    assert parsed == [[f"'{value}"]]


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


def test_query_run_export_returns_csv_response_with_attachment(
    client: TestClient,
    db_session: Session,
    export_executor_override: Any,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)
    executor = export_executor_override(
        FakeExportExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["product_name", "monthly_cost_usd"],
                rows=[
                    {
                        "product_name": "Microsoft 365 E3",
                        "monthly_cost_usd": Decimal("32.00"),
                    }
                ],
                row_count=1,
                duration_ms=4.2,
                truncated=False,
                referenced_tables=["licenses"],
            )
        )
    )

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"filename": " analyst-export ", "include_headers": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="analyst-export.csv"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.text == "product_name,monthly_cost_usd\nMicrosoft 365 E3,32.00\n"
    assert executor.calls
    assert executor.calls[0]["validation_result"].sanitized_sql is not None
    assert "generated_sql_secret" not in response.text
    assert_no_sql_payload(response.text)


def test_query_run_export_uses_default_filename(
    client: TestClient,
    db_session: Session,
    export_executor_override: Any,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)
    export_executor_override(
        FakeExportExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["product_name"],
                rows=[{"product_name": "Jira"}],
                row_count=1,
                duration_ms=3.4,
                truncated=False,
                referenced_tables=["licenses"],
            )
        )
    )

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        f'attachment; filename="query-run-{query_run.id}.csv"'
    )
    assert response.text == "product_name\nJira\n"


def test_query_run_export_omits_header_when_requested(
    client: TestClient,
    db_session: Session,
    export_executor_override: Any,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)
    export_executor_override(
        FakeExportExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["product_name", "monthly_cost_usd"],
                rows=[{"product_name": "Zoom", "monthly_cost_usd": Decimal("15.99")}],
                row_count=1,
                duration_ms=3.4,
                truncated=False,
                referenced_tables=["licenses"],
            )
        )
    )

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"include_headers": False},
    )

    assert response.status_code == 200
    assert response.text == "Zoom,15.99\n"
    assert_no_sql_payload(response.text)


def test_query_run_export_blocks_missing_referenced_tables_metadata(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    query_run = _add_query_run(
        db_session,
        user=analyst,
        referenced_tables=_OMIT_REFERENCED_TABLES,
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSV_EXPORT_NOT_ALLOWED"
    assert_no_sql_payload(response.json())


def test_query_run_export_blocks_invalid_referenced_tables_metadata(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    query_run = _add_query_run(db_session, user=analyst, referenced_tables="licenses")
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSV_EXPORT_NOT_ALLOWED"
    assert_no_sql_payload(response.json())


def test_query_run_export_blocks_non_exportable_data_resource(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    query_run = _add_query_run(
        db_session,
        user=analyst,
        executed_sql="SELECT email FROM directory_users",
        referenced_tables=["directory_users"],
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSV_EXPORT_NOT_ALLOWED"
    assert_no_sql_payload(response.json())


def test_query_run_export_blocks_missing_executed_sql(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    query_run = _add_query_run(db_session, user=analyst, executed_sql=None)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_EXPORTABLE"
    assert_no_sql_payload(response.json())


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


def test_card_export_rejects_missing_card(
    client: TestClient,
) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/cards/{uuid.uuid4()}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CARD_NOT_FOUND"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_archived_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Archived Analyst Personal",
        visibility_scope="personal",
        is_archived=True,
    )
    saved_query = _add_saved_query(db_session, owner=analyst)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(db_session, user=analyst, saved_query=saved_query)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CARD_NOT_FOUND"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_card_without_saved_query(
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
    card = _add_card(db_session, dashboard=dashboard, saved_query=None)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CARD_NOT_EXPORTABLE"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_saved_query_without_successful_query_run(
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
    saved_query = _add_saved_query(db_session, owner=analyst)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(
        db_session,
        user=analyst,
        saved_query=saved_query,
        status=RunStatus.FAILED.value,
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CARD_NOT_EXPORTABLE"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_latest_successful_query_run_without_executed_sql(
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
    saved_query = _add_saved_query(db_session, owner=analyst)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(
        db_session,
        user=analyst,
        saved_query=saved_query,
        completed_at=datetime(2026, 7, 5, 12, 1, tzinfo=UTC),
    )
    _add_query_run(
        db_session,
        user=analyst,
        saved_query=saved_query,
        executed_sql=None,
        completed_at=datetime(2026, 7, 5, 12, 2, tzinfo=UTC),
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CARD_NOT_EXPORTABLE"
    assert_no_sql_payload(response.json())


def test_card_export_rejects_another_users_personal_dashboard_card(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    admin = _user_by_email(db_session, "demo.admin@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=admin,
        title="Admin Personal",
        visibility_scope="personal",
    )
    saved_query = _add_saved_query(db_session, owner=admin)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(
        db_session,
        user=admin,
        saved_query=saved_query,
        executed_sql="SELECT name FROM departments",
        referenced_tables=["departments"],
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


def test_card_export_rejects_non_global_user_for_global_dashboard_card(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    admin = _user_by_email(db_session, "demo.admin@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=admin,
        title="Global Operations",
        visibility_scope="global",
    )
    saved_query = _add_saved_query(db_session, owner=admin)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(db_session, user=admin, saved_query=saved_query)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert_no_sql_payload(response.json())


def test_card_export_blocks_non_exportable_data_resource(
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
    saved_query = _add_saved_query(db_session, owner=analyst)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(
        db_session,
        user=analyst,
        saved_query=saved_query,
        executed_sql="SELECT email FROM directory_users",
        referenced_tables=["directory_users"],
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSV_EXPORT_NOT_ALLOWED"
    assert_no_sql_payload(response.json())


def test_card_export_allows_owner_exporting_personal_dashboard_card(
    client: TestClient,
    db_session: Session,
    export_executor_override: Any,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    saved_query = _add_saved_query(db_session, owner=analyst)
    card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=saved_query,
    )
    _add_query_run(db_session, user=analyst, saved_query=saved_query)
    executor = export_executor_override(
        FakeExportExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["product_name", "monthly_cost_usd"],
                rows=[{"product_name": "Jira", "monthly_cost_usd": Decimal("8.50")}],
                row_count=1,
                duration_ms=2.1,
                truncated=False,
                referenced_tables=["licenses"],
            )
        )
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="card-{card.id}.csv"'
    )
    assert response.text == "product_name,monthly_cost_usd\nJira,8.50\n"
    assert executor.calls
    assert_no_sql_payload(response.text)


def test_card_export_allows_matching_department_dashboard_card(
    client: TestClient,
    db_session: Session,
    export_executor_override: Any,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    it = _department_by_name(db_session, "IT")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="IT Department",
        visibility_scope="department",
        department=it,
    )
    saved_query = _add_saved_query(db_session, owner=analyst)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(db_session, user=analyst, saved_query=saved_query)
    export_executor_override(
        FakeExportExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["product_name"],
                rows=[{"product_name": "Slack"}],
                row_count=1,
                duration_ms=2.1,
                truncated=False,
                referenced_tables=["licenses"],
            )
        )
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 200
    assert response.text == "product_name\nSlack\n"
    assert_no_sql_payload(response.text)


def test_card_export_allows_admin_exporting_global_dashboard_card(
    client: TestClient,
    db_session: Session,
    export_executor_override: Any,
) -> None:
    admin = _user_by_email(db_session, "demo.admin@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=admin,
        title="Global Operations",
        visibility_scope="global",
    )
    saved_query = _add_saved_query(db_session, owner=admin)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(
        db_session,
        user=admin,
        saved_query=saved_query,
        executed_sql="SELECT name FROM departments",
        referenced_tables=["departments"],
    )
    export_executor_override(
        FakeExportExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["name"],
                rows=[{"name": "IT"}],
                row_count=1,
                duration_ms=2.1,
                truncated=False,
                referenced_tables=["departments"],
            )
        )
    )
    csrf_token = _login(client, admin.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"filename": " global-departments.csv "},
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="global-departments.csv"'
    )
    assert response.text == "name\nIT\n"
    assert_no_sql_payload(response.text)


def test_card_export_omits_header_when_requested(
    client: TestClient,
    db_session: Session,
    export_executor_override: Any,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    saved_query = _add_saved_query(db_session, owner=analyst)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(db_session, user=analyst, saved_query=saved_query)
    export_executor_override(
        FakeExportExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["product_name", "monthly_cost_usd"],
                rows=[{"product_name": "Zoom", "monthly_cost_usd": Decimal("15.99")}],
                row_count=1,
                duration_ms=2.1,
                truncated=False,
                referenced_tables=["licenses"],
            )
        )
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={"include_headers": False},
    )

    assert response.status_code == 200
    assert response.text == "Zoom,15.99\n"
    assert_no_sql_payload(response.text)


def test_card_export_sanitizes_csv_injection_values(
    client: TestClient,
    db_session: Session,
    export_executor_override: Any,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    saved_query = _add_saved_query(db_session, owner=analyst)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(db_session, user=analyst, saved_query=saved_query)
    export_executor_override(
        FakeExportExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["product_name"],
                rows=[{"product_name": "=cmd"}],
                row_count=1,
                duration_ms=2.1,
                truncated=False,
                referenced_tables=["licenses"],
            )
        )
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 200
    assert response.text == "product_name\n'=cmd\n"
    assert_no_sql_payload(response.text)


def test_card_export_uses_latest_successful_query_run(
    client: TestClient,
    db_session: Session,
    export_executor_override: Any,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    saved_query = _add_saved_query(db_session, owner=analyst)
    card = _add_card(db_session, dashboard=dashboard, saved_query=saved_query)
    _add_query_run(
        db_session,
        user=analyst,
        saved_query=saved_query,
        executed_sql="SELECT name FROM departments",
        referenced_tables=["departments"],
        completed_at=datetime(2026, 7, 5, 12, 1, tzinfo=UTC),
    )
    _add_query_run(
        db_session,
        user=analyst,
        saved_query=saved_query,
        executed_sql="SELECT product_name FROM licenses",
        referenced_tables=["licenses"],
        completed_at=datetime(2026, 7, 5, 12, 2, tzinfo=UTC),
    )
    executor = export_executor_override(
        FakeExportExecutor(
            SQLExecutionResult(
                status="succeeded",
                columns=["product_name"],
                rows=[{"product_name": "GitHub Enterprise"}],
                row_count=1,
                duration_ms=2.1,
                truncated=False,
                referenced_tables=["licenses"],
            )
        )
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/cards/{card.id}/export-csv",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert response.status_code == 200
    assert executor.calls[0]["validation_result"].referenced_tables == ["licenses"]
    assert response.text == "product_name\nGitHub Enterprise\n"
    assert_no_sql_payload(response.text)


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
    saved_query: SavedQuery | None,
) -> DashboardCard:
    card = DashboardCard(
        dashboard_id=dashboard.id,
        saved_query_id=saved_query.id if saved_query is not None else None,
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
    executed_sql: str | None = "SELECT product_name, monthly_cost_usd FROM licenses",
    referenced_tables: Any = ("licenses",),
    saved_query: SavedQuery | None = None,
    completed_at: datetime | None = None,
) -> QueryRun:
    finished_at = completed_at or datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    query_metadata: dict[str, Any] = {
        "provider": "mock",
        "validation": {"valid": status == RunStatus.SUCCEEDED.value},
        "execution": {"status": status},
    }
    if referenced_tables is not _OMIT_REFERENCED_TABLES:
        query_metadata["referenced_tables"] = referenced_tables

    query_run = QueryRun(
        user_id=user.id,
        saved_query_id=saved_query.id if saved_query is not None else None,
        status=status,
        natural_language_question="Show unused licenses.",
        generated_sql="SELECT generated_sql_secret FROM licenses",
        executed_sql=executed_sql,
        row_count=1 if status == RunStatus.SUCCEEDED.value else None,
        duration_ms=12 if status == RunStatus.SUCCEEDED.value else None,
        error_message=None if status == RunStatus.SUCCEEDED.value else "Query failed.",
        query_metadata=query_metadata,
        started_at=finished_at,
        completed_at=finished_at,
    )
    db_session.add(query_run)
    db_session.commit()
    db_session.refresh(query_run)
    return query_run


class FakeExportExecutor:
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
