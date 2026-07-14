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
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import AppUser, Dashboard, DashboardCard, SavedQuery


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"


def test_postgres_library_and_detail_preserve_dashboard_visibility_and_safe_shape(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        manager = _user_by_email(session, "demo.manager@queryops.local")
        analyst = _user_by_email(session, "demo.analyst@queryops.local")
        finance = _department_by_name(session, "Finance")
        sales = _department_by_name(session, "Sales")
        owned = _dashboard(session, manager, "Owned", "personal")
        shared = _dashboard(session, analyst, "Shared", "department", finance)
        _dashboard(session, analyst, "Foreign private", "personal")
        _dashboard(session, analyst, "Other scope", "department", sales)
        _dashboard(session, analyst, "Archived", "department", finance, archived=True)
        saved_query = SavedQuery(
            owner_user_id=manager.id,
            name="Private source",
            natural_language_question="Show private source.",
            generated_sql="SELECT private_value FROM protected_table",
            visibility_scope="personal",
            parameters={"private": True},
            result_schema={"private": True},
        )
        session.add(saved_query)
        session.flush()
        for position in range(5):
            session.add(
                DashboardCard(
                    dashboard_id=owned.id,
                    saved_query_id=saved_query.id,
                    title=f"Safe card {position}",
                    position=position,
                    layout={"private": True},
                    config={"private": True},
                )
            )
        session.commit()
        owned_id = owned.id
        shared_id = shared.id

    _login(client, "demo.manager@queryops.local")
    library_response = client.get("/api/v1/dashboards/library")
    detail_response = client.get(f"/api/v1/dashboards/{owned_id}")

    assert library_response.status_code == 200
    library = library_response.json()["data"]
    assert {row["id"] for row in library} == {str(owned_id), str(shared_id)}
    assert {row["id"]: row["relationship"] for row in library} == {
        str(owned_id): "owned",
        str(shared_id): "shared",
    }
    owned_item = next(row for row in library if row["id"] == str(owned_id))
    assert owned_item["card_count"] == 5
    assert len(owned_item["preview_cards"]) == 4

    assert detail_response.status_code == 200
    assert len(detail_response.json()["data"]["cards"]) == 5
    _assert_safe(library_response.json())
    _assert_safe(detail_response.json())


def test_postgres_foreign_personal_dashboard_returns_safe_not_found(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        analyst = _user_by_email(session, "demo.analyst@queryops.local")
        dashboard = _dashboard(session, analyst, "Private detail", "personal")
        dashboard_id = dashboard.id
    _login(client, "demo.manager@queryops.local")

    response = client.get(f"/api/v1/dashboards/{dashboard_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DASHBOARD_NOT_FOUND"


def _dashboard(
    session: Session,
    owner: AppUser,
    title: str,
    visibility_scope: str,
    department: Department | None = None,
    archived: bool = False,
) -> Dashboard:
    dashboard = Dashboard(
        owner_user_id=owner.id,
        title=title,
        visibility_scope=visibility_scope,
        department_id=department.id if department else None,
        is_archived=archived,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(dashboard)
    session.flush()
    return dashboard


def _login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200


def _user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _department_by_name(session: Session, name: str) -> Department:
    department = session.scalar(select(Department).where(Department.name == name))
    assert department is not None
    return department


def _assert_safe(payload: object) -> None:
    serialized = json.dumps(payload)
    assert "SELECT " not in serialized
    for forbidden in [
        '"generated_sql"',
        '"executed_sql"',
        '"config"',
        '"layout"',
        '"parameters"',
        '"result_schema"',
        '"email"',
    ]:
        assert forbidden not in serialized


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = _postgres_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")
    _run_alembic_upgrade(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, profile_name="small", reset=True)
        session.commit()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def client(postgres_engine: Engine) -> Generator[TestClient, None, None]:
    session = Session(postgres_engine)

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _postgres_database_url() -> str:
    explicit_test_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if explicit_test_url:
        return explicit_test_url
    database_url = os.environ.get("DATABASE_URL") or LOCAL_POSTGRES_URL
    parsed_url = make_url(database_url)
    if (
        not parsed_url.drivername.startswith("postgresql")
        or parsed_url.host not in {"localhost", "127.0.0.1", "::1"}
        or parsed_url.database != "queryops"
    ):
        raise pytest.UsageError(
            "Destructive dashboard library tests require the local queryops database."
        )
    return database_url


def _run_alembic_upgrade(database_url: str) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
