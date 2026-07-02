from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, distinct, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext, build_user_access_context
from app.core.rls import RLSContext, set_rls_context
from app.db.base import Base
from app.domains.it_operations.models import Department
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser
from app.query_engine.runtime_role import QUERY_RUNTIME_ROLE, set_query_runtime_role
from app.query_engine.schema_context import build_schema_context
from app.query_engine.sql_executor import (
    QUERY_EXECUTION_PUBLIC_ERROR,
    SQLExecutionOptions,
    SQLExecutionResult,
    execute_validated_sql,
)
from app.query_engine.sql_validator import SQLValidationResult, validate_sql


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"


def test_manager_query_returns_only_assigned_department_without_sql_filter(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        manager = access_context_for(session, "demo.manager@queryops.local")
        finance_id = str(manager.default_scope.department_id)
        validation = validate_for_user(
            session,
            manager,
            "SELECT id, department_id, email FROM directory_users ORDER BY email LIMIT 50",
        )

    result = execute_validated_sql(postgres_engine, manager, validation)

    assert_success(result)
    assert result.row_count > 0
    assert result.referenced_tables == ["directory_users"]
    assert {str(row["department_id"]) for row in result.rows} == {finance_id}
    assert result.execution_metadata["runtime_role"] == QUERY_RUNTIME_ROLE
    assert result.execution_metadata["transaction_read_only"] == "on"


def test_manager_cannot_see_another_department_rows(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        manager = access_context_for(session, "demo.manager@queryops.local")
        sales_id = str(department_id(session, "Sales"))
        validation = validate_for_user(
            session,
            manager,
            (
                "SELECT id, department_id, email "
                f"FROM directory_users WHERE department_id = '{sales_id}' "
                "ORDER BY email LIMIT 25"
            ),
        )

    result = execute_validated_sql(postgres_engine, manager, validation)

    assert_success(result)
    assert result.rows == []
    assert result.row_count == 0


def test_analyst_scoped_query_works_for_assigned_it_scope(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        analyst = access_context_for(session, "demo.analyst@queryops.local")
        it_id = str(analyst.default_scope.department_id)
        validation = validate_for_user(
            session,
            analyst,
            "SELECT id, department_id, email FROM directory_users ORDER BY email LIMIT 25",
        )

    result = execute_validated_sql(postgres_engine, analyst, validation)

    assert_success(result)
    assert result.row_count > 0
    assert {str(row["department_id"]) for row in result.rows} == {it_id}


def test_admin_global_query_returns_allowed_global_data(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")
        validation = validate_for_user(
            session,
            admin,
            "SELECT id, department_id, email FROM directory_users ORDER BY email LIMIT 200",
        )
        department_count = session.scalar(select(func.count(distinct(Department.id))))

    result = execute_validated_sql(postgres_engine, admin, validation)

    assert_success(result)
    assert result.row_count > 0
    assert len({str(row["department_id"]) for row in result.rows}) == department_count


def test_denied_context_fails_safe(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        user = access_context_for(session, "demo.user@queryops.local")
        manager = access_context_for(session, "demo.manager@queryops.local")
        validation = validate_for_user(
            session,
            manager,
            "SELECT id, department_id, email FROM directory_users ORDER BY email LIMIT 10",
        )

    result = execute_validated_sql(postgres_engine, user, validation)

    assert_failed(result, "access_denied")
    assert result.rows == []


def test_no_scope_context_fails_safe(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        manager = access_context_for(session, "demo.manager@queryops.local")
        no_scope = UserAccessContext(
            user_id=manager.user_id,
            role=manager.role,
            permissions=manager.permissions,
            scopes=tuple(),
            default_scope=None,
            has_global_scope=False,
            subject_attributes={},
        )
        validation = validate_for_user(
            session,
            manager,
            "SELECT id, department_id, email FROM directory_users ORDER BY email LIMIT 10",
        )

    result = execute_validated_sql(postgres_engine, no_scope, validation)

    assert_failed(result, "access_denied")
    assert result.rows == []


def test_non_queryable_table_execution_is_denied(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")

    result = execute_validated_sql(
        postgres_engine,
        admin,
        SQLValidationResult(
            valid=True,
            sanitized_sql="SELECT id FROM it_audit_events LIMIT 10",
            referenced_tables=["it_audit_events"],
        ),
    )

    assert_failed(result, "resource_not_queryable")


def test_it_audit_events_execution_is_denied(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")

    result = execute_validated_sql(
        postgres_engine,
        admin,
        SQLValidationResult(
            valid=True,
            sanitized_sql="SELECT id, event_type FROM it_audit_events LIMIT 10",
            referenced_tables=["it_audit_events"],
        ),
    )

    assert_failed(result, "resource_not_queryable")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO departments (id, name) VALUES (gen_random_uuid(), 'bad')",
        "UPDATE departments SET description = 'bad'",
        "DELETE FROM departments",
    ],
)
def test_dml_cannot_execute_even_if_attempted_directly(
    postgres_engine: Engine,
    sql: str,
) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")

    result = execute_validated_sql(
        postgres_engine,
        admin,
        SQLValidationResult(
            valid=True,
            sanitized_sql=sql,
            referenced_tables=["departments"],
        ),
    )

    assert_failed(result, "unsafe_sql")


@pytest.mark.parametrize(
    ("sql", "parameters"),
    [
        (
            """
            INSERT INTO departments (id, name, description)
            VALUES (:id, :name, 'executor runtime role write test')
            """,
            {"id": uuid.uuid4(), "name": f"executor-write-{uuid.uuid4()}"},
        ),
        (
            """
            UPDATE departments
            SET description = 'executor runtime role write test'
            WHERE name = :name
            """,
            {"name": f"executor-write-{uuid.uuid4()}"},
        ),
        (
            """
            DELETE FROM departments
            WHERE name = :name
            """,
            {"name": f"executor-write-{uuid.uuid4()}"},
        ),
    ],
)
def test_runtime_role_cannot_insert_update_or_delete_inside_executor_boundary(
    postgres_engine: Engine,
    sql: str,
    parameters: dict[str, object],
) -> None:
    with pytest.raises(DBAPIError):
        with postgres_engine.connect() as connection:
            with connection.begin():
                set_query_runtime_role(connection)
                set_rls_context(connection, global_rls_context())
                connection.execute(text(sql), parameters)


def test_invalid_sql_validation_result_is_refused(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        manager = access_context_for(session, "demo.manager@queryops.local")

    result = execute_validated_sql(
        postgres_engine,
        manager,
        SQLValidationResult(
            valid=False,
            sanitized_sql=None,
            referenced_tables=[],
            error_code="table_not_allowed",
            public_error="SQL is not allowed for safe read-only querying.",
        ),
    )

    assert_failed(result, "invalid_sql")


def test_executor_uses_sanitized_sql_not_raw_sql_attribute(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")
    validation = FakeValidationResult(
        sanitized_sql="SELECT 'sanitized' AS source FROM departments ORDER BY name LIMIT 1",
        raw_sql="SELECT 'raw' AS source FROM departments ORDER BY name LIMIT 1",
        referenced_tables=["departments"],
    )

    result = execute_validated_sql(postgres_engine, admin, validation)

    assert_success(result)
    assert result.rows[0]["source"] == "sanitized"


def test_runtime_current_user_is_query_runtime_role(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")
        validation = validate_for_user(
            session,
            admin,
            "SELECT current_user AS runtime_user, name FROM departments ORDER BY name LIMIT 1",
        )

    result = execute_validated_sql(postgres_engine, admin, validation)

    assert_success(result)
    assert result.rows[0]["runtime_user"] == QUERY_RUNTIME_ROLE
    assert result.execution_metadata["runtime_role"] == QUERY_RUNTIME_ROLE


def test_existing_session_transaction_does_not_weaken_read_only_execution(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")
        session.execute(text("SELECT 1")).scalar_one()
        validation = validate_for_user(
            session,
            admin,
            (
                "SELECT current_setting('transaction_read_only') AS read_only, "
                "name FROM departments ORDER BY name LIMIT 1"
            ),
        )

        result = execute_validated_sql(session, admin, validation)

    assert_success(result)
    assert result.rows[0]["read_only"] == "on"


def test_timeout_behavior_returns_sanitized_error(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")

    result = execute_validated_sql(
        postgres_engine,
        admin,
        SQLValidationResult(
            valid=True,
            sanitized_sql="SELECT pg_sleep(0.2) AS slept FROM departments LIMIT 1",
            referenced_tables=["departments"],
        ),
        options=SQLExecutionOptions(statement_timeout_ms=50),
    )

    assert_failed(result, "database_error")
    assert result.public_error == QUERY_EXECUTION_PUBLIC_ERROR
    assert "pg_sleep" not in result.public_error
    assert "statement timeout" not in result.public_error.lower()


def test_row_limit_and_truncation_behavior(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")
        validation = validate_for_user(
            session,
            admin,
            "SELECT id, name FROM departments ORDER BY name LIMIT 10",
        )

    result = execute_validated_sql(
        postgres_engine,
        admin,
        validation,
        options=SQLExecutionOptions(row_limit=2),
    )

    assert_success(result)
    assert result.row_count == 2
    assert result.truncated is True
    assert len(result.rows) == 2
    assert result.execution_metadata["row_limit"] == 2


def test_database_errors_are_sanitized(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session:
        admin = access_context_for(session, "demo.admin@queryops.local")

    result = execute_validated_sql(
        postgres_engine,
        admin,
        SQLValidationResult(
            valid=True,
            sanitized_sql="SELECT missing_column FROM departments LIMIT 1",
            referenced_tables=["departments"],
        ),
    )

    assert_failed(result, "database_error")
    assert result.public_error == QUERY_EXECUTION_PUBLIC_ERROR
    assert "missing_column" not in result.public_error
    assert "departments" not in result.public_error


def assert_success(result: SQLExecutionResult) -> None:
    assert result.status == "succeeded"
    assert result.error_code is None
    assert result.public_error is None
    assert result.duration_ms >= 0
    assert result.columns


def assert_failed(result: SQLExecutionResult, error_code: str) -> None:
    assert result.status == "failed"
    assert result.error_code == error_code
    assert result.public_error
    assert result.columns == []
    assert result.rows == []
    assert result.row_count == 0


def global_rls_context() -> RLSContext:
    return RLSContext(
        user_id=uuid.uuid4(),
        role="admin",
        scope_type="global",
        scope_keys=tuple(),
        has_global_scope=True,
    )


class FakeValidationResult:
    valid = True
    referenced_columns: dict[str, list[str]] = {}
    error_code = None
    reason = None
    public_error = None

    def __init__(
        self,
        *,
        sanitized_sql: str,
        raw_sql: str,
        referenced_tables: list[str],
    ) -> None:
        self.sanitized_sql = sanitized_sql
        self.raw_sql = raw_sql
        self.referenced_tables = referenced_tables


def validate_for_user(
    session: Session,
    access_context: UserAccessContext,
    sql: str,
) -> SQLValidationResult:
    schema_context = build_schema_context(session, access_context)
    validation = validate_sql(sql, schema_context)
    assert validation.valid is True, validation
    return validation


def access_context_for(session: Session, email: str) -> UserAccessContext:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return build_user_access_context(user, session)


def department_id(session: Session, name: str) -> Any:
    department_id_value = session.scalar(
        select(Department.id).where(Department.name == name)
    )
    assert department_id_value is not None
    return department_id_value


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = postgres_database_url()
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL SQL executor tests require a PostgreSQL DATABASE_URL.")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    run_alembic_upgrade(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, profile_name="small", reset=True)
        session.commit()

    try:
        yield engine
    finally:
        engine.dispose()


def postgres_database_url() -> str:
    return (
        os.environ.get("POSTGRES_TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or LOCAL_POSTGRES_URL
    )


def run_alembic_upgrade(database_url: str) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))

    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(alembic_config, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
