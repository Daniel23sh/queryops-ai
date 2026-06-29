from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import AppUser, RequestStatus, Role, RoleUpgradeRequest


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


def test_create_role_request_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/role-requests",
        json={
            "requested_role": "manager",
            "reason": "I need access for department operations.",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_my_role_requests_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/role-requests/my")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf-token"])
def test_create_role_request_requires_valid_csrf(
    client: TestClient,
    csrf_header: str | None,
) -> None:
    _login(client, "demo.user@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header is not None else {}

    response = client.post(
        "/api/v1/role-requests",
        headers=headers,
        json={
            "requested_role": "manager",
            "reason": "I need access for department operations.",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"


def test_authenticated_user_can_create_role_request(
    client: TestClient,
    db_session: Session,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": "manager",
            "reason": "I need access for department operations.",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["id"]
    assert data["requested_role"] == "manager"
    assert data["status"] == RequestStatus.PENDING.value
    assert data["reason"] == "I need access for department operations."
    assert data["decision_reason"] is None
    assert data["decided_at"] is None
    assert data["created_at"]

    created_request = db_session.get(RoleUpgradeRequest, UUID(data["id"]))
    assert created_request is not None
    assert created_request.status == RequestStatus.PENDING.value
    assert created_request.reason == "I need access for department operations."


@pytest.mark.parametrize("requested_role", ["user", "owner", ""])
def test_create_role_request_rejects_invalid_requested_role(
    client: TestClient,
    requested_role: str,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": requested_role,
            "reason": "I need access for department operations.",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUESTED_ROLE"


def test_create_role_request_rejects_current_role(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": "manager",
            "reason": "I need access for department operations.",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ROLE_REQUEST_CURRENT_ROLE"


def test_create_role_request_rejects_duplicate_pending_request(
    client: TestClient,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")
    payload = {
        "requested_role": "manager",
        "reason": "I need access for department operations.",
    }
    first_response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )
    assert first_response.status_code == 201

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": "analyst",
            "reason": "I also need analyst access.",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PENDING_ROLE_REQUEST_EXISTS"


def test_user_can_list_own_role_requests(
    client: TestClient,
    db_session: Session,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")
    create_response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": "analyst",
            "reason": "I need to inspect generated SQL for Sales requests.",
        },
    )
    assert create_response.status_code == 201

    _create_role_request(
        db_session,
        requester_email="demo.manager@queryops.local",
        requested_role="admin",
        reason="Manager request that should not be visible to the demo user.",
    )

    response = client.get("/api/v1/role-requests/my")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [request["id"] for request in data] == [create_response.json()["data"]["id"]]
    assert data[0]["requested_role"] == "analyst"
    assert data[0]["status"] == RequestStatus.PENDING.value
    assert data[0]["reason"] == "I need to inspect generated SQL for Sales requests."


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def _create_role_request(
    db_session: Session,
    *,
    requester_email: str,
    requested_role: str,
    reason: str,
) -> RoleUpgradeRequest:
    requester = db_session.scalar(select(AppUser).where(AppUser.email == requester_email))
    role = db_session.scalar(select(Role).where(Role.name == requested_role))
    assert requester is not None
    assert role is not None

    role_request = RoleUpgradeRequest(
        requester_user_id=requester.id,
        requested_role_id=role.id,
        department_id=requester.department_id,
        status=RequestStatus.PENDING.value,
        reason=reason,
    )
    db_session.add(role_request)
    db_session.commit()
    return role_request
