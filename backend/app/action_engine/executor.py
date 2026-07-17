from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, text, update
from sqlalchemy.orm import Session

from app.action_engine.revalidation import ReclaimRevalidation
from app.action_engine.runtime_role import ACTION_RUNTIME_ROLE
from app.domains.it_operations.models import AssignmentStatus, ItAuditEvent, LicenseAssignment


@dataclass(frozen=True, kw_only=True)
class ReclaimExecutionOutcome:
    executed_assignment_ids: tuple[uuid.UUID, ...]
    completed_at: datetime
    runtime_role: str
    transaction_read_only: bool
    row_security_enabled: bool


def execute_reclaim(
    db: Session,
    *,
    action_request_id: uuid.UUID,
    approver_app_user_id: uuid.UUID,
    revalidation: ReclaimRevalidation,
    execution_time: datetime,
) -> ReclaimExecutionOutcome:
    """Mutate only the locked, revalidated assignments under the action role."""

    runtime_role = str(db.execute(text("SELECT current_user")).scalar_one())
    transaction_read_only = (
        str(db.execute(text("SHOW transaction_read_only")).scalar_one()) == "on"
    )
    row_security_enabled = str(db.execute(text("SHOW row_security")).scalar_one()) == "on"
    if (
        runtime_role != ACTION_RUNTIME_ROLE
        or transaction_read_only
        or not row_security_enabled
    ):
        raise RuntimeError("The secure action execution boundary is unavailable.")

    records = revalidation.executable_records
    assignment_ids = tuple(record.assignment_id for record in records)
    if assignment_ids:
        result = db.execute(
            update(LicenseAssignment)
            .where(
                LicenseAssignment.id.in_(assignment_ids),
                LicenseAssignment.status == AssignmentStatus.ACTIVE.value,
            )
            .values(
                status=AssignmentStatus.RECLAIMED.value,
                reclaimed_at=execution_time,
                reclaimed_by_app_user_id=approver_app_user_id,
            )
        )
        if result.rowcount != len(assignment_ids):
            raise RuntimeError("The action execution set changed before mutation.")

        db.execute(
            insert(ItAuditEvent),
            [
                {
                    "id": uuid.uuid4(),
                    "actor_user_id": None,
                    "actor_app_user_id": approver_app_user_id,
                    "target_user_id": record.directory_user_id,
                    "department_id": record.department_id,
                    "event_type": "license_removed",
                    "resource_type": "license_assignment",
                    "resource_id": record.assignment_id,
                    "description": "Unused license assignment reclaimed through an approved action.",
                    "occurred_at": execution_time,
                    "metadata": {
                        "action_request_id": str(action_request_id),
                        "action_type": "reclaim_unused_license",
                    },
                }
                for record in records
            ],
        )

    return ReclaimExecutionOutcome(
        executed_assignment_ids=assignment_ids,
        completed_at=execution_time,
        runtime_role=runtime_role,
        transaction_read_only=transaction_read_only,
        row_security_enabled=row_security_enabled,
    )
