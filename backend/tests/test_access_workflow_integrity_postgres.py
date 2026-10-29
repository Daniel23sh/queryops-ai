"""Real role/scope transitions must immediately govern existing Dashboard sessions."""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from test_role_requests_postgres import client as client, postgres_engine as postgres_engine
from app.main import app
from app.models.product import (
    AccessScope, AppAuditLog, AppUser, Dashboard, RoleUpgradeRequest, UserAccessScope,
)


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return response.json()["data"]["csrf_token"]


def _scenario(engine: Engine):
    with Session(engine) as db:
        user = db.scalar(select(AppUser).where(AppUser.email == "demo.user@queryops.local"))
        admin = db.scalar(select(AppUser).where(AppUser.email == "demo.admin@queryops.local"))
        scope = db.scalar(select(AccessScope).where(
            AccessScope.scope_type == "department", AccessScope.scope_key == "it",
        ))
        assert user is not None and admin is not None and scope is not None
        db.execute(delete(UserAccessScope).where(UserAccessScope.user_id == user.id))
        dashboard = Dashboard(owner_user_id=admin.id, title="Protected secondary IT dashboard",
                              visibility_scope="department", department_id=scope.department_id)
        affiliated = Dashboard(owner_user_id=admin.id, title="Affiliation is not a grant",
                               visibility_scope="department", department_id=user.department_id)
        db.add_all([dashboard, affiliated])
        db.commit()
        return user.id, user.department_id, scope.id, dashboard.id, affiliated.id


def test_approved_secondary_scope_and_revocation_apply_to_existing_session(
    client: TestClient, postgres_engine: Engine,
) -> None:
    user_id, affiliation, scope_id, dashboard_id, affiliated_id = _scenario(postgres_engine)
    with TestClient(app) as requester:
        token = _login(requester, "demo.user@queryops.local")
        assert requester.get(f"/api/v1/dashboards/{dashboard_id}").status_code == 404
        created = requester.post("/api/v1/role-requests", headers={"X-CSRF-Token": token}, json={
            "requested_role": "analyst", "requested_scope_id": str(scope_id),
            "reason": "Secondary-scope analysis.",
        })
        assert created.status_code == 201
        admin_token = _login(client, "demo.admin@queryops.local")
        approved = client.post(f"/api/v1/admin/role-requests/{created.json()['data']['id']}/approve",
                               headers={"X-CSRF-Token": admin_token},
                               json={"decision_reason": "Authorize the explicit IT scope."})
        assert approved.status_code == 200
        # Keep the original requester's cookies: no login or creator authority is reused.
        me = requester.get("/api/v1/auth/me").json()["data"]
        assert me["role"] == "analyst"
        assert {item["id"] for item in me["scopes"]} == {str(scope_id)}
        visible = requester.get(f"/api/v1/dashboards/{dashboard_id}")
        assert visible.status_code == 200
        assert visible.json()["data"]["capabilities"]["can_manage"] is True
        assert requester.get(f"/api/v1/dashboards/{affiliated_id}").status_code == 404
        with Session(postgres_engine) as db:
            assert db.get(AppUser, user_id).department_id == affiliation
            db.execute(delete(UserAccessScope).where(UserAccessScope.user_id == user_id))
            db.commit()
        assert requester.get("/api/v1/auth/me").json()["data"]["scopes"] == []
        denied = requester.get(f"/api/v1/dashboards/{dashboard_id}")
        assert denied.status_code == 404
        assert "Protected secondary" not in denied.text
        assert requester.patch(f"/api/v1/dashboards/{dashboard_id}",
                               headers={"X-CSRF-Token": token},
                               json={"title": "Unauthorized update"}).status_code == 404
        with Session(postgres_engine) as db:
            assert db.get(Dashboard, dashboard_id).title == "Protected secondary IT dashboard"


@pytest.mark.parametrize("outcome", ["reject", "stale", "rollback"])
def test_unsuccessful_role_transition_never_grants_dashboard_access(
    client: TestClient, postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    user_id, _, scope_id, dashboard_id, _ = _scenario(postgres_engine)
    with TestClient(app) as requester:
        token = _login(requester, "demo.user@queryops.local")
        created = requester.post("/api/v1/role-requests", headers={"X-CSRF-Token": token}, json={
            "requested_role": "analyst", "requested_scope_id": str(scope_id), "reason": "Review access.",
        })
        assert created.status_code == 201
        request_id = created.json()["data"]["id"]
        if outcome == "stale":
            with Session(postgres_engine) as db:
                scope = db.get(AccessScope, scope_id)
                scope.scope_key = "changed-after-submission"
                db.commit()
        admin_token = _login(client, "demo.admin@queryops.local")
        with monkeypatch.context() as patch:
            if outcome == "rollback":
                def fail_after_flush(db):
                    db.flush()
                    raise SQLAlchemyError("Controlled commit failure must remain private.")
                patch.setattr(Session, "commit", fail_after_flush)
            operation = "reject" if outcome == "reject" else "approve"
            decision = client.post(f"/api/v1/admin/role-requests/{request_id}/{operation}",
                                   headers={"X-CSRF-Token": admin_token},
                                   json={"decision_reason": "Review current access."})
        assert decision.status_code == {"reject": 200, "stale": 409, "rollback": 503}[outcome]
        assert "Controlled commit" not in decision.text
        assert requester.get(f"/api/v1/dashboards/{dashboard_id}").status_code == 404
        me = requester.get("/api/v1/auth/me").json()["data"]
        assert me["role"] == "user" and me["scopes"] == []
        with Session(postgres_engine) as db:
            request = db.get(RoleUpgradeRequest, UUID(request_id))
            assert request.status == ("rejected" if outcome == "reject" else "pending")
            assert db.scalar(select(func.count()).select_from(UserAccessScope).where(
                UserAccessScope.user_id == user_id,
            )) == 0
            assert db.scalar(select(func.count()).select_from(AppAuditLog).where(
                AppAuditLog.entity_id == request.id,
            )) == (1 if outcome == "reject" else 0)
