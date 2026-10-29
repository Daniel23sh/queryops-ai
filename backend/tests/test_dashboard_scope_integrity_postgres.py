from __future__ import annotations

import json
import os
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from action_postgres_test_db import validated_disposable_database_url
from app.db.session import get_db
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AccessScope,
    AppAuditLog,
    AppUser,
    Dashboard,
    DashboardCard,
    DataResource,
    Permission,
    QueryRun,
    SavedQuery,
    UserAccessScope,
    UserPermission,
)


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine, None, None]:
    target = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if target is None:
        pytest.skip("Dashboard scope integrity requires an explicit disposable PostgreSQL URL.")
    target = validated_disposable_database_url(target)
    engine = create_engine(target, pool_pre_ping=True)
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = target
    try:
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
def scenario(postgres_engine: Engine) -> Generator[dict, None, None]:
    with Session(postgres_engine) as db:
        seed_database(db, profile_name="small", reset=True)
        db.commit()
        admin = db.scalar(select(AppUser).where(AppUser.email == "demo.admin@queryops.local"))
        analyst = db.scalar(select(AppUser).where(AppUser.email == "demo.analyst@queryops.local"))
        finance = db.scalar(select(Department).where(Department.name == "Finance"))
        assert admin is not None and analyst is not None and finance is not None
        dashboard = Dashboard(
            owner_user_id=admin.id, title="Scope-protected dashboard",
            description="Protected metadata", visibility_scope="department",
            department_id=analyst.department_id,
        )
        personal = Dashboard(owner_user_id=analyst.id, title="Personal survives", visibility_scope="personal")
        secondary = Dashboard(
            owner_user_id=admin.id, title="Explicit secondary scope",
            visibility_scope="department", department_id=finance.id,
        )
        global_dashboard = Dashboard(owner_user_id=admin.id, title="Global assignment", visibility_scope="global")
        source = SavedQuery(
            owner_user_id=admin.id, name="Protected saved source",
            natural_language_question="Show authorized directory users.",
            generated_sql="SELECT id, department_id FROM directory_users ORDER BY id LIMIT 200",
            visibility_scope="department", department_id=analyst.department_id,
            parameters={},
        )
        db.add_all([dashboard, personal, secondary, global_dashboard, source])
        db.flush()
        card = DashboardCard(
            dashboard_id=dashboard.id, saved_query_id=source.id, title="Protected card",
            card_type="table", position=0,
        )
        run = QueryRun(
            user_id=admin.id, saved_query_id=source.id, status="succeeded",
            natural_language_question=source.natural_language_question,
            generated_sql=source.generated_sql, executed_sql=source.generated_sql,
            row_count=1, query_metadata={"referenced_tables": ["directory_users"]},
            completed_at=datetime.now(UTC),
        )
        own_run = QueryRun(
            user_id=analyst.id, status="succeeded",
            natural_language_question=source.natural_language_question,
            generated_sql=source.generated_sql, executed_sql=source.generated_sql,
            row_count=1, query_metadata={"referenced_tables": ["directory_users"]},
            completed_at=datetime.now(UTC),
        )
        resource = db.scalar(select(DataResource).where(
            DataResource.resource_type == "table", DataResource.table_name == "directory_users",
        ))
        assert resource is not None
        resource.is_exportable = True
        db.add_all([card, run, own_run])
        db.commit()
        ids = {
            "dashboard": dashboard.id, "card": card.id, "personal": personal.id,
            "secondary": secondary.id, "global": global_dashboard.id,
            "user": analyst.id, "department": analyst.department_id,
            "finance": finance.id, "own_run": own_run.id,
        }

    def get_test_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    try:
        with TestClient(app) as client:
            login = client.post("/api/v1/demo/login", json={"email": "demo.analyst@queryops.local"})
            assert login.status_code == 200
            ids["client"] = client
            ids["headers"] = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}
            yield ids
    finally:
        app.dependency_overrides.pop(get_db, None)


def revoke(engine: Engine, user_id) -> None:
    with Session(engine) as db:
        db.execute(delete(UserAccessScope).where(UserAccessScope.user_id == user_id))
        db.commit()


def product_snapshot(engine: Engine) -> dict:
    with engine.connect() as connection:
        return {
            model.__tablename__: sorted(
                json.dumps(dict(row), default=str, sort_keys=True)
                for row in connection.execute(select(model.__table__)).mappings()
            )
            for model in (Dashboard, DashboardCard, SavedQuery, QueryRun, AppAuditLog)
        }


def test_revoked_assignments_hide_metadata_and_source_but_keep_personal_ownership(
    scenario: dict, postgres_engine: Engine,
) -> None:
    client = scenario["client"]
    detail_path = f'/api/v1/dashboards/{scenario["dashboard"]}'
    before = client.get(detail_path)
    assert before.status_code == 200
    assert before.json()["data"]["capabilities"]["can_manage"] is True
    assert client.get(f'/api/v1/cards/{scenario["card"]}/source').status_code == 200

    revoke(postgres_engine, scenario["user"])
    assert client.get("/api/v1/auth/me").json()["data"]["scopes"] == []
    for endpoint in ("catalog", "library"):
        response = client.get(f"/api/v1/dashboards/{endpoint}")
        assert response.status_code == 200
        body = json.dumps(response.json())
        assert str(scenario["dashboard"]) not in body
        assert "Scope-protected dashboard" not in body
        assert "Protected card" not in body
    for path in (detail_path, f'/api/v1/cards/{scenario["card"]}/source'):
        response = client.get(path)
        assert response.status_code == 404
        assert "Protected" not in json.dumps(response.json())
        assert "SELECT" not in json.dumps(response.json())
    personal = client.get(f'/api/v1/dashboards/{scenario["personal"]}')
    assert personal.status_code == 200
    assert personal.json()["data"]["capabilities"]["can_manage"] is True
    assert client.patch(
        f'/api/v1/dashboards/{scenario["personal"]}', headers=scenario["headers"], json={"title": "Still mine"},
    ).status_code == 200


@pytest.mark.parametrize("operation", [
    "dashboard_update", "dashboard_archive", "dashboard_duplicate", "layout",
    "card_update", "card_duplicate", "card_remove", "refresh", "export",
    "save", "create_explicit", "create_affiliation_default",
])
def test_revoked_scope_denies_every_mutation_without_persistence(
    scenario: dict, postgres_engine: Engine, operation: str,
) -> None:
    revoke(postgres_engine, scenario["user"])
    before = product_snapshot(postgres_engine)
    client, headers = scenario["client"], scenario["headers"]
    dashboard = f'/api/v1/dashboards/{scenario["dashboard"]}'
    card = f'/api/v1/cards/{scenario["card"]}'
    if operation == "dashboard_update":
        response = client.patch(dashboard, headers=headers, json={"title": "Unauthorized title"})
    elif operation == "dashboard_archive":
        response = client.delete(dashboard, headers=headers)
    elif operation == "dashboard_duplicate":
        response = client.post(dashboard + "/duplicate", headers=headers, json={})
    elif operation == "layout":
        item = {"card_id": str(scenario["card"])}
        item.update({bp: {"x": 0, "y": 0, "w": width, "h": 3} for bp, width in (("desktop", 6), ("tablet", 6), ("mobile", 1))})
        response = client.patch(dashboard + "/layout", headers=headers, json={"expected_layout_version": 1, "items": [item]})
    elif operation == "card_update":
        response = client.patch(card, headers=headers, json={"title": "Unauthorized card"})
    elif operation == "card_duplicate":
        response = client.post(card + "/duplicate", headers=headers, json={})
    elif operation == "card_remove":
        response = client.delete(card, headers=headers)
    elif operation == "refresh":
        response = client.post(card + "/refresh", headers=headers, json={})
    elif operation == "export":
        response = client.post(card + "/export-csv", headers=headers, json={})
    elif operation == "save":
        response = client.post(f'/api/v1/query-runs/{scenario["own_run"]}/save-card', headers=headers, json={"dashboard_id": str(scenario["dashboard"]), "title": "Unauthorized save", "card_type": "table"})
    else:
        payload = {"title": "Unauthorized create", "visibility_scope": "department"}
        if operation == "create_explicit":
            payload["department_id"] = str(scenario["department"])
        response = client.post("/api/v1/dashboards", headers=headers, json=payload)
    assert response.status_code in {403, 404}, response.text
    assert "Scope-protected dashboard" not in response.text
    assert "SELECT" not in response.text
    assert product_snapshot(postgres_engine) == before


@pytest.mark.parametrize("assignment", ["secondary", "global"])
def test_explicit_assignments_grant_access_without_matching_affiliation(
    scenario: dict, postgres_engine: Engine, assignment: str,
) -> None:
    with Session(postgres_engine) as db:
        if assignment == "secondary":
            scope = db.scalar(select(AccessScope).where(AccessScope.department_id == scenario["finance"]))
        else:
            scope = db.scalar(select(AccessScope).where(AccessScope.scope_type == "global", AccessScope.scope_key == "global"))
        assert scope is not None
        assigned_scope_id = scope.id
        db.add(UserAccessScope(user_id=scenario["user"], scope_id=scope.id, access_level="manage", is_default=False))
        db.commit()
    client, headers = scenario["client"], scenario["headers"]
    detail = client.get(f'/api/v1/dashboards/{scenario["secondary"]}')
    assert detail.status_code == 200
    assert detail.json()["data"]["capabilities"]["can_manage"] is True
    assert client.patch(f'/api/v1/dashboards/{scenario["secondary"]}', headers=headers, json={"title": "Explicitly authorized"}).status_code == 200
    created = client.post("/api/v1/dashboards", headers=headers, json={"title": "Assigned creation", "visibility_scope": "department", "department_id": str(scenario["finance"])})
    assert created.status_code == 201
    assert client.post(f'/api/v1/query-runs/{scenario["own_run"]}/save-card', headers=headers, json={"dashboard_id": str(scenario["secondary"]), "title": "Authorized saved card", "card_type": "table"}).status_code == 201
    global_response = client.get(f'/api/v1/dashboards/{scenario["global"]}')
    assert global_response.status_code == (200 if assignment == "global" else 404)
    with Session(postgres_engine) as db:
        db.execute(delete(UserAccessScope).where(
            UserAccessScope.user_id == scenario["user"],
            UserAccessScope.scope_id == assigned_scope_id,
        ))
        db.commit()
    assert client.get(f'/api/v1/dashboards/{scenario["secondary"]}').status_code == 404
    assert client.get(f'/api/v1/dashboards/{scenario["global"]}').status_code == 404
    assert client.get(f'/api/v1/dashboards/{scenario["dashboard"]}').status_code == 200


def test_refresh_and_export_reauthorize_current_viewer_after_revocation(
    scenario: dict, postgres_engine: Engine,
) -> None:
    client, headers = scenario["client"], scenario["headers"]
    path = f'/api/v1/cards/{scenario["card"]}'
    refresh = client.post(path + "/refresh", headers=headers, json={})
    assert refresh.status_code == 200
    rows = refresh.json()["data"]["rows"]
    assert rows and {row["department_id"] for row in rows} == {str(scenario["department"])}
    exported = client.post(path + "/export-csv", headers=headers, json={})
    assert exported.status_code == 200
    revoke(postgres_engine, scenario["user"])
    before = product_snapshot(postgres_engine)
    assert client.post(path + "/refresh", headers=headers, json={}).status_code == 403
    assert client.post(path + "/export-csv", headers=headers, json={}).status_code == 403
    assert product_snapshot(postgres_engine) == before


def test_matching_scope_does_not_override_effective_permission_denials(
    scenario: dict, postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db:
        for key in ("can_manage_department_dashboard", "can_manage_scope_dashboard", "can_view_sql", "can_export_results"):
            permission = db.scalar(select(Permission).where(Permission.key == key))
            assert permission is not None
            db.add(UserPermission(user_id=scenario["user"], permission_id=permission.id, effect="deny"))
        db.commit()
    client, headers = scenario["client"], scenario["headers"]
    dashboard = f'/api/v1/dashboards/{scenario["dashboard"]}'
    detail = client.get(dashboard)
    assert detail.status_code == 200
    capabilities = detail.json()["data"]["capabilities"]
    assert capabilities["can_manage"] is False
    assert capabilities["can_view_source"] is False
    assert capabilities["can_export_cards"] is False
    before = product_snapshot(postgres_engine)
    assert client.patch(dashboard, headers=headers, json={"title": "Denied"}).status_code == 403
    assert client.get(f'/api/v1/cards/{scenario["card"]}/source').status_code == 403
    assert client.post(f'/api/v1/cards/{scenario["card"]}/export-csv', headers=headers, json={}).status_code == 403
    assert product_snapshot(postgres_engine) == before


@pytest.mark.parametrize("allowed_key", [
    "can_create_department_dashboard", "can_create_scope_dashboard",
    "can_manage_department_dashboard", "can_manage_scope_dashboard",
])
def test_each_effective_creation_permission_agrees_with_card_capability(
    scenario: dict, postgres_engine: Engine, allowed_key: str,
) -> None:
    with Session(postgres_engine) as db:
        for key in (
            "can_create_department_dashboard", "can_create_scope_dashboard",
            "can_manage_department_dashboard", "can_manage_scope_dashboard",
        ):
            permission = db.scalar(select(Permission).where(Permission.key == key))
            assert permission is not None
            db.add(UserPermission(
                user_id=scenario["user"], permission_id=permission.id,
                effect="allow" if key == allowed_key else "deny",
            ))
        db.commit()
    client, headers = scenario["client"], scenario["headers"]
    detail = client.get(f'/api/v1/dashboards/{scenario["dashboard"]}')
    assert detail.status_code == 200
    capabilities = detail.json()["data"]["capabilities"]
    assert capabilities["can_create_cards"] is True
    assert capabilities["can_manage"] is ("manage" in allowed_key)
    assert client.post("/api/v1/dashboards", headers=headers, json={
        "title": "Permission grant", "visibility_scope": "department",
        "department_id": str(scenario["department"]),
    }).status_code == 201
    assert client.post(f'/api/v1/query-runs/{scenario["own_run"]}/save-card', headers=headers, json={
        "dashboard_id": str(scenario["dashboard"]), "title": "Permission-granted card", "card_type": "table",
    }).status_code == 201
    revoke(postgres_engine, scenario["user"])
    before = product_snapshot(postgres_engine)
    assert client.post("/api/v1/dashboards", headers=headers, json={
        "title": "Grant without scope", "visibility_scope": "department",
        "department_id": str(scenario["department"]),
    }).status_code == 403
    assert product_snapshot(postgres_engine) == before


def test_only_secondary_assignment_does_not_restore_revoked_affiliation_scope(
    scenario: dict, postgres_engine: Engine,
) -> None:
    revoke(postgres_engine, scenario["user"])
    with Session(postgres_engine) as db:
        scope = db.scalar(select(AccessScope).where(AccessScope.department_id == scenario["finance"]))
        assert scope is not None
        db.add(UserAccessScope(user_id=scenario["user"], scope_id=scope.id, access_level="manage", is_default=True))
        db.commit()
    client = scenario["client"]
    assert client.get(f'/api/v1/dashboards/{scenario["dashboard"]}').status_code == 404
    assert client.get(f'/api/v1/dashboards/{scenario["secondary"]}').status_code == 200
