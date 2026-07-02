from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.core.rls import RLSContext, set_rls_context
from app.query_engine.runtime_role import (
    QUERY_RUNTIME_ROLE,
    QUERY_RUNTIME_TABLES,
    set_query_runtime_role,
)


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"
RLS_PROTECTED_TABLE = "security_events"
NON_QUERYABLE_TABLE = "it_audit_events"


@dataclass(frozen=True)
class RuntimeRows:
    prefix: str
    finance_department_id: uuid.UUID
    sales_department_id: uuid.UUID
    finance_event_id: uuid.UUID
    sales_event_id: uuid.UUID
    global_event_id: uuid.UUID


def test_query_runtime_role_migration_exists() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0006_query_runtime_role.py"
    )

    assert migration_path.exists()
    source = migration_path.read_text()
    assert 'revision: str = "0006_query_runtime_role"' in source
    assert 'down_revision: Union[str, None] = "0005_scope_aware_rls"' in source
    assert QUERY_RUNTIME_ROLE in source
    assert NON_QUERYABLE_TABLE not in QUERY_RUNTIME_TABLES


def test_app_owner_bypass_is_relevant_without_runtime_role(
    postgres_engine: Engine,
    runtime_rows: RuntimeRows,
) -> None:
    with Session(postgres_engine) as session:
        owner_row = session.execute(
            text(
                """
                SELECT
                    current_user AS current_user,
                    pg_get_userbyid(c.relowner) AS owner,
                    c.relrowsecurity,
                    c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = :table_name
                """
            ),
            {"table_name": RLS_PROTECTED_TABLE},
        ).one()
        visible_count = session.execute(
            text(
                """
                SELECT count(*)
                FROM security_events
                WHERE event_type = :event_type
                """
            ),
            {"event_type": runtime_rows.prefix},
        ).scalar_one()

    assert owner_row.owner == owner_row.current_user
    assert owner_row.relrowsecurity is True
    assert owner_row.relforcerowsecurity is False
    assert visible_count == 3


def test_runtime_role_is_non_owner_read_only_and_has_expected_grants(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.connect() as connection:
        role = connection.execute(
            text(
                """
                SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
                FROM pg_roles
                WHERE rolname = :role_name
                """
            ),
            {"role_name": QUERY_RUNTIME_ROLE},
        ).one()
        table_rows = connection.execute(
            text(
                """
                SELECT c.relname, pg_get_userbyid(c.relowner) AS owner
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
                  AND c.relname = ANY(:table_names)
                ORDER BY c.relname
                """
            ),
            {"table_names": sorted(QUERY_RUNTIME_TABLES)},
        ).all()
        has_audit_select = connection.execute(
            text(
                "SELECT has_table_privilege(:role_name, :table_name, 'SELECT')"
            ),
            {"role_name": QUERY_RUNTIME_ROLE, "table_name": NON_QUERYABLE_TABLE},
        ).scalar_one()
        privileges = {
            privilege
            for privilege in connection.execute(
                text(
                    """
                    SELECT privilege_type
                    FROM information_schema.role_table_grants
                    WHERE grantee = :role_name
                      AND table_schema = 'public'
                      AND table_name = :table_name
                    """
                ),
                {"role_name": QUERY_RUNTIME_ROLE, "table_name": RLS_PROTECTED_TABLE},
            ).scalars()
        }

    assert role.rolcanlogin is False
    assert role.rolsuper is False
    assert role.rolbypassrls is False
    assert role.rolcreatedb is False
    assert role.rolcreaterole is False
    assert {row.relname for row in table_rows} == set(QUERY_RUNTIME_TABLES)
    assert all(row.owner != QUERY_RUNTIME_ROLE for row in table_rows)
    assert has_audit_select is False
    assert privileges == {"SELECT"}


def test_runtime_role_with_manager_context_enforces_department_rls(
    postgres_engine: Engine,
    runtime_rows: RuntimeRows,
) -> None:
    visible_ids = visible_security_event_ids(
        postgres_engine,
        RLSContext(
            user_id=uuid.uuid4(),
            role="manager",
            scope_type="department",
            scope_keys=(str(runtime_rows.finance_department_id),),
            has_global_scope=False,
        ),
        runtime_rows.prefix,
    )

    assert visible_ids == {str(runtime_rows.finance_event_id)}


def test_runtime_role_with_admin_global_context_sees_allowed_global_data(
    postgres_engine: Engine,
    runtime_rows: RuntimeRows,
) -> None:
    visible_ids = visible_security_event_ids(
        postgres_engine,
        RLSContext(
            user_id=uuid.uuid4(),
            role="admin",
            scope_type="global",
            scope_keys=tuple(),
            has_global_scope=True,
        ),
        runtime_rows.prefix,
    )

    assert visible_ids == {
        str(runtime_rows.finance_event_id),
        str(runtime_rows.sales_event_id),
        str(runtime_rows.global_event_id),
    }


@pytest.mark.parametrize(
    ("sql", "parameters"),
    [
        (
            """
            INSERT INTO departments (id, name, description)
            VALUES (:id, :name, 'runtime role write test')
            """,
            {"id": uuid.uuid4(), "name": f"runtime-write-{uuid.uuid4()}"},
        ),
        (
            """
            UPDATE departments
            SET description = 'runtime role write test'
            WHERE name = :name
            """,
            {"name": f"runtime-write-{uuid.uuid4()}"},
        ),
        (
            """
            DELETE FROM departments
            WHERE name = :name
            """,
            {"name": f"runtime-write-{uuid.uuid4()}"},
        ),
    ],
)
def test_runtime_role_cannot_insert_update_or_delete(
    postgres_engine: Engine,
    sql: str,
    parameters: dict[str, object],
) -> None:
    with pytest.raises(DBAPIError):
        with Session(postgres_engine) as session:
            with session.begin():
                set_query_runtime_role(session)
                set_rls_context(session, global_rls_context())
                session.execute(text(sql), parameters)


def test_runtime_role_cannot_select_non_queryable_audit_events(
    postgres_engine: Engine,
) -> None:
    with pytest.raises(DBAPIError):
        with Session(postgres_engine) as session:
            with session.begin():
                set_query_runtime_role(session)
                set_rls_context(session, global_rls_context())
                session.execute(text("SELECT count(*) FROM it_audit_events")).scalar_one()


def visible_security_event_ids(
    engine: Engine,
    rls_context: RLSContext,
    event_type: str,
) -> set[str]:
    with Session(engine) as session:
        with session.begin():
            set_query_runtime_role(session)
            set_rls_context(session, rls_context)
            current_user = session.execute(text("SELECT current_user")).scalar_one()
            rows = session.execute(
                text(
                    """
                    SELECT id
                    FROM security_events
                    WHERE event_type = :event_type
                    ORDER BY id
                    """
                ),
                {"event_type": event_type},
            ).scalars()
            assert current_user == QUERY_RUNTIME_ROLE
            return {str(row) for row in rows}


def global_rls_context() -> RLSContext:
    return RLSContext(
        user_id=uuid.uuid4(),
        role="admin",
        scope_type="global",
        scope_keys=tuple(),
        has_global_scope=True,
    )


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = postgres_database_url()
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL runtime role tests require a PostgreSQL DATABASE_URL.")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    run_alembic_upgrade(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def runtime_rows(postgres_engine: Engine) -> Generator[RuntimeRows, None, None]:
    rows = RuntimeRows(
        prefix=f"runtime_role_{uuid.uuid4().hex[:8]}",
        finance_department_id=uuid.uuid4(),
        sales_department_id=uuid.uuid4(),
        finance_event_id=uuid.uuid4(),
        sales_event_id=uuid.uuid4(),
        global_event_id=uuid.uuid4(),
    )
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO departments (id, name, description)
                VALUES
                    (:finance_department_id, :finance_name, 'Runtime role test'),
                    (:sales_department_id, :sales_name, 'Runtime role test')
                """
            ),
            {
                "finance_department_id": rows.finance_department_id,
                "finance_name": f"{rows.prefix} Finance",
                "sales_department_id": rows.sales_department_id,
                "sales_name": f"{rows.prefix} Sales",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO security_events (
                    id,
                    department_id,
                    event_type,
                    severity,
                    description,
                    occurred_at,
                    status
                )
                VALUES
                    (
                        :finance_event_id,
                        :finance_department_id,
                        :event_type,
                        'high',
                        'Finance runtime role test event',
                        :occurred_at,
                        'open'
                    ),
                    (
                        :sales_event_id,
                        :sales_department_id,
                        :event_type,
                        'high',
                        'Sales runtime role test event',
                        :occurred_at,
                        'open'
                    ),
                    (
                        :global_event_id,
                        NULL,
                        :event_type,
                        'high',
                        'Null department runtime role test event',
                        :occurred_at,
                        'open'
                    )
                """
            ),
            {
                "finance_event_id": rows.finance_event_id,
                "sales_event_id": rows.sales_event_id,
                "global_event_id": rows.global_event_id,
                "finance_department_id": rows.finance_department_id,
                "sales_department_id": rows.sales_department_id,
                "event_type": rows.prefix,
                "occurred_at": datetime.now(UTC),
            },
        )

    try:
        yield rows
    finally:
        cleanup_runtime_rows(postgres_engine, rows)


def cleanup_runtime_rows(engine: Engine, rows: RuntimeRows) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM security_events WHERE event_type = :event_type"),
            {"event_type": rows.prefix},
        )
        connection.execute(
            text(
                """
                DELETE FROM departments
                WHERE id IN (:finance_department_id, :sales_department_id)
                """
            ),
            {
                "finance_department_id": rows.finance_department_id,
                "sales_department_id": rows.sales_department_id,
            },
        )


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
