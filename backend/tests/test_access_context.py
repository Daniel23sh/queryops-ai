from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.responses import ApiError
from app.auth.access_context import build_user_access_context
from app.auth.access_policy import (
    authorize_resource_access,
    evaluate_access,
    prepare_scoped_data_access,
    require_access_decision,
)
from app.db.base import Base
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser, DataResource


PUBLIC_AUTHORIZATION_ERROR = "You are not authorized to access this resource."


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


def test_evaluate_access_denies_scoped_data_without_scope_key() -> None:
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
            {"scope_type": "department"},
        )

        assert decision.allowed is False
        assert decision.effect == "deny"
        assert decision.reason == "missing_scope_key"
        assert decision.matched_scopes == []


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


def test_authorize_resource_access_returns_access_decision() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "directory_users")

        decision = authorize_resource_access(
            subject,
            "query:scoped_data",
            resource,
            {"scope_type": "department", "scope_key": "finance"},
        )

        assert decision.allowed is True
        assert decision.reason == "allow_matching_scope"
        assert decision.matched_scopes == ["department:finance"]


def test_authorize_resource_access_does_not_use_frontend_visibility_to_grant_access() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "directory_users")

        decision = authorize_resource_access(
            subject,
            "query:scoped_data",
            resource,
            {
                "scope_type": "department",
                "scope_key": "sales",
                "frontend_visible": True,
            },
        )

        assert decision.allowed is False
        assert decision.reason == "missing_scope"


def test_authorize_resource_access_does_not_use_frontend_visibility_to_deny_access() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "directory_users")

        decision = authorize_resource_access(
            subject,
            "query:scoped_data",
            resource,
            {
                "scope_type": "department",
                "scope_key": "finance",
                "frontend_visible": False,
            },
        )

        assert decision.allowed is True
        assert decision.reason == "allow_matching_scope"


def test_require_access_decision_does_not_raise_for_allowed_decision() -> None:
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

        require_access_decision(decision)


@pytest.mark.parametrize(
    ("email", "runtime_context", "expected_reason"),
    [
        (
            "demo.user@queryops.local",
            {"scope_type": "department", "scope_key": "sales"},
            "missing_permission",
        ),
        (
            "demo.manager@queryops.local",
            {"scope_type": "department", "scope_key": "sales"},
            "missing_scope",
        ),
        (
            "demo.manager@queryops.local",
            {"scope_type": "department"},
            "missing_scope_key",
        ),
    ],
)
def test_require_access_decision_maps_denials_to_safe_403(
    email: str,
    runtime_context: dict[str, str],
    expected_reason: str,
) -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(user_by_email(session, email), session)
        resource = data_resource_by_table(session, "directory_users")
        decision = evaluate_access(
            subject,
            "query:scoped_data",
            resource,
            runtime_context,
        )

        with pytest.raises(ApiError) as exc_info:
            require_access_decision(decision)

        assert decision.reason == expected_reason
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "FORBIDDEN"
        assert exc_info.value.message == PUBLIC_AUTHORIZATION_ERROR
        assert exc_info.value.details is None


def test_require_access_decision_does_not_leak_internal_policy_details() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "security_events")
        decision = evaluate_access(
            subject,
            "query:scoped_data",
            resource,
            {"scope_type": "department", "scope_key": "sales"},
        )

        with pytest.raises(ApiError) as exc_info:
            require_access_decision(decision)

        public_message = exc_info.value.message
        assert decision.reason == "missing_scope"
        assert "missing_scope" not in public_message
        assert "security_events" not in public_message
        assert "department" not in public_message
        assert "sales" not in public_message
        assert "can_query_scoped_data" not in public_message


def test_prepare_scoped_data_access_applies_rls_context_when_allowed() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        finance = session.scalar(select(Department).where(Department.name == "Finance"))
        assert finance is not None
        resource = data_resource_by_table(session, "directory_users")
        fake_session = FakeSession()

        decision = prepare_scoped_data_access(
            fake_session,
            subject,
            "query:scoped_data",
            resource,
            {"scope_type": "department", "scope_key": "finance"},
        )

        assert decision.allowed is True
        assert fake_session.setting_values["app.current_scope_type"] == "department"
        assert fake_session.setting_values["app.current_scope_keys"] == str(finance.id)
        assert fake_session.setting_values["app.has_global_scope"] == "false"


def test_prepare_scoped_data_access_does_not_apply_rls_context_when_denied() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        subject = build_user_access_context(
            user_by_email(session, "demo.manager@queryops.local"),
            session,
        )
        resource = data_resource_by_table(session, "directory_users")
        fake_session = FakeSession()

        with pytest.raises(ApiError):
            prepare_scoped_data_access(
                fake_session,
                subject,
                "query:scoped_data",
                resource,
                {"scope_type": "department", "scope_key": "sales"},
            )

        assert fake_session.setting_values == {}


class FakeSession:
    def __init__(self) -> None:
        self.setting_values: dict[str, str] = {}

    def execute(self, _statement: Any, parameters: dict[str, str] | None = None) -> None:
        assert parameters is not None
        self.setting_values[parameters["setting_name"]] = parameters["value"]


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
