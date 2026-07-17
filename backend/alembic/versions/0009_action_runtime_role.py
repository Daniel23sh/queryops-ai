"""action runtime role

Revision ID: 0009_action_runtime_role
Revises: 0008_action_engine_foundation
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0009_action_runtime_role"
down_revision: Union[str, None] = "0008_action_engine_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTION_RUNTIME_ROLE = "queryops_action_runtime"
LICENSE_UPDATE_POLICY = "qo_license_assignments_action_scope_update"
AUDIT_INSERT_POLICY = "qo_it_audit_events_action_scope_insert"
SCOPE_EXPRESSION = """
(
    current_setting('app.has_global_scope', true) = 'true'
    OR (
        current_setting('app.current_scope_type', true) = 'department'
        AND department_id IS NOT NULL
        AND department_id::text = ANY(
            string_to_array(
                coalesce(current_setting('app.current_scope_keys', true), ''),
                ','
            )
        )
    )
)
"""


def upgrade() -> None:
    if not _is_postgresql():
        return

    app_role = _current_database_role()
    runtime_role = _quote_identifier(ACTION_RUNTIME_ROLE)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = '{ACTION_RUNTIME_ROLE}'
            ) THEN
                CREATE ROLE {runtime_role}
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
        ALTER ROLE {runtime_role}
            NOLOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOBYPASSRLS
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {runtime_role}")
    op.execute(
        "GRANT SELECT ON license_assignments, directory_users, licenses "
        f"TO {runtime_role}"
    )
    op.execute(
        "GRANT UPDATE (status, reclaimed_at, reclaimed_by_app_user_id) "
        f"ON license_assignments TO {runtime_role}"
    )
    op.execute(f"GRANT INSERT ON it_audit_events TO {runtime_role}")

    if app_role and app_role != ACTION_RUNTIME_ROLE:
        op.execute(f"GRANT {runtime_role} TO {_quote_identifier(app_role)}")

    op.execute(
        f"""
        CREATE POLICY {_quote_identifier(LICENSE_UPDATE_POLICY)}
        ON license_assignments
        FOR UPDATE
        USING {SCOPE_EXPRESSION}
        WITH CHECK {SCOPE_EXPRESSION}
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_quote_identifier(AUDIT_INSERT_POLICY)}
        ON it_audit_events
        FOR INSERT
        WITH CHECK {SCOPE_EXPRESSION}
        """
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    app_role = _current_database_role()
    runtime_role = _quote_identifier(ACTION_RUNTIME_ROLE)
    op.execute(
        f"DROP POLICY IF EXISTS {_quote_identifier(AUDIT_INSERT_POLICY)} "
        "ON it_audit_events"
    )
    op.execute(
        f"DROP POLICY IF EXISTS {_quote_identifier(LICENSE_UPDATE_POLICY)} "
        "ON license_assignments"
    )
    if app_role and app_role != ACTION_RUNTIME_ROLE:
        op.execute(f"REVOKE {runtime_role} FROM {_quote_identifier(app_role)}")
    op.execute(f"REVOKE INSERT ON it_audit_events FROM {runtime_role}")
    op.execute(
        "REVOKE UPDATE (status, reclaimed_at, reclaimed_by_app_user_id) "
        f"ON license_assignments FROM {runtime_role}"
    )
    op.execute(
        "REVOKE SELECT ON license_assignments, directory_users, licenses "
        f"FROM {runtime_role}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {runtime_role}")
    op.execute(f"DROP ROLE IF EXISTS {runtime_role}")


def _current_database_role() -> str | None:
    return op.get_bind().execute(sa.text("SELECT current_user")).scalar_one_or_none()


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
