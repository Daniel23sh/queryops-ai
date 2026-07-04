from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.seed import seed_database
from app.main import app


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


def test_dashboard_catalog_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_my_dashboard_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/dashboards/my")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_authenticated_user_can_call_dashboard_catalog(
    client: TestClient,
) -> None:
    _login(client, "demo.manager@queryops.local")

    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["request_id"]
    assert body["meta"]["timestamp"]
    assert_no_sql_payload(body)


def test_authenticated_user_can_call_my_dashboard(client: TestClient) -> None:
    _login(client, "demo.manager@queryops.local")

    response = client.get("/api/v1/dashboards/my")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["request_id"]
    assert body["meta"]["timestamp"]
    assert_no_sql_payload(body)


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf-token"])
def test_create_dashboard_requires_valid_csrf(
    client: TestClient,
    csrf_header: str | None,
) -> None:
    _login(client, "demo.manager@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header is not None else {}

    response = client.post(
        "/api/v1/dashboards",
        headers=headers,
        json={"title": "My dashboard"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf-token"])
def test_save_card_requires_valid_csrf(
    client: TestClient,
    csrf_header: str | None,
) -> None:
    _login(client, "demo.analyst@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header is not None else {}

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/save-card",
        headers=headers,
        json={"title": "Saved insight"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert_no_sql_payload(response.json())


def test_create_dashboard_rejects_unknown_fields(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "My dashboard", "generated_sql": "SELECT 1"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_unknown_fields(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Saved insight", "executed_sql": "SELECT 1"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SAVE_CARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_create_dashboard_rejects_blank_title(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "  "},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_blank_title_when_provided(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "  "},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SAVE_CARD_REQUEST"
    assert_no_sql_payload(response.json())


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
