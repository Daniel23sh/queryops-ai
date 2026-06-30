from collections.abc import Generator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.responses import ApiError, api_error_handler
from app.auth.permissions import (
    require_any_permission,
    require_permission,
    resolve_effective_permission_keys,
)
from app.auth.session import SESSION_COOKIE_NAME, create_session_token
from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser, Permission, PermissionEffect, UserPermission


EXPECTED_USER_PERMISSIONS = {
    "can_star_dashboard",
    "can_use_query_templates",
    "can_view_own_data",
}

EXPECTED_MANAGER_PERMISSIONS = EXPECTED_USER_PERMISSIONS | {
    "can_create_personal_dashboard",
    "can_query_department_data",
    "can_query_scoped_data",
    "can_request_action",
    "can_run_free_query",
    "can_view_department_data",
    "can_view_department_evaluation",
    "can_view_scoped_data",
    "can_view_scope_evaluation",
}

EXPECTED_ANALYST_PERMISSIONS = EXPECTED_MANAGER_PERMISSIONS | {
    "can_approve_department_action",
    "can_approve_scoped_action",
    "can_create_card",
    "can_create_department_dashboard",
    "can_create_scope_dashboard",
    "can_manage_department_dashboard",
    "can_manage_scope_dashboard",
    "can_view_department_audit",
    "can_view_query_history_department",
    "can_view_query_history_scope",
    "can_view_scope_audit",
    "can_view_sql",
}

EXPECTED_ADMIN_PERMISSIONS = {
    "can_approve_department_action",
    "can_approve_global_action",
    "can_approve_policy_override",
    "can_approve_role_requests",
    "can_approve_scoped_action",
    "can_create_card",
    "can_create_department_dashboard",
    "can_create_global_dashboard",
    "can_create_personal_dashboard",
    "can_create_scope_dashboard",
    "can_disable_app_user",
    "can_downgrade_user_role",
    "can_manage_department_dashboard",
    "can_manage_global_dashboard",
    "can_manage_users",
    "can_manage_scope_dashboard",
    "can_query_department_data",
    "can_query_global_data",
    "can_query_product_tables",
    "can_query_scoped_data",
    "can_request_action",
    "can_run_free_query",
    "can_self_approve_admin_action",
    "can_star_dashboard",
    "can_use_query_templates",
    "can_view_department_audit",
    "can_view_department_data",
    "can_view_department_evaluation",
    "can_view_global_audit",
    "can_view_global_data",
    "can_view_global_evaluation",
    "can_view_own_data",
    "can_view_query_history_department",
    "can_view_query_history_scope",
    "can_view_scoped_data",
    "can_view_scope_audit",
    "can_view_scope_evaluation",
    "can_view_sql",
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


@pytest.mark.parametrize(
    ("email", "expected_permissions"),
    [
        ("demo.user@queryops.local", EXPECTED_USER_PERMISSIONS),
        ("demo.manager@queryops.local", EXPECTED_MANAGER_PERMISSIONS),
        ("demo.analyst@queryops.local", EXPECTED_ANALYST_PERMISSIONS),
        ("demo.admin@queryops.local", EXPECTED_ADMIN_PERMISSIONS),
    ],
)
def test_resolver_returns_expected_permissions_by_role(
    db_session: Session,
    email: str,
    expected_permissions: set[str],
) -> None:
    user = _user_by_email(db_session, email)

    permissions = resolve_effective_permission_keys(user, db_session)

    assert permissions == sorted(expected_permissions)


def test_manager_permissions_exclude_sql_global_and_admin_permissions(
    db_session: Session,
) -> None:
    user = _user_by_email(db_session, "demo.manager@queryops.local")

    permissions = set(resolve_effective_permission_keys(user, db_session))

    assert "can_run_free_query" in permissions
    assert "can_query_department_data" in permissions
    assert "can_query_scoped_data" in permissions
    assert "can_view_department_data" in permissions
    assert "can_view_scoped_data" in permissions
    assert "can_view_sql" not in permissions
    assert "can_query_global_data" not in permissions
    assert "can_manage_users" not in permissions


def test_analyst_permissions_exclude_global_and_admin_permissions(
    db_session: Session,
) -> None:
    user = _user_by_email(db_session, "demo.analyst@queryops.local")

    permissions = set(resolve_effective_permission_keys(user, db_session))

    assert "can_view_sql" in permissions
    assert "can_create_department_dashboard" in permissions
    assert "can_create_scope_dashboard" in permissions
    assert "can_approve_department_action" in permissions
    assert "can_approve_scoped_action" in permissions
    assert "can_query_global_data" not in permissions
    assert "can_approve_global_action" not in permissions
    assert "can_manage_users" not in permissions


def test_resolver_returns_stable_sorted_permission_keys(db_session: Session) -> None:
    user = _user_by_email(db_session, "demo.admin@queryops.local")

    permissions = resolve_effective_permission_keys(user, db_session)

    assert permissions == sorted(permissions)


def test_user_permission_allow_override_adds_permission(db_session: Session) -> None:
    user = _user_by_email(db_session, "demo.user@queryops.local")
    permission = _permission_by_key(db_session, "can_run_free_query")
    db_session.add(
        UserPermission(
            user_id=user.id,
            permission_id=permission.id,
            effect=PermissionEffect.ALLOW.value,
            reason="Temporary test grant",
        )
    )

    permissions = resolve_effective_permission_keys(user, db_session)

    assert "can_run_free_query" in permissions


def test_user_permission_deny_override_removes_role_permission(
    db_session: Session,
) -> None:
    user = _user_by_email(db_session, "demo.analyst@queryops.local")
    permission = _permission_by_key(db_session, "can_view_sql")
    db_session.add(
        UserPermission(
            user_id=user.id,
            permission_id=permission.id,
            effect=PermissionEffect.DENY.value,
            reason="Temporary test denial",
        )
    )

    permissions = resolve_effective_permission_keys(user, db_session)

    assert "can_view_sql" not in permissions


def test_require_permission_returns_401_when_unauthenticated(
    db_session: Session,
) -> None:
    client = _permission_test_client(db_session)

    response = client.get("/needs-sql")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_require_permission_returns_403_when_permission_is_missing(
    db_session: Session,
) -> None:
    client = _permission_test_client(db_session)
    _set_session_cookie(client, _user_by_email(db_session, "demo.manager@queryops.local"))

    response = client.get("/needs-sql")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_require_permission_allows_when_permission_exists(
    db_session: Session,
) -> None:
    client = _permission_test_client(db_session)
    _set_session_cookie(client, _user_by_email(db_session, "demo.analyst@queryops.local"))

    response = client.get("/needs-sql")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_require_any_permission_allows_when_one_permission_exists(
    db_session: Session,
) -> None:
    client = _permission_test_client(db_session)
    _set_session_cookie(client, _user_by_email(db_session, "demo.manager@queryops.local"))

    response = client.get("/needs-sql-or-free-query")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_require_any_permission_rejects_when_no_permissions_exist(
    db_session: Session,
) -> None:
    client = _permission_test_client(db_session)
    _set_session_cookie(client, _user_by_email(db_session, "demo.manager@queryops.local"))

    response = client.get("/needs-sql-or-manage-users")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def _permission_test_client(db_session: Session) -> TestClient:
    test_app = FastAPI()
    test_app.add_exception_handler(ApiError, api_error_handler)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    @test_app.get("/needs-sql")
    def needs_sql(_user: AppUser = Depends(require_permission("can_view_sql"))):
        return {"ok": True}

    @test_app.get("/needs-sql-or-free-query")
    def needs_sql_or_free_query(
        _user: AppUser = Depends(
            require_any_permission(["can_view_sql", "can_run_free_query"])
        ),
    ):
        return {"ok": True}

    @test_app.get("/needs-sql-or-manage-users")
    def needs_sql_or_manage_users(
        _user: AppUser = Depends(
            require_any_permission(["can_view_sql", "can_manage_users"])
        ),
    ):
        return {"ok": True}

    return TestClient(test_app)


def _set_session_cookie(client: TestClient, user: AppUser) -> None:
    client.cookies.set(
        SESSION_COOKIE_NAME,
        create_session_token(
            user_id=user.id,
            auth_provider=user.auth_provider,
            csrf_token="test-csrf-token",
        ),
    )


def _user_by_email(db_session: Session, email: str) -> AppUser:
    user = db_session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _permission_by_key(db_session: Session, key: str) -> Permission:
    permission = db_session.scalar(select(Permission).where(Permission.key == key))
    assert permission is not None
    return permission
