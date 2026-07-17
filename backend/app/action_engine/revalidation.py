from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.action_engine.preview import validate_reclaim_snapshot
from app.action_engine.base import (
    EligibleRecordDescriptor,
    RevalidationResult,
    SkippedRecordDescriptor,
)
from app.auth.access_context import UserAccessContext
from app.domains.it_operations.models import (
    AccountType,
    AssignmentStatus,
    DirectoryUser,
    License,
    LicenseAssignment,
)
from app.models.product import ActionRequest


ELIGIBILITY_DAYS = 60
SAFE_SKIP_REASONS = {
    "record_unavailable": "The record is no longer available for this action.",
    "already_reclaimed": "The license assignment was already reclaimed.",
    "assignment_suspended": "The license assignment is suspended.",
    "recent_usage": "The license was used too recently.",
    "invalid_current_state": "The record no longer has a valid executable state.",
    "scope_unavailable": "The record is no longer in an authorized scope.",
}
SAFE_OVERRIDE_REASONS = {
    "mandatory_license": "A mandatory license requires policy override approval.",
    "exception_assignment": "An exception assignment requires policy override approval.",
    "service_account": "A service account requires policy override approval.",
    "cross_scope": "A cross-scope record requires global approval.",
}


@dataclass(frozen=True, kw_only=True)
class RevalidatedReclaimRecord(EligibleRecordDescriptor):
    assignment_id: uuid.UUID
    directory_user_id: uuid.UUID
    department_id: uuid.UUID
    scope_type: str
    scope_key: str
    override_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class RevalidatedSkip(SkippedRecordDescriptor):

    def as_dict(self) -> dict[str, str]:
        return {
            "record_type": "license_assignment",
            "record_id": str(self.record_id),
            "reason_code": self.reason_code,
            "reason": self.reason,
        }


@dataclass(frozen=True, kw_only=True)
class ReclaimRevalidation(RevalidationResult):
    executable_records: tuple[RevalidatedReclaimRecord, ...]
    override_reason_codes: tuple[str, ...]
    crosses_scopes: bool

    @property
    def requires_policy_override(self) -> bool:
        return bool(self.override_reason_codes)


def revalidate_reclaim_targets(
    db: Session,
    *,
    action_request: ActionRequest,
    approver: UserAccessContext,
    now: datetime,
) -> ReclaimRevalidation:
    """Re-query and lock every persisted deterministic assignment target.

    The caller must already have installed the current approver's RLS context
    and entered ``queryops_action_runtime``.
    """

    validate_reclaim_snapshot(action_request)
    target_ids = _persisted_target_ids(action_request)
    rows = db.execute(
        select(
            LicenseAssignment.id,
            LicenseAssignment.user_id,
            LicenseAssignment.department_id,
            LicenseAssignment.status,
            LicenseAssignment.last_used_at,
            LicenseAssignment.is_mandatory,
            LicenseAssignment.is_exception,
            DirectoryUser.id.label("directory_user_id"),
            DirectoryUser.department_id.label("user_department_id"),
            DirectoryUser.account_type,
            License.monthly_cost_usd,
        )
        .select_from(LicenseAssignment)
        .outerjoin(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
        .outerjoin(License, License.id == LicenseAssignment.license_id)
        .where(LicenseAssignment.id.in_(target_ids))
        .order_by(LicenseAssignment.id)
        .with_for_update(of=LicenseAssignment)
    ).mappings().all()
    by_id = {row["id"]: row for row in rows}
    executable: list[RevalidatedReclaimRecord] = []
    skipped: list[RevalidatedSkip] = []
    override_codes: set[str] = set()
    crosses_scopes = False
    cutoff = _as_utc(now) - timedelta(days=ELIGIBILITY_DAYS)

    for target_id in target_ids:
        row = by_id.get(target_id)
        if row is None:
            skipped.append(_skip(target_id, "record_unavailable"))
            continue
        status = row["status"]
        if status == AssignmentStatus.RECLAIMED.value:
            skipped.append(_skip(target_id, "already_reclaimed"))
            continue
        if status == AssignmentStatus.SUSPENDED.value:
            skipped.append(_skip(target_id, "assignment_suspended"))
            continue
        if status != AssignmentStatus.ACTIVE.value:
            skipped.append(_skip(target_id, "invalid_current_state"))
            continue
        last_used_at = row["last_used_at"]
        if last_used_at is not None and _as_utc(last_used_at) >= cutoff:
            skipped.append(_skip(target_id, "recent_usage"))
            continue
        if not _structurally_valid(row):
            skipped.append(_skip(target_id, "invalid_current_state"))
            continue

        department_id = row["department_id"]
        scope_key = _scope_key_for_department(approver, department_id)
        if scope_key is None and not approver.has_global_scope:
            skipped.append(_skip(target_id, "scope_unavailable"))
            continue

        record_override_codes: list[str] = []
        if row["is_mandatory"]:
            record_override_codes.append("mandatory_license")
        if row["is_exception"]:
            record_override_codes.append("exception_assignment")
        if row["account_type"] == AccountType.SERVICE.value:
            record_override_codes.append("service_account")
        elif row["account_type"] != AccountType.HUMAN.value:
            skipped.append(_skip(target_id, "invalid_current_state"))
            continue
        if (
            action_request.scope_type != "department"
            or action_request.department_id is None
            or department_id != action_request.department_id
        ):
            record_override_codes.append("cross_scope")
            crosses_scopes = True

        override_codes.update(record_override_codes)
        executable.append(
            RevalidatedReclaimRecord(
                record_type="license_assignment",
                record_id=target_id,
                safe_summary=None,
                assignment_id=target_id,
                directory_user_id=row["directory_user_id"],
                department_id=department_id,
                scope_type="department",
                scope_key=scope_key or "global",
                override_reason_codes=tuple(sorted(set(record_override_codes))),
            )
        )

    return ReclaimRevalidation(
        eligible_records=tuple(executable),
        skipped_records=tuple(skipped),
        admin_override_records=tuple(),
        policy_flags=tuple(),
        executable_records=tuple(executable),
        override_reason_codes=tuple(sorted(override_codes)),
        crosses_scopes=crosses_scopes,
        revalidated_at=_as_utc(now),
    )


def safe_revalidation_flags(result: ReclaimRevalidation) -> list[dict[str, object]]:
    return [
        {
            "code": code,
            "reason": SAFE_OVERRIDE_REASONS[code],
            "requires_admin": True,
            "admin_overridable": True,
        }
        for code in result.override_reason_codes
    ]


def _persisted_target_ids(action_request: ActionRequest) -> tuple[uuid.UUID, ...]:
    preview = action_request.preview_json
    records = [
        *preview.get("eligible_records", []),
        *preview.get("override_required_records", []),
    ]
    ids = tuple(
        sorted(
            {
                uuid.UUID(str(record["record_id"]))
                for record in records
                if isinstance(record, dict)
                and record.get("record_type") == "license_assignment"
            },
            key=str,
        )
    )
    if len(ids) != action_request.record_count:
        raise ValueError("The persisted action targets are inconsistent.")
    return ids


def _structurally_valid(row) -> bool:
    if (
        row["directory_user_id"] is None
        or row["user_department_id"] != row["department_id"]
        or row["monthly_cost_usd"] is None
    ):
        return False
    try:
        cost = Decimal(row["monthly_cost_usd"])
    except (InvalidOperation, TypeError, ValueError):
        return False
    return cost.is_finite() and cost >= 0


def _scope_key_for_department(
    approver: UserAccessContext,
    department_id: uuid.UUID,
) -> str | None:
    for scope in approver.scopes:
        if scope.type == "department" and scope.department_id == department_id:
            return scope.key
    return "global" if approver.has_global_scope else None


def _skip(record_id: uuid.UUID, code: str) -> RevalidatedSkip:
    return RevalidatedSkip(
        record_type="license_assignment",
        record_id=record_id,
        scope_type="unavailable",
        scope_key="unavailable",
        reason_code=code,
        reason=SAFE_SKIP_REASONS[code],
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
