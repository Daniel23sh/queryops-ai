from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.access_context import build_user_access_context
from app.auth.access_policy import evaluate_access
from app.db.base import Base
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser, DataResource


def test_user_access_context_resolves_role_permissions_and_scopes() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        user = user_by_email(session, "demo.analyst@queryops.local")

        context = build_user_access_context(user, session)

        assert context.user_id == user.id
        assert context.role == "analyst"
        assert context.has_permission("can_query_scoped_data")
        assert context.has_permission("can_view_sql")
        assert context.has_scope("department", "it")
        assert context.default_scope is not None
        assert context.default_scope.type == "department"
        assert context.default_scope.key == "it"
        assert context.default_scope.display_name == "IT"
        assert context.default_scope.access_level == "manage"
        assert context.has_global_scope is False
        assert context.subject_attributes["role"] == "analyst"
        assert "department" in context.subject_attributes["scope_types"]
        assert context.subject_attributes["auth_provider"] == "demo"


def test_user_access_context_uses_access_scopes_not_app_user_department_id() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        user = user_by_email(session, "demo.analyst@queryops.local")
        finance = session.scalar(select(Department).where(Department.name == "Finance"))
        assert finance is not None
        user.department_id = finance.id

        context = build_user_access_context(user, session)

        assert context.default_scope is not None
        assert context.default_scope.key == "it"
        assert context.default_scope.display_name == "IT"
        assert context.default_scope.department_id != finance.id


def test_user_access_context_marks_admin_global_scope() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        user = user_by_email(session, "demo.admin@queryops.local")

        context = build_user_access_context(user, session)

        assert context.has_global_scope is True
        assert context.has_scope("global", "global")
        assert context.default_scope is not None
        assert context.default_scope.type == "global"


def test_evaluate_access_allows_permission_and_matching_scope() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "directory_users")

        decision = evaluate_access(
            subject,
            "query:scoped_data",
            resource,
            {"scope_type": "department", "scope_key": "finance"},
        )

        assert decision.allowed is True
        assert decision.effect == "allow"
        assert decision.action == "query:scoped_data"
        assert decision.required_permission == "can_query_scoped_data"
        assert decision.resource["table_name"] == "directory_users"
        assert decision.matched_scopes == ["department:finance"]
        assert "allow" in decision.reason


def test_evaluate_access_denies_missing_permission() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.user@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "directory_users")

        decision = evaluate_access(
            subject,
            "query:scoped_data",
            resource,
            {"scope_type": "department", "scope_key": "sales"},
        )

        assert decision.allowed is False
        assert decision.effect == "deny"
        assert decision.required_permission == "can_query_scoped_data"
        assert decision.reason == "missing_permission"


def test_evaluate_access_denies_missing_scope() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "directory_users")

        decision = evaluate_access(
            subject,
            "query:scoped_data",
            resource,
            {"scope_type": "department", "scope_key": "sales"},
        )

        assert decision.allowed is False
        assert decision.effect == "deny"
        assert decision.reason == "missing_scope"
        assert decision.context_snapshot is not None
        assert decision.context_snapshot["has_global_scope"] is False


def test_evaluate_access_allows_global_scope_for_scoped_resource() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.admin@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "security_events")

        decision = evaluate_access(
            subject,
            "query:scoped_data",
            resource,
            {"scope_type": "department", "scope_key": "finance"},
        )

        assert decision.allowed is True
        assert decision.effect == "allow"
        assert decision.matched_scopes == ["global:global"]


def test_evaluate_access_allows_reference_resource_with_query_permission() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "licenses")

        decision = evaluate_access(subject, "query:scoped_data", resource, {})

        assert decision.allowed is True
        assert decision.effect == "allow"
        assert decision.resource["table_name"] == "licenses"


def user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def data_resource_by_table(session: Session, table_name: str) -> DataResource:
    resource = session.scalar(
        select(DataResource).where(DataResource.table_name == table_name)
    )
    assert resource is not None
    return resource


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
