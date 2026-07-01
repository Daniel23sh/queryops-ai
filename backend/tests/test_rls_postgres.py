from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.rls import RLSContext, set_rls_context


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"
RLS_TEST_ROLE = "queryops_rls_test_reader"
PROTECTED_TABLES = {
    "directory_users",
    "login_events",
    "license_assignments",
    "devices",
    "software_installs",
    "support_tickets",
    "groups",
    "user_group_memberships",
    "security_events",
    "it_audit_events",
}


class RLSRows(NamedTuple):
    prefix: str
    finance_department_id: uuid.UUID
    sales_department_id: uuid.UUID
    finance_security_event_id: uuid.UUID
    sales_security_event_id: uuid.UUID
    global_security_event_id: uuid.UUID
    finance_group_id: uuid.UUID
    sales_group_id: uuid.UUID
    global_group_id: uuid.UUID


def test_scope_aware_rls_migration_exists() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0005_scope_aware_rls.py"
    )

    assert migration_path.exists()
    source = migration_path.read_text()
    assert 'revision: str = "0005_scope_aware_rls"' in source
    assert 'down_revision: Union[str, None] = "0004_access_context_foundation"' in source


def test_rls_is_enabled_and_policies_exist_on_domain_tables(
    postgres_engine: Engine,
    rls_reader_role: str,
) -> None:
    with postgres_engine.connect() as connection:
        rls_rows = connection.execute(
            text(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = ANY(:table_names)
                  AND c.relrowsecurity IS TRUE
                """
            ),
            {"table_names": sorted(PROTECTED_TABLES)},
        ).scalars()
        policy_rows = connection.execute(
            text(
                """
                SELECT tablename, policyname
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = ANY(:table_names)
                """
            ),
            {"table_names": sorted(PROTECTED_TABLES)},
        ).all()

    assert set(rls_rows) == PROTECTED_TABLES
    assert {
        (row.tablename, row.policyname) for row in policy_rows
    } == {
        (table_name, f"qo_{table_name}_department_scope_select")
        for table_name in PROTECTED_TABLES
    }
    assert rls_reader_role == RLS_TEST_ROLE


def test_global_context_sees_all_scoped_and_null_department_rows(
    postgres_engine: Engine,
    rls_reader_role: str,
    rls_rows: RLSRows,
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
        rls_rows.prefix,
        rls_reader_role,
    )

    assert visible_ids == {
        str(rls_rows.finance_security_event_id),
        str(rls_rows.sales_security_event_id),
        str(rls_rows.global_security_event_id),
    }


def test_finance_department_context_only_sees_finance_rows(
    postgres_engine: Engine,
    rls_reader_role: str,
    rls_rows: RLSRows,
) -> None:
    visible_ids = visible_security_event_ids(
        postgres_engine,
        RLSContext(
            user_id=uuid.uuid4(),
            role="manager",
            scope_type="department",
            scope_keys=(str(rls_rows.finance_department_id),),
            has_global_scope=False,
        ),
        rls_rows.prefix,
        rls_reader_role,
    )

    assert visible_ids == {str(rls_rows.finance_security_event_id)}


def test_sales_department_context_only_sees_sales_rows(
    postgres_engine: Engine,
    rls_reader_role: str,
    rls_rows: RLSRows,
) -> None:
    visible_ids = visible_security_event_ids(
        postgres_engine,
        RLSContext(
            user_id=uuid.uuid4(),
            role="user",
            scope_type="department",
            scope_keys=(str(rls_rows.sales_department_id),),
            has_global_scope=False,
        ),
        rls_rows.prefix,
        rls_reader_role,
    )

    assert visible_ids == {str(rls_rows.sales_security_event_id)}


def test_no_context_sees_no_scoped_rows(
    postgres_engine: Engine,
    rls_reader_role: str,
    rls_rows: RLSRows,
) -> None:
    with Session(postgres_engine) as session:
        with session.begin():
            session.execute(text(f"SET LOCAL ROLE {rls_reader_role}"))
            rows = session.execute(
                text(
                    """
                    SELECT id
                    FROM security_events
                    WHERE event_type = :event_type
                    ORDER BY id
                    """
                ),
                {"event_type": rls_rows.prefix},
            ).scalars()

            assert {str(row) for row in rows} == set()


def test_empty_department_scope_keys_see_no_rows(
    postgres_engine: Engine,
    rls_reader_role: str,
    rls_rows: RLSRows,
) -> None:
    visible_ids = visible_security_event_ids(
        postgres_engine,
        RLSContext(
            user_id=uuid.uuid4(),
            role="manager",
            scope_type="department",
            scope_keys=tuple(),
            has_global_scope=False,
        ),
        rls_rows.prefix,
        rls_reader_role,
    )

    assert visible_ids == set()


def test_malformed_department_scope_keys_see_no_rows(
    postgres_engine: Engine,
    rls_reader_role: str,
    rls_rows: RLSRows,
) -> None:
    visible_ids = visible_security_event_ids(
        postgres_engine,
        RLSContext(
            user_id=uuid.uuid4(),
            role="manager",
            scope_type="department",
            scope_keys=("not-a-department-uuid",),
            has_global_scope=False,
        ),
        rls_rows.prefix,
        rls_reader_role,
    )

    assert visible_ids == set()


def test_global_context_sees_nullable_group_rows_across_departments(
    postgres_engine: Engine,
    rls_reader_role: str,
    rls_rows: RLSRows,
) -> None:
    visible_ids = visible_group_ids(
        postgres_engine,
        RLSContext(
            user_id=uuid.uuid4(),
            role="admin",
            scope_type="global",
            scope_keys=tuple(),
            has_global_scope=True,
        ),
        rls_rows.prefix,
        rls_reader_role,
    )

    assert visible_ids == {
        str(rls_rows.finance_group_id),
        str(rls_rows.sales_group_id),
        str(rls_rows.global_group_id),
    }


def test_department_context_hides_nullable_group_rows_outside_scope(
    postgres_engine: Engine,
    rls_reader_role: str,
    rls_rows: RLSRows,
) -> None:
    visible_ids = visible_group_ids(
        postgres_engine,
        RLSContext(
            user_id=uuid.uuid4(),
            role="manager",
            scope_type="department",
            scope_keys=(str(rls_rows.finance_department_id),),
            has_global_scope=False,
        ),
        rls_rows.prefix,
        rls_reader_role,
    )

    assert visible_ids == {str(rls_rows.finance_group_id)}


def visible_security_event_ids(
    engine: Engine,
    rls_context: RLSContext,
    event_type: str,
    rls_reader_role: str,
) -> set[str]:
    with Session(engine) as session:
        with session.begin():
            set_rls_context(session, rls_context)
            session.execute(text(f"SET LOCAL ROLE {rls_reader_role}"))
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
            return {str(row) for row in rows}


def visible_group_ids(
    engine: Engine,
    rls_context: RLSContext,
    name_prefix: str,
    rls_reader_role: str,
) -> set[str]:
    with Session(engine) as session:
        with session.begin():
            set_rls_context(session, rls_context)
            session.execute(text(f"SET LOCAL ROLE {rls_reader_role}"))
            rows = session.execute(
                text(
                    """
                    SELECT id
                    FROM groups
                    WHERE name LIKE :name_pattern
                    ORDER BY id
                    """
                ),
                {"name_pattern": f"{name_prefix}%"},
            ).scalars()
            return {str(row) for row in rows}


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = postgres_database_url()
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL RLS tests require a PostgreSQL DATABASE_URL.")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    run_alembic_upgrade(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def rls_reader_role(postgres_engine: Engine) -> Generator[str, None, None]:
    try:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_roles WHERE rolname = 'queryops_rls_test_reader'
                        ) THEN
                            CREATE ROLE queryops_rls_test_reader;
                        END IF;
                    END
                    $$;
                    """
                )
            )
            connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {RLS_TEST_ROLE}"))
            connection.execute(
                text(
                    "GRANT SELECT ON "
                    + ", ".join(sorted(PROTECTED_TABLES))
                    + f" TO {RLS_TEST_ROLE}"
                )
            )
    except (OperationalError, ProgrammingError) as exc:
        pytest.skip(f"Could not create non-owner RLS test role: {exc}")

    try:
        yield RLS_TEST_ROLE
    finally:
        cleanup_rls_reader_role(postgres_engine)


@pytest.fixture()
def rls_rows(postgres_engine: Engine) -> Generator[RLSRows, None, None]:
    prefix = f"rls_test_{uuid.uuid4().hex[:8]}"
    rows = RLSRows(
        prefix=prefix,
        finance_department_id=uuid.uuid4(),
        sales_department_id=uuid.uuid4(),
        finance_security_event_id=uuid.uuid4(),
        sales_security_event_id=uuid.uuid4(),
        global_security_event_id=uuid.uuid4(),
        finance_group_id=uuid.uuid4(),
        sales_group_id=uuid.uuid4(),
        global_group_id=uuid.uuid4(),
    )

    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO departments (id, name, description)
                VALUES
                    (:finance_department_id, :finance_name, 'RLS test department'),
                    (:sales_department_id, :sales_name, 'RLS test department')
                """
            ),
            {
                "finance_department_id": rows.finance_department_id,
                "finance_name": f"{prefix} Finance",
                "sales_department_id": rows.sales_department_id,
                "sales_name": f"{prefix} Sales",
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
                        :finance_security_event_id,
                        :finance_department_id,
                        :event_type,
                        'high',
                        'Finance scoped RLS test event',
                        :occurred_at,
                        'open'
                    ),
                    (
                        :sales_security_event_id,
                        :sales_department_id,
                        :event_type,
                        'high',
                        'Sales scoped RLS test event',
                        :occurred_at,
                        'open'
                    ),
                    (
                        :global_security_event_id,
                        NULL,
                        :event_type,
                        'high',
                        'Null department RLS test event',
                        :occurred_at,
                        'open'
                    )
                """
            ),
            {
                "finance_security_event_id": rows.finance_security_event_id,
                "sales_security_event_id": rows.sales_security_event_id,
                "global_security_event_id": rows.global_security_event_id,
                "finance_department_id": rows.finance_department_id,
                "sales_department_id": rows.sales_department_id,
                "event_type": rows.prefix,
                "occurred_at": datetime.now(UTC),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO groups (
                    id,
                    name,
                    description,
                    group_type,
                    department_id,
                    is_privileged,
                    risk_level
                )
                VALUES
                    (
                        :finance_group_id,
                        :finance_group_name,
                        'Finance scoped RLS test group',
                        'security',
                        :finance_department_id,
                        false,
                        'medium'
                    ),
                    (
                        :sales_group_id,
                        :sales_group_name,
                        'Sales scoped RLS test group',
                        'security',
                        :sales_department_id,
                        false,
                        'medium'
                    ),
                    (
                        :global_group_id,
                        :global_group_name,
                        'Null department RLS test group',
                        'security',
                        NULL,
                        false,
                        'medium'
                    )
                """
            ),
            {
                "finance_group_id": rows.finance_group_id,
                "sales_group_id": rows.sales_group_id,
                "global_group_id": rows.global_group_id,
                "finance_group_name": f"{prefix} Finance Group",
                "sales_group_name": f"{prefix} Sales Group",
                "global_group_name": f"{prefix} Global Group",
                "finance_department_id": rows.finance_department_id,
                "sales_department_id": rows.sales_department_id,
            },
        )

    try:
        yield rows
    finally:
        cleanup_rls_rows(postgres_engine, rows)


def cleanup_rls_rows(engine: Engine, rows: RLSRows) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM groups WHERE name LIKE :name_pattern"),
            {"name_pattern": f"{rows.prefix}%"},
        )
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


def cleanup_rls_reader_role(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "REVOKE SELECT ON "
                + ", ".join(sorted(PROTECTED_TABLES))
                + f" FROM {RLS_TEST_ROLE}"
            )
        )
        connection.execute(text(f"REVOKE USAGE ON SCHEMA public FROM {RLS_TEST_ROLE}"))
        connection.execute(text(f"DROP ROLE IF EXISTS {RLS_TEST_ROLE}"))


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
