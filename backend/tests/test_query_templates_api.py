from __future__ import annotations

import json
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


EXPECTED_TEMPLATE_IDS = [
    "high_severity_security_events_by_department",
    "inactive_users_by_department",
    "non_compliant_devices_by_department",
    "open_support_tickets_by_department",
    "privileged_group_memberships_by_department",
    "unused_licenses_by_department",
]


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


def test_query_templates_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/query-templates")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    "email",
    [
        "demo.manager@queryops.local",
        "demo.analyst@queryops.local",
        "demo.admin@queryops.local",
    ],
)
def test_query_templates_list_returns_allowed_templates_for_query_roles(
    client: TestClient,
    email: str,
) -> None:
    _login(client, email)

    response = client.get("/api/v1/query-templates")

    assert response.status_code == 200
    templates = response.json()["data"]
    assert [template["id"] for template in templates] == EXPECTED_TEMPLATE_IDS
    assert templates == sorted(templates, key=lambda template: template["id"])
    for template in templates:
        assert template["domain"] == "it_operations"
        assert template["required_permission"] == "can_query_scoped_data"
        assert template["scope_type"] == "department"
        assert template["parameters"] == sorted(
            template["parameters"],
            key=lambda parameter: parameter["name"],
        )
        assert "sql" not in template
        assert "referenced_tables" not in template
        assert "generation_metadata" not in template
    assert_no_sql_payload(templates)


def test_user_does_not_see_templates_requiring_missing_permission(
    client: TestClient,
) -> None:
    _login(client, "demo.user@queryops.local")

    response = client.get("/api/v1/query-templates")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_query_template_detail_matches_list_filtering(client: TestClient) -> None:
    _login(client, "demo.manager@queryops.local")

    list_response = client.get("/api/v1/query-templates")
    detail_response = client.get("/api/v1/query-templates/unused_licenses_by_department")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    listed_template = next(
        template
        for template in list_response.json()["data"]
        if template["id"] == "unused_licenses_by_department"
    )
    detail = detail_response.json()["data"]
    assert detail == listed_template
    assert detail["title"] == "Unused licenses"
    assert detail["parameters"] == [
        {
            "name": "unused_days",
            "data_type": "integer",
            "description": "Number of days without license usage.",
            "required": False,
            "default": 60,
        }
    ]
    assert_no_sql_payload(detail)


def test_query_template_unknown_id_returns_safe_404(client: TestClient) -> None:
    _login(client, "demo.manager@queryops.local")

    response = client.get("/api/v1/query-templates/not-a-template")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "QUERY_TEMPLATE_NOT_FOUND"
    assert body["error"]["message"] == "Query template was not found."
    assert "not-a-template" not in body["error"]["message"]


def test_query_template_unauthorized_id_returns_safe_404(client: TestClient) -> None:
    _login(client, "demo.user@queryops.local")

    response = client.get("/api/v1/query-templates/inactive_users_by_department")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "QUERY_TEMPLATE_NOT_FOUND"
    assert body["error"]["message"] == "Query template was not found."
    assert "inactive_users_by_department" not in body["error"]["message"]


def test_query_template_detail_does_not_expose_raw_sql_by_default(
    client: TestClient,
) -> None:
    _login(client, "demo.analyst@queryops.local")

    response = client.get("/api/v1/query-templates/inactive_users_by_department")

    assert response.status_code == 200
    detail = response.json()["data"]
    assert detail["id"] == "inactive_users_by_department"
    assert_no_sql_payload(detail)


def assert_no_sql_payload(payload: Any) -> None:
    serialized = json.dumps(payload)
    assert "SELECT " not in serialized
    assert " JOIN " not in serialized
    assert " WHERE " not in serialized
    _assert_no_forbidden_keys(payload)


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert "sql" not in value
        assert "referenced_tables" not in value
        assert "generation_metadata" not in value
        for child in value.values():
            _assert_no_forbidden_keys(child)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_keys(item)


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return response.json()["data"]["csrf_token"]
