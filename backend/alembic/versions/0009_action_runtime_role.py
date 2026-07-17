"""action runtime role

Revision ID: 0009_action_runtime_role
Revises: 0008_action_engine_foundation
Create Date: 2026-07-17
"""

import os
from typing import Sequence, Union

from alembic import op


revision: str = "0009_action_runtime_role"
down_revision: Union[str, None] = "0008_action_engine_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTION_RUNTIME_ROLE = "queryops_action_runtime"
APPLICATION_LOGIN_ROLE = os.getenv("QUERYOPS_APP_DATABASE_ROLE", "queryops")
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
AUDIT_SCOPE_EXPRESSION = f"""
(
    {SCOPE_EXPRESSION}
    AND actor_app_user_id IS NOT NULL
    AND actor_app_user_id::text =
        current_setting('app.current_user_id', true)
)
"""


def upgrade() -> None:
    if not _is_postgresql():
        return

    runtime_role = _quote_identifier(ACTION_RUNTIME_ROLE)
    app_role = _quote_identifier(APPLICATION_LOGIN_ROLE)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = '{ACTION_RUNTIME_ROLE}'
            ) THEN
                RAISE EXCEPTION
                    'Role {ACTION_RUNTIME_ROLE} already exists; refusing to modify it';
            ELSE
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

    op.execute(
        f"GRANT {runtime_role} TO {app_role} WITH INHERIT FALSE, SET TRUE"
    )

    op.execute(
        f"""
        CREATE POLICY {_quote_identifier(LICENSE_UPDATE_POLICY)}
        ON license_assignments
        FOR UPDATE
        TO {runtime_role}
        USING {SCOPE_EXPRESSION}
        WITH CHECK {SCOPE_EXPRESSION}
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_quote_identifier(AUDIT_INSERT_POLICY)}
        ON it_audit_events
        FOR INSERT
        TO {runtime_role}
        WITH CHECK {AUDIT_SCOPE_EXPRESSION}
        """
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    runtime_role = _quote_identifier(ACTION_RUNTIME_ROLE)
    app_role = _quote_identifier(APPLICATION_LOGIN_ROLE)
    op.execute(
        f"DROP POLICY IF EXISTS {_quote_identifier(AUDIT_INSERT_POLICY)} "
        "ON it_audit_events"
    )
    op.execute(
        f"DROP POLICY IF EXISTS {_quote_identifier(LICENSE_UPDATE_POLICY)} "
        "ON license_assignments"
    )
    op.execute(f"REVOKE {runtime_role} FROM {app_role}")
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


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
