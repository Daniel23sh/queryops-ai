from __future__ import annotations

import os
import threading
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from action_postgres_test_db import validated_disposable_database_url
from app.api.routes import role_requests
from app.db.session import get_db
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AccessScope,
    AppAuditLog,
    AppUser,
    Permission,
    PermissionEffect,
    Role,
    RoleUpgradeRequest,
    UserAccessScope,
    UserPermission,
)


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine, None, None]:
    raw_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Role integrity tests require an explicit disposable PostgreSQL URL.")
    database_url = validated_disposable_database_url(raw_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = database_url
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def client(postgres_engine: Engine) -> Generator[TestClient, None, None]:
    with Session(postgres_engine) as db:
        seed_database(db, profile_name="small", reset=True)
        db.commit()

    def override_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return response.json()["data"]["csrf_token"]


def _user(db: Session, email: str) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _scope(db: Session, key: str, scope_type: str = "department") -> AccessScope:
    scope = db.scalar(select(AccessScope).where(
        AccessScope.scope_type == scope_type, AccessScope.scope_key == key,
    ))
    assert scope is not None
    return scope


def _create(client: TestClient, role: str = "manager", scope_id: UUID | None = None):
    token = _login(client, "demo.user@queryops.local")
    return client.post("/api/v1/role-requests", headers={"X-CSRF-Token": token}, json={
        "requested_role": role, "requested_scope_id": str(scope_id) if scope_id else None,
        "reason": "Controlled role integrity request.",
    })


def _decide(client: TestClient, request_id: str, operation: str = "approve"):
    token = _login(client, "demo.admin@queryops.local")
    return client.post(f"/api/v1/admin/role-requests/{request_id}/{operation}",
        headers={"X-CSRF-Token": token},
        json={"decision_reason": "Controlled role integrity decision."})


def _assert_state(engine: Engine, request_id: str, status: str, role: str, audits: int) -> None:
    with Session(engine) as db:
        request = db.get(RoleUpgradeRequest, UUID(request_id))
        assert request is not None and request.status == status
        user = _user(db, "demo.user@queryops.local")
        assert user.role.name == role
        assert db.scalar(select(func.count()).select_from(AppAuditLog).where(
            AppAuditLog.entity_id == request.id,
            AppAuditLog.event_type.in_(["role_request.approved", "role_request.rejected"]),
        )) == audits


def _force_requester_contention(monkeypatch: pytest.MonkeyPatch):
    first_locked = threading.Event()
    release_first = threading.Event()
    second_attempted = threading.Event()
    second_acquired = threading.Event()
    original = role_requests._lock_role_requester
    guard = threading.Lock()
    count = 0

    def controlled_lock(db, user_id):
        nonlocal count
        with guard:
            count += 1
            position = count
        if position == 2:
            second_attempted.set()
        result = original(db, user_id)
        if position == 1:
            first_locked.set()
            assert release_first.wait(5)
        elif position == 2:
            second_acquired.set()
        return result

    monkeypatch.setattr(role_requests, "_lock_role_requester", controlled_lock)
    return first_locked, release_first, second_attempted, second_acquired


def _wait_for_requester_lock(engine: Engine) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            blocked = connection.scalar(text("""
                SELECT query FROM pg_stat_activity
                WHERE datname = current_database() AND wait_event_type = 'Lock'
                  AND query LIKE '%app_users%' AND query LIKE '%FOR%UPDATE%'
            """))
        if blocked:
            assert "FOR NO KEY UPDATE" in blocked
            return
        time.sleep(0.01)
    pytest.fail("The concurrent request did not reach a PostgreSQL row-lock wait.")


def _run_contended(monkeypatch, engine, first, second):
    locked, release, attempted, acquired = _force_requester_contention(monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(first)
        assert locked.wait(5)
        b = pool.submit(second)
        try:
            assert attempted.wait(5)
            _wait_for_requester_lock(engine)
            assert not acquired.is_set(), "Second operation must wait on PostgreSQL's requester lock."
        finally:
            release.set()
        return a.result(timeout=5), b.result(timeout=5)


def test_concurrent_creates_leave_one_pending_request(client, postgres_engine, monkeypatch):
    def create():
        with TestClient(app) as other:
            return _create(other)

    first, second = _run_contended(monkeypatch, postgres_engine, create, create)
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "PENDING_ROLE_REQUEST_EXISTS"
    with Session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(RoleUpgradeRequest).where(
            RoleUpgradeRequest.requester_user_id == _user(db, "demo.user@queryops.local").id,
            RoleUpgradeRequest.status == "pending",
        )) == 1
        assert db.scalar(select(func.count()).select_from(AppAuditLog).where(
            AppAuditLog.event_type.like("role_request.%"),
        )) == 0


@pytest.mark.parametrize("first_operation,second_operation", [
    ("approve", "approve"), ("approve", "reject"), ("reject", "approve"),
])
def test_concurrent_decisions_have_one_consistent_winner(
    client, postgres_engine, monkeypatch, first_operation, second_operation,
):
    created = _create(client)
    assert created.status_code == 201
    request_id = created.json()["data"]["id"]

    def decide(operation):
        with TestClient(app) as other:
            return _decide(other, request_id, operation)

    first, second = _run_contended(
        monkeypatch, postgres_engine, lambda: decide(first_operation), lambda: decide(second_operation),
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ROLE_REQUEST_ALREADY_PROCESSED"
    _assert_state(postgres_engine, request_id,
        "approved" if first_operation == "approve" else "rejected",
        "manager" if first_operation == "approve" else "user", 1)
    with Session(postgres_engine) as db:
        assignment = db.get(UserAccessScope, {
            "user_id": _user(db, "demo.user@queryops.local").id,
            "scope_id": _scope(db, "sales").id,
        })
        assert assignment is not None and assignment.access_level == "read"
        audit = db.scalar(select(AppAuditLog).where(AppAuditLog.entity_id == UUID(request_id)))
        assert audit.event_type == f"role_request.{first.json()['data']['status']}"


@pytest.mark.parametrize("change", ["role", "role_missing", "inactive", "scope_key", "scope_type", "scope_department", "deleted_scope"])
def test_approval_revalidates_current_requester_and_scope(client, postgres_engine, change):
    with Session(postgres_engine) as db:
        scope_id = _scope(db, "sales").id
    created = _create(client, scope_id=scope_id)
    assert created.status_code == 201
    request_id = created.json()["data"]["id"]
    with Session(postgres_engine) as db:
        user = _user(db, "demo.user@queryops.local")
        if change == "role":
            user.role_id = db.scalar(select(Role.id).where(Role.name == "analyst"))
        elif change == "role_missing":
            user.role_id = None
        elif change == "inactive":
            user.status = "disabled"
        elif change == "scope_key":
            _scope(db, "sales").scope_key = "changed-sales"
        elif change == "scope_type":
            _scope(db, "sales").scope_type = "global"
        elif change == "scope_department":
            _scope(db, "sales").department_id = _scope(db, "it").department_id
        else:
            db.delete(_scope(db, "sales"))
        db.commit()
    response = _decide(client, request_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROLE_REQUEST_STATE_CHANGED"
    with Session(postgres_engine) as db:
        request = db.get(RoleUpgradeRequest, UUID(request_id))
        assert request.status == "pending" and request.decided_at is None
        assert db.scalar(select(func.count()).select_from(AppAuditLog).where(
            AppAuditLog.entity_id == request.id,
        )) == 0


def test_approval_failure_rolls_back_role_scope_decision_and_audit(client, postgres_engine):
    with Session(postgres_engine) as db:
        it_scope = _scope(db, "it").id
    created = _create(client, role="analyst", scope_id=it_scope)
    assert created.status_code == 201
    request_id = created.json()["data"]["id"]

    def fail_audit_flush(session, _flush_context, _instances):
        if any(isinstance(obj, AppAuditLog) and obj.event_type == "role_request.approved" for obj in session.new):
            raise SQLAlchemyError("controlled audit persistence failure")

    event.listen(Session, "before_flush", fail_audit_flush)
    try:
        response = _decide(client, request_id)
    finally:
        event.remove(Session, "before_flush", fail_audit_flush)
    assert response.status_code == 503
    assert "controlled" not in response.text
    _assert_state(postgres_engine, request_id, "pending", "user", 0)
    with Session(postgres_engine) as db:
        user = _user(db, "demo.user@queryops.local")
        assert db.get(UserAccessScope, {"user_id": user.id, "scope_id": it_scope}) is None
        sales = db.get(UserAccessScope, {"user_id": user.id, "scope_id": _scope(db, "sales").id})
        assert sales.is_default is True
    assert _decide(client, request_id).status_code == 200
    _assert_state(postgres_engine, request_id, "approved", "analyst", 1)


@pytest.mark.parametrize("change", ["requester_role", "actor_permission", "actor_role"])
def test_state_loaded_before_lock_wait_is_refreshed(
    client, postgres_engine, monkeypatch, change,
):
    created = _create(client)
    assert created.status_code == 201
    request_id = created.json()["data"]["id"]
    attempted = threading.Event()
    original = role_requests._lock_role_requester

    def notify(db, user_id):
        # Force the request's auth dependency and ORM lookup to precede the other commit.
        db.info["prefetched_requester"] = db.get(AppUser, user_id)
        attempted.set()
        return original(db, user_id)

    monkeypatch.setattr(role_requests, "_lock_role_requester", notify)
    with Session(postgres_engine) as blocking:
        user = _user(blocking, "demo.user@queryops.local")
        blocking.execute(select(AppUser).where(AppUser.id == user.id).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: _decide(TestClient(app), request_id))
            try:
                assert attempted.wait(5)
                _wait_for_requester_lock(postgres_engine)
                if change == "requester_role":
                    user.role_id = blocking.scalar(select(Role.id).where(Role.name == "analyst"))
                else:
                    actor = _user(blocking, "demo.admin@queryops.local")
                    if change == "actor_role":
                        actor.role_id = blocking.scalar(select(Role.id).where(Role.name == "user"))
                    else:
                        permission_id = blocking.scalar(select(Permission.id).where(Permission.key == "can_approve_role_requests"))
                        blocking.add(UserPermission(user_id=actor.id, permission_id=permission_id, effect=PermissionEffect.DENY.value))
                blocking.commit()
            finally:
                blocking.rollback()
            response = future.result(timeout=5)
    assert response.status_code == (409 if change == "requester_role" else 403)
    with Session(postgres_engine) as db:
        request = db.get(RoleUpgradeRequest, UUID(request_id))
        assert request.status == "pending"
        assert db.scalar(select(func.count()).select_from(AppAuditLog).where(AppAuditLog.entity_id == request.id)) == 0


@pytest.mark.parametrize("operation", ["approve", "reject"])
def test_existing_duplicate_pending_requests_fail_closed(client, postgres_engine, operation):
    created = _create(client)
    assert created.status_code == 201
    request_id = created.json()["data"]["id"]
    with Session(postgres_engine) as db:
        original = db.get(RoleUpgradeRequest, UUID(request_id))
        db.add(RoleUpgradeRequest(
            requester_user_id=original.requester_user_id,
            requested_role_id=original.requested_role_id,
            requested_scope_id=original.requested_scope_id,
            requested_scope_type=original.requested_scope_type,
            requested_scope_key=original.requested_scope_key,
            department_id=original.department_id, status="pending", reason="Historical duplicate",
        ))
        db.commit()
    response = _decide(client, request_id, operation)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROLE_REQUEST_STATE_CHANGED"
    _assert_state(postgres_engine, request_id, "pending", "user", 0)
    with Session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(RoleUpgradeRequest).where(
            RoleUpgradeRequest.status == "pending",
        )) == 2


def test_create_revalidates_role_loaded_before_lock_wait(client, postgres_engine, monkeypatch):
    attempted = threading.Event()
    original = role_requests._lock_role_requester

    def notify(db, user_id):
        attempted.set()
        return original(db, user_id)

    monkeypatch.setattr(role_requests, "_lock_role_requester", notify)
    with Session(postgres_engine) as blocking:
        user = _user(blocking, "demo.user@queryops.local")
        blocking.execute(select(AppUser).where(AppUser.id == user.id).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: _create(TestClient(app)))
            try:
                assert attempted.wait(5)
                _wait_for_requester_lock(postgres_engine)
                user.role_id = blocking.scalar(select(Role.id).where(Role.name == "manager"))
                blocking.commit()
            finally:
                blocking.rollback()
            response = future.result(timeout=5)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ROLE_REQUEST_CURRENT_ROLE"
    with Session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(RoleUpgradeRequest)) == 0


def test_independent_cross_approvals_do_not_deadlock_audit_foreign_keys(
    client, postgres_engine, monkeypatch,
):
    emails = ["demo.manager@queryops.local", "demo.analyst@queryops.local"]
    with Session(postgres_engine) as db:
        permission_id = db.scalar(select(Permission.id).where(Permission.key == "can_approve_role_requests"))
        for email in emails:
            db.add(UserPermission(user_id=_user(db, email).id,
                permission_id=permission_id, effect=PermissionEffect.ALLOW.value))
        db.commit()
    request_ids = []
    for email in emails:
        token = _login(client, email)
        response = client.post("/api/v1/role-requests", headers={"X-CSRF-Token": token},
            json={"requested_role": "admin", "reason": "Independent global role request."})
        assert response.status_code == 201
        request_ids.append(response.json()["data"]["id"])

    both_locked = threading.Barrier(2)
    original = role_requests._lock_role_requester

    def synchronized_lock(db, user_id):
        result = original(db, user_id)
        both_locked.wait(timeout=5)
        return result

    monkeypatch.setattr(role_requests, "_lock_role_requester", synchronized_lock)

    def approve(index):
        with TestClient(app) as other:
            token = _login(other, emails[index])
            return other.post(f"/api/v1/admin/role-requests/{request_ids[1-index]}/approve",
                headers={"X-CSRF-Token": token}, json={"decision_reason": "Independent approval."})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(approve, range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    with Session(postgres_engine) as db:
        assert [_user(db, email).role.name for email in emails] == ["admin", "admin"]
        assert db.scalar(select(func.count()).select_from(AppAuditLog).where(
            AppAuditLog.event_type == "role_request.approved",
        )) == 2


def test_admin_approval_persists_global_requested_and_assigned_scope_consistently(client, postgres_engine):
    created = _create(client, role="admin")
    assert created.status_code == 201
    request_id = created.json()["data"]["id"]
    response = _decide(client, request_id)
    assert response.status_code == 200
    with Session(postgres_engine) as db:
        global_scope = _scope(db, "global", "global")
        request = db.get(RoleUpgradeRequest, UUID(request_id))
        assert request.requested_scope_id == global_scope.id
        assert request.requested_scope_type == "global"
        assert request.requested_scope_key == "global"
        assert request.department_id is None
        assignment = db.get(UserAccessScope, {
            "user_id": request.requester_user_id, "scope_id": global_scope.id,
        })
        assert assignment.access_level == "manage" and assignment.is_default
        audit = db.scalar(select(AppAuditLog).where(AppAuditLog.entity_id == request.id))
        assert audit.audit_metadata["requested_scope"] == {
            "id": str(global_scope.id), "type": "global", "key": "global",
        }
        assert audit.audit_metadata["assigned_scope"] == {
            **audit.audit_metadata["requested_scope"], "access_level": "manage",
        }


@pytest.mark.parametrize("malformed", ["department_missing", "department_key_empty", "global_department"])
def test_malformed_scope_metadata_is_not_an_approval_grant(client, postgres_engine, malformed):
    with Session(postgres_engine) as db:
        scope = _scope(db, "global", "global") if malformed == "global_department" else _scope(db, "sales")
        scope_id = scope.id
        if malformed == "department_missing":
            scope.department_id = None
        elif malformed == "department_key_empty":
            scope.scope_key = ""
        else:
            scope.department_id = _scope(db, "sales").department_id
        db.commit()
    response = _create(client, role="admin" if malformed == "global_department" else "manager", scope_id=scope_id)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUESTED_SCOPE"
    with Session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(RoleUpgradeRequest)) == 0
        assert db.scalar(select(func.count()).select_from(AppAuditLog).where(
            AppAuditLog.event_type.like("role_request.%"),
        )) == 0
