from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

from app.auth.access_context import UserAccessContext


@dataclass(frozen=True)
class RLSContext:
    user_id: uuid.UUID
    role: str | None
    scope_type: str
    scope_keys: tuple[str, ...]
    has_global_scope: bool

    @property
    def scope_keys_setting(self) -> str:
        return ",".join(self.scope_keys)

    @property
    def has_global_scope_setting(self) -> str:
        return "true" if self.has_global_scope else "false"


class RLSExecutable(Protocol):
    def execute(
        self,
        statement: TextClause,
        parameters: dict[str, str] | None = None,
    ) -> object:
        ...


def build_rls_context(access_context: UserAccessContext) -> RLSContext:
    if access_context.has_global_scope:
        return RLSContext(
            user_id=access_context.user_id,
            role=access_context.role,
            scope_type="global",
            scope_keys=tuple(),
            has_global_scope=True,
        )

    department_scope_keys = tuple(
        dict.fromkeys(
            str(scope.department_id)
            for scope in access_context.scopes
            if scope.type == "department" and scope.department_id is not None
        )
    )
    if department_scope_keys:
        return RLSContext(
            user_id=access_context.user_id,
            role=access_context.role,
            scope_type="department",
            scope_keys=department_scope_keys,
            has_global_scope=False,
        )

    return RLSContext(
        user_id=access_context.user_id,
        role=access_context.role,
        scope_type="none",
        scope_keys=tuple(),
        has_global_scope=False,
    )


def set_rls_context(db: RLSExecutable, rls_context: RLSContext) -> None:
    """Set PostgreSQL RLS runtime context for the current transaction.

    `SET LOCAL` only lasts for the active transaction. Call this after a
    transaction begins and before scoped reads. In V1, `current_scope_keys`
    contains department UUID strings for department-scoped IT Operations tables,
    even though `access_scopes.scope_key` remains human-readable. If no context
    is set, or this context has no usable scope keys, RLS policies deny by
    default unless `app.has_global_scope` is true.
    """

    settings = (
        ("app.current_user_id", str(rls_context.user_id)),
        ("app.current_role", rls_context.role or ""),
        ("app.current_scope_type", rls_context.scope_type),
        ("app.current_scope_keys", rls_context.scope_keys_setting),
        ("app.has_global_scope", rls_context.has_global_scope_setting),
    )
    for setting_name, value in settings:
        _set_local(db, setting_name, value)


def _set_local(db: RLSExecutable, setting_name: str, value: str) -> None:
    allowed_settings = {
        "app.current_user_id",
        "app.current_role",
        "app.current_scope_type",
        "app.current_scope_keys",
        "app.has_global_scope",
    }
    if setting_name not in allowed_settings:
        raise ValueError(f"Unsupported RLS setting: {setting_name}")

    # set_config(..., true) is PostgreSQL's bind-parameter-safe equivalent of
    # SET LOCAL for custom GUCs.
    db.execute(
        text("SELECT set_config(:setting_name, :value, true)"),
        {"setting_name": setting_name, "value": value},
    )
