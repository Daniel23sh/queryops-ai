from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.action_engine.registry import ActionRegistry
from app.api.routes import actions as actions_routes
from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.actions.reclaim_unused_license import (
    ReclaimCandidateRead,
    ReclaimCandidateRow,
    ReclaimUnusedLicenseHandler,
)
from app.domains.it_operations.models import (
    DirectoryUser,
    License,
    LicenseAssignment,
)
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AccessScope,
    ActionRequest,
    ActionRequestStatus,
    AppAuditLog,
    AppUser,
    ApprovalRequest,
    ApprovalStatus,
    Notification,
    QueryRun,
    Role,
    RunStatus,
    UserAccessScope,
)


NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


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
    registry = ActionRegistry()
    registry.register(
        ReclaimUnusedLicenseHandler(candidate_reader=_sqlite_candidate_reader)
    )

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[actions_routes.get_action_registry] = lambda: registry
    app.dependency_overrides[actions_routes.get_action_clock] = lambda: (lambda: NOW)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(actions_routes.get_action_clock, None)
        app.dependency_overrides.pop(actions_routes.get_action_registry, None)
        app.dependency_overrides.pop(get_db, None)


def test_preview_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/actions/preview", json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("csrf_token", [None, "wrong-token"])
def test_preview_requires_valid_csrf(
    client: TestClient,
    db_session: Session,
    csrf_token: str | None,
) -> None:
    _login(client, "demo.manager@queryops.local")
    headers = {"X-CSRF-Token": csrf_token} if csrf_token else {}

    response = client.post(
        "/api/v1/actions/preview",
        headers=headers,
        json=_preview_payload(db_session, "finance"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"


def test_user_is_forbidden_from_preview(
    client: TestClient,
    db_session: Session,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")

    response = _preview(
        client,
        csrf_token,
        _preview_payload(db_session, "sales"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    ("email", "scope_key", "expected_priority"),
    [
        ("demo.manager@queryops.local", "finance", "high"),
        ("demo.analyst@queryops.local", "it", "normal"),
        ("demo.admin@queryops.local", "global", "high"),
    ],
)
def test_allowed_requesters_create_persisted_preview_with_locked_priority(
    client: TestClient,
    db_session: Session,
    email: str,
    scope_key: str,
    expected_priority: str,
) -> None:
    csrf_token = _login(client, email)

    response = _preview(
        client,
        csrf_token,
        _preview_payload(db_session, scope_key),
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "draft_preview"
    assert data["action_type"] == "reclaim_unused_license"
    assert data["priority"] == expected_priority
    assert data["expires_at"] == "2026-07-17T12:30:00Z"
    action_request = db_session.get(ActionRequest, uuid.UUID(data["id"]))
    assert action_request is not None
    assert action_request.status == ActionRequestStatus.DRAFT_PREVIEW.value
    assert action_request.priority == expected_priority
    assert _utc(action_request.preview_expires_at) == NOW + timedelta(minutes=30)
    assert action_request.idempotency_key == f"action-request:{action_request.id}"


@pytest.mark.parametrize(
    "payload_update",
    [
        {"action_type": "disable_inactive_user"},
        {"action_type": "recliam_unused_license"},
        {"unexpected": True},
        {"scope_id": "not-a-uuid"},
        {"reason": "x" * 1001},
        {"license_assignment_ids": [str(uuid.uuid4()) for _ in range(101)]},
        {
            "target_user_ids": [str(uuid.uuid4()) for _ in range(51)],
            "license_assignment_ids": [str(uuid.uuid4()) for _ in range(50)],
        },
    ],
)
def test_preview_rejects_unsupported_or_invalid_payloads(
    client: TestClient,
    db_session: Session,
    payload_update: dict,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")
    payload = _preview_payload(db_session, "finance")
    payload.update(payload_update)

    response = _preview(client, csrf_token, payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] in {
        "ACTION_TYPE_NOT_SUPPORTED",
        "INVALID_ACTION_REQUEST",
    }


def test_duplicate_selectors_do_not_duplicate_preview_records(
    client: TestClient,
    db_session: Session,
) -> None:
    assignment = _old_assignment_in_scope(db_session, "finance")
    csrf_token = _login(client, "demo.manager@queryops.local")
    payload = _preview_payload(db_session, "finance")
    payload["license_assignment_ids"] = [str(assignment.id), str(assignment.id)]

    response = _preview(client, csrf_token, payload)

    assert response.status_code == 201
    preview = response.json()["data"]["preview"]
    record_ids = [
        record["license_assignment_id"]
        for group in (
            preview["eligible_records"],
            preview["skipped_records"],
            preview["override_required_records"],
        )
        for record in group
        if record["license_assignment_id"] is not None
    ]
    assert record_ids.count(str(assignment.id)) == 1


def test_preview_creation_persists_safe_snapshot_and_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = _preview(
        client,
        csrf_token,
        _preview_payload(db_session, "finance"),
    )

    assert response.status_code == 201
    action_id = uuid.UUID(response.json()["data"]["id"])
    action_request = db_session.get(ActionRequest, action_id)
    assert action_request is not None
    assert "generated_sql" not in json.dumps(action_request.preview_json)
    assert "executed_sql" not in json.dumps(action_request.preview_json)
    assert "email" not in json.dumps(action_request.preview_json).lower()
    assert set(action_request.access_context_snapshot_json) == {
        "app_user_id",
        "effective_action_permissions",
        "assigned_scopes",
        "assigned_scope_ids",
        "has_global_scope",
    }
    audit = db_session.scalar(
        select(AppAuditLog).where(
            AppAuditLog.action_request_id == action_id,
            AppAuditLog.event_type == "action_preview_created",
        )
    )
    assert audit is not None
    assert audit.after_state_json == {"status": "draft_preview"}

    serialized = json.dumps(response.json())
    assert "access_context_snapshot" not in serialized
    assert "access_decision_snapshot" not in serialized
    assert "permissions" not in serialized
    assert "generated_sql" not in serialized
    assert "executed_sql" not in serialized
    assert "@queryops.local" not in serialized


def test_source_query_run_is_owned_succeeded_compatible_provenance_only(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    source = QueryRun(
        user_id=manager.id,
        status=RunStatus.SUCCEEDED.value,
        natural_language_question="Show unused paid licenses in my department.",
        generated_sql="SELECT secret_generated_sql",
        executed_sql="SELECT secret_executed_sql",
        query_metadata={
            "provider": "domain_pack_template",
            "template_id": "unused_licenses_by_department",
            "referenced_tables": ["license_assignments", "licenses"],
        },
    )
    db_session.add(source)
    db_session.commit()
    csrf_token = _login(client, manager.email)
    payload = _preview_payload(db_session, "finance")
    payload["source_query_run_id"] = str(source.id)

    response = _preview(client, csrf_token, payload)

    assert response.status_code == 201
    action = db_session.get(ActionRequest, uuid.UUID(response.json()["data"]["id"]))
    assert action is not None
    assert action.source_query_run_id == source.id
    serialized = json.dumps(response.json()) + json.dumps(action.preview_json)
    assert "secret_generated_sql" not in serialized
    assert "secret_executed_sql" not in serialized


def test_foreign_or_incompatible_query_run_fails_safely(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user(db_session, "demo.analyst@queryops.local")
    manager = _user(db_session, "demo.manager@queryops.local")
    foreign = QueryRun(
        user_id=analyst.id,
        status=RunStatus.SUCCEEDED.value,
        query_metadata={
            "referenced_tables": ["license_assignments", "licenses"]
        },
    )
    incompatible = QueryRun(
        user_id=manager.id,
        status=RunStatus.SUCCEEDED.value,
        query_metadata={"referenced_tables": ["devices"]},
    )
    db_session.add_all([foreign, incompatible])
    db_session.commit()
    csrf_token = _login(client, manager.email)

    for source, expected_status, expected_code in (
        (foreign, 404, "QUERY_RUN_NOT_FOUND"),
        (incompatible, 400, "ACTION_SOURCE_QUERY_INVALID"),
    ):
        payload = _preview_payload(db_session, "finance")
        payload["source_query_run_id"] = str(source.id)
        response = _preview(client, csrf_token, payload)
        assert response.status_code == expected_status
        assert response.json()["error"]["code"] == expected_code
        assert "sql" not in json.dumps(response.json()).lower()


def test_compatible_free_query_run_is_accepted_as_provenance_only(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    source = QueryRun(
        user_id=manager.id,
        status=RunStatus.SUCCEEDED.value,
        generated_sql="SELECT free_query_secret",
        executed_sql="SELECT free_query_execution_secret",
        query_metadata={
            "provider": "mock",
            "template_id": "unused_licenses_by_department",
            "referenced_tables": ["license_assignments", "licenses"],
        },
    )
    db_session.add(source)
    db_session.commit()
    csrf_token = _login(client, manager.email)
    payload = _preview_payload(db_session, "finance")
    payload["source_query_run_id"] = str(source.id)

    response = _preview(client, csrf_token, payload)

    assert response.status_code == 201
    action = db_session.get(ActionRequest, uuid.UUID(response.json()["data"]["id"]))
    assert action is not None
    assert action.source_query_run_id == source.id
    serialized = json.dumps(response.json()) + json.dumps(action.preview_json)
    assert "free_query_secret" not in serialized
    assert "free_query_execution_secret" not in serialized


def test_submit_requires_csrf_and_request_permission(
    client: TestClient,
    db_session: Session,
) -> None:
    manager_token = _login(client, "demo.manager@queryops.local")
    action_id = _create_preview_id(client, db_session, manager_token, "finance")

    no_csrf = client.post(
        "/api/v1/actions/request",
        json={"action_request_id": str(action_id), "reason": "Submit"},
    )
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"]["code"] == "CSRF_TOKEN_MISSING"

    user_token = _login(client, "demo.user@queryops.local")
    forbidden = client.post(
        "/api/v1/actions/request",
        headers={"X-CSRF-Token": user_token},
        json={"action_request_id": str(action_id), "reason": "Submit"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"


def test_submit_atomically_creates_one_approval_audit_and_eligible_notifications(
    client: TestClient,
    db_session: Session,
) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    disabled_analyst = _add_finance_analyst(
        db_session,
        email="disabled.finance.analyst@example.test",
        status="disabled",
    )
    manager_token = _login(client, "demo.manager@queryops.local")
    assignment = _normal_old_assignment_in_scope(db_session, "finance")
    preview_payload = _preview_payload(db_session, "finance")
    preview_payload["license_assignment_ids"] = [str(assignment.id)]
    preview_response = _preview(client, manager_token, preview_payload)
    assert preview_response.status_code == 201, preview_response.json()
    assert preview_response.json()["data"]["requires_admin"] is False
    action_id = uuid.UUID(preview_response.json()["data"]["id"])

    response = _submit(client, manager_token, action_id)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "pending_approval"
    assert data["expires_at"] == "2026-07-18T12:00:00Z"
    action = db_session.get(ActionRequest, action_id)
    assert action is not None
    assert action.status == ActionRequestStatus.PENDING_APPROVAL.value
    assert _utc(action.submitted_at) == NOW
    assert _utc(action.expires_at) == NOW + timedelta(hours=24)
    approvals = db_session.scalars(
        select(ApprovalRequest).where(ApprovalRequest.action_request_id == action_id)
    ).all()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval.status == ApprovalStatus.PENDING.value
    assert approval.decided_by_user_id is None
    assert _utc(approval.expires_at) == NOW + timedelta(hours=24)

    notifications = db_session.scalars(
        select(Notification).where(
            Notification.related_resource_type == "action_request",
            Notification.related_resource_id == action_id,
        )
    ).all()
    recipient_ids = {notification.recipient_user_id for notification in notifications}
    admin = _user(db_session, "demo.admin@queryops.local")
    it_analyst = _user(db_session, "demo.analyst@queryops.local")
    manager = _user(db_session, "demo.manager@queryops.local")
    assert recipient_ids == {finance_analyst.id, admin.id}
    assert it_analyst.id not in recipient_ids
    assert manager.id not in recipient_ids
    assert disabled_analyst.id not in recipient_ids
    assert all(
        notification.notification_type == "action_pending_approval"
        for notification in notifications
    )
    assert all("permissions" not in json.dumps(item.payload) for item in notifications)
    audit = db_session.scalar(
        select(AppAuditLog).where(
            AppAuditLog.action_request_id == action_id,
            AppAuditLog.event_type == "action_requested",
        )
    )
    assert audit is not None
    assert audit.approval_request_id == approval.id


def test_duplicate_submit_is_idempotent_without_duplicate_side_effects(
    client: TestClient,
    db_session: Session,
) -> None:
    manager_token = _login(client, "demo.manager@queryops.local")
    action_id = _create_preview_id(client, db_session, manager_token, "finance")

    first = _submit(client, manager_token, action_id)
    approvals_before = _approval_count(db_session, action_id)
    notifications_before = _notification_count(db_session, action_id)
    audits_before = _audit_count(db_session, action_id, "action_requested")
    second = _submit(client, manager_token, action_id)

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["approval"]["id"] == second.json()["data"]["approval"]["id"]
    assert _approval_count(db_session, action_id) == approvals_before == 1
    assert _notification_count(db_session, action_id) == notifications_before
    assert _audit_count(db_session, action_id, "action_requested") == audits_before == 1


def test_expired_draft_transitions_without_creating_approval(
    client: TestClient,
    db_session: Session,
) -> None:
    manager_token = _login(client, "demo.manager@queryops.local")
    action_id = _create_preview_id(client, db_session, manager_token, "finance")
    action = db_session.get(ActionRequest, action_id)
    assert action is not None
    action.preview_expires_at = NOW - timedelta(seconds=1)
    action.expires_at = action.preview_expires_at
    db_session.commit()

    response = _submit(client, manager_token, action_id)

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "ACTION_REQUEST_EXPIRED"
    db_session.refresh(action)
    assert action.status == ActionRequestStatus.EXPIRED.value
    assert _approval_count(db_session, action_id) == 0
    assert _audit_count(db_session, action_id, "action_expired") == 1


def test_submit_rejects_a_structurally_invalid_persisted_preview(
    client: TestClient,
    db_session: Session,
) -> None:
    manager_token = _login(client, "demo.manager@queryops.local")
    action_id = _create_preview_id(client, db_session, manager_token, "finance")
    action = db_session.get(ActionRequest, action_id)
    assert action is not None
    corrupted = dict(action.preview_json)
    corrupted_summary = dict(corrupted["summary"])
    corrupted_summary["affected_license_assignment_count"] += 1
    corrupted["summary"] = corrupted_summary
    action.preview_json = corrupted
    db_session.commit()

    response = _submit(client, manager_token, action_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ACTION_PREVIEW_UNAVAILABLE"
    assert _approval_count(db_session, action_id) == 0


def test_requester_and_eligible_approver_can_get_safe_detail(
    client: TestClient,
    db_session: Session,
) -> None:
    finance_analyst = _user(db_session, "demo.analyst@queryops.local")
    _grant_scope(db_session, finance_analyst, "finance")
    manager_token = _login(client, "demo.manager@queryops.local")
    assignment = _normal_old_assignment_in_scope(db_session, "finance")
    preview_payload = _preview_payload(db_session, "finance")
    preview_payload["license_assignment_ids"] = [str(assignment.id)]
    preview_response = _preview(client, manager_token, preview_payload)
    assert preview_response.status_code == 201, preview_response.json()
    action_id = uuid.UUID(preview_response.json()["data"]["id"])
    assert _submit(client, manager_token, action_id).status_code == 200

    requester_detail = client.get(f"/api/v1/actions/{action_id}")
    analyst_token = _login(client, finance_analyst.email)
    approver_detail = client.get(f"/api/v1/actions/{action_id}")

    assert requester_detail.status_code == 200
    assert approver_detail.status_code == 200
    assert requester_detail.json()["data"]["timeline"][-1]["event_type"] == "action_requested"
    serialized = json.dumps(requester_detail.json())
    assert "generated_sql" not in serialized
    assert "executed_sql" not in serialized
    assert "access_context_snapshot" not in serialized
    assert "failure_reason_internal" not in serialized
    assert "policy_details" not in serialized
    assert analyst_token
    assert "policy_details" in approver_detail.json()["data"]


def test_unauthorized_viewer_gets_safe_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    manager_token = _login(client, "demo.manager@queryops.local")
    action_id = _create_preview_id(client, db_session, manager_token, "finance")
    assert _submit(client, manager_token, action_id).status_code == 200
    _login(client, "demo.user@queryops.local")

    response = client.get(f"/api/v1/actions/{action_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ACTION_REQUEST_NOT_FOUND"


def test_requester_can_cancel_pending_request_and_related_approval_atomically(
    client: TestClient,
    db_session: Session,
) -> None:
    manager_token = _login(client, "demo.manager@queryops.local")
    action_id = _create_preview_id(client, db_session, manager_token, "finance")
    assert _submit(client, manager_token, action_id).status_code == 200

    response = client.post(
        f"/api/v1/actions/{action_id}/cancel",
        headers={"X-CSRF-Token": manager_token},
        json={"reason": "No longer required."},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "cancelled"
    action = db_session.get(ActionRequest, action_id)
    assert action is not None
    assert action.status == ActionRequestStatus.CANCELLED.value
    assert action.approval_request is not None
    assert action.approval_request.status == ApprovalStatus.CANCELLED.value
    assert _audit_count(db_session, action_id, "action_cancelled") == 1


def test_user_and_non_requester_cannot_cancel(
    client: TestClient,
    db_session: Session,
) -> None:
    manager_token = _login(client, "demo.manager@queryops.local")
    action_id = _create_preview_id(client, db_session, manager_token, "finance")
    assert _submit(client, manager_token, action_id).status_code == 200
    user_token = _login(client, "demo.user@queryops.local")

    user_response = client.post(
        f"/api/v1/actions/{action_id}/cancel",
        headers={"X-CSRF-Token": user_token},
        json={"reason": "Attempted cancellation"},
    )
    assert user_response.status_code == 403
    assert user_response.json()["error"]["code"] == "FORBIDDEN"

    analyst_token = _login(client, "demo.analyst@queryops.local")

    non_requester = client.post(
        f"/api/v1/actions/{action_id}/cancel",
        headers={"X-CSRF-Token": analyst_token},
        json={"reason": "Attempted cancellation"},
    )
    assert non_requester.status_code == 404


@pytest.mark.parametrize(
    ("action_status", "approval_status"),
    [
        (ActionRequestStatus.COMPLETED.value, ApprovalStatus.APPROVED.value),
        (ActionRequestStatus.REJECTED.value, ApprovalStatus.REJECTED.value),
        (ActionRequestStatus.EXPIRED.value, ApprovalStatus.EXPIRED.value),
        (ActionRequestStatus.CANCELLED.value, ApprovalStatus.CANCELLED.value),
    ],
)
def test_terminal_requests_cannot_be_cancelled(
    client: TestClient,
    db_session: Session,
    action_status: str,
    approval_status: str,
) -> None:
    manager_token = _login(client, "demo.manager@queryops.local")
    action_id = _create_preview_id(client, db_session, manager_token, "finance")
    assert _submit(client, manager_token, action_id).status_code == 200

    action = db_session.get(ActionRequest, action_id)
    assert action is not None
    action.status = action_status
    action.approval_request.status = approval_status
    db_session.commit()
    late = client.post(
        f"/api/v1/actions/{action_id}/cancel",
        headers={"X-CSRF-Token": manager_token},
        json={"reason": "Too late"},
    )
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "ACTION_CANNOT_BE_CANCELLED"


def test_preview_submit_detail_and_cancel_never_mutate_license_assignments(
    client: TestClient,
    db_session: Session,
) -> None:
    before = _assignment_state(db_session)
    manager_token = _login(client, "demo.manager@queryops.local")
    action_id = _create_preview_id(client, db_session, manager_token, "finance")
    assert _submit(client, manager_token, action_id).status_code == 200
    assert client.get(f"/api/v1/actions/{action_id}").status_code == 200
    assert client.post(
        f"/api/v1/actions/{action_id}/cancel",
        headers={"X-CSRF-Token": manager_token},
        json={"reason": "No mutation test"},
    ).status_code == 200

    assert _assignment_state(db_session) == before


def _preview(client: TestClient, csrf_token: str, payload: dict):
    return client.post(
        "/api/v1/actions/preview",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )


def _submit(client: TestClient, csrf_token: str, action_id: uuid.UUID):
    return client.post(
        "/api/v1/actions/request",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "action_request_id": str(action_id),
            "reason": "Please review this deterministic reclaim request.",
        },
    )


def _create_preview_id(
    client: TestClient,
    db: Session,
    csrf_token: str,
    scope_key: str,
) -> uuid.UUID:
    response = _preview(client, csrf_token, _preview_payload(db, scope_key))
    assert response.status_code == 201, response.json()
    return uuid.UUID(response.json()["data"]["id"])


def _preview_payload(db: Session, scope_key: str) -> dict:
    scope = db.scalar(
        select(AccessScope).where(
            AccessScope.scope_key == scope_key,
            AccessScope.scope_type == (
                "global" if scope_key == "global" else "department"
            ),
        )
    )
    assert scope is not None
    return {
        "action_type": "reclaim_unused_license",
        "scope_id": str(scope.id),
        "department_id": str(scope.department_id) if scope.department_id else None,
        "reason": "Review current unused license assignments.",
    }


def _sqlite_candidate_reader(
    db: Session,
    target,
    _requester,
) -> ReclaimCandidateRead:
    statement = (
        select(LicenseAssignment, DirectoryUser, License)
        .join(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
        .join(License, License.id == LicenseAssignment.license_id)
        .order_by(LicenseAssignment.id)
    )
    assignment_ids = [
        reference.record_id
        for reference in target.targets
        if reference.record_type == "license_assignment"
    ]
    user_ids = [
        reference.record_id
        for reference in target.targets
        if reference.record_type == "directory_user"
    ]
    conditions = []
    if assignment_ids:
        conditions.append(LicenseAssignment.id.in_(assignment_ids))
    if user_ids:
        conditions.append(LicenseAssignment.user_id.in_(user_ids))
    if conditions:
        statement = statement.where(or_(*conditions))
    elif target.department_id is not None:
        statement = statement.where(
            LicenseAssignment.department_id == target.department_id
        )

    records = []
    for assignment, directory_user, license_record in db.execute(statement).all():
        records.append(
            ReclaimCandidateRow(
                assignment_id=assignment.id,
                assignment_user_id=assignment.user_id,
                assignment_department_id=assignment.department_id,
                assignment_status=assignment.status,
                last_used_at=assignment.last_used_at,
                is_mandatory=assignment.is_mandatory,
                is_exception=assignment.is_exception,
                directory_user_id=directory_user.id,
                directory_user_department_id=directory_user.department_id,
                user_display_label=directory_user.full_name,
                account_type=directory_user.account_type,
                license_id=license_record.id,
                license_product=license_record.product_name,
                license_vendor=license_record.vendor,
                monthly_cost_usd=Decimal(license_record.monthly_cost_usd),
            )
        )
    return ReclaimCandidateRead(
        records=tuple(records),
        runtime_role="queryops_query_runtime",
        transaction_read_only=True,
        row_security_enabled=True,
    )


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def _user(db: Session, email: str) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _old_assignment_in_scope(db: Session, scope_key: str) -> LicenseAssignment:
    scope = db.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == "department",
            AccessScope.scope_key == scope_key,
        )
    )
    assert scope is not None and scope.department_id is not None
    assignment = db.scalar(
        select(LicenseAssignment)
        .where(
            LicenseAssignment.department_id == scope.department_id,
            LicenseAssignment.last_used_at < NOW - timedelta(days=60),
        )
        .order_by(LicenseAssignment.id)
    )
    assert assignment is not None
    return assignment


def _normal_old_assignment_in_scope(
    db: Session,
    scope_key: str,
) -> LicenseAssignment:
    scope = db.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == "department",
            AccessScope.scope_key == scope_key,
        )
    )
    assert scope is not None and scope.department_id is not None
    assignment = db.scalar(
        select(LicenseAssignment)
        .join(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
        .where(
            LicenseAssignment.department_id == scope.department_id,
            LicenseAssignment.status == "active",
            LicenseAssignment.last_used_at < NOW - timedelta(days=60),
            LicenseAssignment.is_mandatory.is_(False),
            LicenseAssignment.is_exception.is_(False),
            DirectoryUser.account_type != "service",
        )
        .order_by(LicenseAssignment.id)
    )
    assert assignment is not None
    return assignment


def _add_finance_analyst(
    db: Session,
    *,
    email: str = "finance.analyst@example.test",
    status: str = "active",
) -> AppUser:
    analyst_role = db.scalar(select(Role).where(Role.name == "analyst"))
    finance_scope = db.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == "department",
            AccessScope.scope_key == "finance",
        )
    )
    assert analyst_role is not None
    assert finance_scope is not None and finance_scope.department_id is not None
    user = AppUser(
        auth_provider="demo",
        provider_user_id=email,
        email=email,
        full_name="Finance Analyst",
        role_id=analyst_role.id,
        department_id=finance_scope.department_id,
        status=status,
    )
    db.add(user)
    db.flush()
    db.add(
        UserAccessScope(
            user_id=user.id,
            scope_id=finance_scope.id,
            access_level="manage",
            is_default=True,
        )
    )
    db.commit()
    return user


def _grant_scope(db: Session, user: AppUser, scope_key: str) -> None:
    scope = db.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == "department",
            AccessScope.scope_key == scope_key,
        )
    )
    assert scope is not None
    db.add(
        UserAccessScope(
            user_id=user.id,
            scope_id=scope.id,
            access_level="manage",
            is_default=False,
        )
    )
    db.commit()


def _approval_count(db: Session, action_id: uuid.UUID) -> int:
    return len(
        db.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.action_request_id == action_id
            )
        ).all()
    )


def _notification_count(db: Session, action_id: uuid.UUID) -> int:
    return len(
        db.scalars(
            select(Notification).where(
                Notification.related_resource_type == "action_request",
                Notification.related_resource_id == action_id,
            )
        ).all()
    )


def _audit_count(db: Session, action_id: uuid.UUID, event_type: str) -> int:
    return len(
        db.scalars(
            select(AppAuditLog).where(
                AppAuditLog.action_request_id == action_id,
                AppAuditLog.event_type == event_type,
            )
        ).all()
    )


def _assignment_state(db: Session) -> list[tuple]:
    return list(
        db.execute(
            select(
                LicenseAssignment.id,
                LicenseAssignment.status,
                LicenseAssignment.reclaimed_at,
                LicenseAssignment.reclaimed_by_app_user_id,
            ).order_by(LicenseAssignment.id)
        ).all()
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
