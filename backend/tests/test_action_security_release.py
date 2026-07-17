from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.action_engine.policy import evaluate_action_approval
from app.auth.access_context import build_user_access_context
from app.domains.it_operations.actions.reclaim_unused_license import (
    ReclaimUnusedLicenseHandler,
)
from app.domains.it_operations.models import ItAuditEvent, LicenseAssignment
from app.models.product import (
    ActionRequest,
    AppAuditLog,
    ApprovalRequest,
)
from test_action_execution_postgres import (
    NOW,
    _admin_global_request,
    _assign_finance_scope,
    _login,
    _manager_finance_request,
    _scope,
    _user,
    client,
    postgres_engine,
    reset_seed,
)


# The imported fixtures make this a standalone PostgreSQL-backed release gate.
# It skips when an explicitly disposable POSTGRES_TEST_DATABASE_URL is absent.


def test_action_security_01_user_cannot_create_action_request(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        scope = _scope(session, "sales")
        assignment = _old_assignment(session, scope.department_id)
    csrf = _login(client, "demo.user@queryops.local")
    response = _preview(client, csrf, scope, assignment.id)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_action_security_02_manager_can_create_but_cannot_approve(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    csrf = _login(client, "demo.manager@queryops.local")
    response = _approve(client, approval_id, csrf)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "APPROVAL_NOT_FOUND"


def test_action_security_03_analyst_can_approve_scoped_request_under_20(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    response = _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    )
    assert response.status_code == 200
    assert response.json()["data"]["executed_records_count"] == 1
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "reclaimed"


def test_action_security_04_analyst_cannot_approve_own_request(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    csrf = _login(client, "demo.analyst@queryops.local")
    _assignment_id, approval_id, _action_id = _request(
        client,
        postgres_engine,
        requester_email="demo.analyst@queryops.local",
        scope_key="it",
        csrf=csrf,
    )
    response = _approve(client, approval_id, csrf)
    assert response.status_code == 404


def test_action_security_05_analyst_cannot_approve_over_20_records(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        analyst = _user(session, "demo.analyst@queryops.local")
        context = build_user_access_context(analyst, session)
    decision = evaluate_action_approval(
        context,
        requester_app_user_id=uuid.uuid4(),
        scope_type="department",
        scope_key="it",
        record_count=21,
    )
    assert decision.allowed is False
    assert decision.code == "global_approval_permission_required"


def test_action_security_06_analyst_cannot_approve_policy_override(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    _set_mandatory(postgres_engine, assignment_id)
    response = _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "POLICY_OVERRIDE_REQUIRED"


def test_action_security_07_admin_can_approve_policy_override(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    _set_mandatory(postgres_engine, assignment_id)
    _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    )
    response = _approve(client, approval_id, _login(client, "demo.admin@queryops.local"))
    assert response.status_code == 200
    assert response.json()["data"]["override_used"] is True


def test_action_security_08_admin_self_approval_is_audited(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assignment_id, approval_id, action_id = _admin_global_request(
        client, postgres_engine
    )
    response = _approve(client, approval_id, _login(client, "demo.admin@queryops.local"))
    assert response.status_code == 200
    assert response.json()["data"]["self_approved"] is True
    with Session(postgres_engine) as session:
        events = session.scalars(
            select(AppAuditLog).where(
                AppAuditLog.action_request_id == action_id,
                AppAuditLog.event_type.in_(("action_approved", "action_executed")),
            )
        ).all()
        assert len(events) == 2
        assert all(event.self_approved is True for event in events)


def test_action_security_09_expired_preview_cannot_be_submitted_for_approval(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        scope = _scope(session, "finance")
        assignment = _old_assignment(session, scope.department_id)
    csrf = _login(client, "demo.manager@queryops.local")
    preview = _preview(client, csrf, scope, assignment.id)
    assert preview.status_code == 201
    action_id = uuid.UUID(preview.json()["data"]["action_request_id"])
    with Session(postgres_engine) as session:
        action = session.get(ActionRequest, action_id)
        assert action is not None
        action.preview_expires_at = NOW - timedelta(seconds=1)
        session.commit()
    submitted = client.post(
        "/api/v1/actions/request",
        headers={"X-CSRF-Token": csrf},
        json={"action_request_id": str(action_id), "reason": "Expired preview."},
    )
    assert submitted.status_code == 410


def test_action_security_10_expired_pending_approval_cannot_be_approved(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    _assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )
    with Session(postgres_engine) as session:
        action = session.get(ActionRequest, action_id)
        approval = session.get(ApprovalRequest, approval_id)
        assert action is not None and approval is not None
        action.expires_at = NOW - timedelta(seconds=1)
        approval.expires_at = NOW - timedelta(seconds=1)
        session.commit()
    response = _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "ACTION_REQUEST_EXPIRED"


def test_action_security_11_revalidation_skips_no_longer_eligible_record(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    with Session(postgres_engine) as session:
        assignment = session.get(LicenseAssignment, assignment_id)
        assert assignment is not None
        assignment.last_used_at = NOW
        session.commit()
    response = _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    )
    assert response.status_code == 200
    assert response.json()["data"]["executed_records_count"] == 0
    assert response.json()["data"]["skipped_records_count"] == 1


def test_action_security_12_new_admin_override_blocks_non_admin_execution(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    _set_mandatory(postgres_engine, assignment_id)
    response = _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    )
    assert response.status_code == 422
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "active"


def test_action_security_13_double_approve_does_not_execute_twice(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    csrf = _login(client, "demo.analyst@queryops.local")
    assert _approve(client, approval_id, csrf).status_code == 200
    assert _approve(client, approval_id, csrf).status_code == 409
    with Session(postgres_engine) as session:
        events = session.scalars(
            select(ItAuditEvent).where(
                ItAuditEvent.resource_id == assignment_id,
                ItAuditEvent.event_type == "license_removed",
                ItAuditEvent.actor_app_user_id.is_not(None),
            )
        ).all()
        assert len(events) == 1


def test_action_security_14_transaction_rolls_back_on_database_failure(
    client: TestClient,
    postgres_engine: Engine,
    monkeypatch,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    real_execute = ReclaimUnusedLicenseHandler.execute

    def fail_after_mutation(*args, **kwargs):
        real_execute(*args, **kwargs)
        raise RuntimeError("rollback-release-gate")

    monkeypatch.setattr(ReclaimUnusedLicenseHandler, "execute", fail_after_mutation)
    response = _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "failed"
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "active"


def test_action_security_15_completed_action_writes_app_audit_log(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    _assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )
    assert _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    ).status_code == 200
    with Session(postgres_engine) as session:
        events = session.scalars(
            select(AppAuditLog.event_type).where(AppAuditLog.action_request_id == action_id)
        ).all()
        assert "action_approved" in events
        assert "action_executed" in events


def test_action_security_16_domain_change_writes_it_audit_event(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    assert _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    ).status_code == 200
    with Session(postgres_engine) as session:
        event = session.scalar(
            select(ItAuditEvent).where(
                ItAuditEvent.resource_id == assignment_id,
                ItAuditEvent.event_type == "license_removed",
                ItAuditEvent.actor_app_user_id.is_not(None),
            )
        )
        assert event is not None
        assert event.actor_user_id is None


def test_action_security_17_user_safe_failure_does_not_leak_internals(
    client: TestClient,
    postgres_engine: Engine,
    monkeypatch,
) -> None:
    _assign_finance_scope(postgres_engine)
    _assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )

    def fail_safely(*_args, **_kwargs):
        raise RuntimeError("driver-secret SELECT * FROM private_table")

    monkeypatch.setattr(ReclaimUnusedLicenseHandler, "execute", fail_safely)
    response = _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    )
    assert response.status_code == 200
    assert "driver-secret" not in str(response.json())
    assert "private_table" not in str(response.json())
    with Session(postgres_engine) as session:
        action = session.get(ActionRequest, action_id)
        assert action is not None
        assert action.failure_reason_user_safe == "The action could not be completed safely."
        assert action.failure_reason_internal == "execution:execution_failed"


def test_action_security_18_llm_cannot_choose_execution_records(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )
    with Session(postgres_engine) as session:
        action = session.get(ActionRequest, action_id)
        assert action is not None
        action.access_decision_snapshot_json = {
            **action.access_decision_snapshot_json,
            "llm_selected_record_ids": [str(uuid.uuid4())],
            "generated_sql": "DELETE FROM license_assignments",
        }
        session.commit()
    response = _approve(
        client,
        approval_id,
        _login(client, "demo.analyst@queryops.local"),
    )
    assert response.status_code == 200
    assert response.json()["data"]["executed_records_count"] == 1
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "reclaimed"


def test_action_security_19_preview_respects_rls_and_access_context(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        finance = _scope(session, "finance")
        assignment = _old_assignment(session, finance.department_id)
    response = _preview(
        client,
        _login(client, "demo.manager@queryops.local"),
        finance,
        assignment.id,
    )
    assert response.status_code == 201
    action_id = uuid.UUID(response.json()["data"]["action_request_id"])
    with Session(postgres_engine) as session:
        action = session.get(ActionRequest, action_id)
        assert action is not None
        read_boundary = action.access_decision_snapshot_json["read_boundary"]
        assert read_boundary == {
            "runtime_role": "queryops_query_runtime",
            "transaction_read_only": True,
            "row_security_enabled": True,
        }
        assert action.scope_key == "finance"


def test_action_security_20_cross_scope_action_requires_admin(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        analyst = _user(session, "demo.analyst@queryops.local")
        admin = _user(session, "demo.admin@queryops.local")
        analyst_context = build_user_access_context(analyst, session)
        admin_context = build_user_access_context(admin, session)
    analyst_decision = evaluate_action_approval(
        analyst_context,
        requester_app_user_id=uuid.uuid4(),
        scope_type="department",
        scope_key="it",
        record_count=2,
        crosses_scopes=True,
    )
    admin_decision = evaluate_action_approval(
        admin_context,
        requester_app_user_id=uuid.uuid4(),
        scope_type="department",
        scope_key="it",
        record_count=2,
        crosses_scopes=True,
    )
    assert analyst_decision.allowed is False
    assert analyst_decision.code == "global_approval_permission_required"
    assert admin_decision.allowed is True
    assert admin_decision.requires_admin is True


def _request(
    client: TestClient,
    engine: Engine,
    *,
    requester_email: str,
    scope_key: str,
    csrf: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        scope = _scope(session, scope_key)
        assignment = _old_assignment(session, scope.department_id)
        assignment_id = assignment.id
    preview = _preview(client, csrf, scope, assignment_id)
    assert preview.status_code == 201, preview.json()
    action_id = uuid.UUID(preview.json()["data"]["action_request_id"])
    submitted = client.post(
        "/api/v1/actions/request",
        headers={"X-CSRF-Token": csrf},
        json={
            "action_request_id": str(action_id),
            "reason": f"Deterministic release gate request by {requester_email}.",
        },
    )
    assert submitted.status_code == 200, submitted.json()
    with Session(engine) as session:
        approval = session.scalar(
            select(ApprovalRequest).where(ApprovalRequest.action_request_id == action_id)
        )
        assert approval is not None
        return assignment_id, approval.id, action_id


def _old_assignment(session: Session, department_id) -> LicenseAssignment:
    assignment = session.scalar(
        select(LicenseAssignment)
        .where(
            LicenseAssignment.department_id == department_id,
            LicenseAssignment.status == "active",
            LicenseAssignment.last_used_at < NOW - timedelta(days=60),
            LicenseAssignment.is_mandatory.is_(False),
            LicenseAssignment.is_exception.is_(False),
        )
        .order_by(LicenseAssignment.id)
    )
    assert assignment is not None
    return assignment


def _preview(client: TestClient, csrf: str, scope, assignment_id: uuid.UUID):
    return client.post(
        "/api/v1/actions/preview",
        headers={"X-CSRF-Token": csrf},
        json={
            "action_type": "reclaim_unused_license",
            "scope_id": str(scope.id),
            "department_id": str(scope.department_id),
            "license_assignment_ids": [str(assignment_id)],
            "reason": "Deterministic release-blocking action security preview.",
        },
    )


def _approve(client: TestClient, approval_id: uuid.UUID, csrf: str):
    return client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Deterministic release-blocking approval."},
    )


def _set_mandatory(engine: Engine, assignment_id: uuid.UUID) -> None:
    with Session(engine) as session:
        assignment = session.get(LicenseAssignment, assignment_id)
        assert assignment is not None
        assignment.is_mandatory = True
        session.commit()
