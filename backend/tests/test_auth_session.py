from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.providers import (
    AuthCredentials,
    AuthProviderUnavailableError,
    SupabaseAuthProvider,
)
from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import AppUser, UserStatus


DEMO_USERS = {
    "demo.admin@queryops.local": "admin",
    "demo.analyst@queryops.local": "analyst",
    "demo.manager@queryops.local": "manager",
    "demo.user@queryops.local": "user",
}


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


@pytest.mark.parametrize(("email", "role"), DEMO_USERS.items())
def test_demo_login_succeeds_for_seeded_demo_users(
    client: TestClient,
    email: str,
    role: str,
) -> None:
    response = client.post("/api/v1/demo/login", json={"email": email})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["user"]["email"] == email
    assert body["data"]["user"]["role"] == role
    assert body["data"]["user"]["status"] == UserStatus.ACTIVE.value
    assert body["data"]["requires_onboarding"] is False
    assert body["data"]["csrf_token"]
    assert body["meta"]["request_id"]
    assert body["meta"]["timestamp"]

    session_cookie = _set_cookie_header(response, "qo_session")
    csrf_cookie = _set_cookie_header(response, "qo_csrf")
    assert session_cookie is not None
    assert "httponly" in session_cookie.lower()
    assert csrf_cookie is not None
    assert "httponly" not in csrf_cookie.lower()
    assert body["data"]["csrf_token"] in csrf_cookie


def test_demo_login_rejects_unknown_users(client: TestClient) -> None:
    response = client.post(
        "/api/v1/demo/login",
        json={"email": "not-a-demo-user@queryops.local"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_demo_login_rejects_disabled_users(
    client: TestClient,
    db_session: Session,
) -> None:
    user = db_session.scalar(
        select(AppUser).where(AppUser.email == "demo.user@queryops.local")
    )
    assert user is not None
    user.status = UserStatus.DISABLED.value

    response = client.post(
        "/api/v1/demo/login",
        json={"email": "demo.user@queryops.local"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_auth_me_rejects_unauthenticated_requests(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_auth_me_returns_logged_in_user_role_department_and_permissions(
    client: TestClient,
) -> None:
    login_response = client.post(
        "/api/v1/demo/login",
        json={"email": "demo.manager@queryops.local"},
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"]
    assert data["email"] == "demo.manager@queryops.local"
    assert data["full_name"] == "Demo Manager"
    assert data["role"] == "manager"
    assert data["status"] == UserStatus.ACTIVE.value
    assert data["department"]["name"] == "Finance"
    assert data["auth_mode"] == "demo"
    assert "can_run_free_query" in data["permissions"]
    assert "can_query_department_data" in data["permissions"]
    assert "can_view_sql" not in data["permissions"]
    assert "can_manage_users" not in data["permissions"]


def test_logout_requires_csrf_for_authenticated_session(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/demo/login",
        json={"email": "demo.manager@queryops.local"},
    )
    assert login_response.status_code == 200

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"


def test_logout_clears_session_and_csrf_cookies(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/demo/login",
        json={"email": "demo.manager@queryops.local"},
    )
    csrf_token = login_response.json()["data"]["csrf_token"]

    response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"ok": True}
    session_cookie = _set_cookie_header(response, "qo_session")
    csrf_cookie = _set_cookie_header(response, "qo_csrf")
    assert session_cookie is not None
    assert "max-age=0" in session_cookie.lower()
    assert csrf_cookie is not None
    assert "max-age=0" in csrf_cookie.lower()

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401

    second_logout_response = client.post("/api/v1/auth/logout")
    assert second_logout_response.status_code == 200
    assert second_logout_response.json()["data"] == {"ok": True}


def test_supabase_provider_is_skeleton_without_external_config(
    db_session: Session,
) -> None:
    provider = SupabaseAuthProvider()

    with pytest.raises(AuthProviderUnavailableError):
        provider.authenticate(AuthCredentials(access_token="test-token"), db_session)


def _set_cookie_header(response, cookie_name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{cookie_name}="):
            return header
    return None
