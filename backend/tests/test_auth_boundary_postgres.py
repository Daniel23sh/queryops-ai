"""Exercise provider identity, sessions and permissions on guarded disposable PostgreSQL."""
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_role_requests_postgres import client as client, postgres_engine as postgres_engine
from test_auth_session import DEMO_USERS, DEMO_USER_SCOPES
from app.auth.permissions import get_current_app_user_for_session
from app.auth.session import SESSION_COOKIE_NAME, create_session_token, decode_session_token
from app.core.config import AuthConfigurationError
from app.models.product import AppUser, UserStatus


@pytest.mark.parametrize("email", DEMO_USERS)
def test_demo_persona_session_permissions_scopes_and_logout(client, email):
    login = client.post("/api/v1/demo/login", json={"email": email})
    assert login.status_code == 200
    data = login.json()["data"]
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"] == data["user"]
    assert data["user"]["auth_mode"] == "demo"
    assert data["user"]["role"] == DEMO_USERS[email]
    scope = data["user"]["scopes"][0]
    assert (scope["type"], scope["key"], scope["access_level"], scope["display_name"]) == DEMO_USER_SCOPES[email]
    assert client.get("/api/v1/audit/logs").status_code == (200 if DEMO_USERS[email] in {"admin", "analyst"} else 403)
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    logout = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": data["csrf_token"]})
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("mode", [None, "", "disabled", "supabase", "unknown"])
def test_existing_session_cannot_cross_configuration_boundary(client, postgres_engine, monkeypatch, mode):
    assert client.post("/api/v1/demo/login", json={"email": "demo.admin@queryops.local"}).status_code == 200
    session_data = decode_session_token(client.cookies.get(SESSION_COOKIE_NAME))
    assert session_data is not None
    if mode is None:
        monkeypatch.delenv("AUTH_MODE")
    else:
        monkeypatch.setenv("AUTH_MODE", mode)
    for path in ["/api/v1/auth/me", "/api/v1/audit/logs", "/api/v1/dashboards"]:
        assert client.get(path).status_code == 503
    assert client.post("/api/v1/demo/login", json={"email": "demo.admin@queryops.local"}).status_code == 503
    with Session(postgres_engine) as db:
        with pytest.raises(AuthConfigurationError):
            get_current_app_user_for_session(session_data, db)


@pytest.mark.parametrize(("session_provider", "user_provider"), [("supabase", "demo"), ("demo", "supabase"), ("supabase", "supabase"), ("", "demo")])
def test_signed_session_must_match_configured_and_current_user_provider(client, postgres_engine, session_provider, user_provider):
    with Session(postgres_engine) as db:
        user = db.scalar(select(AppUser).where(AppUser.email == "demo.admin@queryops.local"))
        assert user is not None
        user.auth_provider = user_provider
        user_id = user.id
        db.commit()
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(user_id=user_id, auth_provider=session_provider, csrf_token="test"))
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/audit/logs").status_code == 401
    if user_provider != "demo":
        assert client.post("/api/v1/demo/login", json={"email": "demo.admin@queryops.local"}).status_code == 401


@pytest.mark.parametrize("failure", ["disabled", "deleted", "expired", "tampered", "invalid"])
def test_existing_session_security_still_fails_closed(client, postgres_engine, monkeypatch, failure):
    assert client.post("/api/v1/demo/login", json={"email": "demo.admin@queryops.local"}).status_code == 200
    token = client.cookies.get(SESSION_COOKIE_NAME)
    session_data = decode_session_token(token)
    assert session_data is not None
    if failure in {"disabled", "deleted"}:
        with Session(postgres_engine) as db:
            user = db.get(AppUser, session_data.user_id)
            assert user is not None
            user.status = UserStatus.DISABLED.value
            db.commit()
        assert client.post("/api/v1/demo/login", json={"email": "demo.admin@queryops.local"}).status_code == 403
        if failure == "deleted":
            # A correctly signed token for a nonexistent identity must also fail.
            token = create_session_token(user_id=uuid4(), auth_provider="demo", csrf_token="test")
    elif failure == "expired":
        monkeypatch.setattr("app.auth.session.time.time", lambda: session_data.exp + 1)
    elif failure == "tampered":
        token += "tampered"
    else:
        token = "invalid"
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, token)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/audit/logs").status_code == 401
