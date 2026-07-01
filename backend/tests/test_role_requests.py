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
from app.models.product import (
    AccessScope,
    AppAuditLog,
    AppUser,
    RequestStatus,
    Role,
    RoleUpgradeRequest,
    UserAccessScope,
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
    assert data["requested_scope"] == {
        "id": data["requested_scope"]["id"],
        "type": "department",
        "key": "sales",
        "display_name": "Sales",
        "access_level": "read",
        "is_default": True,
        "department_id": data["requested_scope"]["department_id"],
    }
    assert data["decision_reason"] is None
    assert data["decided_at"] is None
    assert data["created_at"]

    created_request = db_session.get(RoleUpgradeRequest, UUID(data["id"]))
    assert created_request is not None
    assert created_request.status == RequestStatus.PENDING.value
    assert created_request.reason == "I need access for department operations."
    assert created_request.requested_scope_id == UUID(data["requested_scope"]["id"])
    assert created_request.requested_scope_type == "department"
    assert created_request.requested_scope_key == "sales"


def test_create_role_request_can_include_requested_scope_id(
    client: TestClient,
    db_session: Session,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")
    sales_scope = _scope_by_type_key(db_session, "department", "sales")

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": "analyst",
            "requested_scope_id": str(sales_scope.id),
            "reason": "I need SQL-visible access for Sales operations.",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["requested_scope"]["id"] == str(sales_scope.id)
    assert data["requested_scope"]["type"] == "department"
    assert data["requested_scope"]["key"] == "sales"
    assert data["requested_scope"]["display_name"] == "Sales"

    created_request = db_session.get(RoleUpgradeRequest, UUID(data["id"]))
    assert created_request is not None
    assert created_request.requested_scope_id == sales_scope.id
    assert created_request.requested_scope_type == "department"
    assert created_request.requested_scope_key == "sales"


@pytest.mark.parametrize("requested_role", ["manager", "analyst"])
def test_non_admin_role_request_rejects_global_requested_scope_id(
    client: TestClient,
    db_session: Session,
    requested_role: str,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")
    global_scope = _scope_by_type_key(db_session, "global", "global")

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": requested_role,
            "requested_scope_id": str(global_scope.id),
            "reason": f"I need {requested_role} access for department operations.",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUESTED_SCOPE"


def test_admin_role_request_rejects_department_requested_scope_id(
    client: TestClient,
    db_session: Session,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")
    sales_scope = _scope_by_type_key(db_session, "department", "sales")

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": "admin",
            "requested_scope_id": str(sales_scope.id),
            "reason": "I need global administration access.",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUESTED_SCOPE"


def test_valid_department_scope_request_still_works(
    client: TestClient,
    db_session: Session,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")
    sales_scope = _scope_by_type_key(db_session, "department", "sales")

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": "manager",
            "requested_scope_id": str(sales_scope.id),
            "reason": "I need manager access for Sales operations.",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["requested_scope"]["id"] == str(sales_scope.id)


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


def test_manager_can_request_analyst_role(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": "analyst",
            "reason": "I need SQL-visible access for Finance operations.",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["requested_role"] == "analyst"


def test_analyst_can_request_admin_role(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": "admin",
            "reason": "I need temporary global administration access.",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["requested_role"] == "admin"


@pytest.mark.parametrize(
    ("email", "requested_role"),
    [
        ("demo.analyst@queryops.local", "manager"),
        ("demo.admin@queryops.local", "manager"),
    ],
)
def test_role_request_must_be_upward_only(
    client: TestClient,
    email: str,
    requested_role: str,
) -> None:
    csrf_token = _login(client, email)

    response = client.post(
        "/api/v1/role-requests",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requested_role": requested_role,
            "reason": "Trying to request a non-upgrade role.",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ROLE_REQUEST_NOT_UPWARD"


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


def test_admin_can_list_role_requests(
    client: TestClient,
    db_session: Session,
) -> None:
    user_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="manager",
        reason="I need manager access for Sales operations.",
    )
    manager_request = _create_role_request(
        db_session,
        requester_email="demo.manager@queryops.local",
        requested_role="analyst",
        reason="I need analyst access for Finance data review.",
    )
    _login(client, "demo.admin@queryops.local")

    response = client.get("/api/v1/admin/role-requests")

    assert response.status_code == 200
    data = response.json()["data"]
    assert {request["id"] for request in data} == {
        str(user_request.id),
        str(manager_request.id),
    }
    assert data[0]["requester"]["email"] in {
        "demo.user@queryops.local",
        "demo.manager@queryops.local",
    }
    assert data[0]["requested_role"] in {"manager", "analyst"}
    assert data[0]["status"] == RequestStatus.PENDING.value


@pytest.mark.parametrize(
    "email",
    [
        "demo.user@queryops.local",
        "demo.manager@queryops.local",
        "demo.analyst@queryops.local",
    ],
)
def test_non_admin_users_cannot_list_admin_role_requests(
    client: TestClient,
    db_session: Session,
    email: str,
) -> None:
    _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="manager",
        reason="I need manager access for Sales operations.",
    )
    _login(client, email)

    response = client.get("/api/v1/admin/role-requests")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_can_approve_pending_role_request(
    client: TestClient,
    db_session: Session,
) -> None:
    role_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="manager",
        reason="I need manager access for Sales operations.",
    )
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/approve",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "Approved for Sales operational ownership."},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(role_request.id)
    assert data["status"] == RequestStatus.APPROVED.value
    assert data["decision_reason"] == "Approved for Sales operational ownership."
    assert data["decided_by"]["email"] == "demo.admin@queryops.local"
    assert data["decided_at"]

    db_session.expire_all()
    requester = _user_by_email(db_session, "demo.user@queryops.local")
    assert requester.role.name == "manager"
    sales_scope = _scope_by_type_key(db_session, "department", "sales")
    requester_scope = db_session.get(
        UserAccessScope,
        {"user_id": requester.id, "scope_id": sales_scope.id},
    )
    assert requester_scope is not None
    assert requester_scope.access_level == "read"
    assert requester_scope.is_default is True

    audit_log = _single_audit_log(db_session)
    assert audit_log.actor.email == "demo.admin@queryops.local"
    assert audit_log.event_type == "role_request.approved"
    assert audit_log.action == "approve"
    assert audit_log.status == "success"
    assert audit_log.entity_type == "role_upgrade_request"
    assert audit_log.entity_id == role_request.id
    assert audit_log.audit_metadata["requester_user_id"] == str(requester.id)
    assert audit_log.audit_metadata["old_role"] == "user"
    assert audit_log.audit_metadata["new_role"] == "manager"
    assert audit_log.audit_metadata["requested_scope"] == {
        "id": str(sales_scope.id),
        "type": "department",
        "key": "sales",
    }
    assert audit_log.audit_metadata["assigned_scope"] == {
        "id": str(sales_scope.id),
        "type": "department",
        "key": "sales",
        "access_level": "read",
    }
    assert (
        audit_log.audit_metadata["decision_reason"]
        == "Approved for Sales operational ownership."
    )


def test_approve_role_request_requires_decision_reason(
    client: TestClient,
    db_session: Session,
) -> None:
    role_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="manager",
        reason="I need manager access for Sales operations.",
    )
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/approve",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "   "},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ROLE_REQUEST_DECISION_REASON_REQUIRED"


def test_approve_role_request_assigns_requested_scope_for_analyst(
    client: TestClient,
    db_session: Session,
) -> None:
    sales_scope = _scope_by_type_key(db_session, "department", "sales")
    role_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="analyst",
        reason="I need analyst access for Sales reporting.",
        requested_scope=sales_scope,
    )
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/approve",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "Approved for Sales analyst work."},
    )

    assert response.status_code == 200
    db_session.expire_all()
    requester = _user_by_email(db_session, "demo.user@queryops.local")
    user_scope = db_session.get(
        UserAccessScope,
        {"user_id": requester.id, "scope_id": sales_scope.id},
    )
    assert requester.role.name == "analyst"
    assert user_scope is not None
    assert user_scope.access_level == "manage"
    assert user_scope.is_default is True


def test_approve_admin_role_request_without_requested_scope_assigns_global_scope(
    client: TestClient,
    db_session: Session,
) -> None:
    role_request = _create_role_request(
        db_session,
        requester_email="demo.manager@queryops.local",
        requested_role="admin",
        reason="I need temporary global administration access.",
    )
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/approve",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "Approved temporary global administration."},
    )

    assert response.status_code == 200
    db_session.expire_all()
    requester = _user_by_email(db_session, "demo.manager@queryops.local")
    global_scope = _scope_by_type_key(db_session, "global", "global")
    requester_scope = db_session.get(
        UserAccessScope,
        {"user_id": requester.id, "scope_id": global_scope.id},
    )
    assert requester.role.name == "admin"
    assert requester_scope is not None
    assert requester_scope.access_level == "manage"

    audit_log = _single_audit_log(db_session)
    assert audit_log.audit_metadata["assigned_scope"] == {
        "id": str(global_scope.id),
        "type": "global",
        "key": "global",
        "access_level": "manage",
    }


def test_admin_can_reject_pending_role_request(
    client: TestClient,
    db_session: Session,
) -> None:
    role_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="analyst",
        reason="I need SQL-visible access for Sales reviews.",
    )
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/reject",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "Current responsibilities do not require analyst access."},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(role_request.id)
    assert data["status"] == RequestStatus.REJECTED.value
    assert data["decision_reason"] == (
        "Current responsibilities do not require analyst access."
    )

    db_session.expire_all()
    requester = _user_by_email(db_session, "demo.user@queryops.local")
    assert requester.role.name == "user"
    sales_scope = _scope_by_type_key(db_session, "department", "sales")
    requester_scope = db_session.get(
        UserAccessScope,
        {"user_id": requester.id, "scope_id": sales_scope.id},
    )
    assert requester_scope is not None
    assert requester_scope.access_level == "read"

    audit_log = _single_audit_log(db_session)
    assert audit_log.event_type == "role_request.rejected"
    assert audit_log.action == "reject"
    assert audit_log.status == "success"
    assert audit_log.entity_id == role_request.id
    assert audit_log.audit_metadata["requester_user_id"] == str(requester.id)
    assert audit_log.audit_metadata["old_role"] == "user"
    assert audit_log.audit_metadata["requested_role"] == "analyst"
    assert (
        audit_log.audit_metadata["decision_reason"]
        == "Current responsibilities do not require analyst access."
    )


def test_reject_role_request_requires_decision_reason(
    client: TestClient,
    db_session: Session,
) -> None:
    role_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="analyst",
        reason="I need SQL-visible access for Sales reviews.",
    )
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/reject",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": ""},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ROLE_REQUEST_DECISION_REASON_REQUIRED"


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf-token"])
def test_admin_approve_requires_valid_csrf(
    client: TestClient,
    db_session: Session,
    csrf_header: str | None,
) -> None:
    role_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="manager",
        reason="I need manager access for Sales operations.",
    )
    _login(client, "demo.admin@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header is not None else {}

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/approve",
        headers=headers,
        json={"decision_reason": "Approved."},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"


def test_admin_reject_requires_valid_csrf(
    client: TestClient,
    db_session: Session,
) -> None:
    role_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="manager",
        reason="I need manager access for Sales operations.",
    )
    _login(client, "demo.admin@queryops.local")

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/reject",
        json={"decision_reason": "Rejected."},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"


@pytest.mark.parametrize(
    ("email", "action"),
    [
        ("demo.user@queryops.local", "approve"),
        ("demo.manager@queryops.local", "reject"),
        ("demo.analyst@queryops.local", "approve"),
    ],
)
def test_non_admin_users_cannot_process_role_requests(
    client: TestClient,
    db_session: Session,
    email: str,
    action: str,
) -> None:
    role_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="manager",
        reason="I need manager access for Sales operations.",
    )
    csrf_token = _login(client, email)

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/{action}",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "Trying to process without admin permission."},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_cannot_approve_own_role_request(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _user_by_email(db_session, "demo.admin@queryops.local")
    user_role = _role_by_name(db_session, "user")
    admin.role_id = user_role.id
    db_session.commit()
    role_request = _create_role_request(
        db_session,
        requester_email="demo.admin@queryops.local",
        requested_role="admin",
        reason="I want to restore my own admin access.",
    )
    admin.role_id = _role_by_name(db_session, "admin").id
    db_session.commit()
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/approve",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "Approving my own request."},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_REQUEST_SELF_APPROVAL"


def test_already_processed_role_request_cannot_be_processed_again(
    client: TestClient,
    db_session: Session,
) -> None:
    role_request = _create_role_request(
        db_session,
        requester_email="demo.user@queryops.local",
        requested_role="manager",
        reason="I need manager access for Sales operations.",
    )
    csrf_token = _login(client, "demo.admin@queryops.local")
    first_response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/approve",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "Approved."},
    )
    assert first_response.status_code == 200

    response = client.post(
        f"/api/v1/admin/role-requests/{role_request.id}/reject",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "Trying to reject after approval."},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROLE_REQUEST_ALREADY_PROCESSED"


def test_admin_processing_unknown_role_request_returns_404(
    client: TestClient,
) -> None:
    csrf_token = _login(client, "demo.admin@queryops.local")
    unknown_request_id = "00000000-0000-0000-0000-000000000000"

    response = client.post(
        f"/api/v1/admin/role-requests/{unknown_request_id}/approve",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision_reason": "Approved."},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROLE_REQUEST_NOT_FOUND"


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
    requested_scope: AccessScope | None = None,
) -> RoleUpgradeRequest:
    requester = db_session.scalar(select(AppUser).where(AppUser.email == requester_email))
    role = db_session.scalar(select(Role).where(Role.name == requested_role))
    assert requester is not None
    assert role is not None

    role_request = RoleUpgradeRequest(
        requester_user_id=requester.id,
        requested_role_id=role.id,
        department_id=requester.department_id,
        requested_scope_id=requested_scope.id if requested_scope else None,
        requested_scope_type=requested_scope.scope_type if requested_scope else None,
        requested_scope_key=requested_scope.scope_key if requested_scope else None,
        status=RequestStatus.PENDING.value,
        reason=reason,
    )
    db_session.add(role_request)
    db_session.commit()
    return role_request


def _user_by_email(db_session: Session, email: str) -> AppUser:
    user = db_session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _role_by_name(db_session: Session, role_name: str) -> Role:
    role = db_session.scalar(select(Role).where(Role.name == role_name))
    assert role is not None
    return role


def _scope_by_type_key(
    db_session: Session,
    scope_type: str,
    scope_key: str,
) -> AccessScope:
    scope = db_session.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == scope_type,
            AccessScope.scope_key == scope_key,
        )
    )
    assert scope is not None
    return scope


def _single_audit_log(db_session: Session) -> AppAuditLog:
    audit_logs = list(db_session.scalars(select(AppAuditLog)))
    assert len(audit_logs) == 1
    return audit_logs[0]
