from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.action_engine.audit import build_action_audit_log
from app.action_engine.notifications import (
    build_pending_approval_notifications,
    eligible_approvers,
)
from app.action_engine.policy import evaluate_action_approval, evaluate_action_request
from app.action_engine.preview import (
    InvalidPreviewSnapshotError,
    build_reclaim_preview_storage,
    safe_policy_details,
    safe_reclaim_preview,
    validate_reclaim_snapshot,
)
from app.action_engine.registry import ActionRegistry, UnknownActionTypeError
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.domains.it_operations.actions.reclaim_unused_license import (
    ReclaimActionPreview,
    ReclaimPreviewAuthorizationError,
    ReclaimPreviewError,
    ReclaimPreviewTooLargeError,
)
from app.models.product import (
    AccessScope,
    ActionPriority,
    ActionRequest,
    ActionRequestStatus,
    AppAuditLog,
    AppUser,
    ApprovalRequest,
    ApprovalStatus,
    QueryRun,
    RunStatus,
    SupportedActionType,
)
from app.schemas.actions import (
    ActionCancelRequest,
    ActionPreviewRequest,
    ActionSubmitRequest,
)


PREVIEW_LIFETIME = timedelta(minutes=30)
PENDING_APPROVAL_LIFETIME = timedelta(hours=24)
RECLAIM_TEMPLATE_ID = "unused_licenses_by_department"
RECLAIM_PROVENANCE_REQUIRED_TABLES = frozenset(
    {"license_assignments", "licenses"}
)
RECLAIM_PROVENANCE_ALLOWED_TABLES = frozenset(
    {"departments", "directory_users", "license_assignments", "licenses"}
)


@dataclass(frozen=True)
class ActionServiceError(Exception):
    code: str
    message: str
    status_code: int


class ActionLifecycleService:
    def __init__(
        self,
        *,
        registry: ActionRegistry,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_preview(
        self,
        db: Session,
        *,
        current_user: AppUser,
        payload: ActionPreviewRequest,
    ) -> dict[str, Any]:
        access_context = build_user_access_context(current_user, db)
        if not access_context.has_permission("can_request_action"):
            raise _forbidden()
        handler = self._registered_handler(payload.action_type)
        scope = _resolve_request_scope(db, payload.scope_id, access_context)
        _validate_department_bridge(scope, payload.department_id)
        source_query_run = _validate_source_query_run(
            db,
            current_user=current_user,
            source_query_run_id=payload.source_query_run_id,
        )
        target = _target_input(payload, scope)
        now = _as_utc(self._clock())

        try:
            preview = handler.build_preview(
                db=db,
                target=target,
                requester=access_context,
                now=now,
            )
        except ReclaimPreviewAuthorizationError as exc:
            raise _forbidden() from exc
        except ReclaimPreviewTooLargeError as exc:
            raise ActionServiceError(
                code="ACTION_PREVIEW_TOO_LARGE",
                message="The requested action preview exceeds the supported record limit.",
                status_code=422,
            ) from exc
        except ReclaimPreviewError as exc:
            raise ActionServiceError(
                code="ACTION_PREVIEW_FAILED",
                message="The action preview could not be created safely.",
                status_code=500,
            ) from exc
        if not isinstance(preview, ReclaimActionPreview):
            raise ActionServiceError(
                code="ACTION_PREVIEW_FAILED",
                message="The action preview could not be created safely.",
                status_code=500,
            )
        if (
            _as_utc(preview.timestamps.generated_at) != now
            or _as_utc(preview.timestamps.expires_at) != now + PREVIEW_LIFETIME
        ):
            raise ActionServiceError(
                code="ACTION_PREVIEW_FAILED",
                message="The action preview could not be created safely.",
                status_code=500,
            )

        storage = build_reclaim_preview_storage(preview)
        action_request_id = uuid.uuid4()
        action_request = ActionRequest(
            id=action_request_id,
            action_type=preview.action_type.value,
            requested_by_app_user_id=current_user.id,
            source_query_run_id=(source_query_run.id if source_query_run else None),
            department_id=scope.department_id,
            scope_id=scope.id,
            scope_type=scope.scope_type,
            scope_key=scope.scope_key,
            access_context_snapshot_json=storage.access_context_snapshot_json,
            access_decision_snapshot_json=storage.access_decision_snapshot_json,
            preview_json=storage.preview_json,
            policy_flags_json=storage.policy_flags_json,
            skipped_records_json=storage.skipped_records_json,
            status=ActionRequestStatus.DRAFT_PREVIEW.value,
            priority=_default_priority(access_context),
            reason=payload.reason,
            requires_admin=preview.requires_admin,
            record_count=storage.record_count,
            skipped_count=storage.skipped_count,
            idempotency_key=f"action-request:{action_request_id}",
            preview_generated_at=preview.timestamps.generated_at,
            preview_expires_at=preview.timestamps.expires_at,
            expires_at=preview.timestamps.expires_at,
        )
        try:
            validate_reclaim_snapshot(action_request)
        except InvalidPreviewSnapshotError as exc:
            raise ActionServiceError(
                code="ACTION_PREVIEW_FAILED",
                message="The action preview could not be created safely.",
                status_code=500,
            ) from exc
        policy_flag_codes = [flag.code for flag in preview.policy_flags]
        audit_metadata: dict[str, Any] = {
            "policy_flag_codes": policy_flag_codes,
        }
        if source_query_run is not None:
            audit_metadata["source_query_run_id"] = source_query_run.id
        audit_log = build_action_audit_log(
            actor=current_user,
            action_request=action_request,
            event_type="action_preview_created",
            action="preview",
            status=ActionRequestStatus.DRAFT_PREVIEW.value,
            summary="Reclaim unused license preview created.",
            metadata=audit_metadata,
            before_state=None,
            after_state={"status": ActionRequestStatus.DRAFT_PREVIEW.value},
        )
        db.add_all([action_request, audit_log])
        _commit_or_fail(db, "The action preview could not be saved safely.")
        db.refresh(action_request)
        return _serialize_action_request(
            action_request,
            now=now,
            include_reason=False,
            include_policy_details=access_context.has_permission("can_view_sql"),
        )

    def submit_request(
        self,
        db: Session,
        *,
        current_user: AppUser,
        payload: ActionSubmitRequest,
    ) -> dict[str, Any]:
        access_context = build_user_access_context(current_user, db)
        if not access_context.has_permission("can_request_action"):
            raise _forbidden()
        action_request = _owned_action_for_update(
            db,
            payload.action_request_id,
            current_user.id,
        )
        self._registered_handler(action_request.action_type)
        now = _as_utc(self._clock())

        if action_request.status == ActionRequestStatus.PENDING_APPROVAL.value:
            if _deadline_passed(action_request.expires_at, now):
                _expire_action_request(
                    db,
                    actor=current_user,
                    action_request=action_request,
                    now=now,
                    expiration_kind="pending_approval",
                )
            _require_valid_snapshot(action_request)
            approval = action_request.approval_request
            if approval is None:
                raise _conflict("The action request is not in a valid state.")
            return _serialize_action_request(
                action_request,
                now=now,
                include_reason=True,
                include_policy_details=access_context.has_permission("can_view_sql"),
                approval=approval,
            )

        if action_request.status != ActionRequestStatus.DRAFT_PREVIEW.value:
            raise _conflict("The action request has already been processed.")
        if _deadline_passed(action_request.preview_expires_at, now):
            _expire_action_request(
                db,
                actor=current_user,
                action_request=action_request,
                now=now,
                expiration_kind="draft_preview",
            )
        _require_valid_snapshot(action_request)
        if action_request.record_count <= 0:
            raise ActionServiceError(
                code="ACTION_NOT_ELIGIBLE",
                message="The action preview contains no eligible records.",
                status_code=422,
            )

        previous_status = action_request.status
        action_request.status = ActionRequestStatus.PENDING_APPROVAL.value
        action_request.reason = payload.reason
        action_request.submitted_at = now
        action_request.expires_at = now + PENDING_APPROVAL_LIFETIME
        approval = ApprovalRequest(
            id=uuid.uuid4(),
            requester_user_id=current_user.id,
            decided_by_user_id=None,
            query_run_id=None,
            action_request_id=action_request.id,
            request_type=action_request.action_type,
            title="Reclaim unused licenses",
            description=payload.reason,
            status=ApprovalStatus.PENDING.value,
            target_type="action_request",
            target_id=action_request.id,
            payload={
                "action_type": action_request.action_type,
                "record_count": action_request.record_count,
                "skipped_count": action_request.skipped_count,
                "requires_admin": action_request.requires_admin,
                "scope": {
                    "id": str(action_request.scope_id),
                    "type": action_request.scope_type,
                    "key": action_request.scope_key,
                },
            },
            policy_snapshot=_safe_approval_policy_snapshot(action_request),
            required_approver_role=(
                "admin" if action_request.requires_admin else "analyst_or_admin"
            ),
            expires_at=action_request.expires_at,
        )
        recipients = eligible_approvers(db, action_request=action_request)
        notifications = build_pending_approval_notifications(
            action_request=action_request,
            approval_request=approval,
            recipients=recipients,
        )
        audit_log = build_action_audit_log(
            actor=current_user,
            action_request=action_request,
            approval_request=approval,
            event_type="action_requested",
            action="request",
            status=ActionRequestStatus.PENDING_APPROVAL.value,
            summary="Reclaim unused license request submitted for approval.",
            metadata={
                "approval_request_id": approval.id,
                "notification_count": len(notifications),
                "policy_flag_codes": _policy_flag_codes(action_request),
            },
            before_state={"status": previous_status},
            after_state={"status": ActionRequestStatus.PENDING_APPROVAL.value},
        )
        db.add_all([action_request, approval, *notifications, audit_log])
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = _owned_action(db, action_request.id, current_user.id)
            if (
                existing is not None
                and existing.status == ActionRequestStatus.PENDING_APPROVAL.value
                and existing.approval_request is not None
            ):
                return _serialize_action_request(
                    existing,
                    now=now,
                    include_reason=True,
                    include_policy_details=access_context.has_permission("can_view_sql"),
                    approval=existing.approval_request,
                )
            raise _conflict("The action request has already been processed.")
        except SQLAlchemyError as exc:
            db.rollback()
            raise ActionServiceError(
                code="INTERNAL_ERROR",
                message="The action request could not be submitted safely.",
                status_code=500,
            ) from exc

        db.refresh(action_request)
        db.refresh(approval)
        return _serialize_action_request(
            action_request,
            now=now,
            include_reason=True,
            include_policy_details=access_context.has_permission("can_view_sql"),
            approval=approval,
        )

    def get_detail(
        self,
        db: Session,
        *,
        current_user: AppUser,
        action_request_id: uuid.UUID,
    ) -> dict[str, Any]:
        action_request = db.get(ActionRequest, action_request_id)
        if action_request is None:
            raise _not_found()
        access_context = build_user_access_context(current_user, db)
        now = _as_utc(self._clock())
        if not _can_view_action_request(
            action_request,
            current_user=current_user,
            access_context=access_context,
            now=now,
        ):
            raise _not_found()
        self._registered_handler(action_request.action_type)
        timeline = db.scalars(
            select(AppAuditLog)
            .where(AppAuditLog.action_request_id == action_request.id)
            .order_by(
                AppAuditLog.created_at,
                case(
                    (AppAuditLog.event_type == "action_preview_created", 0),
                    (AppAuditLog.event_type == "action_requested", 1),
                    (AppAuditLog.event_type == "action_cancelled", 2),
                    (AppAuditLog.event_type == "action_expired", 2),
                    else_=99,
                ),
                AppAuditLog.id,
            )
        ).all()
        try:
            return _serialize_action_request(
                action_request,
                now=now,
                include_reason=True,
                include_policy_details=access_context.has_permission("can_view_sql"),
                include_global_audit_details=access_context.has_permission(
                    "can_view_global_audit"
                ),
                approval=action_request.approval_request,
                timeline=tuple(timeline),
            )
        except InvalidPreviewSnapshotError as exc:
            raise ActionServiceError(
                code="ACTION_PREVIEW_UNAVAILABLE",
                message="The stored action preview is unavailable.",
                status_code=500,
            ) from exc

    def cancel_request(
        self,
        db: Session,
        *,
        current_user: AppUser,
        action_request_id: uuid.UUID,
        payload: ActionCancelRequest,
    ) -> dict[str, Any]:
        access_context = build_user_access_context(current_user, db)
        if not access_context.has_permission("can_request_action"):
            raise _forbidden()
        action_request = _owned_action_for_update(
            db,
            action_request_id,
            current_user.id,
        )
        self._registered_handler(action_request.action_type)
        now = _as_utc(self._clock())
        if (
            action_request.status == ActionRequestStatus.PENDING_APPROVAL.value
            and _deadline_passed(action_request.expires_at, now)
        ):
            _expire_action_request(
                db,
                actor=current_user,
                action_request=action_request,
                now=now,
                expiration_kind="pending_approval",
            )
        if action_request.status != ActionRequestStatus.PENDING_APPROVAL.value:
            raise ActionServiceError(
                code="ACTION_CANNOT_BE_CANCELLED",
                message="The action request can no longer be cancelled.",
                status_code=409,
            )
        _require_valid_snapshot(action_request)
        approval = action_request.approval_request
        if approval is None or approval.status != ApprovalStatus.PENDING.value:
            raise _conflict("The action request is not in a valid state.")

        previous_action_status = action_request.status
        previous_approval_status = approval.status
        action_request.status = ActionRequestStatus.CANCELLED.value
        approval.status = ApprovalStatus.CANCELLED.value
        approval.decision_reason = payload.reason
        approval.decided_at = now
        audit_log = build_action_audit_log(
            actor=current_user,
            action_request=action_request,
            approval_request=approval,
            event_type="action_cancelled",
            action="cancel",
            status=ActionRequestStatus.CANCELLED.value,
            summary="Reclaim unused license request cancelled by the requester.",
            metadata={
                "approval_request_id": approval.id,
                "cancellation_reason": payload.reason,
            },
            before_state={
                "action_status": previous_action_status,
                "approval_status": previous_approval_status,
            },
            after_state={
                "action_status": ActionRequestStatus.CANCELLED.value,
                "approval_status": ApprovalStatus.CANCELLED.value,
            },
        )
        db.add_all([action_request, approval, audit_log])
        _commit_or_fail(db, "The action request could not be cancelled safely.")
        db.refresh(action_request)
        db.refresh(approval)
        return _serialize_action_request(
            action_request,
            now=now,
            include_reason=True,
            include_policy_details=access_context.has_permission("can_view_sql"),
            approval=approval,
        )

    def _registered_handler(self, action_type: SupportedActionType | str):
        try:
            return self._registry.get(action_type)
        except UnknownActionTypeError as exc:
            raise ActionServiceError(
                code="ACTION_TYPE_NOT_SUPPORTED",
                message="The requested action type is not available.",
                status_code=422,
            ) from exc


def _resolve_request_scope(
    db: Session,
    scope_id: uuid.UUID,
    access_context: UserAccessContext,
) -> AccessScope:
    scope = db.get(AccessScope, scope_id)
    if scope is None:
        raise _scope_not_found()
    decision = evaluate_action_request(
        access_context,
        scope_type=scope.scope_type,
        scope_key=scope.scope_key,
    )
    if not decision.allowed:
        if decision.code == "request_permission_required":
            raise _forbidden()
        raise _scope_not_found()
    if scope.scope_type == "department" and scope.department_id is not None:
        return scope
    if (
        scope.scope_type == "global"
        and scope.scope_key == "global"
        and scope.department_id is None
    ):
        return scope
    raise _scope_not_found()


def _validate_department_bridge(
    scope: AccessScope,
    requested_department_id: uuid.UUID | None,
) -> None:
    if requested_department_id is None:
        return
    if scope.department_id != requested_department_id:
        raise ActionServiceError(
            code="ACTION_SCOPE_MISMATCH",
            message="The requested scope is invalid.",
            status_code=400,
        )


def _validate_source_query_run(
    db: Session,
    *,
    current_user: AppUser,
    source_query_run_id: uuid.UUID | None,
) -> QueryRun | None:
    if source_query_run_id is None:
        return None
    query_run = db.get(QueryRun, source_query_run_id)
    if (
        query_run is None
        or query_run.user_id != current_user.id
        or query_run.status != RunStatus.SUCCEEDED.value
    ):
        raise ActionServiceError(
            code="QUERY_RUN_NOT_FOUND",
            message="Query run was not found.",
            status_code=404,
        )
    metadata = query_run.query_metadata
    if not isinstance(metadata, dict):
        raise _invalid_source_query()
    raw_tables = metadata.get("referenced_tables")
    if not isinstance(raw_tables, list):
        raise _invalid_source_query()
    tables = {
        table.strip().lower()
        for table in raw_tables
        if isinstance(table, str) and table.strip()
    }
    if (
        not RECLAIM_PROVENANCE_REQUIRED_TABLES.issubset(tables)
        or not tables.issubset(RECLAIM_PROVENANCE_ALLOWED_TABLES)
    ):
        raise _invalid_source_query()

    if (
        metadata.get("provider") == "domain_pack_template"
        and metadata.get("template_id") != RECLAIM_TEMPLATE_ID
    ):
        raise _invalid_source_query()
    return query_run


def _target_input(payload: ActionPreviewRequest, scope: AccessScope):
    from app.action_engine.base import ActionTargetInput, ActionTargetReference

    references = tuple(
        [
            ActionTargetReference(record_type="directory_user", record_id=user_id)
            for user_id in payload.target_user_ids or []
        ]
        + [
            ActionTargetReference(
                record_type="license_assignment",
                record_id=assignment_id,
            )
            for assignment_id in payload.license_assignment_ids or []
        ]
    )
    return ActionTargetInput(
        action_type=payload.action_type,
        scope_type=scope.scope_type,
        scope_key=scope.scope_key,
        scope_id=scope.id,
        department_id=scope.department_id,
        targets=references,
        reason=payload.reason,
        source_query_run_id=payload.source_query_run_id,
    )


def _owned_action_for_update(
    db: Session,
    action_request_id: uuid.UUID,
    current_user_id: uuid.UUID,
) -> ActionRequest:
    action_request = db.scalar(
        select(ActionRequest)
        .where(ActionRequest.id == action_request_id)
        .with_for_update()
    )
    if (
        action_request is None
        or action_request.requested_by_app_user_id != current_user_id
    ):
        raise _not_found()
    return action_request


def _owned_action(
    db: Session,
    action_request_id: uuid.UUID,
    current_user_id: uuid.UUID,
) -> ActionRequest | None:
    action_request = db.get(ActionRequest, action_request_id)
    if (
        action_request is None
        or action_request.requested_by_app_user_id != current_user_id
    ):
        return None
    return action_request


def _expire_action_request(
    db: Session,
    *,
    actor: AppUser,
    action_request: ActionRequest,
    now: datetime,
    expiration_kind: str,
) -> None:
    previous_status = action_request.status
    approval = action_request.approval_request
    previous_approval_status = approval.status if approval is not None else None
    action_request.status = ActionRequestStatus.EXPIRED.value
    if approval is not None and approval.status == ApprovalStatus.PENDING.value:
        approval.status = ApprovalStatus.EXPIRED.value
        approval.decided_at = now
    audit_log = build_action_audit_log(
        actor=actor,
        action_request=action_request,
        approval_request=approval,
        event_type="action_expired",
        action="expire",
        status=ActionRequestStatus.EXPIRED.value,
        summary=(
            "Action preview expired."
            if expiration_kind == "draft_preview"
            else "Pending action request expired."
        ),
        metadata={"expiration_kind": expiration_kind},
        before_state={
            "action_status": previous_status,
            "approval_status": previous_approval_status,
        },
        after_state={
            "action_status": ActionRequestStatus.EXPIRED.value,
            "approval_status": (
                ApprovalStatus.EXPIRED.value if approval is not None else None
            ),
        },
    )
    db.add_all([action_request, audit_log])
    if approval is not None:
        db.add(approval)
    _commit_or_fail(db, "The expired action request could not be updated safely.")
    raise ActionServiceError(
        code="ACTION_REQUEST_EXPIRED",
        message="The action request has expired. Create a new preview.",
        status_code=410,
    )


def _can_view_action_request(
    action_request: ActionRequest,
    *,
    current_user: AppUser,
    access_context: UserAccessContext,
    now: datetime,
) -> bool:
    if action_request.requested_by_app_user_id == current_user.id:
        return True
    if action_request.status != ActionRequestStatus.PENDING_APPROVAL.value:
        return False
    if _deadline_passed(action_request.expires_at, now):
        return False
    return _approval_decision_allowed(action_request, access_context)


def _approval_decision_allowed(
    action_request: ActionRequest,
    access_context: UserAccessContext,
) -> bool:
    policy = action_request.policy_flags_json
    requires_policy_override = (
        isinstance(policy, dict)
        and (
            policy.get("requires_policy_override") is True
            or policy.get("revalidation_requires_policy_override") is True
        )
    )
    crosses_scopes = (
        action_request.scope_type == "global"
        or action_request.record_count > 20
        or (
            isinstance(policy, dict)
            and (
                policy.get("crosses_scopes") is True
                or policy.get("revalidation_crosses_scopes") is True
            )
        )
    )
    decision = evaluate_action_approval(
        access_context,
        requester_app_user_id=action_request.requested_by_app_user_id,
        scope_type=action_request.scope_type or "",
        scope_key=action_request.scope_key or "",
        record_count=action_request.record_count,
        crosses_scopes=crosses_scopes,
        requires_policy_override=requires_policy_override,
    )
    return decision.allowed


def _serialize_action_request(
    action_request: ActionRequest,
    *,
    now: datetime,
    include_reason: bool,
    include_policy_details: bool,
    include_global_audit_details: bool = False,
    approval: ApprovalRequest | None = None,
    timeline: tuple[AppAuditLog, ...] = (),
) -> dict[str, Any]:
    preview = safe_reclaim_preview(action_request)
    deadline = (
        action_request.preview_expires_at
        if action_request.status == ActionRequestStatus.DRAFT_PREVIEW.value
        else action_request.expires_at
    )
    scope = action_request.scope
    data: dict[str, Any] = {
        "id": str(action_request.id),
        "action_request_id": str(action_request.id),
        "action_type": action_request.action_type,
        "status": action_request.status,
        "priority": action_request.priority,
        "scope": {
            "id": str(action_request.scope_id)
            if action_request.scope_id is not None
            else None,
            "type": action_request.scope_type,
            "key": action_request.scope_key,
            "display_name": scope.display_name if scope is not None else None,
        },
        "preview": preview,
        "generated_at": _timestamp(action_request.preview_generated_at),
        "preview_expires_at": _timestamp(action_request.preview_expires_at),
        "expires_at": _timestamp(deadline),
        "requires_admin": action_request.requires_admin,
        "is_expired": _deadline_passed(deadline, now),
        "submitted_at": _timestamp(action_request.submitted_at),
        "created_at": _timestamp(action_request.created_at),
        "updated_at": _timestamp(action_request.updated_at),
    }
    if include_reason:
        data["reason"] = action_request.reason
    if include_policy_details:
        data["policy_details"] = safe_policy_details(action_request)
    if approval is not None:
        data["approval"] = {
            "id": str(approval.id),
            "status": approval.status,
            "required_approver_role": approval.required_approver_role,
            "created_at": _timestamp(approval.created_at),
            "expires_at": _timestamp(approval.expires_at),
        }
    else:
        data["approval"] = None
    if timeline:
        data["timeline"] = [
            {
                "event_type": event.event_type,
                "status": event.status,
                "summary": event.summary,
                "timestamp": _timestamp(event.created_at),
                "created_at": _timestamp(event.created_at),
                "actor": (
                    {
                        "id": str(event.actor_user_id),
                        "display_name": event.actor.full_name,
                    }
                    if event.actor is not None
                    else None
                ),
                **(
                    {"self_approved": event.self_approved is True}
                    if include_global_audit_details
                    else {}
                ),
            }
            for event in timeline
        ]
    return data


def _safe_approval_policy_snapshot(action_request: ActionRequest) -> dict[str, Any]:
    policy = action_request.policy_flags_json
    if not isinstance(policy, dict):
        return {}
    return {
        "flag_codes": _policy_flag_codes(action_request),
        "requires_admin": action_request.requires_admin,
        "crosses_scopes": policy.get("crosses_scopes") is True,
        "requires_policy_override": policy.get("requires_policy_override") is True,
    }


def _policy_flag_codes(action_request: ActionRequest) -> list[str]:
    policy = action_request.policy_flags_json
    if not isinstance(policy, dict):
        return []
    flags = policy.get("flags")
    if not isinstance(flags, list):
        return []
    return sorted(
        {
            flag["code"]
            for flag in flags
            if isinstance(flag, dict) and isinstance(flag.get("code"), str)
        }
    )


def _require_valid_snapshot(action_request: ActionRequest) -> None:
    try:
        validate_reclaim_snapshot(action_request)
    except InvalidPreviewSnapshotError as exc:
        raise ActionServiceError(
            code="ACTION_PREVIEW_UNAVAILABLE",
            message="The stored action preview is unavailable.",
            status_code=409,
        ) from exc


def _default_priority(access_context: UserAccessContext) -> str:
    if access_context.role in {"manager", "admin"}:
        return ActionPriority.HIGH.value
    return ActionPriority.NORMAL.value


def _deadline_passed(deadline: datetime | None, now: datetime) -> bool:
    return deadline is None or _as_utc(deadline) <= now


def _commit_or_fail(db: Session, message: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ActionServiceError(
            code="INTERNAL_ERROR",
            message=message,
            status_code=500,
        ) from exc


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _forbidden() -> ActionServiceError:
    return ActionServiceError(
        code="FORBIDDEN",
        message="You are not authorized to perform this action.",
        status_code=403,
    )


def _not_found() -> ActionServiceError:
    return ActionServiceError(
        code="ACTION_REQUEST_NOT_FOUND",
        message="Action request was not found.",
        status_code=404,
    )


def _scope_not_found() -> ActionServiceError:
    return ActionServiceError(
        code="ACTION_SCOPE_NOT_FOUND",
        message="Action scope was not found.",
        status_code=404,
    )


def _conflict(message: str) -> ActionServiceError:
    return ActionServiceError(
        code="ACTION_ALREADY_PROCESSED",
        message=message,
        status_code=409,
    )


def _invalid_source_query() -> ActionServiceError:
    return ActionServiceError(
        code="ACTION_SOURCE_QUERY_INVALID",
        message="The source query is not compatible with this action.",
        status_code=400,
    )
