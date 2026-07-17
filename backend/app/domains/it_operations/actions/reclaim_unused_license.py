from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from sqlalchemy import Engine, or_, select, text
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
    SafeEstimatedImpact,
    SafeResourceDescriptor,
    SkippedRecordDescriptor,
)
from app.action_engine.policy import REQUEST_PERMISSION, evaluate_action_request
from app.auth.access_context import UserAccessContext
from app.auth.access_policy import authorize_resource_access
from app.core.rls import build_rls_context, set_rls_context
from app.domains.it_operations.models import (
    AccountType,
    AssignmentStatus,
    DirectoryUser,
    License,
    LicenseAssignment,
)
from app.models.product import AccessScope, DataResource, SupportedActionType
from app.query_engine.runtime_role import QUERY_RUNTIME_ROLE, set_query_runtime_role


RECLAIM_RESOURCE_TABLES = (
    "directory_users",
    "license_assignments",
    "licenses",
)
NORMAL_ELIGIBILITY_DAYS = 60
HIGH_CONFIDENCE_DAYS = 90
SCOPED_APPROVAL_LIMIT = 20
MAX_PREVIEW_RECORDS = 500
MONEY_QUANTUM = Decimal("0.01")

ELIGIBLE_NO_USAGE = "no_recorded_usage"
ELIGIBLE_UNUSED = "unused_over_60_days"
SKIP_RECLAIMED = "assignment_already_reclaimed"
SKIP_SUSPENDED = "assignment_suspended"
SKIP_RECENT = "recent_usage"
SKIP_INVALID = "record_structurally_invalid"
SKIP_UNAVAILABLE = "record_not_found_or_not_authorized"
OVERRIDE_MANDATORY = "mandatory_assignment"
OVERRIDE_EXCEPTION = "exception_assignment"
OVERRIDE_SERVICE_ACCOUNT = "service_account_assignment"
OVERRIDE_CROSS_SCOPE = "cross_scope_target"
OVER_THRESHOLD = "record_count_over_analyst_threshold"
GLOBAL_SCOPE_REQUEST = "global_scope_request"

SAFE_REASONS = {
    ELIGIBLE_NO_USAGE: "No license usage is recorded.",
    ELIGIBLE_UNUSED: "The license has not been used for more than 60 days.",
    SKIP_RECLAIMED: "The assignment is already reclaimed.",
    SKIP_SUSPENDED: "The assignment is suspended.",
    SKIP_RECENT: "The license was used within the last 60 days.",
    SKIP_INVALID: "The assignment is not structurally valid for this action.",
    SKIP_UNAVAILABLE: "The selected record is unavailable.",
    OVERRIDE_MANDATORY: "The assignment is mandatory and requires Admin review.",
    OVERRIDE_EXCEPTION: "The assignment is an exception and requires Admin review.",
    OVERRIDE_SERVICE_ACCOUNT: (
        "The assignment belongs to a service account and requires Admin review."
    ),
    OVERRIDE_CROSS_SCOPE: (
        "The assignment is outside the requested scope and requires Admin review."
    ),
    OVER_THRESHOLD: "The request contains more than 20 actionable records.",
    GLOBAL_SCOPE_REQUEST: "The request targets global scope and requires global approval.",
}


class ReclaimPreviewError(RuntimeError):
    """Base class for safe reclaim preview failures."""


class ReclaimPreviewAuthorizationError(ReclaimPreviewError):
    pass


class ReclaimPreviewTooLargeError(ReclaimPreviewError):
    pass


@dataclass(frozen=True, kw_only=True)
class ReclaimCandidateRow:
    assignment_id: uuid.UUID
    assignment_user_id: uuid.UUID
    assignment_department_id: uuid.UUID
    assignment_status: str
    last_used_at: datetime | None
    is_mandatory: bool
    is_exception: bool
    directory_user_id: uuid.UUID | None
    directory_user_department_id: uuid.UUID | None
    user_display_label: str | None
    account_type: str | None
    license_id: uuid.UUID | None
    license_product: str | None
    license_vendor: str | None
    monthly_cost_usd: Decimal | None


@dataclass(frozen=True, kw_only=True)
class ReclaimCandidateRead:
    records: tuple[ReclaimCandidateRow, ...]
    runtime_role: str
    transaction_read_only: bool
    row_security_enabled: bool


class ReclaimCandidateReader(Protocol):
    def __call__(
        self,
        db: Session,
        target: ActionTargetInput,
        requester: UserAccessContext,
    ) -> ReclaimCandidateRead: ...


@dataclass(frozen=True, kw_only=True)
class ReclaimEligibleRecord(EligibleRecordDescriptor):
    directory_user_id: uuid.UUID
    department_id: uuid.UUID
    scope_id: uuid.UUID
    user_display_label: str
    license_product: str
    license_vendor: str
    last_used_at: datetime | None
    monthly_cost_usd: Decimal
    reason_code: str
    high_confidence: bool


@dataclass(frozen=True, kw_only=True)
class ReclaimSkippedRecord(SkippedRecordDescriptor):
    directory_user_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    scope_id: uuid.UUID | None = None
    user_display_label: str | None = None
    license_product: str | None = None
    license_vendor: str | None = None
    last_used_at: datetime | None = None
    monthly_cost_usd: Decimal | None = None
    high_confidence: bool = False


@dataclass(frozen=True, kw_only=True)
class ReclaimAdminOverrideRecord(AdminOverrideRecordDescriptor):
    directory_user_id: uuid.UUID
    department_id: uuid.UUID
    scope_id: uuid.UUID
    user_display_label: str
    license_product: str
    license_vendor: str
    last_used_at: datetime | None
    monthly_cost_usd: Decimal
    high_confidence: bool
    override_reason_codes: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class ReclaimExclusionCount:
    reason_code: str
    count: int


@dataclass(frozen=True, kw_only=True)
class ReclaimActionPreview(ActionPreview):
    affected_license_assignment_count: int
    affected_user_count: int
    normal_eligible_count: int
    skipped_count: int
    override_required_count: int
    high_confidence_count: int
    estimated_monthly_savings: Decimal
    override_estimated_monthly_savings: Decimal
    exclusions_by_reason: tuple[ReclaimExclusionCount, ...]
    requires_admin: bool
    crosses_scopes: bool
    requires_policy_override: bool


class ReclaimUnusedLicenseHandler:
    action_type = SupportedActionType.RECLAIM_UNUSED_LICENSE

    def __init__(
        self,
        *,
        candidate_reader: ReclaimCandidateReader | None = None,
    ) -> None:
        self._candidate_reader = candidate_reader or read_reclaim_candidates

    def build_preview(
        self,
        *,
        db: Session,
        target: ActionTargetInput,
        requester: UserAccessContext,
        now: datetime,
    ) -> ReclaimActionPreview:
        if target.action_type != self.action_type:
            raise ReclaimPreviewAuthorizationError("Unsupported action type.")
        if target.scope_id is None:
            raise ReclaimPreviewAuthorizationError("An exact action scope is required.")

        request_decision = evaluate_action_request(
            requester,
            scope_type=target.scope_type,
            scope_key=target.scope_key,
        )
        if not request_decision.allowed:
            raise ReclaimPreviewAuthorizationError(
                "The action is not authorized by the current policy."
            )

        resources, resource_decisions = _authorize_required_resources(
            db,
            requester,
            target,
        )
        candidate_read = self._candidate_reader(db, target, requester)
        current_time = _as_utc(now)
        department_scopes = _department_scopes_for_rows(
            db,
            candidate_read.records,
        )
        eligible, skipped, overrides = _classify_records(
            candidate_read.records,
            target=target,
            department_scopes=department_scopes,
            now=current_time,
        )
        skipped = (*skipped, *_missing_selector_records(target, candidate_read.records))

        eligible = tuple(sorted(eligible, key=lambda item: str(item.record_id)))
        skipped = tuple(
            sorted(skipped, key=lambda item: (item.record_type, str(item.record_id)))
        )
        overrides = tuple(sorted(overrides, key=lambda item: str(item.record_id)))
        actionable_count = len(eligible) + len(overrides)
        crosses_scopes = any(
            OVERRIDE_CROSS_SCOPE in record.override_reason_codes
            for record in overrides
        )
        requires_policy_override = bool(overrides)
        policy_flags = _policy_flags(
            overrides,
            actionable_count=actionable_count,
            global_scope=target.scope_type == "global",
        )
        requires_admin = bool(policy_flags)
        estimated_savings = _sum_costs(eligible)
        override_savings = _sum_costs(overrides)
        actionable_records = (*eligible, *overrides)
        high_confidence_count = sum(
            1 for record in actionable_records if record.high_confidence
        )
        target_scope_ids = tuple(
            sorted(
                {
                    *(record.scope_id for record in actionable_records),
                    target.scope_id,
                },
                key=str,
            )
        )
        exclusion_counts = Counter(
            [record.reason_code for record in skipped]
            + [
                reason_code
                for record in overrides
                for reason_code in record.override_reason_codes
            ]
        )

        return ReclaimActionPreview(
            action_type=self.action_type,
            target_input=target,
            eligible_records=eligible,
            skipped_records=skipped,
            admin_override_records=overrides,
            estimated_impact=(
                SafeEstimatedImpact(
                    metric_key="estimated_monthly_savings",
                    value=estimated_savings,
                    unit="USD/month",
                    description="Estimated savings from normally eligible assignments.",
                ),
                SafeEstimatedImpact(
                    metric_key="override_estimated_monthly_savings",
                    value=override_savings,
                    unit="USD/month",
                    description="Separate estimated impact of Admin-override assignments.",
                ),
            ),
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
                assigned_scope_ids=tuple(sorted((scope.id for scope in requester.scopes), key=str)),
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
            affected_license_assignment_count=actionable_count,
            affected_user_count=len(
                {record.directory_user_id for record in actionable_records}
            ),
            normal_eligible_count=len(eligible),
            skipped_count=len(skipped),
            override_required_count=len(overrides),
            high_confidence_count=high_confidence_count,
            estimated_monthly_savings=estimated_savings,
            override_estimated_monthly_savings=override_savings,
            exclusions_by_reason=tuple(
                ReclaimExclusionCount(reason_code=code, count=count)
                for code, count in sorted(exclusion_counts.items())
            ),
            requires_admin=requires_admin,
            crosses_scopes=crosses_scopes,
            requires_policy_override=requires_policy_override,
        )

    def revalidate(
        self,
        *,
        db: Session,
        action_request,
        approver: UserAccessContext,
        now: datetime,
    ) -> RevalidationResult:
        from app.action_engine.revalidation import revalidate_reclaim_targets

        return revalidate_reclaim_targets(
            db,
            action_request=action_request,
            approver=approver,
            now=now,
        )

    def execute(
        self,
        *,
        db: Session,
        action_request,
        approved_by_app_user_id: uuid.UUID,
        revalidation: RevalidationResult,
        now: datetime,
    ) -> ExecutionResult:
        from app.action_engine.executor import execute_reclaim
        from app.action_engine.revalidation import ReclaimRevalidation

        if not isinstance(revalidation, ReclaimRevalidation):
            raise TypeError("Reclaim execution requires a reclaim revalidation result.")
        outcome = execute_reclaim(
            db,
            action_request_id=action_request.id,
            approver_app_user_id=approved_by_app_user_id,
            revalidation=revalidation,
            execution_time=now,
        )
        return ExecutionResult(
            action_request_id=action_request.id,
            executed_record_ids=outcome.executed_assignment_ids,
            skipped_records=tuple(),
            completed_at=outcome.completed_at,
            idempotency_key=action_request.idempotency_key,
        )


def read_reclaim_candidates(
    db: Session,
    target: ActionTargetInput,
    requester: UserAccessContext,
) -> ReclaimCandidateRead:
    engine = _engine_from_session(db)
    if engine.dialect.name != "postgresql":
        raise ReclaimPreviewError("Reclaim previews require PostgreSQL.")

    statement = _candidate_statement(target)
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
            rows = connection.execute(statement).mappings().all()

    if len(rows) > MAX_PREVIEW_RECORDS:
        raise ReclaimPreviewTooLargeError(
            "The requested preview exceeds the supported record limit."
        )

    return ReclaimCandidateRead(
        records=tuple(_candidate_from_mapping(row) for row in rows),
        runtime_role=runtime_role,
        transaction_read_only=transaction_read_only,
        row_security_enabled=row_security_enabled,
    )


def _candidate_statement(target: ActionTargetInput):
    statement = (
        select(
            LicenseAssignment.id.label("assignment_id"),
            LicenseAssignment.user_id.label("assignment_user_id"),
            LicenseAssignment.department_id.label("assignment_department_id"),
            LicenseAssignment.status.label("assignment_status"),
            LicenseAssignment.last_used_at,
            LicenseAssignment.is_mandatory,
            LicenseAssignment.is_exception,
            DirectoryUser.id.label("directory_user_id"),
            DirectoryUser.department_id.label("directory_user_department_id"),
            DirectoryUser.full_name.label("user_display_label"),
            DirectoryUser.account_type,
            License.id.label("license_id"),
            License.product_name.label("license_product"),
            License.vendor.label("license_vendor"),
            License.monthly_cost_usd,
        )
        .select_from(LicenseAssignment)
        .outerjoin(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
        .outerjoin(License, License.id == LicenseAssignment.license_id)
        .order_by(LicenseAssignment.id)
        .limit(MAX_PREVIEW_RECORDS + 1)
    )

    assignment_ids = [
        reference.record_id
        for reference in target.targets
        if reference.record_type == "license_assignment"
    ]
    user_ids = [
        reference.record_id
        for reference in target.targets
        if reference.record_type == "directory_user"
    ]
    selector_conditions = []
    if assignment_ids:
        selector_conditions.append(LicenseAssignment.id.in_(assignment_ids))
    if user_ids:
        selector_conditions.append(LicenseAssignment.user_id.in_(user_ids))

    if selector_conditions:
        return statement.where(or_(*selector_conditions))
    if target.department_id is not None:
        return statement.where(LicenseAssignment.department_id == target.department_id)
    if target.scope_type == "global":
        return statement
    raise ReclaimPreviewAuthorizationError(
        "A department-backed or global scope is required."
    )


def _candidate_from_mapping(row) -> ReclaimCandidateRow:
    monthly_cost = row["monthly_cost_usd"]
    return ReclaimCandidateRow(
        assignment_id=row["assignment_id"],
        assignment_user_id=row["assignment_user_id"],
        assignment_department_id=row["assignment_department_id"],
        assignment_status=row["assignment_status"],
        last_used_at=row["last_used_at"],
        is_mandatory=bool(row["is_mandatory"]),
        is_exception=bool(row["is_exception"]),
        directory_user_id=row["directory_user_id"],
        directory_user_department_id=row["directory_user_department_id"],
        user_display_label=row["user_display_label"],
        account_type=row["account_type"],
        license_id=row["license_id"],
        license_product=row["license_product"],
        license_vendor=row["license_vendor"],
        monthly_cost_usd=(
            _money(Decimal(monthly_cost)) if monthly_cost is not None else None
        ),
    )


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
                DataResource.table_name.in_(RECLAIM_RESOURCE_TABLES),
            )
        ).all()
    }
    if set(resources) != set(RECLAIM_RESOURCE_TABLES):
        raise ReclaimPreviewAuthorizationError(
            "The action is not authorized for the required resources."
        )

    ordered_resources = tuple(resources[table] for table in RECLAIM_RESOURCE_TABLES)
    snapshots: list[ResourceAccessDecisionSnapshot] = []
    for resource in ordered_resources:
        decision = authorize_resource_access(
            requester,
            "action:request",
            resource,
            {"scope_type": target.scope_type, "scope_key": target.scope_key},
        )
        snapshots.append(
            ResourceAccessDecisionSnapshot(
                table_name=resource.table_name,
                allowed=decision.allowed and resource.is_queryable is True,
                required_permission=decision.required_permission,
                matched_scopes=tuple(decision.matched_scopes),
            )
        )
        if not decision.allowed or resource.is_queryable is not True:
            raise ReclaimPreviewAuthorizationError(
                "The action is not authorized for the required resources."
            )
    return ordered_resources, tuple(snapshots)


def _department_scopes_for_rows(
    db: Session,
    rows: tuple[ReclaimCandidateRow, ...],
) -> dict[uuid.UUID, AccessScope]:
    department_ids = sorted(
        {row.assignment_department_id for row in rows},
        key=str,
    )
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
    rows: tuple[ReclaimCandidateRow, ...],
    *,
    target: ActionTargetInput,
    department_scopes: dict[uuid.UUID, AccessScope],
    now: datetime,
) -> tuple[
    tuple[ReclaimEligibleRecord, ...],
    tuple[ReclaimSkippedRecord, ...],
    tuple[ReclaimAdminOverrideRecord, ...],
]:
    eligible: list[ReclaimEligibleRecord] = []
    skipped: list[ReclaimSkippedRecord] = []
    overrides: list[ReclaimAdminOverrideRecord] = []
    normal_cutoff = now - timedelta(days=NORMAL_ELIGIBILITY_DAYS)
    high_confidence_cutoff = now - timedelta(days=HIGH_CONFIDENCE_DAYS)

    for row in rows:
        scope = department_scopes.get(row.assignment_department_id)
        safe_scope_type = scope.scope_type if scope is not None else target.scope_type
        safe_scope_key = scope.scope_key if scope is not None else target.scope_key
        structural_error = (
            scope is None
            or row.directory_user_id is None
            or row.directory_user_department_id != row.assignment_department_id
            or not row.user_display_label
            or row.license_id is None
            or not row.license_product
            or not row.license_vendor
            or row.monthly_cost_usd is None
            or not row.monthly_cost_usd.is_finite()
            or row.monthly_cost_usd < 0
        )

        skip_code: str | None = None
        if row.assignment_status == AssignmentStatus.RECLAIMED.value:
            skip_code = SKIP_RECLAIMED
        elif row.assignment_status == AssignmentStatus.SUSPENDED.value:
            skip_code = SKIP_SUSPENDED
        elif row.assignment_status != AssignmentStatus.ACTIVE.value or structural_error:
            skip_code = SKIP_INVALID
        elif row.last_used_at is not None and _as_utc(row.last_used_at) >= normal_cutoff:
            skip_code = SKIP_RECENT

        high_confidence = row.last_used_at is None or (
            _as_utc(row.last_used_at) < high_confidence_cutoff
        )
        if skip_code is not None:
            skipped.append(
                _skipped_record(
                    row,
                    scope=scope,
                    scope_type=safe_scope_type,
                    scope_key=safe_scope_key,
                    reason_code=skip_code,
                    high_confidence=high_confidence,
                )
            )
            continue

        assert scope is not None
        assert row.directory_user_id is not None
        assert row.user_display_label is not None
        assert row.license_product is not None
        assert row.license_vendor is not None
        assert row.monthly_cost_usd is not None
        monthly_cost_usd = _money(row.monthly_cost_usd)

        override_codes: list[str] = []
        if _is_cross_scope(row, target):
            override_codes.append(OVERRIDE_CROSS_SCOPE)
        if row.account_type == AccountType.SERVICE.value:
            override_codes.append(OVERRIDE_SERVICE_ACCOUNT)
        elif row.account_type != AccountType.HUMAN.value:
            skipped.append(
                _skipped_record(
                    row,
                    scope=scope,
                    scope_type=scope.scope_type,
                    scope_key=scope.scope_key,
                    reason_code=SKIP_INVALID,
                    high_confidence=high_confidence,
                )
            )
            continue
        if row.is_mandatory:
            override_codes.append(OVERRIDE_MANDATORY)
        if row.is_exception:
            override_codes.append(OVERRIDE_EXCEPTION)

        eligibility_code = (
            ELIGIBLE_NO_USAGE if row.last_used_at is None else ELIGIBLE_UNUSED
        )
        if override_codes:
            primary_reason = override_codes[0]
            overrides.append(
                ReclaimAdminOverrideRecord(
                    record_type="license_assignment",
                    record_id=row.assignment_id,
                    scope_type=scope.scope_type,
                    scope_key=scope.scope_key,
                    reason_code=primary_reason,
                    reason=SAFE_REASONS[primary_reason],
                    directory_user_id=row.directory_user_id,
                    department_id=row.assignment_department_id,
                    scope_id=scope.id,
                    user_display_label=row.user_display_label,
                    license_product=row.license_product,
                    license_vendor=row.license_vendor,
                    last_used_at=row.last_used_at,
                    monthly_cost_usd=monthly_cost_usd,
                    high_confidence=high_confidence,
                    override_reason_codes=tuple(override_codes),
                )
            )
            continue

        eligible.append(
            ReclaimEligibleRecord(
                record_type="license_assignment",
                record_id=row.assignment_id,
                scope_type=scope.scope_type,
                scope_key=scope.scope_key,
                safe_summary=row.user_display_label,
                directory_user_id=row.directory_user_id,
                department_id=row.assignment_department_id,
                scope_id=scope.id,
                user_display_label=row.user_display_label,
                license_product=row.license_product,
                license_vendor=row.license_vendor,
                last_used_at=row.last_used_at,
                monthly_cost_usd=monthly_cost_usd,
                reason_code=eligibility_code,
                high_confidence=high_confidence,
            )
        )

    return tuple(eligible), tuple(skipped), tuple(overrides)


def _skipped_record(
    row: ReclaimCandidateRow,
    *,
    scope: AccessScope | None,
    scope_type: str,
    scope_key: str,
    reason_code: str,
    high_confidence: bool,
) -> ReclaimSkippedRecord:
    return ReclaimSkippedRecord(
        record_type="license_assignment",
        record_id=row.assignment_id,
        scope_type=scope_type,
        scope_key=scope_key,
        reason_code=reason_code,
        reason=SAFE_REASONS[reason_code],
        directory_user_id=row.directory_user_id,
        department_id=row.assignment_department_id,
        scope_id=scope.id if scope is not None else None,
        user_display_label=row.user_display_label,
        license_product=row.license_product,
        license_vendor=row.license_vendor,
        last_used_at=row.last_used_at,
        monthly_cost_usd=_safe_monthly_cost(row.monthly_cost_usd),
        high_confidence=high_confidence,
    )


def _missing_selector_records(
    target: ActionTargetInput,
    rows: tuple[ReclaimCandidateRow, ...],
) -> tuple[ReclaimSkippedRecord, ...]:
    returned_assignment_ids = {row.assignment_id for row in rows}
    returned_user_ids = {row.assignment_user_id for row in rows}
    missing: list[ReclaimSkippedRecord] = []
    for reference in target.targets:
        if reference.record_type == "license_assignment":
            found = reference.record_id in returned_assignment_ids
        elif reference.record_type == "directory_user":
            found = reference.record_id in returned_user_ids
        else:
            found = False
        if found:
            continue
        missing.append(
            ReclaimSkippedRecord(
                record_type=reference.record_type,
                record_id=reference.record_id,
                scope_type=target.scope_type,
                scope_key=target.scope_key,
                reason_code=SKIP_UNAVAILABLE,
                reason=SAFE_REASONS[SKIP_UNAVAILABLE],
            )
        )
    return tuple(missing)


def _policy_flags(
    overrides: tuple[ReclaimAdminOverrideRecord, ...],
    *,
    actionable_count: int,
    global_scope: bool,
) -> tuple[PolicyFlag, ...]:
    codes = {
        code for record in overrides for code in record.override_reason_codes
    }
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


def _is_cross_scope(row: ReclaimCandidateRow, target: ActionTargetInput) -> bool:
    return (
        target.scope_type != "department"
        or target.department_id is None
        or row.assignment_department_id != target.department_id
    )


def _sum_costs(records) -> Decimal:
    return _money(sum((record.monthly_cost_usd for record in records), Decimal("0")))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _safe_monthly_cost(value: Decimal | None) -> Decimal | None:
    if value is None or not value.is_finite() or value < 0:
        return None
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _engine_from_session(db: Session) -> Engine:
    bind = db.get_bind()
    if isinstance(bind, Engine):
        return bind
    if isinstance(bind, Connection):
        return bind.engine
    raise TypeError("Reclaim preview requires a SQLAlchemy Session with an engine bind.")


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
        raise ReclaimPreviewError("The secure action preview read boundary is unavailable.")
