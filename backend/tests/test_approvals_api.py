from __future__ import annotations

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
from app.api.routes import approvals as approvals_routes
from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.actions.reclaim_unused_license import (
    ReclaimCandidateRead,
    ReclaimCandidateRow,
    ReclaimUnusedLicenseHandler,
)
from app.domains.it_operations.models import DirectoryUser, License, LicenseAssignment
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AccessScope,
    ActionRequest,
    AppAuditLog,
    AppUser,
    ApprovalRequest,
    Notification,
    Role,
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
    registry.register(ReclaimUnusedLicenseHandler(candidate_reader=_candidate_reader))

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[actions_routes.get_action_registry] = lambda: registry
    app.dependency_overrides[actions_routes.get_action_clock] = lambda: (lambda: NOW)
    app.dependency_overrides[approvals_routes.get_approval_clock] = lambda: (lambda: NOW)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_pending_approval_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/approvals/pending")
    assert response.status_code == 401


@pytest.mark.parametrize(
    "email",
    ["demo.user@queryops.local", "demo.manager@queryops.local"],
)
def test_user_and_manager_cannot_list_or_decide(
    client: TestClient, db_session: Session, email: str
) -> None:
    manager_csrf = _login(client, "demo.manager@queryops.local")
    approval = _create_pending(client, db_session, manager_csrf, "finance")
    csrf = _login(client, email)
    assert client.get("/api/v1/approvals/pending").status_code == 403
    response = client.post(
        f"/api/v1/approvals/{approval.id}/reject",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Reviewed and rejected."},
    )
    assert response.status_code == 404


def test_scoped_analyst_sees_matching_approval_and_safe_detail(
    client: TestClient, db_session: Session
) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    manager_csrf = _login(client, "demo.manager@queryops.local")
    approval = _create_pending(client, db_session, manager_csrf, "finance")
    _login(client, finance_analyst.email)

    response = client.get("/api/v1/approvals/pending")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["approval_id"] for item in items] == [str(approval.id)]
    assert "policy_snapshot" not in str(items)

    detail = client.get(f"/api/v1/approvals/{approval.id}")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["viewer_capabilities"]["can_approve"] is True
    assert "access_context_snapshot_json" not in str(data)
    assert "generated_sql" not in str(data)


def test_action_policy_details_include_revalidated_cross_scope_state(
    client: TestClient, db_session: Session
) -> None:
    manager_csrf = _login(client, "demo.manager@queryops.local")
    approval = _create_pending(client, db_session, manager_csrf, "finance")
    action = approval.action_request
    assert action is not None
    action.policy_flags_json = {
        **action.policy_flags_json,
        "revalidation_crosses_scopes": True,
    }
    db_session.commit()

    _login(client, "demo.admin@queryops.local")
    response = client.get(f"/api/v1/actions/{action.id}")
    assert response.status_code == 200
    assert response.json()["data"]["policy_details"]["crosses_scopes"] is True


def test_scoped_analyst_cannot_see_foreign_scope_or_own_request(
    client: TestClient, db_session: Session
) -> None:
    manager_csrf = _login(client, "demo.manager@queryops.local")
    finance_approval = _create_pending(client, db_session, manager_csrf, "finance")
    analyst_csrf = _login(client, "demo.analyst@queryops.local")
    own_approval = _create_pending(client, db_session, analyst_csrf, "it")

    response = client.get("/api/v1/approvals/pending")
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    assert client.get(f"/api/v1/approvals/{finance_approval.id}").status_code == 404
    assert client.get(f"/api/v1/approvals/{own_approval.id}").status_code == 404

    own_attempt = client.post(
        f"/api/v1/approvals/{own_approval.id}/approve",
        headers={"X-CSRF-Token": analyst_csrf},
        json={"decision_reason": "Self-approval must fail closed."},
    )
    assert own_attempt.status_code == 404


def test_scoped_analyst_cannot_approve_over_threshold_or_admin_request(
    client: TestClient, db_session: Session
) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    manager_csrf = _login(client, "demo.manager@queryops.local")
    over_threshold = _create_pending(client, db_session, manager_csrf, "finance")
    admin_required = _create_pending(client, db_session, manager_csrf, "finance")
    assert over_threshold.action_request is not None
    assert admin_required.action_request is not None
    over_threshold.action_request.record_count = 21
    admin_required.action_request.requires_admin = True
    admin_required.action_request.policy_flags_json = {
        **admin_required.action_request.policy_flags_json,
        "requires_policy_override": True,
    }
    db_session.commit()
    csrf = _login(client, finance_analyst.email)

    for approval in (over_threshold, admin_required):
        response = client.post(
            f"/api/v1/approvals/{approval.id}/approve",
            headers={"X-CSRF-Token": csrf},
            json={"decision_reason": "This request exceeds scoped authority."},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "APPROVAL_NOT_FOUND"


def test_pending_list_sorts_by_priority_and_admin_sees_authorized_scopes(
    client: TestClient, db_session: Session
) -> None:
    manager_csrf = _login(client, "demo.manager@queryops.local")
    approvals = [
        _create_pending(client, db_session, manager_csrf, "finance")
        for _ in range(3)
    ]
    for approval, priority in zip(approvals, ("normal", "urgent", "high"), strict=True):
        assert approval.action_request is not None
        approval.action_request.priority = priority
    db_session.commit()

    _login(client, "demo.admin@queryops.local")
    response = client.get("/api/v1/approvals/pending")
    assert response.status_code == 200
    ids = [item["approval_id"] for item in response.json()["data"]["items"]]
    assert ids == [str(approvals[1].id), str(approvals[2].id), str(approvals[0].id)]


def test_scoped_pending_list_does_not_expire_foreign_scope_requests(
    client: TestClient, db_session: Session
) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    manager_csrf = _login(client, "demo.manager@queryops.local")
    visible = _create_pending(client, db_session, manager_csrf, "finance")
    foreign = _create_pending(client, db_session, manager_csrf, "finance")
    sales = _scope(db_session, "sales")
    assert visible.action_request is not None and foreign.action_request is not None
    foreign.action_request.scope_id = sales.id
    foreign.action_request.scope_type = sales.scope_type
    foreign.action_request.scope_key = sales.scope_key
    foreign.action_request.department_id = sales.department_id
    for approval in (visible, foreign):
        assert approval.action_request is not None
        approval.expires_at = NOW - timedelta(seconds=1)
        approval.action_request.expires_at = NOW - timedelta(seconds=1)
    db_session.commit()

    _login(client, finance_analyst.email)
    response = client.get("/api/v1/approvals/pending")
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(ApprovalRequest, visible.id).status == "expired"
    assert db_session.get(ActionRequest, visible.action_request_id).status == "expired"
    assert db_session.get(ApprovalRequest, foreign.id).status == "pending"
    assert db_session.get(ActionRequest, foreign.action_request_id).status == "pending_approval"


def test_reject_requires_csrf_and_strict_bounded_reason(
    client: TestClient, db_session: Session
) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    manager_csrf = _login(client, "demo.manager@queryops.local")
    approval = _create_pending(client, db_session, manager_csrf, "finance")
    _login(client, finance_analyst.email)

    missing = client.post(
        f"/api/v1/approvals/{approval.id}/reject",
        json={"decision_reason": "Reviewed."},
    )
    assert missing.status_code == 403
    csrf = _login(client, finance_analyst.email)
    invalid = client.post(
        f"/api/v1/approvals/{approval.id}/reject",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "ok", "unexpected": True},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_APPROVAL_DECISION"


def test_approve_requires_csrf(client: TestClient, db_session: Session) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    manager_csrf = _login(client, "demo.manager@queryops.local")
    approval = _create_pending(client, db_session, manager_csrf, "finance")
    _login(client, finance_analyst.email)
    response = client.post(
        f"/api/v1/approvals/{approval.id}/approve",
        json={"decision_reason": "Missing CSRF must not approve."},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"


def test_rejection_is_atomic_and_second_decision_conflicts(
    client: TestClient, db_session: Session
) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    manager = _user(db_session, "demo.manager@queryops.local")
    manager_csrf = _login(client, manager.email)
    approval = _create_pending(client, db_session, manager_csrf, "finance")
    action_id = approval.action_request_id
    csrf = _login(client, finance_analyst.email)

    response = client.post(
        f"/api/v1/approvals/{approval.id}/reject",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Current state requires more review."},
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "rejected"
    db_session.expire_all()
    action = db_session.get(ActionRequest, action_id)
    updated_approval = db_session.get(ApprovalRequest, approval.id)
    assert action is not None and action.status == "rejected"
    assert updated_approval is not None and updated_approval.status == "rejected"
    assert updated_approval.decided_by_user_id == finance_analyst.id
    assert db_session.scalar(
        select(AppAuditLog).where(
            AppAuditLog.action_request_id == action_id,
            AppAuditLog.event_type == "action_rejected",
        )
    ) is not None
    assert db_session.scalar(
        select(Notification).where(
            Notification.recipient_user_id == manager.id,
            Notification.notification_type == "action_rejected",
        )
    ) is not None
    second = client.post(
        f"/api/v1/approvals/{approval.id}/reject",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Second decision."},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ACTION_ALREADY_PROCESSED"
    _login(client, manager.email)
    detail = client.get(f"/api/v1/actions/{action_id}")
    assert detail.status_code == 200
    rejected_event = next(
        item
        for item in detail.json()["data"]["timeline"]
        if item["event_type"] == "action_rejected"
    )
    assert rejected_event["actor"]["id"] == str(finance_analyst.id)
    assert rejected_event["timestamp"].endswith("Z")
    assert "self_approved" not in rejected_event


def test_rejection_does_not_notify_disabled_requester(
    client: TestClient, db_session: Session
) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    manager = _user(db_session, "demo.manager@queryops.local")
    manager_csrf = _login(client, manager.email)
    approval = _create_pending(client, db_session, manager_csrf, "finance")
    manager.status = "disabled"
    db_session.commit()

    csrf = _login(client, finance_analyst.email)
    response = client.post(
        f"/api/v1/approvals/{approval.id}/reject",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Requester is no longer an active recipient."},
    )
    assert response.status_code == 200
    assert db_session.scalar(
        select(Notification).where(
            Notification.recipient_user_id == manager.id,
            Notification.notification_type == "action_rejected",
        )
    ) is None


def test_expired_pending_approval_is_persisted_and_cannot_be_decided(
    client: TestClient, db_session: Session
) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    manager_csrf = _login(client, "demo.manager@queryops.local")
    approval = _create_pending(client, db_session, manager_csrf, "finance")
    action = approval.action_request
    assert action is not None
    action.expires_at = NOW - timedelta(seconds=1)
    approval.expires_at = NOW - timedelta(seconds=1)
    db_session.commit()
    csrf = _login(client, finance_analyst.email)

    response = client.post(
        f"/api/v1/approvals/{approval.id}/approve",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Too late."},
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "ACTION_REQUEST_EXPIRED"
    db_session.expire_all()
    assert db_session.get(ActionRequest, action.id).status == "expired"
    assert db_session.get(ApprovalRequest, approval.id).status == "expired"


def test_notification_apis_are_recipient_only_and_idempotent(
    client: TestClient, db_session: Session
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    other = _user(db_session, "demo.user@queryops.local")
    own = Notification(
        recipient_user_id=manager.id,
        notification_type="action_completed",
        title="Completed",
        body="Safe body.",
        status="unread",
    )
    foreign = Notification(
        recipient_user_id=other.id,
        notification_type="action_completed",
        title="Other",
        body="Safe body.",
        status="unread",
    )
    db_session.add_all([own, foreign])
    db_session.commit()
    csrf = _login(client, manager.email)

    listed = client.get("/api/v1/notifications?is_read=false")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]["items"]] == [str(own.id)]
    assert client.post(
        f"/api/v1/notifications/{foreign.id}/read",
        headers={"X-CSRF-Token": csrf},
    ).status_code == 404
    for _ in range(2):
        response = client.post(
            f"/api/v1/notifications/{own.id}/read",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_read"] is True


def test_notification_read_all_updates_only_current_recipient(
    client: TestClient, db_session: Session
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    other = _user(db_session, "demo.user@queryops.local")
    db_session.add_all(
        [
            Notification(
                recipient_user_id=recipient.id,
                notification_type="action_completed",
                title="Completed",
                status="unread",
            )
            for recipient in (manager, manager, other)
        ]
    )
    db_session.commit()
    csrf = _login(client, manager.email)
    response = client.post(
        "/api/v1/notifications/read-all", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    assert response.json()["data"]["affected_count"] == 2
    db_session.expire_all()
    own_unread = db_session.scalars(
        select(Notification).where(
            Notification.recipient_user_id == manager.id,
            Notification.status == "unread",
        )
    ).all()
    foreign_unread = db_session.scalars(
        select(Notification).where(
            Notification.recipient_user_id == other.id,
            Notification.status == "unread",
        )
    ).all()
    assert own_unread == []
    assert len(foreign_unread) == 1


def test_audit_api_enforces_scope_and_global_detail_permissions(
    client: TestClient, db_session: Session
) -> None:
    finance_analyst = _add_finance_analyst(db_session)
    finance_scope = _scope(db_session, "finance")
    it_scope = _scope(db_session, "sales")
    manager = _user(db_session, "demo.manager@queryops.local")
    logs = [
        AppAuditLog(
            event_type="action_executed",
            actor_user_id=manager.id,
            scope_id=scope.id,
            scope_type=scope.scope_type,
            scope_key=scope.scope_key,
            department_id=scope.department_id,
            summary=f"{scope.scope_key} safe summary",
            audit_metadata={"failure_category": "IntegrityError", "raw": "hidden"},
            before_state_json={"status": "active"},
            after_state_json={"status": "reclaimed"},
            self_approved=True,
        )
        for scope in (finance_scope, it_scope)
    ]
    db_session.add_all(logs)
    db_session.commit()

    assert client.get("/api/v1/audit/logs").status_code == 401
    _login(client, "demo.manager@queryops.local")
    assert client.get("/api/v1/audit/logs").status_code == 403
    _login(client, finance_analyst.email)
    scoped = client.get("/api/v1/audit/logs")
    assert scoped.status_code == 200
    scoped_items = scoped.json()["data"]["items"]
    assert len(scoped_items) == 1 and scoped_items[0]["scope"]["key"] == "finance"
    assert "before_state" not in scoped_items[0]
    assert "raw" not in str(scoped_items)
    bypass = client.get("/api/v1/audit/logs?scope_key=sales")
    assert bypass.status_code == 200
    assert bypass.json()["data"]["items"] == []
    _login(client, "demo.admin@queryops.local")
    global_items = client.get("/api/v1/audit/logs").json()["data"]["items"]
    assert len(global_items) == 2
    assert global_items[0]["before_state"] == {"status": "active"}
    assert global_items[0]["self_approved"] is True
    assert global_items[0]["failure_category"] == "IntegrityError"
    assert "raw" not in str(global_items)


def _create_pending(
    client: TestClient,
    db: Session,
    csrf: str,
    scope_key: str,
) -> ApprovalRequest:
    scope = _scope(db, scope_key)
    assignment = db.scalar(
        select(LicenseAssignment)
        .join(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
        .where(
            LicenseAssignment.department_id == scope.department_id,
            LicenseAssignment.status == "active",
            LicenseAssignment.last_used_at < NOW - timedelta(days=60),
            LicenseAssignment.is_mandatory.is_(False),
            LicenseAssignment.is_exception.is_(False),
            DirectoryUser.account_type == "human",
        )
        .order_by(LicenseAssignment.id)
    )
    assert assignment is not None
    preview = client.post(
        "/api/v1/actions/preview",
        headers={"X-CSRF-Token": csrf},
        json={
            "action_type": "reclaim_unused_license",
            "scope_id": str(scope.id),
            "department_id": str(scope.department_id),
            "license_assignment_ids": [str(assignment.id)],
            "reason": "Review current unused licenses.",
        },
    )
    assert preview.status_code == 201, preview.json()
    action_id = preview.json()["data"]["action_request_id"]
    submitted = client.post(
        "/api/v1/actions/request",
        headers={"X-CSRF-Token": csrf},
        json={
            "action_request_id": action_id,
            "reason": "Please approve the deterministic reclaim request.",
        },
    )
    assert submitted.status_code == 200, submitted.json()
    approval = db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.action_request_id == uuid.UUID(action_id))
    )
    assert approval is not None
    return approval


def _candidate_reader(db: Session, target, _requester) -> ReclaimCandidateRead:
    statement = (
        select(LicenseAssignment, DirectoryUser, License)
        .join(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
        .join(License, License.id == LicenseAssignment.license_id)
        .order_by(LicenseAssignment.id)
    )
    if target.department_id is not None:
        statement = statement.where(LicenseAssignment.department_id == target.department_id)
    assignment_ids = [
        ref.record_id for ref in target.targets if ref.record_type == "license_assignment"
    ]
    user_ids = [ref.record_id for ref in target.targets if ref.record_type == "directory_user"]
    conditions = []
    if assignment_ids:
        conditions.append(LicenseAssignment.id.in_(assignment_ids))
    if user_ids:
        conditions.append(LicenseAssignment.user_id.in_(user_ids))
    if conditions:
        statement = statement.where(or_(*conditions))
    rows = []
    for assignment, user, license_record in db.execute(statement).all():
        rows.append(
            ReclaimCandidateRow(
                assignment_id=assignment.id,
                assignment_user_id=assignment.user_id,
                assignment_department_id=assignment.department_id,
                assignment_status=assignment.status,
                last_used_at=assignment.last_used_at,
                is_mandatory=assignment.is_mandatory,
                is_exception=assignment.is_exception,
                directory_user_id=user.id,
                directory_user_department_id=user.department_id,
                user_display_label=user.full_name,
                account_type=user.account_type,
                license_id=license_record.id,
                license_product=license_record.product_name,
                license_vendor=license_record.vendor,
                monthly_cost_usd=Decimal(license_record.monthly_cost_usd),
            )
        )
    return ReclaimCandidateRead(
        records=tuple(rows),
        runtime_role="queryops_query_runtime",
        transaction_read_only=True,
        row_security_enabled=True,
    )


def _add_finance_analyst(db: Session) -> AppUser:
    existing = _user(db, "demo.analyst@queryops.local")
    scope = _scope(db, "finance")
    assigned = db.scalar(
        select(UserAccessScope).where(
            UserAccessScope.user_id == existing.id,
            UserAccessScope.scope_id == scope.id,
        )
    )
    if assigned is None:
        db.add(
            UserAccessScope(
                user_id=existing.id,
                scope_id=scope.id,
                access_level="manage",
                is_default=False,
            )
        )
        db.commit()
    return existing


def _scope(db: Session, key: str) -> AccessScope:
    scope = db.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == "department", AccessScope.scope_key == key
        )
    )
    assert scope is not None and scope.department_id is not None
    return scope


def _user(db: Session, email: str) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200, response.json()
    return str(response.json()["data"]["csrf_token"])
