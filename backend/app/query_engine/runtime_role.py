from __future__ import annotations

from typing import Protocol

from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause


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


class RuntimeRoleExecutable(Protocol):
    def execute(
        self,
        statement: TextClause,
        parameters: dict[str, str] | None = None,
    ) -> object:
        ...


def set_query_runtime_role(db: RuntimeRoleExecutable) -> None:
    """Constrain the current transaction to the read-only query runtime role.

    `SET LOCAL ROLE` only lasts for the active transaction. Future query
    execution should call this before running validated SQL so generated reads
    do not execute as the app/table-owner role and bypass PostgreSQL RLS.
    """

    db.execute(text(f"SET LOCAL ROLE {_quote_identifier(QUERY_RUNTIME_ROLE)}"))


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
