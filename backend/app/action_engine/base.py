from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext
from app.models.product import SupportedActionType


@dataclass(frozen=True, kw_only=True)
class ActionTargetReference:
    """A deterministic identifier selected by backend action logic."""

    record_type: str
    record_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ActionTargetInput:
    """Validated input to an action handler; never an LLM-produced row set."""

    action_type: SupportedActionType
    scope_type: str
    scope_key: str
    targets: tuple[ActionTargetReference, ...]
    reason: str
    source_query_run_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class EligibleRecordDescriptor:
    record_type: str
    record_id: uuid.UUID
    scope_type: str
    scope_key: str
    safe_summary: str | None = None


@dataclass(frozen=True, kw_only=True)
class SkippedRecordDescriptor:
    record_type: str
    record_id: uuid.UUID
    scope_type: str
    scope_key: str
    reason_code: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class AdminOverrideRecordDescriptor:
    record_type: str
    record_id: uuid.UUID
    scope_type: str
    scope_key: str
    reason_code: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class SafeEstimatedImpact:
    metric_key: str
    value: int | float | Decimal
    unit: str
    description: str


@dataclass(frozen=True, kw_only=True)
class PolicyFlag:
    code: str
    reason: str
    requires_admin: bool
    admin_overridable: bool


@dataclass(frozen=True, kw_only=True)
class PreviewTimestamps:
    generated_at: datetime
    expires_at: datetime


@dataclass(frozen=True, kw_only=True)
class AccessContextSnapshot:
    app_user_id: uuid.UUID
    permissions: tuple[str, ...]
    assigned_scopes: tuple[str, ...]
    has_global_scope: bool


@dataclass(frozen=True, kw_only=True)
class AccessDecisionSnapshot:
    allowed: bool
    reason: str
    required_permission: str | None
    matched_scopes: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class ActionPreview:
    action_type: SupportedActionType
    target_input: ActionTargetInput
    eligible_records: tuple[EligibleRecordDescriptor, ...]
    skipped_records: tuple[SkippedRecordDescriptor, ...]
    admin_override_records: tuple[AdminOverrideRecordDescriptor, ...]
    estimated_impact: tuple[SafeEstimatedImpact, ...]
    policy_flags: tuple[PolicyFlag, ...]
    timestamps: PreviewTimestamps
    access_context_snapshot: AccessContextSnapshot
    access_decision_snapshot: AccessDecisionSnapshot


@dataclass(frozen=True, kw_only=True)
class RevalidationResult:
    eligible_records: tuple[EligibleRecordDescriptor, ...]
    skipped_records: tuple[SkippedRecordDescriptor, ...]
    admin_override_records: tuple[AdminOverrideRecordDescriptor, ...]
    policy_flags: tuple[PolicyFlag, ...]
    revalidated_at: datetime


@dataclass(frozen=True, kw_only=True)
class ExecutionResult:
    action_request_id: uuid.UUID
    executed_record_ids: tuple[uuid.UUID, ...]
    skipped_records: tuple[SkippedRecordDescriptor, ...]
    completed_at: datetime
    idempotency_key: str


@runtime_checkable
class ActionHandler(Protocol):
    """Deterministic handler boundary implemented by approved domain code only."""

    action_type: SupportedActionType

    def build_preview(
        self,
        *,
        db: Session,
        target: ActionTargetInput,
        requester: UserAccessContext,
        now: datetime,
    ) -> ActionPreview: ...

    def revalidate(
        self,
        *,
        db: Session,
        preview: ActionPreview,
        approver: UserAccessContext,
        now: datetime,
    ) -> RevalidationResult: ...

    def execute(
        self,
        *,
        db: Session,
        action_request_id: uuid.UUID,
        approved_by_app_user_id: uuid.UUID,
        revalidation: RevalidationResult,
        idempotency_key: str,
        now: datetime,
    ) -> ExecutionResult: ...
