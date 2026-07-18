"""extend action runtime for inactive-user disablement

Revision ID: 0010_disable_inactive_user
Revises: 0009_action_runtime_role
Create Date: 2026-07-18
"""

import os
from typing import Sequence, Union

from alembic import op


revision: str = "0010_disable_inactive_user"
down_revision: Union[str, None] = "0009_action_runtime_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTION_RUNTIME_ROLE = "queryops_action_runtime"
APPLICATION_LOGIN_ROLE = os.getenv("QUERYOPS_APP_DATABASE_ROLE", "queryops")
DIRECTORY_UPDATE_POLICY = "qo_directory_users_action_scope_update"
LOGIN_SELECT_POLICY = "qo_login_events_action_user_scope_select"
MEMBERSHIP_SELECT_POLICY = "qo_user_group_memberships_action_user_scope_select"
GROUP_SELECT_POLICY = "qo_groups_action_membership_scope_select"
SECURITY_EVENT_SELECT_POLICY = "qo_security_events_action_user_scope_select"

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

USER_SCOPE_EXPRESSION = """
(
    user_id IS NOT NULL
    AND EXISTS (
        SELECT 1
        FROM directory_users action_user
        WHERE action_user.id = user_id
    )
)
"""

GROUP_SCOPE_EXPRESSION = """
(
    EXISTS (
        SELECT 1
        FROM user_group_memberships action_membership
        WHERE action_membership.group_id = groups.id
    )
)
"""


def upgrade() -> None:
    if not _is_postgresql():
        return

    runtime_role = _quote_identifier(ACTION_RUNTIME_ROLE)
    app_role_literal = _quote_literal(APPLICATION_LOGIN_ROLE)
    op.execute(
        f"""
        DO $$
        DECLARE
            role_is_safe boolean;
            membership_count integer;
            unexpected_membership_count integer;
            unexpected_table_grants integer;
            unexpected_column_grants integer;
            unexpected_usage_grants integer;
            owned_objects integer;
        BEGIN
            SELECT
                NOT rolcanlogin
                AND NOT rolsuper
                AND NOT rolcreatedb
                AND NOT rolcreaterole
                AND NOT rolinherit
                AND NOT rolbypassrls
                AND NOT rolreplication
            INTO role_is_safe
            FROM pg_roles
            WHERE rolname = '{ACTION_RUNTIME_ROLE}';

            IF role_is_safe IS DISTINCT FROM TRUE THEN
                RAISE EXCEPTION
                    'Role {ACTION_RUNTIME_ROLE} is missing or unsafe; refusing to modify it';
            END IF;

            SELECT count(*)
            INTO membership_count
            FROM pg_auth_members membership
            JOIN pg_roles granted_role ON granted_role.oid = membership.roleid
            JOIN pg_roles member_role ON member_role.oid = membership.member
            WHERE granted_role.rolname = '{ACTION_RUNTIME_ROLE}'
                AND member_role.rolname = {app_role_literal}
                AND membership.inherit_option = false
                AND membership.set_option = true;

            SELECT count(*)
            INTO unexpected_membership_count
            FROM pg_auth_members membership
            JOIN pg_roles granted_role ON granted_role.oid = membership.roleid
            JOIN pg_roles member_role ON member_role.oid = membership.member
            WHERE (
                granted_role.rolname = '{ACTION_RUNTIME_ROLE}'
                AND NOT (
                    member_role.rolname = {app_role_literal}
                    AND membership.inherit_option = false
                    AND membership.set_option = true
                )
            ) OR member_role.rolname = '{ACTION_RUNTIME_ROLE}';

            IF membership_count != 1 OR unexpected_membership_count != 0 THEN
                RAISE EXCEPTION
                    'Role {ACTION_RUNTIME_ROLE} has unknown membership; refusing to modify it';
            END IF;

            SELECT count(*)
            INTO unexpected_table_grants
            FROM information_schema.role_table_grants grants
            WHERE grants.grantee = '{ACTION_RUNTIME_ROLE}'
                AND NOT (
                    (grants.table_name IN (
                        'directory_users', 'license_assignments', 'licenses'
                    ) AND grants.privilege_type = 'SELECT')
                    OR (
                        grants.table_name = 'it_audit_events'
                        AND grants.privilege_type = 'INSERT'
                    )
                );

            SELECT count(*)
            INTO unexpected_column_grants
            FROM information_schema.role_column_grants grants
            WHERE grants.grantee = '{ACTION_RUNTIME_ROLE}'
                AND NOT (
                    (
                        grants.privilege_type = 'SELECT'
                        AND grants.table_name IN (
                            'directory_users', 'license_assignments', 'licenses'
                        )
                    )
                    OR (
                        grants.privilege_type = 'UPDATE'
                        AND grants.table_name = 'license_assignments'
                        AND grants.column_name IN (
                            'status', 'reclaimed_at', 'reclaimed_by_app_user_id'
                        )
                    )
                    OR (
                        grants.privilege_type = 'INSERT'
                        AND grants.table_name = 'it_audit_events'
                    )
                );

            SELECT count(*)
            INTO unexpected_usage_grants
            FROM information_schema.role_usage_grants grants
            WHERE grants.grantee = '{ACTION_RUNTIME_ROLE}';

            SELECT
                (SELECT count(*) FROM pg_database database
                    JOIN pg_roles owner ON owner.oid = database.datdba
                    WHERE owner.rolname = '{ACTION_RUNTIME_ROLE}')
                + (SELECT count(*) FROM pg_namespace namespace
                    JOIN pg_roles owner ON owner.oid = namespace.nspowner
                    WHERE owner.rolname = '{ACTION_RUNTIME_ROLE}')
                + (SELECT count(*) FROM pg_class relation
                    JOIN pg_roles owner ON owner.oid = relation.relowner
                    WHERE owner.rolname = '{ACTION_RUNTIME_ROLE}')
                + (SELECT count(*) FROM pg_proc procedure
                    JOIN pg_roles owner ON owner.oid = procedure.proowner
                    WHERE owner.rolname = '{ACTION_RUNTIME_ROLE}')
            INTO owned_objects;

            IF unexpected_table_grants != 0
                OR unexpected_column_grants != 0
                OR unexpected_usage_grants != 0
                OR owned_objects != 0
                OR NOT has_schema_privilege(
                    '{ACTION_RUNTIME_ROLE}', 'public', 'USAGE'
                )
                OR has_schema_privilege(
                    '{ACTION_RUNTIME_ROLE}', 'public', 'CREATE'
                )
                OR NOT has_table_privilege(
                    '{ACTION_RUNTIME_ROLE}', 'license_assignments', 'SELECT'
                )
                OR NOT has_table_privilege(
                    '{ACTION_RUNTIME_ROLE}', 'directory_users', 'SELECT'
                )
                OR NOT has_table_privilege(
                    '{ACTION_RUNTIME_ROLE}', 'licenses', 'SELECT'
                )
                OR NOT has_table_privilege(
                    '{ACTION_RUNTIME_ROLE}', 'it_audit_events', 'INSERT'
                )
                OR NOT has_column_privilege(
                    '{ACTION_RUNTIME_ROLE}', 'license_assignments', 'status', 'UPDATE'
                )
                OR NOT has_column_privilege(
                    '{ACTION_RUNTIME_ROLE}', 'license_assignments', 'reclaimed_at', 'UPDATE'
                )
                OR NOT has_column_privilege(
                    '{ACTION_RUNTIME_ROLE}', 'license_assignments',
                    'reclaimed_by_app_user_id', 'UPDATE'
                )
            THEN
                RAISE EXCEPTION
                    'Role {ACTION_RUNTIME_ROLE} has unknown grants; refusing to modify it';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        "GRANT SELECT (user_id, event_type, occurred_at) "
        f"ON login_events TO {runtime_role}"
    )
    op.execute(
        f"GRANT SELECT (id, is_privileged) ON groups TO {runtime_role}"
    )
    op.execute(
        "GRANT SELECT (user_id, group_id) "
        f"ON user_group_memberships TO {runtime_role}"
    )
    op.execute(
        "GRANT SELECT (id, user_id, severity, status) "
        f"ON security_events TO {runtime_role}"
    )
    op.execute(
        "GRANT UPDATE (account_status, updated_at) "
        f"ON directory_users TO {runtime_role}"
    )
    op.execute(
        f"""
        CREATE POLICY {_quote_identifier(DIRECTORY_UPDATE_POLICY)}
        ON directory_users
        FOR UPDATE
        TO {runtime_role}
        USING (
            {SCOPE_EXPRESSION}
            AND account_type = 'human'
            AND account_status = 'active'
        )
        WITH CHECK (
            {SCOPE_EXPRESSION}
            AND account_type = 'human'
            AND account_status = 'disabled'
        )
        """
    )
    _create_select_policy(LOGIN_SELECT_POLICY, "login_events", USER_SCOPE_EXPRESSION)
    _create_select_policy(
        MEMBERSHIP_SELECT_POLICY,
        "user_group_memberships",
        USER_SCOPE_EXPRESSION,
    )
    _create_select_policy(GROUP_SELECT_POLICY, "groups", GROUP_SCOPE_EXPRESSION)
    _create_select_policy(
        SECURITY_EVENT_SELECT_POLICY,
        "security_events",
        USER_SCOPE_EXPRESSION,
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    runtime_role = _quote_identifier(ACTION_RUNTIME_ROLE)
    for policy_name, table_name in (
        (SECURITY_EVENT_SELECT_POLICY, "security_events"),
        (GROUP_SELECT_POLICY, "groups"),
        (MEMBERSHIP_SELECT_POLICY, "user_group_memberships"),
        (LOGIN_SELECT_POLICY, "login_events"),
        (DIRECTORY_UPDATE_POLICY, "directory_users"),
    ):
        op.execute(
            f"DROP POLICY IF EXISTS {_quote_identifier(policy_name)} "
            f"ON {_quote_identifier(table_name)}"
        )
    op.execute(
        "REVOKE UPDATE (account_status, updated_at) "
        f"ON directory_users FROM {runtime_role}"
    )
    op.execute(
        "REVOKE SELECT (id, user_id, severity, status) "
        f"ON security_events FROM {runtime_role}"
    )
    op.execute(
        "REVOKE SELECT (user_id, group_id) "
        f"ON user_group_memberships FROM {runtime_role}"
    )
    op.execute(
        f"REVOKE SELECT (id, is_privileged) ON groups FROM {runtime_role}"
    )
    op.execute(
        "REVOKE SELECT (user_id, event_type, occurred_at) "
        f"ON login_events FROM {runtime_role}"
    )


def _create_select_policy(policy_name: str, table_name: str, expression: str) -> None:
    op.execute(
        f"""
        CREATE POLICY {_quote_identifier(policy_name)}
        ON {_quote_identifier(table_name)}
        FOR SELECT
        TO {_quote_identifier(ACTION_RUNTIME_ROLE)}
        USING {expression}
        """
    )


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
