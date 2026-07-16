from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AppUser,
    Dashboard,
    DashboardCard,
    Permission,
    QueryRun,
    RunStatus,
    SavedQuery,
    UserPermission,
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


def test_editor_mutations_require_authentication_and_csrf(
    client: TestClient,
) -> None:
    dashboard_id = uuid.uuid4()
    card_id = uuid.uuid4()
    unauthenticated = [
        client.patch(f"/api/v1/dashboards/{dashboard_id}", json={"title": "New"}),
        client.post(f"/api/v1/dashboards/{dashboard_id}/duplicate", json={}),
        client.delete(f"/api/v1/dashboards/{dashboard_id}"),
        client.patch(
            f"/api/v1/dashboards/{dashboard_id}/layout",
            json={"expected_layout_version": 1, "items": []},
        ),
        client.patch(f"/api/v1/cards/{card_id}", json={"title": "New"}),
        client.post(f"/api/v1/cards/{card_id}/duplicate", json={}),
        client.delete(f"/api/v1/cards/{card_id}"),
    ]
    assert all(response.status_code == 401 for response in unauthenticated)

    _login(client, "demo.analyst@queryops.local")
    csrf_missing = [
        client.patch(f"/api/v1/dashboards/{dashboard_id}", json={"title": "New"}),
        client.post(f"/api/v1/dashboards/{dashboard_id}/duplicate", json={}),
        client.delete(f"/api/v1/dashboards/{dashboard_id}"),
        client.patch(
            f"/api/v1/dashboards/{dashboard_id}/layout",
            json={"expected_layout_version": 1, "items": []},
        ),
        client.patch(f"/api/v1/cards/{card_id}", json={"title": "New"}),
        client.post(f"/api/v1/cards/{card_id}/duplicate", json={}),
        client.delete(f"/api/v1/cards/{card_id}"),
    ]
    assert all(response.status_code == 403 for response in csrf_missing)
    assert all(
        response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
        for response in csrf_missing
    )


def test_detail_returns_effective_capabilities_and_sanitized_editor_metadata(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user(db_session, "demo.analyst@queryops.local")
    dashboard = _dashboard(db_session, analyst, "Editor dashboard")
    card = _card(
        db_session,
        dashboard,
        _saved_query(db_session, analyst),
        layout={"w": 999, "rows": [{"secret": True}]},
        config={"javascript": "alert(1)", "rows": [{"secret": True}]},
    )
    _login(client, analyst.email)

    response = client.get(f"/api/v1/dashboards/{dashboard.id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["layout_version"] == 1
    assert data["capabilities"] == {
        "can_manage": True,
        "can_duplicate": True,
        "can_refresh_cards": True,
        "can_export_cards": True,
        "can_view_source": True,
        "can_create_cards": True,
    }
    serialized_card = data["cards"][0]
    assert serialized_card["id"] == str(card.id)
    assert serialized_card["layout"] == _layout_for_table(0)
    assert serialized_card["visualization"] == _visualization("table")
    assert serialized_card["allowed_sizes"]["mobile"] == [
        {"w": 1, "h": 2},
        {"w": 1, "h": 3},
        {"w": 1, "h": 4},
    ]
    assert "config" not in serialized_card
    assert "javascript" not in response.text
    assert "secret" not in response.text

    _deny_permission(db_session, analyst, "can_create_personal_dashboard")
    denied_response = client.get(f"/api/v1/dashboards/{dashboard.id}")
    assert denied_response.status_code == 200
    assert denied_response.json()["data"]["capabilities"]["can_manage"] is False


def test_layout_save_persists_complete_breakpoint_layout_and_rejects_stale_version(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user(db_session, "demo.analyst@queryops.local")
    dashboard = _dashboard(db_session, analyst, "Layout dashboard")
    card = _card(db_session, dashboard, _saved_query(db_session, analyst))
    csrf_token = _login(client, analyst.email)
    compact_layout = {
        "desktop": {"x": 0, "y": 0, "w": 12, "h": 2},
        "tablet": {"x": 0, "y": 0, "w": 3, "h": 2},
        "mobile": {"x": 0, "y": 0, "w": 1, "h": 2},
    }
    payload = {
        "expected_layout_version": 1,
        "items": [{"card_id": str(card.id), **compact_layout}],
    }

    response = client.patch(
        f"/api/v1/dashboards/{dashboard.id}/layout",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["data"]["layout_version"] == 2
    assert response.json()["data"]["items"][0]["position"] == 0
    db_session.expire_all()
    assert db_session.get(Dashboard, dashboard.id).layout_version == 2
    assert db_session.get(DashboardCard, card.id).layout == {
        "version": 1,
        **compact_layout,
    }

    stale_response = client.patch(
        f"/api/v1/dashboards/{dashboard.id}/layout",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )
    assert stale_response.status_code == 409
    assert stale_response.json()["error"]["code"] == "DASHBOARD_LAYOUT_CONFLICT"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda items: items[0]["desktop"].update({"x": True}),
        lambda items: items[0]["desktop"].update({"x": -1}),
        lambda items: items[0]["desktop"].update({"w": 5}),
        lambda items: items[0]["mobile"].update({"x": 1}),
        lambda items: items[0]["mobile"].update({"w": 2}),
        lambda items: items[1]["desktop"].update({"x": 0, "y": 0}),
        lambda items: items[1]["tablet"].update({"x": 0, "y": 0}),
        lambda items: items[1]["mobile"].update({"x": 0, "y": 0}),
    ],
)
def test_layout_rejects_invalid_sizes_coordinates_and_overlaps_atomically(
    client: TestClient,
    db_session: Session,
    mutate,
) -> None:
    analyst = _user(db_session, "demo.analyst@queryops.local")
    dashboard = _dashboard(db_session, analyst, "Invalid layout")
    saved_query = _saved_query(db_session, analyst)
    first = _card(db_session, dashboard, saved_query, position=0)
    second = _card(db_session, dashboard, saved_query, position=1)
    items = [
        {"card_id": str(first.id), **_layout_item_for_table(0)},
        {"card_id": str(second.id), **_layout_item_for_table(1)},
    ]
    mutate(items)
    csrf_token = _login(client, analyst.email)

    response = client.patch(
        f"/api/v1/dashboards/{dashboard.id}/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={"expected_layout_version": 1, "items": items},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_LAYOUT_REQUEST"
    db_session.expire_all()
    assert db_session.get(Dashboard, dashboard.id).layout_version == 1
    assert db_session.get(DashboardCard, first.id).layout is None
    assert db_session.get(DashboardCard, second.id).layout is None


def test_layout_rejects_missing_and_foreign_cards_without_existence_disclosure(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user(db_session, "demo.analyst@queryops.local")
    admin = _user(db_session, "demo.admin@queryops.local")
    dashboard = _dashboard(db_session, analyst, "Owned")
    card = _card(db_session, dashboard, _saved_query(db_session, analyst))
    foreign_dashboard = _dashboard(db_session, admin, "Foreign")
    foreign_card = _card(
        db_session,
        foreign_dashboard,
        _saved_query(db_session, admin),
    )
    csrf_token = _login(client, analyst.email)

    for items in [
        [],
        [{"card_id": str(foreign_card.id), **_layout_item_for_table(0)}],
        [
            {"card_id": str(card.id), **_layout_item_for_table(0)},
            {"card_id": str(foreign_card.id), **_layout_item_for_table(1)},
        ],
    ]:
        response = client.patch(
            f"/api/v1/dashboards/{dashboard.id}/layout",
            headers={"X-CSRF-Token": csrf_token},
            json={"expected_layout_version": 1, "items": items},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DASHBOARD_LAYOUT_CONFLICT"
        assert str(foreign_card.id) not in response.text


def test_dashboard_rename_duplicate_and_archive_follow_safe_policies(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _user(db_session, "demo.admin@queryops.local")
    analyst = _user(db_session, "demo.analyst@queryops.local")
    department = _department(db_session, "IT")
    shared = _dashboard(
        db_session,
        analyst,
        "Shared source",
        visibility_scope="department",
        department=department,
    )
    saved_query = _saved_query(db_session, analyst)
    source_card = _card(db_session, shared, saved_query)
    source_run = _query_run(db_session, analyst, saved_query)
    csrf_token = _login(client, admin.email)

    rejected = client.patch(
        f"/api/v1/dashboards/{shared.id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"visibility_scope": "personal"},
    )
    assert rejected.status_code == 400

    renamed = client.patch(
        f"/api/v1/dashboards/{shared.id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Renamed shared", "description": "Updated"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["data"]["title"] == "Renamed shared"

    query_run_count = db_session.scalar(select(func.count(QueryRun.id)))
    duplicated = client.post(
        f"/api/v1/dashboards/{shared.id}/duplicate",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )
    assert duplicated.status_code == 201
    duplicate_id = uuid.UUID(duplicated.json()["data"]["id"])
    duplicate = db_session.get(Dashboard, duplicate_id)
    assert duplicate is not None
    assert duplicate.owner_user_id == admin.id
    assert duplicate.visibility_scope == "personal"
    assert duplicate.department_id is None
    assert duplicate.layout_version == 1
    duplicate_card = db_session.scalar(
        select(DashboardCard).where(DashboardCard.dashboard_id == duplicate.id)
    )
    assert duplicate_card is not None
    assert duplicate_card.saved_query_id == source_card.saved_query_id
    assert duplicate_card.layout["version"] == 1
    assert db_session.scalar(select(func.count(QueryRun.id))) == query_run_count
    assert db_session.get(QueryRun, source_run.id) is not None

    archived = client.delete(
        f"/api/v1/dashboards/{duplicate.id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["is_archived"] is True
    assert client.get(f"/api/v1/dashboards/{duplicate.id}").status_code == 404
    assert all(
        item["id"] != str(duplicate.id)
        for item in client.get("/api/v1/dashboards/library").json()["data"]
    )


def test_card_update_duplicate_remove_and_source_preserve_query_history(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user(db_session, "demo.analyst@queryops.local")
    dashboard = _dashboard(db_session, analyst, "Cards")
    saved_query = _saved_query(db_session, analyst)
    card = _card(db_session, dashboard, saved_query)
    older_run = _query_run(
        db_session,
        analyst,
        saved_query,
        completed_at=datetime.now(UTC) - timedelta(hours=1),
        sql="SELECT older FROM licenses",
    )
    latest_run = _query_run(
        db_session,
        analyst,
        saved_query,
        completed_at=datetime.now(UTC),
        sql="SELECT latest FROM licenses",
    )
    csrf_token = _login(client, analyst.email)

    invalid = client.patch(
        f"/api/v1/cards/{card.id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"config": {"rows": [{"secret": True}]}},
    )
    assert invalid.status_code == 400
    assert "secret" not in invalid.text

    updated = client.patch(
        f"/api/v1/cards/{card.id}",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "title": "Updated card",
            "description": "Updated description",
            "visualization": _visualization("bar"),
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["layout_version"] == 2
    assert updated.json()["data"]["card"]["visualization"]["type"] == "bar"
    db_session.expire_all()
    persisted_card = db_session.get(DashboardCard, card.id)
    assert persisted_card.title == "Updated card"
    assert set(persisted_card.config) == {"visualization"}
    assert "rows" not in json.dumps(persisted_card.config)

    query_run_count = db_session.scalar(select(func.count(QueryRun.id)))
    duplicated = client.post(
        f"/api/v1/cards/{card.id}/duplicate",
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )
    assert duplicated.status_code == 201
    duplicate_id = uuid.UUID(duplicated.json()["data"]["card"]["id"])
    duplicate = db_session.get(DashboardCard, duplicate_id)
    assert duplicate.saved_query_id == saved_query.id
    assert duplicate.title == "Updated card Copy"
    assert duplicated.json()["data"]["layout_version"] == 3
    assert db_session.scalar(select(func.count(QueryRun.id))) == query_run_count

    source = client.get(f"/api/v1/cards/{card.id}/source")
    assert source.status_code == 200
    assert source.json()["data"] == {
        "question": "Original question",
        "sql": "SELECT latest FROM licenses",
    }
    assert set(source.json()["data"]) == {"question", "sql"}

    removed = client.delete(
        f"/api/v1/cards/{card.id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert removed.status_code == 200
    assert removed.json()["data"]["layout_version"] == 4
    assert db_session.get(DashboardCard, card.id) is None
    assert db_session.get(SavedQuery, saved_query.id) is not None
    assert db_session.get(QueryRun, older_run.id) is not None
    assert db_session.get(QueryRun, latest_run.id) is not None
    assert db_session.get(DashboardCard, duplicate_id).position == 0


def test_source_requires_effective_sql_permission_and_visibility(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user(db_session, "demo.manager@queryops.local")
    analyst = _user(db_session, "demo.analyst@queryops.local")
    admin = _user(db_session, "demo.admin@queryops.local")
    finance = _department(db_session, "Finance")
    shared = _dashboard(
        db_session,
        admin,
        "Finance shared",
        visibility_scope="department",
        department=finance,
    )
    shared_query = _saved_query(db_session, admin)
    shared_card = _card(db_session, shared, shared_query)
    _query_run(db_session, admin, shared_query)
    private = _dashboard(db_session, analyst, "Private")
    private_query = _saved_query(db_session, analyst)
    private_card = _card(db_session, private, private_query)
    _query_run(db_session, analyst, private_query)

    _login(client, manager.email)
    denied = client.get(f"/api/v1/cards/{shared_card.id}/source")
    hidden = client.get(f"/api/v1/cards/{private_card.id}/source")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    assert hidden.status_code == 404

    _login(client, analyst.email)
    allowed = client.get(f"/api/v1/cards/{private_card.id}/source")
    assert allowed.status_code == 200
    _deny_permission(db_session, analyst, "can_view_sql")
    directly_denied = client.get(f"/api/v1/cards/{private_card.id}/source")
    assert directly_denied.status_code == 403


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def _user(db: Session, email: str) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _department(db: Session, name: str) -> Department:
    department = db.scalar(select(Department).where(Department.name == name))
    assert department is not None
    return department


def _dashboard(
    db: Session,
    owner: AppUser,
    title: str,
    *,
    visibility_scope: str = "personal",
    department: Department | None = None,
) -> Dashboard:
    dashboard = Dashboard(
        owner_user_id=owner.id,
        title=title,
        description=f"{title} description",
        visibility_scope=visibility_scope,
        department_id=department.id if department else None,
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return dashboard


def _saved_query(db: Session, owner: AppUser) -> SavedQuery:
    saved_query = SavedQuery(
        owner_user_id=owner.id,
        name="Saved query",
        description="Saved query description",
        natural_language_question="Original question",
        generated_sql="SELECT generated FROM licenses",
        visibility_scope="personal",
        parameters={},
        result_schema={"columns": ["product_name", "count"]},
    )
    db.add(saved_query)
    db.commit()
    db.refresh(saved_query)
    return saved_query


def _card(
    db: Session,
    dashboard: Dashboard,
    saved_query: SavedQuery,
    *,
    position: int = 0,
    layout: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> DashboardCard:
    card = DashboardCard(
        dashboard_id=dashboard.id,
        saved_query_id=saved_query.id,
        title=f"Card {position}",
        description="Card description",
        card_type="table",
        position=position,
        layout=layout,
        config=config,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def _query_run(
    db: Session,
    user: AppUser,
    saved_query: SavedQuery,
    *,
    completed_at: datetime | None = None,
    sql: str = "SELECT safe FROM licenses",
) -> QueryRun:
    query_run = QueryRun(
        user_id=user.id,
        saved_query_id=saved_query.id,
        status=RunStatus.SUCCEEDED.value,
        natural_language_question="Original question",
        generated_sql="SELECT generated FROM licenses",
        executed_sql=sql,
        row_count=1,
        duration_ms=10,
        completed_at=completed_at or datetime.now(UTC),
        query_metadata={"referenced_tables": ["licenses"]},
    )
    db.add(query_run)
    db.commit()
    db.refresh(query_run)
    return query_run


def _deny_permission(db: Session, user: AppUser, key: str) -> None:
    permission = db.scalar(select(Permission).where(Permission.key == key))
    assert permission is not None
    db.add(
        UserPermission(
            user_id=user.id,
            permission_id=permission.id,
            effect="deny",
            reason="Editor direct-deny test",
        )
    )
    db.commit()


def _visualization(visualization_type: str) -> dict[str, Any]:
    return {
        "mode": "auto",
        "type": visualization_type,
        "recommended_type": visualization_type,
        "mapping": {
            "category_column": None,
            "value_columns": [],
            "series_column": None,
            "label_column": None,
            "target_column": None,
        },
    }


def _layout_item_for_table(index: int) -> dict[str, dict[str, int]]:
    return {
        "desktop": {"x": (index % 2) * 6, "y": (index // 2) * 3, "w": 6, "h": 3},
        "tablet": {"x": 0, "y": index * 3, "w": 6, "h": 3},
        "mobile": {"x": 0, "y": index * 3, "w": 1, "h": 3},
    }


def _layout_for_table(index: int) -> dict[str, Any]:
    return {"version": 1, **_layout_item_for_table(index)}
