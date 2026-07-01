from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.access_context import UserAccessContext, build_user_access_context
from app.core.rls import build_rls_context, set_rls_context
from app.db.base import Base
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser


def test_build_rls_context_marks_admin_global_scope() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = build_user_access_context(
            user_by_email(session, "demo.admin@queryops.local"),
            session,
        )

        rls_context = build_rls_context(access_context)

        assert rls_context.user_id == access_context.user_id
        assert rls_context.role == "admin"
        assert rls_context.scope_type == "global"
        assert rls_context.scope_keys == tuple()
        assert rls_context.has_global_scope is True


def test_build_rls_context_uses_finance_department_uuid_for_manager() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        finance = department_by_name(session, "Finance")

        rls_context = build_rls_context(access_context)

        assert rls_context.role == "manager"
        assert rls_context.scope_type == "department"
        assert rls_context.scope_keys == (str(finance.id),)
        assert rls_context.has_global_scope is False


def test_build_rls_context_uses_it_department_uuid_for_analyst() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = build_user_access_context(
            user_by_email(session, "demo.analyst@queryops.local"),
            session,
        )
        it = department_by_name(session, "IT")

        rls_context = build_rls_context(access_context)

        assert rls_context.role == "analyst"
        assert rls_context.scope_type == "department"
        assert rls_context.scope_keys == (str(it.id),)
        assert rls_context.has_global_scope is False


def test_build_rls_context_uses_sales_department_uuid_for_user() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = build_user_access_context(
            user_by_email(session, "demo.user@queryops.local"),
            session,
        )
        sales = department_by_name(session, "Sales")

        rls_context = build_rls_context(access_context)

        assert rls_context.role == "user"
        assert rls_context.scope_type == "department"
        assert rls_context.scope_keys == (str(sales.id),)
        assert rls_context.has_global_scope is False


def test_build_rls_context_without_scopes_fails_closed() -> None:
    access_context = UserAccessContext(
        user_id=uuid.uuid4(),
        role="manager",
        permissions=frozenset({"can_query_scoped_data"}),
        scopes=tuple(),
        default_scope=None,
        has_global_scope=False,
        subject_attributes={},
    )

    rls_context = build_rls_context(access_context)

    assert rls_context.scope_type == "none"
    assert rls_context.scope_keys == tuple()
    assert rls_context.has_global_scope is False


def test_set_rls_context_emits_expected_set_local_settings() -> None:
    user_id = uuid.uuid4()
    access_context = UserAccessContext(
        user_id=user_id,
        role="analyst",
        permissions=frozenset({"can_query_scoped_data"}),
        scopes=tuple(),
        default_scope=None,
        has_global_scope=False,
        subject_attributes={},
    )
    rls_context = build_rls_context(access_context)
    fake_session = FakeSession()

    set_rls_context(fake_session, rls_context)

    assert fake_session.calls == [
        (
            "SELECT set_config(:setting_name, :value, true)",
            {"setting_name": "app.current_user_id", "value": str(user_id)},
        ),
        (
            "SELECT set_config(:setting_name, :value, true)",
            {"setting_name": "app.current_role", "value": "analyst"},
        ),
        (
            "SELECT set_config(:setting_name, :value, true)",
            {"setting_name": "app.current_scope_type", "value": "none"},
        ),
        (
            "SELECT set_config(:setting_name, :value, true)",
            {"setting_name": "app.current_scope_keys", "value": ""},
        ),
        (
            "SELECT set_config(:setting_name, :value, true)",
            {"setting_name": "app.has_global_scope", "value": "false"},
        ),
    ]


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> None:
        self.calls.append((str(statement), parameters))


def user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def department_by_name(session: Session, name: str) -> Department:
    department = session.scalar(select(Department).where(Department.name == name))
    assert department is not None
    return department


@contextmanager
def session_scope() -> Generator[Session, None, None]:
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
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
