from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import Engine, exists, func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.action_engine.base import (
    AccessContextSnapshot,
    AccessDecisionSnapshot,
    ActionPreview,
    ActionTargetInput,
    AdminOverrideRecordDescriptor,
    EligibleRecordDescriptor,
    ExecutionResult,
    PolicyFlag,
    PreviewTimestamps,
    ResourceAccessDecisionSnapshot,
    RevalidationResult,
    SafeResourceDescriptor,
    SkippedRecordDescriptor,
)
from app.action_engine.policy import REQUEST_PERMISSION, evaluate_action_request
from app.auth.access_context import UserAccessContext
from app.auth.access_policy import authorize_resource_access
from app.core.rls import build_rls_context, set_rls_context
from app.domains.it_operations.models import (
    AccountStatus,
    AccountType,
    DirectoryUser,
    Group,
    LoginEvent,
    LoginEventType,
    SecurityEvent,
    SecurityEventStatus,
    UserGroupMembership,
)
from app.models.product import (
    AccessScope,
    ActionRequest,
    DataResource,
    SupportedActionType,
)
from app.query_engine.runtime_role import QUERY_RUNTIME_ROLE, set_query_runtime_role


DISABLE_RESOURCE_TABLES = (
    "directory_users",
    "login_events",
    "groups",
    "user_group_memberships",
    "security_events",
)
INACTIVITY_DAYS = 90
SCOPED_APPROVAL_LIMIT = 20
MAX_PREVIEW_RECORDS = 500

ELIGIBLE_INACTIVE = "inactive_human_user"
SKIP_SERVICE_ACCOUNT = "service_account_excluded"
SKIP_ALREADY_DISABLED = "user_already_disabled"
SKIP_RECENT_LOGIN = "recent_successful_login"
SKIP_INVALID = "invalid_current_state"
SKIP_UNAVAILABLE = "record_not_found_or_not_authorized"
OVERRIDE_PRIVILEGED = "privileged_user"
OVERRIDE_OPEN_CRITICAL_EVENT = "open_critical_security_event"
OVERRIDE_CROSS_SCOPE = "cross_scope_target"
OVER_THRESHOLD = "record_count_over_analyst_threshold"
GLOBAL_SCOPE_REQUEST = "global_scope_request"

SAFE_REASONS = {
    ELIGIBLE_INACTIVE: "The human account has no successful login within 90 days.",
    SKIP_SERVICE_ACCOUNT: "Service accounts are excluded from this action.",
    SKIP_ALREADY_DISABLED: "The user account is already disabled.",
    SKIP_RECENT_LOGIN: "The user logged in successfully within the last 90 days.",
    SKIP_INVALID: "The user no longer has a valid executable state.",
    SKIP_UNAVAILABLE: "The selected record is unavailable.",
    OVERRIDE_PRIVILEGED: "A privileged user requires Admin review.",
    OVERRIDE_OPEN_CRITICAL_EVENT: (
        "A user with an open critical security event requires Admin review."
    ),
    OVERRIDE_CROSS_SCOPE: "A cross-scope user requires Admin review.",
    OVER_THRESHOLD: "The request contains more than 20 actionable records.",
    GLOBAL_SCOPE_REQUEST: "The request targets global scope and requires global approval.",
}


class DisablePreviewError(RuntimeError):
    """Base class for safe disable-action preview failures."""


class DisablePreviewAuthorizationError(DisablePreviewError):
    pass


class DisablePreviewTooLargeError(DisablePreviewError):
    pass


@dataclass(frozen=True, kw_only=True)
class DisableCandidateRow:
    directory_user_id: uuid.UUID
    department_id: uuid.UUID
    account_type: str
    account_status: str
    user_display_label: str
    latest_successful_login_at: datetime | None
    is_privileged: bool
    has_open_critical_security_event: bool


@dataclass(frozen=True, kw_only=True)
class DisableCandidateRead:
    records: tuple[DisableCandidateRow, ...]
    runtime_role: str
    transaction_read_only: bool
    row_security_enabled: bool


class DisableCandidateReader(Protocol):
    def __call__(
        self,
        db: Session,
        target: ActionTargetInput,
        requester: UserAccessContext,
    ) -> DisableCandidateRead: ...


@dataclass(frozen=True, kw_only=True)
class DisableEligibleRecord(EligibleRecordDescriptor):
    department_id: uuid.UUID
    scope_id: uuid.UUID
    user_display_label: str
    last_successful_login_at: datetime | None
    reason_code: str


@dataclass(frozen=True, kw_only=True)
class DisableSkippedRecord(SkippedRecordDescriptor):
    department_id: uuid.UUID | None = None
    scope_id: uuid.UUID | None = None
    user_display_label: str | None = None
    last_successful_login_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class DisableAdminOverrideRecord(AdminOverrideRecordDescriptor):
    department_id: uuid.UUID
    scope_id: uuid.UUID
    user_display_label: str
    last_successful_login_at: datetime | None
    override_reason_codes: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class DisableExclusionCount:
    reason_code: str
    count: int


@dataclass(frozen=True, kw_only=True)
class DisableInactiveUserPreview(ActionPreview):
    affected_users_count: int
    privileged_users_count: int
    service_accounts_excluded_count: int
    open_security_events_count: int
    recent_login_skipped_count: int
    normal_eligible_count: int
    skipped_count: int
    override_required_count: int
    exclusions_by_reason: tuple[DisableExclusionCount, ...]
    requires_admin: bool
    crosses_scopes: bool
    requires_policy_override: bool
    scope_decision_reason: str


class DisableInactiveUserHandler:
    action_type = SupportedActionType.DISABLE_INACTIVE_USER

    def __init__(
        self,
        *,
        candidate_reader: DisableCandidateReader | None = None,
    ) -> None:
        self._candidate_reader = candidate_reader or read_disable_candidates

    def build_preview(
        self,
        *,
        db: Session,
        target: ActionTargetInput,
        requester: UserAccessContext,
        now: datetime,
    ) -> DisableInactiveUserPreview:
        if target.action_type != self.action_type:
            raise DisablePreviewAuthorizationError("Unsupported action type.")
        if target.scope_id is None:
            raise DisablePreviewAuthorizationError("An exact action scope is required.")
        if not target.targets or any(
            reference.record_type != "directory_user" for reference in target.targets
        ):
            raise DisablePreviewAuthorizationError(
                "Explicit Directory User targets are required."
            )

        request_decision = evaluate_action_request(
            requester,
            scope_type=target.scope_type,
            scope_key=target.scope_key,
        )
        if not request_decision.allowed:
            raise DisablePreviewAuthorizationError(
                "The action is not authorized by the current policy."
            )

        resources, resource_decisions = _authorize_required_resources(
            db,
            requester,
            target,
        )
        candidate_read = self._candidate_reader(db, target, requester)
        current_time = _as_utc(now)
        department_scopes = _department_scopes_for_rows(db, candidate_read.records)
        eligible, skipped, overrides = _classify_records(
            candidate_read.records,
            target=target,
            department_scopes=department_scopes,
            now=current_time,
        )
        skipped = (*skipped, *_missing_selector_records(target, candidate_read.records))
        eligible = tuple(sorted(eligible, key=lambda item: str(item.record_id)))
        skipped = tuple(sorted(skipped, key=lambda item: str(item.record_id)))
        overrides = tuple(sorted(overrides, key=lambda item: str(item.record_id)))
        actionable_records = (*eligible, *overrides)
        actionable_count = len(actionable_records)
        override_codes = {
            code for record in overrides for code in record.override_reason_codes
        }
        crosses_scopes = OVERRIDE_CROSS_SCOPE in override_codes
        policy_flags = _policy_flags(
            override_codes,
            actionable_count=actionable_count,
            global_scope=target.scope_type == "global",
        )
        target_scope_ids = tuple(
            sorted(
                {
                    target.scope_id,
                    *(record.scope_id for record in actionable_records),
                },
                key=str,
            )
        )
        exclusions = Counter(
            [record.reason_code for record in skipped]
            + [
                code
                for record in overrides
                for code in record.override_reason_codes
            ]
        )

        return DisableInactiveUserPreview(
            action_type=self.action_type,
            target_input=target,
            eligible_records=eligible,
            skipped_records=skipped,
            admin_override_records=overrides,
            estimated_impact=(),
            policy_flags=policy_flags,
            timestamps=PreviewTimestamps(
                generated_at=current_time,
                expires_at=current_time + timedelta(minutes=30),
            ),
            access_context_snapshot=AccessContextSnapshot(
                app_user_id=requester.user_id,
                permissions=tuple(
                    sorted({REQUEST_PERMISSION}.intersection(requester.permissions))
                ),
                assigned_scopes=tuple(
                    sorted(f"{scope.type}:{scope.key}" for scope in requester.scopes)
                ),
                has_global_scope=requester.has_global_scope,
                assigned_scope_ids=tuple(
                    sorted((scope.id for scope in requester.scopes), key=str)
                ),
            ),
            access_decision_snapshot=AccessDecisionSnapshot(
                allowed=True,
                reason="all_required_resources_authorized",
                required_permission=REQUEST_PERMISSION,
                matched_scopes=tuple(sorted(set(request_decision.matched_scopes))),
                resource_decisions=resource_decisions,
                runtime_role=candidate_read.runtime_role,
                transaction_read_only=candidate_read.transaction_read_only,
                row_security_enabled=candidate_read.row_security_enabled,
            ),
            requester_scope_ids=tuple(
                sorted((scope.id for scope in requester.scopes), key=str)
            ),
            target_scope_ids=target_scope_ids,
            resource_descriptors=tuple(
                SafeResourceDescriptor(
                    table_name=resource.table_name,
                    display_name=resource.display_name,
                    sensitivity_level=resource.sensitivity_level,
                )
                for resource in resources
            ),
            affected_users_count=actionable_count,
            privileged_users_count=sum(
                OVERRIDE_PRIVILEGED in record.override_reason_codes
                for record in overrides
            ),
            service_accounts_excluded_count=sum(
                record.reason_code == SKIP_SERVICE_ACCOUNT for record in skipped
            ),
            open_security_events_count=sum(
                OVERRIDE_OPEN_CRITICAL_EVENT in record.override_reason_codes
                for record in overrides
            ),
            recent_login_skipped_count=sum(
                record.reason_code == SKIP_RECENT_LOGIN for record in skipped
            ),
            normal_eligible_count=len(eligible),
            skipped_count=len(skipped),
            override_required_count=len(overrides),
            exclusions_by_reason=tuple(
                DisableExclusionCount(reason_code=code, count=count)
                for code, count in sorted(exclusions.items())
            ),
            requires_admin=bool(policy_flags),
            crosses_scopes=crosses_scopes,
            requires_policy_override=bool(overrides),
            scope_decision_reason=request_decision.code,
        )

    def revalidate(
        self,
        *,
        db: Session,
        action_request: ActionRequest,
        approver: UserAccessContext,
        now: datetime,
    ) -> RevalidationResult:
        from app.action_engine.disable_execution import revalidate_disable_targets

        return revalidate_disable_targets(
            db,
            action_request=action_request,
            approver=approver,
            now=now,
        )

    def execute(
        self,
        *,
        db: Session,
        action_request: ActionRequest,
        approved_by_app_user_id: uuid.UUID,
        revalidation: RevalidationResult,
        now: datetime,
    ) -> ExecutionResult:
        from app.action_engine.disable_execution import (
            DisableRevalidation,
            execute_disable,
        )

        if not isinstance(revalidation, DisableRevalidation):
            raise TypeError("Disable execution requires a disable revalidation result.")
        executed_user_ids = execute_disable(
            db,
            action_request_id=action_request.id,
            approver_app_user_id=approved_by_app_user_id,
            revalidation=revalidation,
            execution_time=now,
        )
        return ExecutionResult(
            action_request_id=action_request.id,
            executed_record_ids=executed_user_ids,
            skipped_records=revalidation.skipped_records,
            completed_at=now,
            idempotency_key=action_request.idempotency_key,
        )


def read_disable_candidates(
    db: Session,
    target: ActionTargetInput,
    requester: UserAccessContext,
) -> DisableCandidateRead:
    engine = _engine_from_session(db)
    if engine.dialect.name != "postgresql":
        raise DisablePreviewError("Disable previews require PostgreSQL.")

    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            set_query_runtime_role(connection)
            set_rls_context(connection, build_rls_context(requester))
            runtime_role = str(
                connection.execute(text("SELECT current_user")).scalar_one()
            )
            transaction_read_only = (
                str(connection.execute(text("SHOW transaction_read_only")).scalar_one())
                == "on"
            )
            row_security_enabled = (
                str(connection.execute(text("SHOW row_security")).scalar_one()) == "on"
            )
            _require_secure_read_boundary(
                runtime_role=runtime_role,
                transaction_read_only=transaction_read_only,
                row_security_enabled=row_security_enabled,
            )
            rows = connection.execute(_candidate_statement(target)).mappings().all()

    if len(rows) > MAX_PREVIEW_RECORDS:
        raise DisablePreviewTooLargeError(
            "The requested preview exceeds the supported record limit."
        )
    return DisableCandidateRead(
        records=tuple(disable_candidate_from_mapping(row) for row in rows),
        runtime_role=runtime_role,
        transaction_read_only=transaction_read_only,
        row_security_enabled=row_security_enabled,
    )


def disable_candidate_statement(target_ids: tuple[uuid.UUID, ...]):
    latest_success = (
        select(func.max(LoginEvent.occurred_at))
        .where(
            LoginEvent.user_id == DirectoryUser.id,
            LoginEvent.event_type == LoginEventType.SUCCESS.value,
        )
        .correlate(DirectoryUser)
        .scalar_subquery()
    )
    privileged = exists(
        select(UserGroupMembership.user_id)
        .join(Group, Group.id == UserGroupMembership.group_id)
        .where(
            UserGroupMembership.user_id == DirectoryUser.id,
            Group.is_privileged.is_(True),
        )
    )
    open_critical = exists(
        select(SecurityEvent.id).where(
            SecurityEvent.user_id == DirectoryUser.id,
            SecurityEvent.severity == "critical",
            SecurityEvent.status.in_(
                (
                    SecurityEventStatus.OPEN.value,
                    SecurityEventStatus.INVESTIGATING.value,
                )
            ),
        )
    )
    return (
        select(
            DirectoryUser.id.label("directory_user_id"),
            DirectoryUser.department_id,
            DirectoryUser.account_type,
            DirectoryUser.account_status,
            DirectoryUser.full_name.label("user_display_label"),
            DirectoryUser.last_login_at.label("stored_last_login_at"),
            latest_success.label("latest_successful_login_at"),
            privileged.label("is_privileged"),
            open_critical.label("has_open_critical_security_event"),
        )
        .where(DirectoryUser.id.in_(target_ids))
        .order_by(DirectoryUser.id)
        .limit(MAX_PREVIEW_RECORDS + 1)
    )


def _candidate_statement(target: ActionTargetInput):
    target_ids = tuple(reference.record_id for reference in target.targets)
    if not target_ids:
        raise DisablePreviewAuthorizationError(
            "Explicit Directory User targets are required."
        )
    return disable_candidate_statement(target_ids)


def disable_candidate_from_mapping(row) -> DisableCandidateRow:
    return DisableCandidateRow(
        directory_user_id=row["directory_user_id"],
        department_id=row["department_id"],
        account_type=row["account_type"],
        account_status=row["account_status"],
        user_display_label=row["user_display_label"],
        latest_successful_login_at=_latest_successful_login(row),
        is_privileged=bool(row["is_privileged"]),
        has_open_critical_security_event=bool(
            row["has_open_critical_security_event"]
        ),
    )


def _latest_successful_login(row) -> datetime | None:
    values = [
        _as_utc(value)
        for value in (
            row["stored_last_login_at"],
            row["latest_successful_login_at"],
        )
        if value is not None
    ]
    return max(values) if values else None


def _authorize_required_resources(
    db: Session,
    requester: UserAccessContext,
    target: ActionTargetInput,
) -> tuple[tuple[DataResource, ...], tuple[ResourceAccessDecisionSnapshot, ...]]:
    resources = {
        resource.table_name: resource
        for resource in db.scalars(
            select(DataResource).where(
                DataResource.resource_type == "table",
                DataResource.table_name.in_(DISABLE_RESOURCE_TABLES),
            )
        ).all()
    }
    if set(resources) != set(DISABLE_RESOURCE_TABLES):
        raise DisablePreviewAuthorizationError(
            "The action is not authorized for the required resources."
        )

    ordered_resources = tuple(resources[table] for table in DISABLE_RESOURCE_TABLES)
    snapshots: list[ResourceAccessDecisionSnapshot] = []
    for resource in ordered_resources:
        decision = authorize_resource_access(
            requester,
            "action:request",
            resource,
            {"scope_type": target.scope_type, "scope_key": target.scope_key},
        )
        allowed = decision.allowed and resource.is_queryable is True
        snapshots.append(
            ResourceAccessDecisionSnapshot(
                table_name=resource.table_name,
                allowed=allowed,
                required_permission=decision.required_permission,
                matched_scopes=tuple(decision.matched_scopes),
            )
        )
        if not allowed:
            raise DisablePreviewAuthorizationError(
                "The action is not authorized for the required resources."
            )
    return ordered_resources, tuple(snapshots)


def _department_scopes_for_rows(
    db: Session,
    rows: tuple[DisableCandidateRow, ...],
) -> dict[uuid.UUID, AccessScope]:
    department_ids = sorted({row.department_id for row in rows}, key=str)
    if not department_ids:
        return {}
    scopes = db.scalars(
        select(AccessScope).where(
            AccessScope.scope_type == "department",
            AccessScope.department_id.in_(department_ids),
        )
    ).all()
    return {
        scope.department_id: scope
        for scope in scopes
        if scope.department_id is not None
    }


def _classify_records(
    rows: tuple[DisableCandidateRow, ...],
    *,
    target: ActionTargetInput,
    department_scopes: dict[uuid.UUID, AccessScope],
    now: datetime,
) -> tuple[
    tuple[DisableEligibleRecord, ...],
    tuple[DisableSkippedRecord, ...],
    tuple[DisableAdminOverrideRecord, ...],
]:
    eligible: list[DisableEligibleRecord] = []
    skipped: list[DisableSkippedRecord] = []
    overrides: list[DisableAdminOverrideRecord] = []
    cutoff = _as_utc(now) - timedelta(days=INACTIVITY_DAYS)

    for row in rows:
        scope = department_scopes.get(row.department_id)
        scope_type = scope.scope_type if scope is not None else target.scope_type
        scope_key = scope.scope_key if scope is not None else target.scope_key
        skip_code: str | None = None
        if row.account_type == AccountType.SERVICE.value:
            skip_code = SKIP_SERVICE_ACCOUNT
        elif row.account_type != AccountType.HUMAN.value or scope is None:
            skip_code = SKIP_INVALID
        elif row.account_status == AccountStatus.DISABLED.value:
            skip_code = SKIP_ALREADY_DISABLED
        elif row.account_status != AccountStatus.ACTIVE.value:
            skip_code = SKIP_INVALID
        elif (
            row.latest_successful_login_at is not None
            and _as_utc(row.latest_successful_login_at) > cutoff
        ):
            skip_code = SKIP_RECENT_LOGIN

        if skip_code is not None:
            skipped.append(
                DisableSkippedRecord(
                    record_type="directory_user",
                    record_id=row.directory_user_id,
                    scope_type=scope_type,
                    scope_key=scope_key,
                    reason_code=skip_code,
                    reason=SAFE_REASONS[skip_code],
                    department_id=row.department_id,
                    scope_id=scope.id if scope is not None else None,
                    user_display_label=row.user_display_label,
                    last_successful_login_at=row.latest_successful_login_at,
                )
            )
            continue

        assert scope is not None
        override_codes: list[str] = []
        if row.is_privileged:
            override_codes.append(OVERRIDE_PRIVILEGED)
        if row.has_open_critical_security_event:
            override_codes.append(OVERRIDE_OPEN_CRITICAL_EVENT)
        if _is_cross_scope(row.department_id, target):
            override_codes.append(OVERRIDE_CROSS_SCOPE)

        if override_codes:
            primary_reason = override_codes[0]
            overrides.append(
                DisableAdminOverrideRecord(
                    record_type="directory_user",
                    record_id=row.directory_user_id,
                    scope_type=scope.scope_type,
                    scope_key=scope.scope_key,
                    reason_code=primary_reason,
                    reason=SAFE_REASONS[primary_reason],
                    department_id=row.department_id,
                    scope_id=scope.id,
                    user_display_label=row.user_display_label,
                    last_successful_login_at=row.latest_successful_login_at,
                    override_reason_codes=tuple(override_codes),
                )
            )
            continue

        eligible.append(
            DisableEligibleRecord(
                record_type="directory_user",
                record_id=row.directory_user_id,
                scope_type=scope.scope_type,
                scope_key=scope.scope_key,
                safe_summary=row.user_display_label,
                department_id=row.department_id,
                scope_id=scope.id,
                user_display_label=row.user_display_label,
                last_successful_login_at=row.latest_successful_login_at,
                reason_code=ELIGIBLE_INACTIVE,
            )
        )

    return tuple(eligible), tuple(skipped), tuple(overrides)


def _missing_selector_records(
    target: ActionTargetInput,
    rows: tuple[DisableCandidateRow, ...],
) -> tuple[DisableSkippedRecord, ...]:
    returned_ids = {row.directory_user_id for row in rows}
    return tuple(
        DisableSkippedRecord(
            record_type="directory_user",
            record_id=reference.record_id,
            scope_type=target.scope_type,
            scope_key=target.scope_key,
            reason_code=SKIP_UNAVAILABLE,
            reason=SAFE_REASONS[SKIP_UNAVAILABLE],
        )
        for reference in target.targets
        if reference.record_id not in returned_ids
    )


def _policy_flags(
    override_codes: set[str],
    *,
    actionable_count: int,
    global_scope: bool,
) -> tuple[PolicyFlag, ...]:
    codes = set(override_codes)
    if actionable_count > SCOPED_APPROVAL_LIMIT:
        codes.add(OVER_THRESHOLD)
    if global_scope:
        codes.add(GLOBAL_SCOPE_REQUEST)
    return tuple(
        PolicyFlag(
            code=code,
            reason=SAFE_REASONS[code],
            requires_admin=True,
            admin_overridable=True,
        )
        for code in sorted(codes)
    )


def _is_cross_scope(department_id: uuid.UUID, target: ActionTargetInput) -> bool:
    return (
        target.scope_type != "department"
        or target.department_id is None
        or department_id != target.department_id
    )


def _engine_from_session(db: Session) -> Engine:
    bind = db.get_bind()
    if isinstance(bind, Engine):
        return bind
    if isinstance(bind, Connection):
        return bind.engine
    raise TypeError("Disable preview requires a SQLAlchemy Session with an engine bind.")


def _require_secure_read_boundary(
    *,
    runtime_role: str,
    transaction_read_only: bool,
    row_security_enabled: bool,
) -> None:
    if (
        runtime_role != QUERY_RUNTIME_ROLE
        or not transaction_read_only
        or not row_security_enabled
    ):
        raise DisablePreviewError("The secure action preview read boundary is unavailable.")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
