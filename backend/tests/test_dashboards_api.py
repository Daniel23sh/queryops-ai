from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AccessScope,
    AppUser,
    Dashboard,
    DashboardCard,
    QueryRun,
    RunStatus,
    SavedQuery,
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


def test_dashboard_catalog_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_my_dashboard_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/dashboards/my")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_authenticated_user_can_call_dashboard_catalog(
    client: TestClient,
) -> None:
    _login(client, "demo.manager@queryops.local")

    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["request_id"]
    assert body["meta"]["timestamp"]
    assert_no_sql_payload(body)


def test_authenticated_user_can_call_my_dashboard(client: TestClient) -> None:
    _login(client, "demo.manager@queryops.local")

    response = client.get("/api/v1/dashboards/my")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["request_id"]
    assert body["meta"]["timestamp"]
    assert_no_sql_payload(body)


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf-token"])
def test_create_dashboard_requires_valid_csrf(
    client: TestClient,
    csrf_header: str | None,
) -> None:
    _login(client, "demo.manager@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header is not None else {}

    response = client.post(
        "/api/v1/dashboards",
        headers=headers,
        json={"title": "My dashboard"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf-token"])
def test_save_card_requires_valid_csrf(
    client: TestClient,
    csrf_header: str | None,
) -> None:
    _login(client, "demo.analyst@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header is not None else {}

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/save-card",
        headers=headers,
        json={"title": "Saved insight"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert_no_sql_payload(response.json())


def test_update_dashboard_layout_requires_authentication(client: TestClient) -> None:
    response = client.patch("/api/v1/dashboards/my/layout", json={"items": []})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf-token"])
def test_update_dashboard_layout_requires_valid_csrf(
    client: TestClient,
    csrf_header: str | None,
) -> None:
    _login(client, "demo.manager@queryops.local")
    headers = {"X-CSRF-Token": csrf_header} if csrf_header is not None else {}

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers=headers,
        json={"items": []},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"items": []},
        {"items": "not-a-list"},
        {"items": [], "dashboard_id": str(uuid.uuid4())},
    ],
)
def test_update_dashboard_layout_rejects_malformed_root_payload(
    client: TestClient,
    payload: Any,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_LAYOUT_REQUEST"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize(
    "items",
    [
        [None],
        [{"card_id": str(uuid.uuid4())}],
        [{"position": 0}],
        [{"card_id": str(uuid.uuid4()), "position": 0, "title": "extra"}],
        [{"card_id": "not-a-uuid", "position": 0}],
        [{"card_id": str(uuid.uuid4()), "position": -1}],
        [{"card_id": str(uuid.uuid4()), "position": True}],
        [{"card_id": str(uuid.uuid4()), "position": "0"}],
        [
            {"card_id": str(uuid.uuid4()), "position": 0},
            {"card_id": str(uuid.uuid4()), "position": 0},
        ],
        [
            {"card_id": str(uuid.uuid4()), "position": 0},
            {"card_id": str(uuid.uuid4()), "position": 2},
        ],
    ],
)
def test_update_dashboard_layout_rejects_invalid_items(
    client: TestClient,
    items: list[Any],
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={"items": items},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_LAYOUT_REQUEST"
    assert_no_sql_payload(response.json())


def test_update_dashboard_layout_rejects_duplicate_card_ids(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")
    card_id = str(uuid.uuid4())

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "items": [
                {"card_id": card_id, "position": 0},
                {"card_id": card_id, "position": 1},
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_LAYOUT_REQUEST"
    assert_no_sql_payload(response.json())


def test_update_dashboard_layout_rejects_unknown_card_without_leaking_existence(
    client: TestClient,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={"items": [{"card_id": str(uuid.uuid4()), "position": 0}]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DASHBOARD_NOT_FOUND"
    assert_no_sql_payload(response.json())


def test_update_dashboard_layout_rejects_another_users_personal_dashboard_without_leakage(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=analyst),
        title="Analyst card",
        position=0,
    )
    csrf_token = _login(client, manager.email)

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={"items": [{"card_id": str(card.id), "position": 0}]},
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "DASHBOARD_NOT_FOUND",
        "message": "Dashboard was not found.",
        "details": {},
        "request_id": response.json()["error"]["request_id"],
    }
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize("visibility_scope", ["department", "global"])
def test_update_dashboard_layout_rejects_non_personal_dashboard(
    client: TestClient,
    db_session: Session,
    visibility_scope: str,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    department = (
        _department_by_name(db_session, "Finance")
        if visibility_scope == "department"
        else None
    )
    dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title=f"{visibility_scope.title()} dashboard",
        visibility_scope=visibility_scope,
        department=department,
    )
    card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
        title="Shared card",
        position=0,
    )
    csrf_token = _login(client, manager.email)

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={"items": [{"card_id": str(card.id), "position": 0}]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DASHBOARD_NOT_FOUND"
    assert_no_sql_payload(response.json())


def test_update_dashboard_layout_rejects_archived_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Archived Personal",
        visibility_scope="personal",
        is_archived=True,
    )
    card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
        title="Archived card",
        position=0,
    )
    csrf_token = _login(client, manager.email)

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={"items": [{"card_id": str(card.id), "position": 0}]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DASHBOARD_NOT_FOUND"
    assert_no_sql_payload(response.json())


def test_update_dashboard_layout_rejects_mixed_dashboards(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    first_dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="First",
        visibility_scope="personal",
    )
    second_dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Second",
        visibility_scope="personal",
        minute=1,
    )
    first_card = _add_card(
        db_session,
        dashboard=first_dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
        title="First card",
        position=0,
    )
    second_card = _add_card(
        db_session,
        dashboard=second_dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
        title="Second card",
        position=0,
    )
    csrf_token = _login(client, manager.email)

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "items": [
                {"card_id": str(first_card.id), "position": 0},
                {"card_id": str(second_card.id), "position": 1},
            ]
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DASHBOARD_LAYOUT_CONFLICT"
    assert_no_sql_payload(response.json())


def test_update_dashboard_layout_rejects_partial_or_stale_card_set(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Manager Personal",
        visibility_scope="personal",
    )
    first_card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
        title="First card",
        position=0,
    )
    _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
        title="Added after stale view",
        position=1,
    )
    csrf_token = _login(client, manager.email)

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={"items": [{"card_id": str(first_card.id), "position": 0}]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DASHBOARD_LAYOUT_CONFLICT"
    assert_no_sql_payload(response.json())


def test_update_dashboard_layout_persists_atomic_normalized_order(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Manager Personal",
        visibility_scope="personal",
    )
    first_saved_query = _add_saved_query(db_session, owner=manager)
    second_saved_query = _add_saved_query(db_session, owner=manager)
    third_saved_query = _add_saved_query(db_session, owner=manager)
    first_card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=first_saved_query,
        title="First card",
        position=4,
    )
    second_card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=second_saved_query,
        title="Second card",
        position=1,
    )
    third_card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=third_saved_query,
        title="Third card",
        position=9,
    )
    refresh_run = _add_query_run(db_session, user=manager)
    refresh_run.saved_query_id = first_saved_query.id
    db_session.commit()
    csrf_token = _login(client, manager.email)

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "items": [
                {"card_id": str(third_card.id), "position": 0},
                {"card_id": str(first_card.id), "position": 1},
                {"card_id": str(second_card.id), "position": 2},
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(dashboard.id)
    assert [(card["id"], card["position"]) for card in data["cards"]] == [
        (str(third_card.id), 0),
        (str(first_card.id), 1),
        (str(second_card.id), 2),
    ]
    assert_no_sql_payload(response.json())

    db_session.expire_all()
    persisted_cards = db_session.scalars(
        select(DashboardCard)
        .where(DashboardCard.dashboard_id == dashboard.id)
        .order_by(DashboardCard.position)
    ).all()
    assert [(card.id, card.position) for card in persisted_cards] == [
        (third_card.id, 0),
        (first_card.id, 1),
        (second_card.id, 2),
    ]
    assert first_card.layout == {"w": 4}
    assert first_card.config == {"columns": ["product_name"]}
    assert first_card.saved_query_id == first_saved_query.id
    assert second_card.saved_query_id == second_saved_query.id
    assert third_card.saved_query_id == third_saved_query.id
    assert db_session.get(QueryRun, refresh_run.id) is not None
    assert db_session.get(QueryRun, refresh_run.id).saved_query_id == first_saved_query.id


def test_update_dashboard_layout_is_idempotent_for_one_card(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Manager Personal",
        visibility_scope="personal",
    )
    card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
        title="Only card",
        position=0,
    )
    csrf_token = _login(client, manager.email)

    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={"items": [{"card_id": str(card.id), "position": 0}]},
    )

    assert response.status_code == 200
    assert response.json()["data"]["cards"][0]["id"] == str(card.id)
    assert response.json()["data"]["cards"][0]["position"] == 0
    assert_no_sql_payload(response.json())


def test_update_dashboard_layout_rolls_back_after_database_failure(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Manager Personal",
        visibility_scope="personal",
    )
    first_card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
        title="First card",
        position=0,
    )
    second_card = _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=_add_saved_query(db_session, owner=manager),
        title="Second card",
        position=1,
    )
    csrf_token = _login(client, manager.email)
    original_commit = db_session.commit

    def fail_commit() -> None:
        db_session.flush()
        raise SQLAlchemyError("private database failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    response = client.patch(
        "/api/v1/dashboards/my/layout",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "items": [
                {"card_id": str(second_card.id), "position": 0},
                {"card_id": str(first_card.id), "position": 1},
            ]
        },
    )
    monkeypatch.setattr(db_session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "DASHBOARD_LAYOUT_UPDATE_FAILED"
    assert "private database failure" not in response.text
    assert_no_sql_payload(response.json())

    db_session.expire_all()
    assert db_session.get(DashboardCard, first_card.id).position == 0
    assert db_session.get(DashboardCard, second_card.id).position == 1


def test_create_dashboard_rejects_unknown_fields(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "My dashboard", "generated_sql": "SELECT 1"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_unknown_fields(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Saved insight", "executed_sql": "SELECT 1"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SAVE_CARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_create_dashboard_rejects_blank_title(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "  "},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_blank_title_when_provided(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "  "},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SAVE_CARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_my_dashboard_returns_owned_personal_dashboards_with_cards(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    own_dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Manager Personal",
        visibility_scope="personal",
        minute=1,
    )
    saved_query = _add_saved_query(db_session, owner=manager)
    card = _add_card(
        db_session,
        dashboard=own_dashboard,
        saved_query=saved_query,
        title="Unused Licenses",
        position=2,
    )
    _add_dashboard(
        db_session,
        owner=manager,
        title="Manager Department",
        visibility_scope="department",
        department=_department_by_name(db_session, "Finance"),
        minute=2,
    )
    _login(client, manager.email)

    response = client.get("/api/v1/dashboards/my")

    assert response.status_code == 200
    dashboards = response.json()["data"]
    assert [dashboard["title"] for dashboard in dashboards] == ["Manager Personal"]
    dashboard = dashboards[0]
    assert dashboard["id"] == str(own_dashboard.id)
    assert dashboard["visibility_scope"] == "personal"
    assert dashboard["department_id"] is None
    assert dashboard["is_archived"] is False
    assert len(dashboard["cards"]) == 1
    assert dashboard["cards"][0] == {
        "id": str(card.id),
        "dashboard_id": str(own_dashboard.id),
        "saved_query_id": str(saved_query.id),
        "title": "Unused Licenses",
        "description": "Card description",
        "card_type": "table",
        "position": 2,
        "layout": {"w": 4},
        "config": {"columns": ["product_name"]},
        "created_at": dashboard["cards"][0]["created_at"],
        "updated_at": dashboard["cards"][0]["updated_at"],
    }
    assert dashboard["created_at"]
    assert dashboard["updated_at"]
    assert_no_sql_payload(response.json())


def test_my_dashboard_hides_another_users_personal_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    _login(client, manager.email)

    response = client.get("/api/v1/dashboards/my")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_catalog_excludes_archived_dashboards(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    _add_dashboard(
        db_session,
        owner=manager,
        title="Active Personal",
        visibility_scope="personal",
        minute=1,
    )
    _add_dashboard(
        db_session,
        owner=manager,
        title="Archived Personal",
        visibility_scope="personal",
        is_archived=True,
        minute=2,
    )
    _login(client, manager.email)

    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 200
    titles = [dashboard["title"] for dashboard in response.json()["data"]]
    assert titles == ["Active Personal"]
    assert "Archived Personal" not in titles
    assert_no_sql_payload(response.json())


def test_catalog_shows_department_dashboard_for_matching_department_scope(
    client: TestClient,
    db_session: Session,
) -> None:
    finance = _department_by_name(db_session, "Finance")
    sales_user = _user_by_email(db_session, "demo.user@queryops.local")
    _assign_department_scope(db_session, sales_user, finance)
    dashboard = _add_dashboard(
        db_session,
        owner=_user_by_email(db_session, "demo.analyst@queryops.local"),
        title="Finance Department",
        visibility_scope="department",
        department=finance,
    )
    _login(client, sales_user.email)

    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 200
    dashboards = response.json()["data"]
    assert [row["id"] for row in dashboards] == [str(dashboard.id)]
    assert dashboards[0]["department_id"] == str(finance.id)
    assert_no_sql_payload(response.json())


def test_catalog_shows_department_dashboard_for_same_department(
    client: TestClient,
    db_session: Session,
) -> None:
    finance = _department_by_name(db_session, "Finance")
    dashboard = _add_dashboard(
        db_session,
        owner=_user_by_email(db_session, "demo.analyst@queryops.local"),
        title="Finance Department",
        visibility_scope="department",
        department=finance,
    )
    _login(client, "demo.manager@queryops.local")

    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 200
    dashboards = response.json()["data"]
    assert [row["id"] for row in dashboards] == [str(dashboard.id)]
    assert dashboards[0]["department_id"] == str(finance.id)
    assert_no_sql_payload(response.json())


def test_catalog_hides_department_dashboard_without_matching_scope(
    client: TestClient,
    db_session: Session,
) -> None:
    finance = _department_by_name(db_session, "Finance")
    _add_dashboard(
        db_session,
        owner=_user_by_email(db_session, "demo.analyst@queryops.local"),
        title="Finance Department",
        visibility_scope="department",
        department=finance,
    )
    _login(client, "demo.user@queryops.local")

    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_catalog_shows_global_dashboard_to_admin(
    client: TestClient,
    db_session: Session,
) -> None:
    dashboard = _add_dashboard(
        db_session,
        owner=_user_by_email(db_session, "demo.admin@queryops.local"),
        title="Global Dashboard",
        visibility_scope="global",
    )
    _login(client, "demo.admin@queryops.local")

    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["data"]] == [str(dashboard.id)]
    assert response.json()["data"][0]["visibility_scope"] == "global"


def test_catalog_hides_global_dashboard_from_non_global_user(
    client: TestClient,
    db_session: Session,
) -> None:
    _add_dashboard(
        db_session,
        owner=_user_by_email(db_session, "demo.admin@queryops.local"),
        title="Global Dashboard",
        visibility_scope="global",
    )
    _login(client, "demo.manager@queryops.local")

    response = client.get("/api/v1/dashboards/catalog")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_user_without_personal_dashboard_permission_cannot_create_personal_dashboard(
    client: TestClient,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "User Personal"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_manager_can_create_personal_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "title": " Manager Personal ",
            "description": "  Personal metrics  ",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["id"]
    assert data["title"] == "Manager Personal"
    assert data["description"] == "Personal metrics"
    assert data["visibility_scope"] == "personal"
    assert data["department_id"] is None
    assert data["cards"] == []
    created = db_session.get(Dashboard, uuid.UUID(data["id"]))
    assert created is not None
    assert created.owner_user_id == _user_by_email(
        db_session,
        "demo.manager@queryops.local",
    ).id
    assert created.visibility_scope == "personal"
    assert created.department_id is None
    assert_no_sql_payload(response.json())


def test_analyst_can_create_department_dashboard_for_allowed_department(
    client: TestClient,
    db_session: Session,
) -> None:
    it = _department_by_name(db_session, "IT")
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "title": "IT Department",
            "visibility_scope": "department",
            "department_id": str(it.id),
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["title"] == "IT Department"
    assert data["visibility_scope"] == "department"
    assert data["department_id"] == str(it.id)
    created = db_session.get(Dashboard, uuid.UUID(data["id"]))
    assert created is not None
    assert created.department_id == it.id
    assert_no_sql_payload(response.json())


def test_user_without_department_dashboard_permission_cannot_create_department_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    finance = _department_by_name(db_session, "Finance")
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "title": "Finance Department",
            "visibility_scope": "department",
            "department_id": str(finance.id),
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_can_create_global_dashboard(client: TestClient, db_session: Session) -> None:
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "title": "Global Operations",
            "visibility_scope": "global",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["visibility_scope"] == "global"
    assert data["department_id"] is None
    created = db_session.get(Dashboard, uuid.UUID(data["id"]))
    assert created is not None
    assert created.visibility_scope == "global"
    assert created.department_id is None


def test_non_global_user_cannot_create_global_dashboard(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "title": "Global Operations",
            "visibility_scope": "global",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_create_dashboard_rejects_invalid_visibility_scope(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Invalid Scope", "visibility_scope": "team"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_REQUEST"


def test_create_dashboard_rejects_invalid_department_id(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        "/api/v1/dashboards",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "title": "Invalid Department",
            "visibility_scope": "department",
            "department_id": "not-a-uuid",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DASHBOARD_REQUEST"


def test_save_card_rejects_invalid_dashboard_id(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": "not-a-uuid"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SAVE_CARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_missing_dashboard_id(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"title": "Saved insight"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SAVE_CARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_unsupported_card_type(client: TestClient) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    response = client.post(
        f"/api/v1/query-runs/{uuid.uuid4()}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(uuid.uuid4()), "card_type": "chart"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SAVE_CARD_REQUEST"
    assert_no_sql_payload(response.json())


def test_user_without_create_card_permission_cannot_save_card(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Manager Personal",
        visibility_scope="personal",
    )
    query_run = _add_query_run(db_session, user=manager)
    csrf_token = _login(client, manager.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id), "title": "Saved insight"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert_no_sql_payload(response.json())


def test_analyst_can_save_successful_own_query_run_as_card(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "dashboard_id": str(dashboard.id),
            "title": " Saved licenses ",
            "description": "  Licensing detail  ",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["id"]
    assert data["dashboard_id"] == str(dashboard.id)
    assert data["saved_query_id"]
    assert data["title"] == "Saved licenses"
    assert data["description"] == "Licensing detail"
    assert data["card_type"] == "table"
    assert data["position"] == 0
    assert data["layout"] is None
    assert data["config"] is None
    assert_no_sql_payload(response.json())

    saved_query = db_session.get(SavedQuery, uuid.UUID(data["saved_query_id"]))
    assert saved_query is not None
    assert saved_query.owner_user_id == analyst.id
    assert saved_query.name == "Saved licenses"
    assert saved_query.description == "Licensing detail"
    assert saved_query.natural_language_question == query_run.natural_language_question
    assert saved_query.generated_sql == query_run.generated_sql
    assert saved_query.visibility_scope == "personal"
    assert saved_query.department_id is None
    assert saved_query.parameters == {}
    assert saved_query.result_schema is None

    db_session.refresh(query_run)
    assert query_run.saved_query_id == saved_query.id

    card = db_session.get(DashboardCard, uuid.UUID(data["id"]))
    assert card is not None
    assert card.dashboard_id == dashboard.id
    assert card.saved_query_id == saved_query.id

    dashboard_response = client.get("/api/v1/dashboards/my")
    assert dashboard_response.status_code == 200
    cards = dashboard_response.json()["data"][0]["cards"]
    assert [card["id"] for card in cards] == [data["id"]]
    assert_no_sql_payload(dashboard_response.json())


def test_save_card_rejects_another_users_query_run(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    admin = _user_by_email(db_session, "demo.admin@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    query_run = _add_query_run(db_session, user=admin)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id)},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_FOUND"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_failed_query_run(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    query_run = _add_query_run(db_session, user=analyst, status=RunStatus.FAILED.value)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id)},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_SAVEABLE"
    assert_no_sql_payload(response.json())


@pytest.mark.parametrize(
    "status",
    [
        RunStatus.QUEUED.value,
        RunStatus.RUNNING.value,
        RunStatus.CANCELLED.value,
    ],
)
def test_save_card_rejects_incomplete_query_run_statuses(
    client: TestClient,
    db_session: Session,
    status: str,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    query_run = _add_query_run(db_session, user=analyst, status=status)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id)},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_SAVEABLE"


def test_save_card_rejects_clarification_required_query_run(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    query_run = _add_query_run(
        db_session,
        user=analyst,
        query_metadata={"clarification_required": True},
    )
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id)},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_SAVEABLE"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_another_users_personal_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=manager,
        title="Manager Personal",
        visibility_scope="personal",
    )
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id)},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_archived_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Archived Personal",
        visibility_scope="personal",
        is_archived=True,
    )
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id)},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DASHBOARD_NOT_FOUND"
    assert_no_sql_payload(response.json())


def test_save_card_rejects_department_dashboard_outside_scope(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    finance = _department_by_name(db_session, "Finance")
    dashboard = _add_dashboard(
        db_session,
        owner=_user_by_email(db_session, "demo.admin@queryops.local"),
        title="Finance Department",
        visibility_scope="department",
        department=finance,
    )
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id)},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert_no_sql_payload(response.json())


def test_save_card_allows_department_dashboard_in_scope(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    it = _department_by_name(db_session, "IT")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="IT Department",
        visibility_scope="department",
        department=it,
    )
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id)},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["dashboard_id"] == str(dashboard.id)
    saved_query = db_session.get(SavedQuery, uuid.UUID(data["saved_query_id"]))
    assert saved_query is not None
    assert saved_query.visibility_scope == "department"
    assert saved_query.department_id == it.id
    assert_no_sql_payload(response.json())


def test_save_card_global_dashboard_requires_global_permission(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    admin = _user_by_email(db_session, "demo.admin@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=admin,
        title="Global Dashboard",
        visibility_scope="global",
    )
    query_run = _add_query_run(db_session, user=analyst)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id)},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert_no_sql_payload(response.json())


def test_admin_can_save_card_to_global_dashboard(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _user_by_email(db_session, "demo.admin@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=admin,
        title="Global Dashboard",
        visibility_scope="global",
    )
    query_run = _add_query_run(db_session, user=admin)
    csrf_token = _login(client, admin.email)

    response = client.post(
        f"/api/v1/query-runs/{query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id), "card_type": "table"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["dashboard_id"] == str(dashboard.id)
    saved_query = db_session.get(SavedQuery, uuid.UUID(data["saved_query_id"]))
    assert saved_query is not None
    assert saved_query.visibility_scope == "global"
    assert saved_query.department_id is None
    assert_no_sql_payload(response.json())


def test_save_card_positions_increment_deterministically(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    dashboard = _add_dashboard(
        db_session,
        owner=analyst,
        title="Analyst Personal",
        visibility_scope="personal",
    )
    existing_saved_query = _add_saved_query(db_session, owner=analyst)
    _add_card(
        db_session,
        dashboard=dashboard,
        saved_query=existing_saved_query,
        title="Existing",
        position=3,
    )
    first_query_run = _add_query_run(db_session, user=analyst, question="First")
    second_query_run = _add_query_run(db_session, user=analyst, question="Second")
    csrf_token = _login(client, analyst.email)

    first_response = client.post(
        f"/api/v1/query-runs/{first_query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id), "title": "First"},
    )
    second_response = client.post(
        f"/api/v1/query-runs/{second_query_run.id}/save-card",
        headers={"X-CSRF-Token": csrf_token},
        json={"dashboard_id": str(dashboard.id), "title": "Second"},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["data"]["position"] == 4
    assert second_response.json()["data"]["position"] == 5
    assert_no_sql_payload(first_response.json())
    assert_no_sql_payload(second_response.json())


def assert_no_sql_payload(payload: Any) -> None:
    serialized = json.dumps(payload)
    assert "SELECT " not in serialized
    _assert_no_forbidden_keys(payload)


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert "generated_sql" not in value
        assert "executed_sql" not in value
        for child in value.values():
            _assert_no_forbidden_keys(child)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_keys(item)


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def _user_by_email(db_session: Session, email: str) -> AppUser:
    user = db_session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _department_by_name(db_session: Session, name: str) -> Department:
    department = db_session.scalar(select(Department).where(Department.name == name))
    assert department is not None
    return department


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


def _assign_department_scope(
    db_session: Session,
    user: AppUser,
    department: Department,
) -> None:
    scope = _scope_by_type_key(db_session, "department", department.name.lower())
    existing = db_session.get(
        UserAccessScope,
        {"user_id": user.id, "scope_id": scope.id},
    )
    if existing is None:
        db_session.add(
            UserAccessScope(
                user_id=user.id,
                scope_id=scope.id,
                access_level="read",
                is_default=False,
            )
        )
        db_session.commit()


def _add_dashboard(
    db_session: Session,
    *,
    owner: AppUser,
    title: str,
    visibility_scope: str,
    department: Department | None = None,
    is_archived: bool = False,
    minute: int = 0,
) -> Dashboard:
    created_at = datetime(2026, 7, 4, 12, minute, tzinfo=UTC)
    dashboard = Dashboard(
        owner_user_id=owner.id,
        title=title,
        description=f"{title} description",
        visibility_scope=visibility_scope,
        department_id=department.id if department else None,
        is_archived=is_archived,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(dashboard)
    db_session.commit()
    db_session.refresh(dashboard)
    return dashboard


def _add_saved_query(db_session: Session, *, owner: AppUser) -> SavedQuery:
    saved_query = SavedQuery(
        owner_user_id=owner.id,
        name="Unsafe saved query",
        description="Saved query description",
        natural_language_question="Show unused licenses.",
        generated_sql="SELECT should_not_leak FROM licenses",
        visibility_scope="personal",
        department_id=None,
        parameters={},
        result_schema={"columns": ["product_name"]},
    )
    db_session.add(saved_query)
    db_session.commit()
    db_session.refresh(saved_query)
    return saved_query


def _add_card(
    db_session: Session,
    *,
    dashboard: Dashboard,
    saved_query: SavedQuery,
    title: str,
    position: int,
) -> DashboardCard:
    card = DashboardCard(
        dashboard_id=dashboard.id,
        saved_query_id=saved_query.id,
        title=title,
        description="Card description",
        card_type="table",
        position=position,
        layout={"w": 4},
        config={"columns": ["product_name"]},
    )
    db_session.add(card)
    db_session.commit()
    db_session.refresh(card)
    return card


def _add_query_run(
    db_session: Session,
    *,
    user: AppUser,
    status: str = RunStatus.SUCCEEDED.value,
    question: str = "Show unused licenses.",
    query_metadata: dict[str, Any] | None = None,
) -> QueryRun:
    query_run = QueryRun(
        user_id=user.id,
        status=status,
        natural_language_question=question,
        generated_sql="SELECT should_not_leak FROM licenses",
        executed_sql="SELECT should_not_leak FROM licenses WHERE department_id = :id",
        row_count=1 if status == RunStatus.SUCCEEDED.value else None,
        duration_ms=12 if status == RunStatus.SUCCEEDED.value else None,
        error_message=None if status == RunStatus.SUCCEEDED.value else "Query failed.",
        query_metadata=query_metadata
        if query_metadata is not None
        else {
            "provider": "mock",
            "validation": {"valid": status == RunStatus.SUCCEEDED.value},
            "execution": {"status": status},
        },
    )
    db_session.add(query_run)
    db_session.commit()
    db_session.refresh(query_run)
    return query_run
