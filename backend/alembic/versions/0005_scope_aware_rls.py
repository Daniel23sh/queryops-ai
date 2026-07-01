"""scope aware rls

Revision ID: 0005_scope_aware_rls
Revises: 0004_access_context_foundation
Create Date: 2026-07-01
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0005_scope_aware_rls"
down_revision: Union[str, None] = "0004_access_context_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PROTECTED_TABLES = (
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
)

POLICY_EXPRESSION = """
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

    for table_name in PROTECTED_TABLES:
        quoted_table = _quote_identifier(table_name)
        policy_name = _policy_name(table_name)
        quoted_policy = _quote_identifier(policy_name)
        op.execute(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {quoted_policy}
            ON {quoted_table}
            FOR SELECT
            USING {POLICY_EXPRESSION}
            """
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    for table_name in PROTECTED_TABLES:
        quoted_table = _quote_identifier(table_name)
        quoted_policy = _quote_identifier(_policy_name(table_name))
        op.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table}")
        op.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY")


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _policy_name(table_name: str) -> str:
    return f"qo_{table_name}_department_scope_select"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
