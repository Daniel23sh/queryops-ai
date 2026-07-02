"""query runtime role

Revision ID: 0006_query_runtime_role
Revises: 0005_scope_aware_rls
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006_query_runtime_role"
down_revision: Union[str, None] = "0005_scope_aware_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


QUERY_RUNTIME_ROLE = "queryops_query_runtime"
QUERY_RUNTIME_TABLES = (
    "departments",
    "devices",
    "directory_users",
    "groups",
    "license_assignments",
    "licenses",
    "login_events",
    "security_events",
    "software_installs",
    "support_tickets",
    "user_group_memberships",
)


def upgrade() -> None:
    if not _is_postgresql():
        return

    app_role = _current_database_role()
    quoted_runtime_role = _quote_identifier(QUERY_RUNTIME_ROLE)
    quoted_tables = ", ".join(_quote_identifier(table) for table in QUERY_RUNTIME_TABLES)

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = '{QUERY_RUNTIME_ROLE}'
            ) THEN
                CREATE ROLE {quoted_runtime_role}
                    NOLOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOINHERIT
                    NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    op.execute(
        f"""
        ALTER ROLE {quoted_runtime_role}
            NOLOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOBYPASSRLS
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {quoted_runtime_role}")
    op.execute(f"GRANT SELECT ON {quoted_tables} TO {quoted_runtime_role}")
    op.execute(
        f"REVOKE ALL PRIVILEGES ON {_quote_identifier('it_audit_events')} "
        f"FROM {quoted_runtime_role}"
    )

    if app_role and app_role != QUERY_RUNTIME_ROLE:
        op.execute(
            f"GRANT {quoted_runtime_role} TO {_quote_identifier(app_role)}"
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    app_role = _current_database_role()
    quoted_runtime_role = _quote_identifier(QUERY_RUNTIME_ROLE)
    quoted_tables = ", ".join(_quote_identifier(table) for table in QUERY_RUNTIME_TABLES)

    if app_role and app_role != QUERY_RUNTIME_ROLE:
        op.execute(
            f"REVOKE {quoted_runtime_role} FROM {_quote_identifier(app_role)}"
        )
    op.execute(f"REVOKE SELECT ON {quoted_tables} FROM {quoted_runtime_role}")
    op.execute(
        f"REVOKE ALL PRIVILEGES ON {_quote_identifier('it_audit_events')} "
        f"FROM {quoted_runtime_role}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {quoted_runtime_role}")
    op.execute(f"DROP ROLE IF EXISTS {quoted_runtime_role}")


def _current_database_role() -> str | None:
    bind = op.get_bind()
    return bind.execute(sa.text("SELECT current_user")).scalar_one_or_none()


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
