from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, select, text, update
from sqlalchemy.orm import Session

from app.action_engine.base import (
    AdminOverrideRecordDescriptor,
    EligibleRecordDescriptor,
    PolicyFlag,
    RevalidationResult,
    SkippedRecordDescriptor,
)
from app.action_engine.runtime_role import ACTION_RUNTIME_ROLE
from app.auth.access_context import UserAccessContext
from app.domains.it_operations.actions.disable_inactive_user import (
    INACTIVITY_DAYS,
    OVERRIDE_CROSS_SCOPE,
    OVERRIDE_OPEN_CRITICAL_EVENT,
    OVERRIDE_PRIVILEGED,
    SAFE_REASONS,
    SKIP_ALREADY_DISABLED,
    SKIP_INVALID,
    SKIP_RECENT_LOGIN,
    SKIP_SERVICE_ACCOUNT,
    SKIP_UNAVAILABLE,
    disable_candidate_from_mapping,
    disable_candidate_statement,
)
from app.domains.it_operations.models import (
    AccountStatus,
    AccountType,
    DirectoryUser,
    Group,
    ItAuditEvent,
    LoginEvent,
    SecurityEvent,
    UserGroupMembership,
)
from app.models.product import ActionRequest, SupportedActionType


SAFE_SKIP_REASONS = {
    SKIP_UNAVAILABLE: SAFE_REASONS[SKIP_UNAVAILABLE],
    SKIP_ALREADY_DISABLED: SAFE_REASONS[SKIP_ALREADY_DISABLED],
    SKIP_SERVICE_ACCOUNT: SAFE_REASONS[SKIP_SERVICE_ACCOUNT],
    SKIP_RECENT_LOGIN: SAFE_REASONS[SKIP_RECENT_LOGIN],
    SKIP_INVALID: SAFE_REASONS[SKIP_INVALID],
    "scope_unavailable": "The user is no longer in an authorized scope.",
}


@dataclass(frozen=True, kw_only=True)
class RevalidatedDisableRecord(EligibleRecordDescriptor):
    department_id: uuid.UUID
    override_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class DisableRevalidatedSkip(SkippedRecordDescriptor):
    def as_dict(self) -> dict[str, object]:
        return {
            "record_type": "directory_user",
            "record_id": str(self.record_id),
            "directory_user_id": str(self.record_id),
            "scope": {
                "id": None,
                "type": self.scope_type,
                "key": self.scope_key,
            },
            "user_display_label": None,
            "last_successful_login_at": None,
            "reason_code": self.reason_code,
            "reason": self.reason,
        }


@dataclass(frozen=True, kw_only=True)
class DisableRevalidation(RevalidationResult):
    executable_records: tuple[RevalidatedDisableRecord, ...]
    override_reason_codes: tuple[str, ...]
    crosses_scopes: bool

    @property
    def requires_policy_override(self) -> bool:
        return bool(self.override_reason_codes)


def revalidate_disable_targets(
    db: Session,
    *,
    action_request: ActionRequest,
    approver: UserAccessContext,
    now: datetime,
) -> DisableRevalidation:
    """Re-read and lock persisted users under the approver's action-role RLS."""

    from app.action_engine.preview import validate_action_snapshot

    validate_action_snapshot(action_request)
    target_ids = _persisted_target_ids(action_request)
    rows = db.execute(
        disable_candidate_statement(target_ids).with_for_update(of=DirectoryUser)
    ).mappings().all()
    by_id = {
        row["directory_user_id"]: disable_candidate_from_mapping(row) for row in rows
    }
    executable: list[RevalidatedDisableRecord] = []
    skipped: list[DisableRevalidatedSkip] = []
    override_codes: set[str] = set()
    crosses_scopes = False
    cutoff = _as_utc(now) - timedelta(days=INACTIVITY_DAYS)

    for target_id in target_ids:
        row = by_id.get(target_id)
        if row is None:
            skipped.append(_skip(target_id, SKIP_UNAVAILABLE))
            continue
        if row.account_type == AccountType.SERVICE.value:
            skipped.append(_skip(target_id, SKIP_SERVICE_ACCOUNT))
            continue
        if row.account_type != AccountType.HUMAN.value:
            skipped.append(_skip(target_id, SKIP_INVALID))
            continue
        if row.account_status == AccountStatus.DISABLED.value:
            skipped.append(_skip(target_id, SKIP_ALREADY_DISABLED))
            continue
        if row.account_status != AccountStatus.ACTIVE.value:
            skipped.append(_skip(target_id, SKIP_INVALID))
            continue
        if (
            row.latest_successful_login_at is not None
            and _as_utc(row.latest_successful_login_at) > cutoff
        ):
            skipped.append(_skip(target_id, SKIP_RECENT_LOGIN))
            continue

        scope_key = _scope_key_for_department(approver, row.department_id)
        if scope_key is None:
            skipped.append(_skip(target_id, "scope_unavailable"))
            continue

        record_override_codes: list[str] = []
        if row.is_privileged:
            record_override_codes.append(OVERRIDE_PRIVILEGED)
        if row.has_open_critical_security_event:
            record_override_codes.append(OVERRIDE_OPEN_CRITICAL_EVENT)
        if (
            action_request.scope_type != "department"
            or action_request.department_id is None
            or row.department_id != action_request.department_id
        ):
            record_override_codes.append(OVERRIDE_CROSS_SCOPE)
            crosses_scopes = True

        override_codes.update(record_override_codes)
        executable.append(
            RevalidatedDisableRecord(
                record_type="directory_user",
                record_id=target_id,
                department_id=row.department_id,
                scope_type="department",
                scope_key=scope_key,
                safe_summary=row.user_display_label,
                override_reason_codes=tuple(record_override_codes),
            )
        )

    override_records = tuple(
        AdminOverrideRecordDescriptor(
            record_type=record.record_type,
            record_id=record.record_id,
            scope_type=record.scope_type,
            scope_key=record.scope_key,
            reason_code=record.override_reason_codes[0],
            reason=SAFE_REASONS[record.override_reason_codes[0]],
        )
        for record in executable
        if record.override_reason_codes
    )
    policy_flags = tuple(
        PolicyFlag(
            code=code,
            reason=SAFE_REASONS[code],
            requires_admin=True,
            admin_overridable=True,
        )
        for code in sorted(override_codes)
    )
    return DisableRevalidation(
        eligible_records=tuple(
            record for record in executable if not record.override_reason_codes
        ),
        skipped_records=tuple(skipped),
        admin_override_records=override_records,
        policy_flags=policy_flags,
        executable_records=tuple(executable),
        override_reason_codes=tuple(sorted(override_codes)),
        crosses_scopes=crosses_scopes,
        revalidated_at=_as_utc(now),
    )


def lock_disable_dependencies(
    db: Session,
    revalidation: DisableRevalidation,
) -> None:
    """Lock mutable eligibility dependencies before the final RLS revalidation.

    The first action-role pass has already locked each target DirectoryUser. That
    parent-row lock also blocks new FK-backed dependency inserts. These locks
    stabilize existing dependency rows and group privilege flags.
    """

    user_ids = sorted(
        {record.record_id for record in revalidation.executable_records},
        key=str,
    )
    if not user_ids:
        return
    db.scalars(
        select(LoginEvent.id)
        .where(LoginEvent.user_id.in_(user_ids))
        .order_by(LoginEvent.id)
        .with_for_update()
    ).all()
    membership_rows = db.execute(
        select(UserGroupMembership.user_id, UserGroupMembership.group_id)
        .where(UserGroupMembership.user_id.in_(user_ids))
        .order_by(UserGroupMembership.user_id, UserGroupMembership.group_id)
        .with_for_update()
    ).all()
    group_ids = sorted({group_id for _user_id, group_id in membership_rows}, key=str)
    if group_ids:
        db.scalars(
            select(Group.id)
            .where(Group.id.in_(group_ids))
            .order_by(Group.id)
            .with_for_update()
        ).all()
    db.scalars(
        select(SecurityEvent.id)
        .where(SecurityEvent.user_id.in_(user_ids))
        .order_by(SecurityEvent.id)
        .with_for_update()
    ).all()


def safe_disable_revalidation_flags(
    result: DisableRevalidation,
) -> list[dict[str, object]]:
    return [
        {
            "code": code,
            "reason": SAFE_REASONS[code],
            "requires_admin": True,
            "admin_overridable": True,
        }
        for code in result.override_reason_codes
    ]


def execute_disable(
    db: Session,
    *,
    action_request_id: uuid.UUID,
    approver_app_user_id: uuid.UUID,
    revalidation: DisableRevalidation,
    execution_time: datetime,
) -> tuple[uuid.UUID, ...]:
    """Disable only the locked and revalidated human users under the action role."""

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
    user_ids = tuple(record.record_id for record in records)
    if user_ids:
        result = db.execute(
            update(DirectoryUser)
            .where(
                DirectoryUser.id.in_(user_ids),
                DirectoryUser.account_type == AccountType.HUMAN.value,
                DirectoryUser.account_status == AccountStatus.ACTIVE.value,
            )
            .values(
                account_status=AccountStatus.DISABLED.value,
                updated_at=execution_time,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != len(user_ids):
            raise RuntimeError("The action execution set changed before mutation.")
        db.execute(
            insert(ItAuditEvent.__table__),
            [
                {
                    "id": uuid.uuid4(),
                    "actor_user_id": None,
                    "actor_app_user_id": approver_app_user_id,
                    "target_user_id": record.record_id,
                    "department_id": record.department_id,
                    "event_type": "user_disabled",
                    "resource_type": "directory_user",
                    "resource_id": record.record_id,
                    "description": (
                        "Inactive Directory User disabled through an approved action."
                    ),
                    "occurred_at": execution_time,
                    "metadata": {
                        "action_request_id": str(action_request_id),
                        "action_type": SupportedActionType.DISABLE_INACTIVE_USER.value,
                        "changed_fields": {
                            "account_status": {
                                "before": AccountStatus.ACTIVE.value,
                                "after": AccountStatus.DISABLED.value,
                            }
                        },
                    },
                }
                for record in records
            ],
        )
    return user_ids


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
                and record.get("record_type") == "directory_user"
            },
            key=str,
        )
    )
    if len(ids) != action_request.record_count:
        raise ValueError("The persisted action targets are inconsistent.")
    return ids


def _scope_key_for_department(
    approver: UserAccessContext,
    department_id: uuid.UUID,
) -> str | None:
    for scope in approver.scopes:
        if scope.type == "department" and scope.department_id == department_id:
            return scope.key
    return "global" if approver.has_global_scope else None


def _skip(record_id: uuid.UUID, code: str) -> DisableRevalidatedSkip:
    return DisableRevalidatedSkip(
        record_type="directory_user",
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
