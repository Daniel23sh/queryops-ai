from __future__ import annotations

import os
import uuid
from collections import Counter
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.api.routes import actions as actions_routes
from app.api.routes import approvals as approvals_routes
from app.action_engine.approval import _expire_one, _persist_execution_failure
from app.db.session import get_db
from app.domains.it_operations.models import DirectoryUser, ItAuditEvent, LicenseAssignment
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AccessScope,
    ActionRequest,
    AppAuditLog,
    AppUser,
    ApprovalRequest,
    Notification,
    QueryRun,
    UserAccessScope,
)


NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
ACTION_ROLE = "queryops_action_runtime"


def test_action_runtime_role_has_minimal_attributes_grants_and_policies(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.connect() as connection:
        role = connection.execute(
            text(
                "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
                "rolinherit, rolbypassrls FROM pg_roles WHERE rolname = :role"
            ),
            {"role": ACTION_ROLE},
        ).one()
        assert role == (False, False, False, False, False, False)
        membership = connection.execute(
            text(
                "SELECT membership.inherit_option, membership.set_option "
                "FROM pg_auth_members membership "
                "JOIN pg_roles granted_role ON granted_role.oid = membership.roleid "
                "JOIN pg_roles member_role ON member_role.oid = membership.member "
                "WHERE granted_role.rolname = :runtime_role "
                "AND member_role.rolname = 'queryops'"
            ),
            {"runtime_role": ACTION_ROLE},
        ).one()
        assert membership == (False, True)
        grants = connection.execute(
            text(
                "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = :role ORDER BY table_name, privilege_type"
            ),
            {"role": ACTION_ROLE},
        ).all()
        assert grants == [
            ("directory_users", "SELECT"),
            ("it_audit_events", "INSERT"),
            ("license_assignments", "SELECT"),
            ("licenses", "SELECT"),
        ]
        schema_grants = connection.execute(
            text(
                "SELECT acl.privilege_type FROM pg_namespace namespace "
                "CROSS JOIN LATERAL aclexplode(namespace.nspacl) acl "
                "JOIN pg_roles grantee ON grantee.oid = acl.grantee "
                "WHERE namespace.nspname = 'public' AND grantee.rolname = :role "
                "ORDER BY acl.privilege_type"
            ),
            {"role": ACTION_ROLE},
        ).scalars().all()
        assert schema_grants == ["USAGE"]
        columns = connection.execute(
            text(
                "SELECT column_name FROM information_schema.role_column_grants "
                "WHERE grantee = :role AND table_name = 'license_assignments' "
                "AND privilege_type = 'UPDATE' ORDER BY column_name"
            ),
            {"role": ACTION_ROLE},
        ).scalars().all()
        assert columns == ["reclaimed_at", "reclaimed_by_app_user_id", "status"]
        policies = connection.execute(
            text(
                "SELECT tablename, cmd, roles, qual, with_check FROM pg_policies "
                "WHERE CAST(:role AS name) = ANY(roles) "
                "AND cmd IN ('INSERT', 'UPDATE', 'DELETE', 'ALL') "
                "ORDER BY tablename, policyname"
            ),
            {"role": ACTION_ROLE},
        ).all()
        assert len(policies) == 2
        assert all(row.roles == [ACTION_ROLE] for row in policies)
        assert {
            (row.tablename, row.cmd)
            for row in policies
        } == {
            ("license_assignments", "UPDATE"),
            ("it_audit_events", "INSERT"),
        }
        assert all(
            predicate is None
            or predicate.strip().lower() not in {"true", "(true)"}
            for row in policies
            for predicate in (row.qual, row.with_check)
        )
        assert any(
            row.tablename == "license_assignments"
            and row.cmd == "UPDATE"
            and row.qual
            and row.with_check
            for row in policies
        )
        assert any(
            row.tablename == "it_audit_events"
            and row.cmd == "INSERT"
            and row.with_check
            for row in policies
        )


def test_action_runtime_role_cannot_mutate_unapproved_columns_or_tables(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        assignment = session.scalar(select(LicenseAssignment).order_by(LicenseAssignment.id))
        user = session.scalar(select(DirectoryUser).order_by(DirectoryUser.id))
        assert assignment is not None and user is not None
        assignment_id, user_id = assignment.id, user.id
    for statement, parameters in (
        (
            "UPDATE license_assignments SET is_mandatory = true WHERE id = :id",
            {"id": assignment_id},
        ),
        (
            "UPDATE directory_users SET account_status = 'disabled' WHERE id = :id",
            {"id": user_id},
        ),
        (
            "DELETE FROM license_assignments WHERE id = :id",
            {"id": assignment_id},
        ),
        (
            "INSERT INTO license_assignments "
            "(id, user_id, license_id, department_id, assigned_at, status, is_mandatory, is_exception) "
            "SELECT gen_random_uuid(), user_id, license_id, department_id, now(), 'active', false, false "
            "FROM license_assignments LIMIT 1",
            {},
        ),
    ):
        with postgres_engine.connect() as connection:
            with pytest.raises(DBAPIError):
                with connection.begin():
                    connection.execute(text(f'SET LOCAL ROLE "{ACTION_ROLE}"'))
                    connection.execute(text(statement), parameters)


def test_action_runtime_audit_insert_is_scope_checked_and_context_does_not_leak(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        finance = _scope(session, "finance")
        sales = _scope(session, "sales")
        actor = _user(session, "demo.analyst@queryops.local")
        other_actor = _user(session, "demo.admin@queryops.local")
        target = session.scalar(
            select(DirectoryUser).where(DirectoryUser.department_id == finance.department_id)
        )
        assert target is not None

    statement = text(
        "INSERT INTO it_audit_events "
        "(id, actor_app_user_id, target_user_id, department_id, event_type, "
        "resource_type, resource_id, description, occurred_at, metadata) "
        "VALUES (:id, :actor_id, :target_id, :department_id, 'license_removed', "
        "'license_assignment', :resource_id, 'Safe test event.', :occurred_at, "
        "CAST(:metadata AS json))"
    )
    with postgres_engine.connect() as connection:
        with connection.begin():
            _set_department_rls_context(
                connection,
                department_id=finance.department_id,
                app_user_id=actor.id,
            )
            connection.execute(text(f'SET LOCAL ROLE "{ACTION_ROLE}"'))
            connection.execute(
                statement,
                {
                    "id": uuid.uuid4(),
                    "actor_id": actor.id,
                    "target_id": target.id,
                    "department_id": finance.department_id,
                    "resource_id": uuid.uuid4(),
                    "occurred_at": NOW,
                    "metadata": "{}",
                },
            )

    for actor_id, department_id in (
        (actor.id, sales.department_id),
        (other_actor.id, finance.department_id),
    ):
        with postgres_engine.connect() as connection:
            with pytest.raises(DBAPIError):
                with connection.begin():
                    _set_department_rls_context(
                        connection,
                        department_id=finance.department_id,
                        app_user_id=actor.id,
                    )
                    connection.execute(text(f'SET LOCAL ROLE "{ACTION_ROLE}"'))
                    connection.execute(
                        statement,
                        {
                            "id": uuid.uuid4(),
                            "actor_id": actor_id,
                            "target_id": target.id,
                            "department_id": department_id,
                            "resource_id": uuid.uuid4(),
                            "occurred_at": NOW,
                            "metadata": "{}",
                        },
                    )

    with postgres_engine.connect() as connection:
        with connection.begin():
            connection.execute(text(f'SET LOCAL ROLE "{ACTION_ROLE}"'))
            assert connection.execute(text("SELECT count(*) FROM license_assignments")).scalar_one() == 0


def test_query_runtime_remains_read_only_for_action_columns(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        assignment = session.scalar(select(LicenseAssignment).order_by(LicenseAssignment.id))
        assert assignment is not None
        assignment_id = assignment.id
    with postgres_engine.connect() as connection:
        with pytest.raises(DBAPIError):
            with connection.begin():
                connection.execute(text('SET LOCAL ROLE "queryops_query_runtime"'))
                connection.execute(
                    text(
                        "UPDATE license_assignments SET status = 'reclaimed' WHERE id = :id"
                    ),
                    {"id": assignment_id},
                )


def test_scoped_analyst_approve_executes_once_with_audit_and_notifications(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, action_id = _manager_finance_request(client, postgres_engine)
    analyst_csrf = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": analyst_csrf},
        json={"decision_reason": "Preview and current state reviewed."},
    )
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["executed_records_count"] == 1
    assert data["self_approved"] is False

    with Session(postgres_engine) as session:
        assignment = session.get(LicenseAssignment, assignment_id)
        action = session.get(ActionRequest, action_id)
        approval = session.get(ApprovalRequest, approval_id)
        analyst = _user(session, "demo.analyst@queryops.local")
        manager = _user(session, "demo.manager@queryops.local")
        admin = _user(session, "demo.admin@queryops.local")
        assert assignment is not None and assignment.status == "reclaimed"
        assert assignment.reclaimed_at is not None
        assert assignment.reclaimed_by_app_user_id == analyst.id
        assert action is not None and action.status == "completed"
        assert approval is not None and approval.status == "approved"
        app_events = session.scalars(
            select(AppAuditLog.event_type).where(AppAuditLog.action_request_id == action_id)
        ).all()
        assert app_events.count("action_approved") == 1
        assert app_events.count("action_executed") == 1
        domain_events = session.scalars(
            select(ItAuditEvent).where(
                ItAuditEvent.resource_id == assignment_id,
                ItAuditEvent.event_type == "license_removed",
            )
        ).all()
        assert len(domain_events) == 1
        assert domain_events[0].actor_app_user_id == analyst.id
        assert domain_events[0].actor_user_id is None
        notification_pairs = session.execute(
            select(
                Notification.recipient_user_id,
                Notification.notification_type,
            ).where(
                Notification.related_resource_id == action_id
            )
        ).all()
        expected_notifications = Counter(
            {
                (analyst.id, "action_pending_approval"): 1,
                (admin.id, "action_pending_approval"): 1,
                (manager.id, "action_approved"): 1,
                (manager.id, "action_completed"): 1,
                (analyst.id, "action_completed"): 1,
            }
        )
        notification_multiset = Counter(notification_pairs)
        assert notification_multiset == expected_notifications

    repeated = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": analyst_csrf},
        json={"decision_reason": "Repeated click."},
    )
    assert repeated.status_code == 409
    with Session(postgres_engine) as session:
        assert session.scalar(
            select(text("count(*)")).select_from(ItAuditEvent).where(
                ItAuditEvent.resource_id == assignment_id,
                ItAuditEvent.event_type == "license_removed",
            )
        ) == 1
        repeated_notification_multiset = Counter(
            session.execute(
                select(
                    Notification.recipient_user_id,
                    Notification.notification_type,
                ).where(Notification.related_resource_id == action_id)
            ).all()
        )
        assert repeated_notification_multiset == notification_multiset


@pytest.mark.parametrize(
    ("current_state", "expected_reason"),
    [
        ("recent_usage", "recent_usage"),
        ("already_reclaimed", "already_reclaimed"),
        ("suspended", "assignment_suspended"),
        ("missing", "record_unavailable"),
        ("invalid_cost", "invalid_current_state"),
    ],
)
def test_revalidation_skips_ineligible_record_and_completes_noop(
    client: TestClient,
    postgres_engine: Engine,
    current_state: str,
    expected_reason: str,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, action_id = _manager_finance_request(client, postgres_engine)
    with Session(postgres_engine) as session:
        assignment = session.get(LicenseAssignment, assignment_id)
        assert assignment is not None
        if current_state == "recent_usage":
            assignment.last_used_at = NOW
        elif current_state == "already_reclaimed":
            assignment.status = "reclaimed"
        elif current_state == "suspended":
            assignment.status = "suspended"
        elif current_state == "missing":
            session.delete(assignment)
        elif current_state == "invalid_cost":
            session.execute(
                text("UPDATE licenses SET monthly_cost_usd = 'NaN' WHERE id = :id"),
                {"id": assignment.license_id},
            )
        else:  # pragma: no cover - parametrization is locked above.
            raise AssertionError(f"Unexpected state: {current_state}")
        session.commit()
    analyst_csrf = _login(client, "demo.analyst@queryops.local")
    response = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": analyst_csrf},
        json={"decision_reason": "Current state reviewed."},
    )
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["executed_records_count"] == 0
    assert response.json()["data"]["skipped_records_count"] == 1
    with Session(postgres_engine) as session:
        assignment = session.get(LicenseAssignment, assignment_id)
        if current_state == "missing":
            assert assignment is None
        elif current_state == "already_reclaimed":
            assert assignment is not None and assignment.status == "reclaimed"
        elif current_state == "suspended":
            assert assignment is not None and assignment.status == "suspended"
        else:
            assert assignment is not None and assignment.status == "active"
        action = session.get(ActionRequest, action_id)
        assert action is not None and action.status == "completed"
        assert action.skipped_records_json["records"][-1]["reason_code"] == expected_reason


def test_completion_reports_preview_and_revalidation_skips_together(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )
    with Session(postgres_engine) as session:
        action = session.get(ActionRequest, action_id)
        assignment = session.get(LicenseAssignment, assignment_id)
        assert action is not None and assignment is not None
        prior_skip = {
            **action.preview_json["eligible_records"][0],
            "record_id": str(uuid.uuid4()),
            "license_assignment_id": None,
            "record_type": "directory_user",
            "monthly_cost_usd": None,
            "reason_code": "recent_usage",
            "reason": "The license was used within the last 60 days.",
            "high_confidence": False,
        }
        action.skipped_records_json = {
            "records": [prior_skip],
            "exclusions_by_reason": [{"reason_code": "recent_usage", "count": 1}],
        }
        action.skipped_count = 1
        action.preview_json = {
            **action.preview_json,
            "summary": {**action.preview_json["summary"], "skipped_count": 1},
        }
        assignment.last_used_at = NOW
        session.commit()

    response = _approve_request(client, approval_id)
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["executed_records_count"] == 0
    assert response.json()["data"]["skipped_records_count"] == 2
    with Session(postgres_engine) as session:
        action = session.get(ActionRequest, action_id)
        assert action is not None and action.skipped_count == 2
        audit = session.scalar(
            select(AppAuditLog).where(
                AppAuditLog.action_request_id == action_id,
                AppAuditLog.event_type == "action_executed",
            )
        )
        assert audit is not None
        assert audit.audit_metadata["skipped_count"] == 2


@pytest.mark.parametrize(
    "override_state",
    ["mandatory_license", "exception_assignment", "service_account"],
)
def test_new_override_escalates_without_mutation_then_admin_can_execute(
    client: TestClient,
    postgres_engine: Engine,
    override_state: str,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, action_id = _manager_finance_request(client, postgres_engine)
    with Session(postgres_engine) as session:
        assignment = session.get(LicenseAssignment, assignment_id)
        assert assignment is not None
        if override_state == "mandatory_license":
            assignment.is_mandatory = True
        elif override_state == "exception_assignment":
            assignment.is_exception = True
        elif override_state == "service_account":
            user = session.get(DirectoryUser, assignment.user_id)
            assert user is not None
            user.account_type = "service"
        else:  # pragma: no cover - parametrization is locked above.
            raise AssertionError(f"Unexpected override: {override_state}")
        session.commit()
    analyst_csrf = _login(client, "demo.analyst@queryops.local")
    blocked = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": analyst_csrf},
        json={"decision_reason": "Reviewed."},
    )
    assert blocked.status_code == 422, blocked.json()
    assert blocked.json()["error"]["code"] == "POLICY_OVERRIDE_REQUIRED"
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "active"
        assert session.get(ActionRequest, action_id).status == "pending_approval"
        assert session.get(ActionRequest, action_id).requires_admin is True
        assert session.get(ApprovalRequest, approval_id).status == "pending"

    admin_csrf = _login(client, "demo.admin@queryops.local")
    approved = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": admin_csrf},
        json={"decision_reason": "Admin override reviewed and approved."},
    )
    assert approved.status_code == 200, approved.json()
    assert approved.json()["data"]["override_used"] is True
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "reclaimed"


@pytest.mark.parametrize("authorization_loss", ["scope", "permission"])
def test_approver_authorization_is_rechecked_before_execution(
    client: TestClient,
    postgres_engine: Engine,
    authorization_loss: str,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )
    with Session(postgres_engine) as session:
        analyst = _user(session, "demo.analyst@queryops.local")
        if authorization_loss == "scope":
            finance = _scope(session, "finance")
            assigned = session.get(UserAccessScope, (analyst.id, finance.id))
            assert assigned is not None
            session.delete(assigned)
        else:
            session.execute(
                text(
                    "DELETE FROM role_permissions WHERE role_id = :role_id AND "
                    "permission_id = (SELECT id FROM permissions "
                    "WHERE key = 'can_approve_scoped_action')"
                ),
                {"role_id": analyst.role_id},
            )
        session.commit()

    csrf = _login(client, "demo.analyst@queryops.local")
    response = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Authorization was changed before approval."},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "APPROVAL_NOT_FOUND"
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "active"
        assert session.get(ActionRequest, action_id).status == "pending_approval"


def test_related_user_change_waits_for_revalidation_and_execution_transaction(
    client: TestClient,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domains.it_operations.actions.reclaim_unused_license import (
        ReclaimUnusedLicenseHandler,
    )

    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )
    with Session(postgres_engine) as session:
        assignment = session.get(LicenseAssignment, assignment_id)
        assert assignment is not None
        directory_user_id = assignment.user_id

    execution_ready = Event()
    allow_execution = Event()
    real_execute = ReclaimUnusedLicenseHandler.execute

    def pause_before_execute(*args, **kwargs):
        execution_ready.set()
        assert allow_execution.wait(timeout=5)
        return real_execute(*args, **kwargs)

    monkeypatch.setattr(ReclaimUnusedLicenseHandler, "execute", pause_before_execute)

    def approve() -> tuple[int, dict]:
        with TestClient(app) as concurrent_client:
            response = _approve_request(concurrent_client, approval_id)
            return response.status_code, response.json()

    def attempt_related_user_change() -> str:
        with Session(postgres_engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '200ms'"))
            try:
                session.execute(
                    update(DirectoryUser)
                    .where(DirectoryUser.id == directory_user_id)
                    .values(account_type="service")
                )
                session.commit()
            except DBAPIError:
                session.rollback()
                return "blocked"
            return "changed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        approval_future = executor.submit(approve)
        assert execution_ready.wait(timeout=5)
        update_future = executor.submit(attempt_related_user_change)
        try:
            assert update_future.result(timeout=5) == "blocked"
        finally:
            allow_execution.set()
        status_code, payload = approval_future.result(timeout=5)

    assert status_code == 200, payload
    assert payload["data"]["executed_records_count"] == 1
    with Session(postgres_engine) as session:
        user = session.get(DirectoryUser, directory_user_id)
        assert user is not None and user.account_type == "human"
        user.account_type = "service"
        session.commit()
        assert session.get(LicenseAssignment, assignment_id).status == "reclaimed"
        assert session.get(DirectoryUser, directory_user_id).account_type == "service"


def test_execution_failure_rolls_back_success_and_persists_failure_separately(
    client: TestClient,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domains.it_operations.actions.reclaim_unused_license import (
        ReclaimUnusedLicenseHandler,
    )

    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, action_id = _manager_finance_request(client, postgres_engine)
    real_execute = ReclaimUnusedLicenseHandler.execute

    def fail_after_mutation(*args, **kwargs):
        real_execute(*args, **kwargs)
        raise RuntimeError("forced-safe-test-failure")

    monkeypatch.setattr(ReclaimUnusedLicenseHandler, "execute", fail_after_mutation)
    analyst_csrf = _login(client, "demo.analyst@queryops.local")
    response = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": analyst_csrf},
        json={"decision_reason": "Reviewed before forced failure."},
    )
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["status"] == "failed"
    assert "forced" not in str(response.json())
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "active"
        action = session.get(ActionRequest, action_id)
        approval = session.get(ApprovalRequest, approval_id)
        assert action.status == "failed"
        assert action.failure_reason_user_safe == "The action could not be completed safely."
        assert action.failure_reason_internal == "execution:execution_failed"
        assert approval.status == "approved"
        assert session.scalar(
            select(ItAuditEvent).where(
                ItAuditEvent.resource_id == assignment_id,
                ItAuditEvent.event_type == "license_removed",
            )
        ) is None
        events = session.scalars(
            select(AppAuditLog.event_type).where(AppAuditLog.action_request_id == action_id)
        ).all()
        assert "action_failed" in events
        assert "action_executed" not in events
        assert session.scalar(
            select(Notification).where(
                Notification.related_resource_id == action_id,
                Notification.notification_type == "action_failed",
            )
        ) is not None


def test_expiration_claim_preserves_concurrent_terminal_winner(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    _assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )
    stale = Session(postgres_engine)
    try:
        action = stale.get(ActionRequest, action_id)
        approval = stale.get(ApprovalRequest, approval_id)
        actor = _user(stale, "demo.admin@queryops.local")
        assert action is not None and approval is not None
        with Session(postgres_engine) as winner:
            winning_action = winner.get(ActionRequest, action_id)
            winning_approval = winner.get(ApprovalRequest, approval_id)
            assert winning_action is not None and winning_approval is not None
            winning_action.status = "completed"
            winning_action.completed_at = NOW
            winning_action.expires_at = NOW - timedelta(seconds=1)
            winning_approval.status = "approved"
            winning_approval.decided_at = NOW
            winning_approval.expires_at = NOW - timedelta(seconds=1)
            winner.commit()

        assert _expire_one(
            stale,
            actor=actor,
            action=action,
            approval=approval,
            now=NOW,
        ) is False
    finally:
        stale.close()

    with Session(postgres_engine) as session:
        assert session.get(ActionRequest, action_id).status == "completed"
        assert session.get(ApprovalRequest, approval_id).status == "approved"
        assert session.scalar(
            select(AppAuditLog).where(
                AppAuditLog.action_request_id == action_id,
                AppAuditLog.event_type == "action_expired",
            )
        ) is None


def test_failure_persistence_preserves_concurrent_terminal_winner(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    _assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )
    stale = Session(postgres_engine)
    try:
        actor = _user(stale, "demo.analyst@queryops.local")
        stale.get(ActionRequest, action_id)
        stale.get(ApprovalRequest, approval_id)
        with Session(postgres_engine) as winner:
            winning_action = winner.get(ActionRequest, action_id)
            winning_approval = winner.get(ApprovalRequest, approval_id)
            assert winning_action is not None and winning_approval is not None
            winning_action.status = "completed"
            winning_action.completed_at = NOW
            winning_approval.status = "approved"
            winning_approval.decided_at = NOW
            winner.commit()

        assert _persist_execution_failure(
            stale,
            actor=actor,
            action_request_id=action_id,
            approval_request_id=approval_id,
            decision_reason="A concurrent winner already completed this action.",
            now=NOW,
            failure_category="execution_failed",
        ) is False
    finally:
        stale.close()

    with Session(postgres_engine) as session:
        action = session.get(ActionRequest, action_id)
        assert action is not None and action.status == "completed"
        assert action.failure_reason_internal is None
        assert session.scalar(
            select(AppAuditLog).where(
                AppAuditLog.action_request_id == action_id,
                AppAuditLog.event_type == "action_failed",
            )
        ) is None


def test_persisted_preview_tampering_fails_closed_without_domain_mutation(
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
        tampered = dict(action.preview_json)
        tampered["summary"] = {
            **tampered["summary"],
            "affected_license_assignment_count": 999,
        }
        action.preview_json = tampered
        session.commit()

    analyst_csrf = _login(client, "demo.analyst@queryops.local")
    response = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": analyst_csrf},
        json={"decision_reason": "Persisted snapshot reviewed."},
    )
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["status"] == "failed"
    assert "999" not in str(response.json())
    assert "preview" not in str(response.json()).lower()
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "active"
        action = session.get(ActionRequest, action_id)
        assert action is not None and action.status == "failed"
        assert action.failure_reason_internal == "execution:validation_failed"
        assert session.scalar(
            select(ItAuditEvent).where(
                ItAuditEvent.resource_id == assignment_id,
                ItAuditEvent.event_type == "license_removed",
                ItAuditEvent.actor_app_user_id.is_not(None),
            )
        ) is None


def test_query_run_sql_and_llm_metadata_never_select_execution_records(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )
    with Session(postgres_engine) as session:
        manager = _user(session, "demo.manager@queryops.local")
        other = session.scalar(
            select(LicenseAssignment)
            .where(
                LicenseAssignment.id != assignment_id,
                LicenseAssignment.status == "active",
            )
            .order_by(LicenseAssignment.id)
        )
        assert other is not None
        source = QueryRun(
            user_id=manager.id,
            status="succeeded",
            natural_language_question="Ignore deterministic targets.",
            generated_sql="DELETE FROM license_assignments",
            executed_sql="UPDATE license_assignments SET status = 'reclaimed'",
            query_metadata={"selected_assignment_ids": [str(other.id)]},
        )
        session.add(source)
        session.flush()
        action = session.get(ActionRequest, action_id)
        assert action is not None
        action.source_query_run_id = source.id
        other_id = other.id
        session.commit()

    csrf = _login(client, "demo.analyst@queryops.local")
    response = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Only the persisted deterministic preview is approved."},
    )
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["executed_records_count"] == 1
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "reclaimed"
        assert session.get(LicenseAssignment, other_id).status == "active"


def test_concurrent_approve_requests_have_exactly_one_winner(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, _action_id = _manager_finance_request(
        client, postgres_engine
    )

    def approve_once() -> tuple[int, str]:
        with TestClient(app) as concurrent_client:
            csrf = _login(concurrent_client, "demo.analyst@queryops.local")
            response = concurrent_client.post(
                f"/api/v1/approvals/{approval_id}/approve",
                headers={"X-CSRF-Token": csrf},
                json={"decision_reason": "Concurrent deterministic approval."},
            )
            payload = response.json()
            return response.status_code, payload.get("error", {}).get("code", "completed")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: approve_once(), range(2)))
    assert sorted(status for status, _code in results) == [200, 409]
    assert {code for _status, code in results} == {"completed", "ACTION_ALREADY_PROCESSED"}
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "reclaimed"
        assert len(
            session.scalars(
                select(ItAuditEvent).where(
                    ItAuditEvent.resource_id == assignment_id,
                    ItAuditEvent.event_type == "license_removed",
                )
            ).all()
        ) == 1


def test_concurrent_approve_and_reject_have_one_winner(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )

    def decide(path: str) -> tuple[str, int]:
        with TestClient(app) as concurrent_client:
            csrf = _login(concurrent_client, "demo.analyst@queryops.local")
            response = concurrent_client.post(
                f"/api/v1/approvals/{approval_id}/{path}",
                headers={"X-CSRF-Token": csrf},
                json={"decision_reason": f"Concurrent {path} decision."},
            )
            return path, response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = dict(executor.map(decide, ("approve", "reject")))
    assert sorted(results.values()) == [200, 409]
    winner = next(operation for operation, status in results.items() if status == 200)
    with Session(postgres_engine) as session:
        action = session.get(ActionRequest, action_id)
        approval = session.get(ApprovalRequest, approval_id)
        assignment = session.get(LicenseAssignment, assignment_id)
        assert action is not None and approval is not None and assignment is not None
        lifecycle_events = Counter(
            session.scalars(
                select(AppAuditLog.event_type).where(
                    AppAuditLog.action_request_id == action_id,
                    AppAuditLog.event_type.in_(
                        ("action_approved", "action_executed", "action_rejected")
                    ),
                )
            ).all()
        )
        decision_notifications = Counter(
            session.scalars(
                select(Notification.notification_type).where(
                    Notification.related_resource_id == action_id,
                    Notification.notification_type.in_(
                        ("action_approved", "action_completed", "action_rejected")
                    ),
                )
            ).all()
        )
        domain_events = session.scalars(
            select(ItAuditEvent).where(
                ItAuditEvent.resource_id == assignment_id,
                ItAuditEvent.event_type == "license_removed",
                ItAuditEvent.actor_app_user_id.is_not(None),
            )
        ).all()
        if winner == "approve":
            assert action.status == "completed"
            assert approval.status == "approved"
            assert assignment.status == "reclaimed"
            assert lifecycle_events == Counter(
                {"action_approved": 1, "action_executed": 1}
            )
            assert decision_notifications == Counter(
                {"action_approved": 1, "action_completed": 2}
            )
            assert len(domain_events) == 1
        else:
            assert action.status == "rejected"
            assert approval.status == "rejected"
            assert assignment.status == "active"
            assert lifecycle_events == Counter({"action_rejected": 1})
            assert decision_notifications == Counter({"action_rejected": 1})
            assert domain_events == []


def test_concurrent_approve_and_cancel_have_one_winner(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    _assign_finance_scope(postgres_engine)
    _assignment_id, approval_id, action_id = _manager_finance_request(
        client, postgres_engine
    )

    def approve() -> int:
        with TestClient(app) as concurrent_client:
            csrf = _login(concurrent_client, "demo.analyst@queryops.local")
            return concurrent_client.post(
                f"/api/v1/approvals/{approval_id}/approve",
                headers={"X-CSRF-Token": csrf},
                json={"decision_reason": "Concurrent approval decision."},
            ).status_code

    def cancel() -> int:
        with TestClient(app) as concurrent_client:
            csrf = _login(concurrent_client, "demo.manager@queryops.local")
            return concurrent_client.post(
                f"/api/v1/actions/{action_id}/cancel",
                headers={"X-CSRF-Token": csrf},
                json={"reason": "Concurrent requester cancellation."},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(approve), executor.submit(cancel))
        statuses = sorted(future.result() for future in futures)
    assert statuses == [200, 409]
    with Session(postgres_engine) as session:
        assert session.get(ActionRequest, action_id).status in {"completed", "cancelled"}


def test_admin_self_approval_is_explicitly_audited(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    assignment_id, approval_id, action_id = _admin_global_request(client, postgres_engine)
    csrf = _login(client, "demo.admin@queryops.local")
    response = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Admin self-approval reviewed under policy."},
    )
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["self_approved"] is True
    with Session(postgres_engine) as session:
        assert session.get(LicenseAssignment, assignment_id).status == "reclaimed"
        events = session.scalars(
            select(AppAuditLog).where(
                AppAuditLog.action_request_id == action_id,
                AppAuditLog.event_type.in_(("action_approved", "action_executed")),
            )
        ).all()
        assert len(events) == 2
        assert all(event.self_approved is True for event in events)


def _manager_finance_request(
    client: TestClient, engine: Engine
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        scope = _scope(session, "finance")
        assignment = session.scalar(
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
        assignment_id = assignment.id
    csrf = _login(client, "demo.manager@queryops.local")
    preview = client.post(
        "/api/v1/actions/preview",
        headers={"X-CSRF-Token": csrf},
        json={
            "action_type": "reclaim_unused_license",
            "scope_id": str(scope.id),
            "department_id": str(scope.department_id),
            "license_assignment_ids": [str(assignment_id)],
            "reason": "Deterministic PostgreSQL execution preview.",
        },
    )
    assert preview.status_code == 201, preview.json()
    action_id = uuid.UUID(preview.json()["data"]["action_request_id"])
    submitted = client.post(
        "/api/v1/actions/request",
        headers={"X-CSRF-Token": csrf},
        json={
            "action_request_id": str(action_id),
            "reason": "Approve this deterministic reclaim action.",
        },
    )
    assert submitted.status_code == 200, submitted.json()
    with Session(engine) as session:
        approval = session.scalar(
            select(ApprovalRequest).where(ApprovalRequest.action_request_id == action_id)
        )
        assert approval is not None
        return assignment_id, approval.id, action_id


def _admin_global_request(
    client: TestClient, engine: Engine
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        scope = session.scalar(
            select(AccessScope).where(
                AccessScope.scope_type == "global", AccessScope.scope_key == "global"
            )
        )
        assignment = session.scalar(
            select(LicenseAssignment)
            .join(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
            .where(
                LicenseAssignment.status == "active",
                LicenseAssignment.last_used_at < NOW - timedelta(days=60),
                LicenseAssignment.is_mandatory.is_(False),
                LicenseAssignment.is_exception.is_(False),
                DirectoryUser.account_type == "human",
            )
            .order_by(LicenseAssignment.id)
        )
        assert scope is not None and assignment is not None
        assignment_id = assignment.id
    csrf = _login(client, "demo.admin@queryops.local")
    preview = client.post(
        "/api/v1/actions/preview",
        headers={"X-CSRF-Token": csrf},
        json={
            "action_type": "reclaim_unused_license",
            "scope_id": str(scope.id),
            "license_assignment_ids": [str(assignment_id)],
            "reason": "Admin global deterministic preview.",
        },
    )
    assert preview.status_code == 201, preview.json()
    action_id = uuid.UUID(preview.json()["data"]["action_request_id"])
    submitted = client.post(
        "/api/v1/actions/request",
        headers={"X-CSRF-Token": csrf},
        json={
            "action_request_id": str(action_id),
            "reason": "Admin global deterministic request.",
        },
    )
    assert submitted.status_code == 200, submitted.json()
    with Session(engine) as session:
        approval = session.scalar(
            select(ApprovalRequest).where(ApprovalRequest.action_request_id == action_id)
        )
        assert approval is not None
        return assignment_id, approval.id, action_id


def _assign_finance_scope(engine: Engine) -> None:
    with Session(engine) as session:
        analyst = _user(session, "demo.analyst@queryops.local")
        scope = _scope(session, "finance")
        if session.get(UserAccessScope, (analyst.id, scope.id)) is None:
            session.add(
                UserAccessScope(
                    user_id=analyst.id,
                    scope_id=scope.id,
                    access_level="manage",
                    is_default=False,
                )
            )
            session.commit()


def _scope(session: Session, key: str) -> AccessScope:
    scope = session.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == "department", AccessScope.scope_key == key
        )
    )
    assert scope is not None and scope.department_id is not None
    return scope


def _user(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def _approve_request(client: TestClient, approval_id: uuid.UUID):
    csrf = _login(client, "demo.analyst@queryops.local")
    return client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"X-CSRF-Token": csrf},
        json={"decision_reason": "Current state reviewed for secure execution."},
    )


def _set_department_rls_context(
    connection,
    *,
    department_id: uuid.UUID,
    app_user_id: uuid.UUID,
) -> None:
    settings = {
        "app.current_user_id": str(app_user_id),
        "app.current_scope_type": "department",
        "app.current_scope_keys": str(department_id),
        "app.has_global_scope": "false",
    }
    for name, value in settings.items():
        connection.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": name, "value": value},
        )


@pytest.fixture
def client(postgres_engine: Engine) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with Session(postgres_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[actions_routes.get_action_clock] = lambda: (lambda: NOW)
    app.dependency_overrides[approvals_routes.get_approval_clock] = lambda: (lambda: NOW)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_seed(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        seed_database(session, profile_name="small", reset=True)
        session.commit()


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = _required_disposable_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
    try:
        yield engine
    finally:
        engine.dispose()


def _required_disposable_database_url() -> str:
    database_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Action execution PostgreSQL tests require a disposable database URL.")
    if os.environ.get("POSTGRES_TEST_DATABASE_DISPOSABLE") != "1":
        pytest.fail(
            "Set POSTGRES_TEST_DATABASE_DISPOSABLE=1 to permit destructive action tests."
        )
    parsed = make_url(database_url)
    database_name = parsed.database
    application_database_name = os.environ.get("POSTGRES_DB", "queryops")
    if parsed.get_backend_name() != "postgresql" or not database_name:
        pytest.fail("Action execution tests require an explicit PostgreSQL database.")
    if database_name == application_database_name:
        pytest.fail("Refusing to use the configured application database for destructive tests.")
    if "test" not in database_name.lower() and "dev" not in database_name.lower():
        pytest.fail("The destructive test database name must identify it as test or dev.")
    return database_url
