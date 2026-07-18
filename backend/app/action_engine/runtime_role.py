from __future__ import annotations

from typing import Protocol

from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause


ACTION_RUNTIME_ROLE = "queryops_action_runtime"


class ActionRuntimeExecutable(Protocol):
    def execute(
        self,
        statement: TextClause,
        parameters: dict[str, str] | None = None,
    ) -> object: ...


def set_action_runtime_role(db: ActionRuntimeExecutable) -> None:
    """Enter the fixed, narrowly privileged action role for this transaction."""

    db.execute(text(f'SET LOCAL ROLE "{ACTION_RUNTIME_ROLE}"'))


def reset_action_runtime_role(db: ActionRuntimeExecutable) -> None:
    """Return to the application/session role before product-table writes."""

    db.execute(text("RESET ROLE"))
