from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.action_engine.action_dispatch import (
    ActionRevalidation,
    lock_action_dependencies,
    require_action_revalidation,
    require_stable_execution_set,
    safe_action_revalidation_flags,
)
from app.action_engine.audit import action_timeline_order, build_action_audit_log
from app.action_engine.notifications import (
    build_action_notification,
    build_pending_approval_notifications,
    eligible_approvers,
)
from app.action_engine.policy import evaluate_action_approval
from app.action_engine.presentation import ActionPresentation, action_presentation
from app.action_engine.preview import safe_action_preview, validate_action_snapshot
from app.action_engine.registry import ActionRegistry, build_default_action_registry
from app.action_engine.runtime_role import (
    reset_action_runtime_role,
    set_action_runtime_role,
)
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.core.rls import build_rls_context, set_rls_context
from app.models.product import (
    ActionPriority,
    ActionRequest,
    ActionRequestStatus,
    AppAuditLog,
    AppUser,
    ApprovalRequest,
    ApprovalStatus,
    Notification,
    UserStatus,
)


APPROVAL_PERMISSIONS = frozenset(
    {
        "can_approve_scoped_action",
        "can_approve_global_action",
        "can_approve_policy_override",
    }
)
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApprovalServiceError(Exception):
    code: str
    message: str
    status_code: int


class ApprovalLifecycleService:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        registry: ActionRegistry | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._registry = registry or build_default_action_registry()

    def list_pending(
        self,
        db: Session,
        *,
        current_user: AppUser,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        context = build_user_access_context(current_user, db)
        if not APPROVAL_PERMISSIONS.intersection(context.permissions):
            raise _forbidden()
        now = _as_utc(self._clock())
        _expire_pending_requests(
            db,
            actor=current_user,
            context=context,
            now=now,
        )
        candidates = db.scalars(
            select(ApprovalRequest)
            .join(ActionRequest, ActionRequest.id == ApprovalRequest.action_request_id)
            .where(
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
                ActionRequest.status == ActionRequestStatus.PENDING_APPROVAL.value,
                ApprovalRequest.expires_at > now,
                ActionRequest.expires_at > now,
            )
            .order_by(
                case(
                    (ActionRequest.priority == ActionPriority.URGENT.value, 0),
                    (ActionRequest.priority == ActionPriority.HIGH.value, 1),
                    else_=2,
                ),
                ActionRequest.created_at,
                ApprovalRequest.id,
            )
        ).all()
        visible = [
            approval
            for approval in candidates
            if approval.action_request is not None
            and _approval_decision(approval.action_request, context).allowed
        ]
        page = visible[offset : offset + limit]
        return {
            "items": [_serialize_pending_item(item) for item in page],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned": len(page),
                "total": len(visible),
            },
        }

    def get_detail(
        self,
        db: Session,
        *,
        current_user: AppUser,
        approval_id: uuid.UUID,
    ) -> dict[str, Any]:
        approval = db.get(ApprovalRequest, approval_id)
        if approval is None or approval.action_request is None:
            raise _not_found()
        action = approval.action_request
        context = build_user_access_context(current_user, db)
        decision = _approval_decision(action, context)
        can_view_global = context.has_permission("can_view_global_audit")
        if not decision.allowed and not can_view_global:
            raise _not_found()
        now = _as_utc(self._clock())
        if (
            action.status == ActionRequestStatus.PENDING_APPROVAL.value
            and _expired(action, approval, now)
        ):
            action, approval = _locked_pair(db, approval_id)
            if (
                action.status == ActionRequestStatus.PENDING_APPROVAL.value
                and approval.status == ApprovalStatus.PENDING.value
                and _expired(action, approval, now)
            ):
                expired = _expire_one(
                    db,
                    actor=current_user,
                    action=action,
                    approval=approval,
                    now=now,
                )
                if not expired:
                    refreshed = db.get(ApprovalRequest, approval_id)
                    if refreshed is None or refreshed.action_request is None:
                        raise _not_found()
                    approval = refreshed
                    action = refreshed.action_request
        return _serialize_approval_detail(
            db,
            approval=approval,
            action=action,
            context=context,
            now=now,
        )

    def reject(
        self,
        db: Session,
        *,
        current_user: AppUser,
        approval_id: uuid.UUID,
        decision_reason: str,
    ) -> dict[str, Any]:
        context = build_user_access_context(current_user, db)
        action, approval = _locked_pair(db, approval_id)
        presentation = action_presentation(action.action_type)
        decision = _approval_decision(action, context)
        if not decision.allowed:
            raise _not_found()
        now = _as_utc(self._clock())
        if (
            action.status == ActionRequestStatus.PENDING_APPROVAL.value
            and approval.status == ApprovalStatus.PENDING.value
            and _expired(action, approval, now)
        ):
            if not _expire_one(
                db,
                actor=current_user,
                action=action,
                approval=approval,
                now=now,
            ):
                raise _already_processed()
            raise _expired_error()
        _require_pending(action, approval, now)
        action_result = db.execute(
            update(ActionRequest)
            .where(
                ActionRequest.id == action.id,
                ActionRequest.status == ActionRequestStatus.PENDING_APPROVAL.value,
                ActionRequest.expires_at > now,
            )
            .values(status=ActionRequestStatus.REJECTED.value)
            .execution_options(synchronize_session=False)
        )
        approval_result = db.execute(
            update(ApprovalRequest)
            .where(
                ApprovalRequest.id == approval.id,
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
                ApprovalRequest.expires_at > now,
            )
            .values(
                status=ApprovalStatus.REJECTED.value,
                decided_by_user_id=current_user.id,
                decision_reason=decision_reason,
                decided_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if action_result.rowcount != 1 or approval_result.rowcount != 1:
            db.rollback()
            raise _already_processed()
        action.status = ActionRequestStatus.REJECTED.value
        approval.status = ApprovalStatus.REJECTED.value
        approval.decided_by_user_id = current_user.id
        approval.decision_reason = decision_reason
        approval.decided_at = now
        audit = build_action_audit_log(
            actor=current_user,
            action_request=action,
            approval_request=approval,
            event_type="action_rejected",
            action="reject",
            status=ActionRequestStatus.REJECTED.value,
            summary=presentation.rejected_summary,
            before_state={
                "action_status": ActionRequestStatus.PENDING_APPROVAL.value,
                "approval_status": ApprovalStatus.PENDING.value,
            },
            after_state={
                "action_status": ActionRequestStatus.REJECTED.value,
                "approval_status": ApprovalStatus.REJECTED.value,
            },
        )
        notification = build_action_notification(
            recipient_user_id=action.requested_by_app_user_id,
            actor_user_id=current_user.id,
            notification_type="action_rejected",
            title="Action request rejected",
            body=presentation.rejected_body,
            action_request=action,
            approval_request=approval,
        )
        db.add(audit)
        db.add_all(_active_notifications(db, [notification]))
        _commit(db, "The approval decision could not be saved safely.")
        return {
            "approval_id": str(approval.id),
            "action_request_id": str(action.id),
            "status": ActionRequestStatus.REJECTED.value,
            "decided_at": _timestamp(now),
        }

    def approve(
        self,
        db: Session,
        *,
        current_user: AppUser,
        approval_id: uuid.UUID,
        decision_reason: str,
    ) -> dict[str, Any]:
        context = build_user_access_context(current_user, db)
        action, approval = _locked_pair(db, approval_id)
        presentation = action_presentation(action.action_type)
        initial_decision = _approval_decision(action, context)
        if not initial_decision.allowed:
            raise _not_found()
        now = _as_utc(self._clock())
        if (
            action.status == ActionRequestStatus.PENDING_APPROVAL.value
            and approval.status == ApprovalStatus.PENDING.value
            and _expired(action, approval, now)
        ):
            if not _expire_one(
                db,
                actor=current_user,
                action=action,
                approval=approval,
                now=now,
            ):
                raise _already_processed()
            raise _expired_error()
        _require_pending(action, approval, now)
        failure_category = "validation_failed"
        try:
            validate_action_snapshot(action)
            handler = self._registry.get(action.action_type)
            set_rls_context(db, build_rls_context(context))
            set_action_runtime_role(db)
            initial_revalidation = require_action_revalidation(
                action.action_type,
                handler.revalidate(
                    db=db,
                    action_request=action,
                    approver=context,
                    now=now,
                ),
            )
            reset_action_runtime_role(db)
            lock_action_dependencies(db, action.action_type, initial_revalidation)
            set_action_runtime_role(db)
            revalidation = require_action_revalidation(
                action.action_type,
                handler.revalidate(
                    db=db,
                    action_request=action,
                    approver=context,
                    now=now,
                ),
            )
            reset_action_runtime_role(db)
            require_stable_execution_set(initial_revalidation, revalidation)

            current_decision = evaluate_action_approval(
                context,
                requester_app_user_id=action.requested_by_app_user_id,
                scope_type=action.scope_type or "",
                scope_key=action.scope_key or "",
                record_count=len(revalidation.executable_records),
                crosses_scopes=revalidation.crosses_scopes,
                requires_policy_override=revalidation.requires_policy_override,
            )
            if not current_decision.allowed:
                if (
                    revalidation.requires_policy_override
                    and current_decision.code == "override_permission_required"
                ):
                    _persist_escalation(
                        db,
                        actor=current_user,
                        action=action,
                        approval=approval,
                        revalidation=revalidation,
                    )
                    raise ApprovalServiceError(
                        code="POLICY_OVERRIDE_REQUIRED",
                        message="Current policy requires an authorized override approver.",
                        status_code=422,
                    )
                raise _forbidden()

            failure_category = "execution_failed"
            claim = db.execute(
                update(ActionRequest)
                .where(
                    ActionRequest.id == action.id,
                    ActionRequest.status == ActionRequestStatus.PENDING_APPROVAL.value,
                    ActionRequest.expires_at > now,
                )
                .values(
                    status=ActionRequestStatus.APPROVED_EXECUTING.value,
                    approved_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if claim.rowcount != 1 or approval.status != ApprovalStatus.PENDING.value:
                db.rollback()
                raise _already_processed()

            set_action_runtime_role(db)
            outcome = handler.execute(
                db=db,
                action_request=action,
                approved_by_app_user_id=current_user.id,
                revalidation=revalidation,
                now=now,
            )
            reset_action_runtime_role(db)

            _complete_success(
                db,
                actor=current_user,
                action=action,
                approval=approval,
                decision_reason=decision_reason,
                revalidation=revalidation,
                executed_record_ids=outcome.executed_record_ids,
                self_approved=current_decision.self_approved,
                now=now,
                presentation=presentation,
            )
            db.commit()
            return {
                "approval_id": str(approval.id),
                "action_request_id": str(action.id),
                "status": ActionRequestStatus.COMPLETED.value,
                "executed_records_count": len(outcome.executed_record_ids),
                "skipped_records_count": action.skipped_count,
                "self_approved": current_decision.self_approved,
                "override_used": revalidation.requires_policy_override,
                "completed_at": _timestamp(now),
            }
        except ApprovalServiceError:
            raise
        except Exception:
            db.rollback()
            LOGGER.exception(
                "Action approval failed during %s for action %s.",
                failure_category,
                action.id,
            )
            try:
                persisted = _persist_execution_failure(
                    db,
                    actor=current_user,
                    action_request_id=action.id,
                    approval_request_id=approval.id,
                    decision_reason=decision_reason,
                    now=now,
                    failure_category=failure_category,
                )
            except Exception as failure_exc:
                db.rollback()
                raise ApprovalServiceError(
                    code="INTERNAL_ERROR",
                    message="The action could not be completed safely.",
                    status_code=500,
                ) from failure_exc
            if not persisted:
                raise _already_processed()
            return {
                "approval_id": str(approval.id),
                "action_request_id": str(action.id),
                "status": ActionRequestStatus.FAILED.value,
                "executed_records_count": 0,
                "skipped_records_count": 0,
                "self_approved": initial_decision.self_approved,
                "override_used": False,
                "completed_at": _timestamp(now),
            }


def _approval_decision(action: ActionRequest, context: UserAccessContext):
    policy = action.policy_flags_json if isinstance(action.policy_flags_json, dict) else {}
    return evaluate_action_approval(
        context,
        requester_app_user_id=action.requested_by_app_user_id,
        scope_type=action.scope_type or "",
        scope_key=action.scope_key or "",
        record_count=action.record_count,
        crosses_scopes=(
            action.scope_type == "global"
            or policy.get("crosses_scopes") is True
            or policy.get("revalidation_crosses_scopes") is True
            or action.record_count > 20
        ),
        requires_policy_override=(
            policy.get("requires_policy_override") is True
            or policy.get("revalidation_requires_policy_override") is True
        ),
    )


def _locked_pair(
    db: Session, approval_id: uuid.UUID
) -> tuple[ActionRequest, ApprovalRequest]:
    probe = db.get(ApprovalRequest, approval_id)
    if probe is None or probe.action_request_id is None:
        raise _not_found()
    action = db.scalar(
        select(ActionRequest)
        .where(ActionRequest.id == probe.action_request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    approval = db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if action is None or approval is None or approval.action_request_id != action.id:
        raise _not_found()
    return action, approval


def _require_pending(
    action: ActionRequest,
    approval: ApprovalRequest,
    now: datetime,
) -> None:
    if (
        action.status != ActionRequestStatus.PENDING_APPROVAL.value
        or approval.status != ApprovalStatus.PENDING.value
    ):
        raise _already_processed()
    if _expired(action, approval, now):
        raise _expired_error()


def _expired(action: ActionRequest, approval: ApprovalRequest, now: datetime) -> bool:
    return (
        action.expires_at is None
        or approval.expires_at is None
        or _as_utc(action.expires_at) <= now
        or _as_utc(approval.expires_at) <= now
    )


def _expire_pending_requests(
    db: Session,
    *,
    actor: AppUser,
    context: UserAccessContext,
    now: datetime,
) -> None:
    rows = db.execute(
        select(ActionRequest, ApprovalRequest)
        .join(ApprovalRequest, ApprovalRequest.action_request_id == ActionRequest.id)
        .where(
            ActionRequest.status == ActionRequestStatus.PENDING_APPROVAL.value,
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
            or_(
                ActionRequest.expires_at.is_(None),
                ApprovalRequest.expires_at.is_(None),
                ActionRequest.expires_at <= now,
                ApprovalRequest.expires_at <= now,
            ),
        )
    ).all()
    changed = False
    for action, approval in rows:
        if not _approval_decision(action, context).allowed:
            continue
        result = db.execute(
            update(ActionRequest)
            .where(
                ActionRequest.id == action.id,
                ActionRequest.status == ActionRequestStatus.PENDING_APPROVAL.value,
            )
            .values(status=ActionRequestStatus.EXPIRED.value)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            continue
        action.status = ActionRequestStatus.EXPIRED.value
        approval.status = ApprovalStatus.EXPIRED.value
        approval.decided_at = now
        db.add(
            build_action_audit_log(
                actor=actor,
                action_request=action,
                approval_request=approval,
                event_type="action_expired",
                action="expire",
                status=ActionRequestStatus.EXPIRED.value,
                summary="Pending action request expired.",
                metadata={"expiration_kind": "pending_approval"},
                before_state={
                    "action_status": ActionRequestStatus.PENDING_APPROVAL.value,
                    "approval_status": ApprovalStatus.PENDING.value,
                },
                after_state={
                    "action_status": ActionRequestStatus.EXPIRED.value,
                    "approval_status": ApprovalStatus.EXPIRED.value,
                },
            )
        )
        changed = True
    if changed:
        _commit(db, "Expired approvals could not be updated safely.")


def _expire_one(
    db: Session,
    *,
    actor: AppUser,
    action: ActionRequest,
    approval: ApprovalRequest,
    now: datetime,
) -> bool:
    action_result = db.execute(
        update(ActionRequest)
        .where(
            ActionRequest.id == action.id,
            ActionRequest.status == ActionRequestStatus.PENDING_APPROVAL.value,
            or_(
                ActionRequest.expires_at.is_(None),
                ActionRequest.expires_at <= now,
            ),
        )
        .values(status=ActionRequestStatus.EXPIRED.value)
        .execution_options(synchronize_session=False)
    )
    approval_result = db.execute(
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == approval.id,
            ApprovalRequest.action_request_id == action.id,
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
            or_(
                ApprovalRequest.expires_at.is_(None),
                ApprovalRequest.expires_at <= now,
            ),
        )
        .values(
            status=ApprovalStatus.EXPIRED.value,
            decided_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if action_result.rowcount != 1 or approval_result.rowcount != 1:
        db.rollback()
        return False
    action.status = ActionRequestStatus.EXPIRED.value
    approval.status = ApprovalStatus.EXPIRED.value
    approval.decided_at = now
    db.add(
        build_action_audit_log(
            actor=actor,
            action_request=action,
            approval_request=approval,
            event_type="action_expired",
            action="expire",
            status=ActionRequestStatus.EXPIRED.value,
            summary="Pending action request expired.",
            metadata={"expiration_kind": "pending_approval"},
            before_state={"action_status": "pending_approval", "approval_status": "pending"},
            after_state={"action_status": "expired", "approval_status": "expired"},
        )
    )
    _commit(db, "The expired approval could not be updated safely.")
    return True


def _persist_escalation(
    db: Session,
    *,
    actor: AppUser,
    action: ActionRequest,
    approval: ApprovalRequest,
    revalidation: ActionRevalidation,
) -> None:
    policy = dict(action.policy_flags_json or {})
    policy["revalidation_flags"] = safe_action_revalidation_flags(
        action.action_type,
        revalidation,
    )
    policy["revalidation_requires_admin"] = True
    policy["revalidation_requires_policy_override"] = True
    policy["revalidation_crosses_scopes"] = revalidation.crosses_scopes
    action.policy_flags_json = policy
    action.requires_admin = True
    approval.required_approver_role = "admin"
    audit = build_action_audit_log(
        actor=actor,
        action_request=action,
        approval_request=approval,
        event_type="action_approval_escalated",
        action="escalate",
        status=ActionRequestStatus.PENDING_APPROVAL.value,
        summary="Current policy requires an authorized override approver.",
        metadata={"escalation_reason": "policy_override_required"},
        before_state={"requires_admin": False},
        after_state={"requires_admin": True},
        severity="warning",
    )
    recipients = eligible_approvers(db, action_request=action)
    pending = build_pending_approval_notifications(
        action_request=action,
        approval_request=approval,
        recipients=recipients,
    )
    existing_recipient_ids = set(
        db.scalars(
            select(Notification.recipient_user_id).where(
                Notification.notification_type == "action_pending_approval",
                Notification.related_resource_type == "action_request",
                Notification.related_resource_id == action.id,
            )
        ).all()
    )
    db.add_all(
        [audit, *[item for item in pending if item.recipient_user_id not in existing_recipient_ids]]
    )
    _commit(db, "The approval escalation could not be saved safely.")


def _complete_success(
    db: Session,
    *,
    actor: AppUser,
    action: ActionRequest,
    approval: ApprovalRequest,
    decision_reason: str,
    revalidation: ActionRevalidation,
    executed_record_ids: tuple[uuid.UUID, ...],
    self_approved: bool,
    now: datetime,
    presentation: ActionPresentation,
) -> None:
    approval.status = ApprovalStatus.APPROVED.value
    approval.decided_by_user_id = actor.id
    approval.decision_reason = decision_reason
    approval.decided_at = now
    action.status = ActionRequestStatus.COMPLETED.value
    action.approved_at = now
    action.executed_at = now
    action.completed_at = now
    previous_skips = action.skipped_records_json
    prior_records = (
        list(previous_skips.get("records", []))
        if isinstance(previous_skips, dict) and isinstance(previous_skips.get("records"), list)
        else []
    )
    current_skips = [item.as_dict() for item in revalidation.skipped_records]
    override_reason_records = [
        {"reason_code": code}
        for record in action.preview_json.get("override_required_records", [])
        if isinstance(record, dict)
        for code in record.get("override_reason_codes", [])
        if isinstance(code, str)
    ]
    action.skipped_records_json = {
        "records": [*prior_records, *current_skips],
        "exclusions_by_reason": _skip_counts(
            [*prior_records, *current_skips, *override_reason_records]
        ),
    }
    action.skipped_count = len(prior_records) + len(current_skips)
    preview = dict(action.preview_json or {})
    summary = dict(preview.get("summary") or {})
    summary["skipped_count"] = action.skipped_count
    if "service_accounts_excluded_count" in summary:
        summary["service_accounts_excluded_count"] = sum(
            record.get("reason_code") == "service_account_excluded"
            for record in [*prior_records, *current_skips]
        )
    if "recent_login_skipped_count" in summary:
        summary["recent_login_skipped_count"] = sum(
            record.get("reason_code") == "recent_successful_login"
            for record in [*prior_records, *current_skips]
        )
    preview["summary"] = summary
    action.preview_json = preview
    before = {
        "records": [
            {
                presentation.target_id_field: str(record_id),
                presentation.status_field: presentation.before_status,
            }
            for record_id in executed_record_ids
        ]
    }
    after = {
        "records": [
            {
                presentation.target_id_field: str(record_id),
                presentation.status_field: presentation.after_status,
            }
            for record_id in executed_record_ids
        ]
    }
    common_metadata = {
        "executed_count": len(executed_record_ids),
        "skipped_count": action.skipped_count,
        "override_used": revalidation.requires_policy_override,
    }
    approved_audit = build_action_audit_log(
        actor=actor,
        action_request=action,
        approval_request=approval,
        event_type="action_approved",
        action="approve",
        status=ActionRequestStatus.APPROVED_EXECUTING.value,
        summary=presentation.approved_summary,
        metadata=common_metadata,
        before_state={"status": ActionRequestStatus.PENDING_APPROVAL.value},
        after_state={"status": ActionRequestStatus.APPROVED_EXECUTING.value},
        self_approved=self_approved,
    )
    executed_audit = build_action_audit_log(
        actor=actor,
        action_request=action,
        approval_request=approval,
        event_type="action_executed",
        action="execute",
        status=ActionRequestStatus.COMPLETED.value,
        summary=presentation.executed_summary,
        metadata=common_metadata,
        before_state=before,
        after_state=after,
        self_approved=self_approved,
    )
    notifications = [
        build_action_notification(
            recipient_user_id=action.requested_by_app_user_id,
            actor_user_id=actor.id,
            notification_type="action_approved",
            title="Action request approved",
            body=presentation.approved_body,
            action_request=action,
            approval_request=approval,
        ),
        build_action_notification(
            recipient_user_id=action.requested_by_app_user_id,
            actor_user_id=actor.id,
            notification_type="action_completed",
            title="Action completed",
            body=presentation.completed_body,
            action_request=action,
            approval_request=approval,
        ),
        build_action_notification(
            recipient_user_id=actor.id,
            actor_user_id=actor.id,
            notification_type="action_completed",
            title="Approved action completed",
            body=presentation.approver_completed_body,
            action_request=action,
            approval_request=approval,
        ),
    ]
    if revalidation.requires_policy_override:
        for recipient in eligible_approvers(db, action_request=action):
            if recipient.id in {action.requested_by_app_user_id, actor.id}:
                continue
            notifications.append(
                build_action_notification(
                    recipient_user_id=recipient.id,
                    actor_user_id=actor.id,
                    notification_type="action_completed",
                    title="Sensitive action completed",
                    body="An approved policy-override action completed.",
                    action_request=action,
                    approval_request=approval,
                )
            )
    notifications = _active_notifications(db, _dedupe_notifications(notifications))
    db.add_all([approval, action, approved_audit, executed_audit, *notifications])


def _persist_execution_failure(
    db: Session,
    *,
    actor: AppUser,
    action_request_id: uuid.UUID,
    approval_request_id: uuid.UUID,
    decision_reason: str,
    now: datetime,
    failure_category: str,
) -> bool:
    action = db.scalar(
        select(ActionRequest)
        .where(ActionRequest.id == action_request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    approval = db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == approval_request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if action is None or approval is None:
        raise RuntimeError("Failure persistence target is unavailable.")
    if (
        action.status != ActionRequestStatus.PENDING_APPROVAL.value
        or approval.status != ApprovalStatus.PENDING.value
    ):
        db.rollback()
        return False
    claim = db.execute(
        update(ActionRequest)
        .where(
            ActionRequest.id == action_request_id,
            ActionRequest.status == ActionRequestStatus.PENDING_APPROVAL.value,
        )
        .values(
            status=ActionRequestStatus.FAILED.value,
            failure_reason_user_safe="The action could not be completed safely.",
            failure_reason_internal=f"execution:{failure_category}",
            completed_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        db.rollback()
        return False
    approval_claim = db.execute(
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == approval_request_id,
            ApprovalRequest.action_request_id == action_request_id,
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
        )
        .values(
            status=ApprovalStatus.APPROVED.value,
            decided_by_user_id=actor.id,
            decision_reason=decision_reason,
            decided_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if approval_claim.rowcount != 1:
        db.rollback()
        return False
    action.status = ActionRequestStatus.FAILED.value
    action.failure_reason_user_safe = "The action could not be completed safely."
    action.failure_reason_internal = f"execution:{failure_category}"
    action.completed_at = now
    approval.status = ApprovalStatus.APPROVED.value
    approval.decided_by_user_id = actor.id
    approval.decision_reason = decision_reason
    approval.decided_at = now
    audit = build_action_audit_log(
        actor=actor,
        action_request=action,
        approval_request=approval,
        event_type="action_failed",
        action="execute",
        status=ActionRequestStatus.FAILED.value,
        summary="The approved action could not be completed safely.",
        metadata={"failure_category": failure_category},
        before_state={"status": ActionRequestStatus.PENDING_APPROVAL.value},
        after_state={"status": ActionRequestStatus.FAILED.value},
        severity="error",
    )
    recipients = {action.requested_by_app_user_id, actor.id}
    notifications = [
        build_action_notification(
            recipient_user_id=recipient_id,
            actor_user_id=actor.id,
            notification_type="action_failed",
            title="Action failed",
            body="The action could not be completed safely.",
            action_request=action,
            approval_request=approval,
        )
        for recipient_id in sorted(recipients, key=str)
    ]
    notifications = _active_notifications(db, notifications)
    db.add_all([action, approval, audit, *notifications])
    db.commit()
    return True


def _serialize_pending_item(approval: ApprovalRequest) -> dict[str, Any]:
    action = approval.action_request
    assert action is not None
    summary = action.preview_json.get("summary", {})
    return {
        "approval_id": str(approval.id),
        "action_request_id": str(action.id),
        "action_type": action.action_type,
        "requester": {
            "id": str(action.requested_by_app_user_id),
            "display_name": action.requester.full_name,
        },
        "scope": _safe_scope(action),
        "priority": action.priority,
        "affected_count": action.record_count,
        "skipped_count": action.skipped_count,
        "override_count": int(summary.get("override_required_count", 0)),
        "requires_admin": action.requires_admin,
        "expires_at": _timestamp(approval.expires_at),
        "status": approval.status,
    }


def _serialize_approval_detail(
    db: Session,
    *,
    approval: ApprovalRequest,
    action: ActionRequest,
    context: UserAccessContext,
    now: datetime,
) -> dict[str, Any]:
    decision = _approval_decision(action, context)
    currently_pending = (
        action.status == ActionRequestStatus.PENDING_APPROVAL.value
        and approval.status == ApprovalStatus.PENDING.value
        and not _expired(action, approval, now)
    )
    can_decide = decision.allowed and currently_pending
    preview = safe_action_preview(action)
    presentation = action_presentation(action.action_type)
    timeline = db.scalars(
        select(AppAuditLog)
        .where(AppAuditLog.action_request_id == action.id)
        .order_by(AppAuditLog.created_at, action_timeline_order(), AppAuditLog.id)
    ).all()
    can_view_global_audit = context.has_permission("can_view_global_audit")
    return {
        "approval_id": str(approval.id),
        "action_request_id": str(action.id),
        "action_type": action.action_type,
        "requester": {
            "id": str(action.requested_by_app_user_id),
            "display_name": action.requester.full_name,
        },
        "reason": action.reason,
        "priority": action.priority,
        "scope": _safe_scope(action),
        "preview": preview,
        "expires_at": _timestamp(approval.expires_at),
        "affected_count": action.record_count,
        "skipped_count": action.skipped_count,
        "override_count": int(preview["summary"].get("override_required_count", 0)),
        "estimated_impact": {
            key: preview["summary"].get(key)
            for key in presentation.estimated_impact_keys
        },
        "policy_flags": preview["policy_flags"],
        "requires_admin": action.requires_admin,
        "status": approval.status,
        "timeline": [
            {
                "event_type": event.event_type,
                "timestamp": _timestamp(event.created_at),
                "actor": (
                    {"id": str(event.actor_user_id), "display_name": event.actor.full_name}
                    if event.actor is not None
                    else None
                ),
                "summary": event.summary,
                "status": event.status,
                **(
                    {"self_approved": event.self_approved is True}
                    if can_view_global_audit
                    else {}
                ),
            }
            for event in timeline
        ],
        "viewer_capabilities": {
            "can_approve": can_decide,
            "can_reject": can_decide,
            "can_execute_on_approval": can_decide,
            "self_approval": decision.self_approved if decision.allowed else False,
            "reason": None if can_decide else decision.code,
        },
    }


def _safe_scope(action: ActionRequest) -> dict[str, Any]:
    return {
        "id": str(action.scope_id) if action.scope_id else None,
        "type": action.scope_type,
        "key": action.scope_key,
        "display_name": action.scope.display_name if action.scope else None,
    }


def _skip_counts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for record in records:
        code = record.get("reason_code")
        if isinstance(code, str):
            counts[code] = counts.get(code, 0) + 1
    return [{"reason_code": code, "count": counts[code]} for code in sorted(counts)]


def _dedupe_notifications(items: list[Notification]) -> list[Notification]:
    by_key: dict[tuple[uuid.UUID, str, uuid.UUID | None], Notification] = {}
    for item in items:
        by_key[(item.recipient_user_id, item.notification_type, item.related_resource_id)] = item
    return list(by_key.values())


def _active_notifications(
    db: Session,
    items: list[Notification],
) -> list[Notification]:
    recipient_ids = {item.recipient_user_id for item in items}
    if not recipient_ids:
        return []
    active_recipient_ids = set(
        db.scalars(
            select(AppUser.id).where(
                AppUser.id.in_(recipient_ids),
                AppUser.status == UserStatus.ACTIVE.value,
            )
        ).all()
    )
    return [item for item in items if item.recipient_user_id in active_recipient_ids]


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ApprovalServiceError(
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


def _not_found() -> ApprovalServiceError:
    return ApprovalServiceError(
        code="APPROVAL_NOT_FOUND",
        message="Approval request was not found.",
        status_code=404,
    )


def _forbidden() -> ApprovalServiceError:
    return ApprovalServiceError(
        code="FORBIDDEN",
        message="You are not authorized to perform this action.",
        status_code=403,
    )


def _already_processed() -> ApprovalServiceError:
    return ApprovalServiceError(
        code="ACTION_ALREADY_PROCESSED",
        message="The action request has already been processed.",
        status_code=409,
    )


def _expired_error() -> ApprovalServiceError:
    return ApprovalServiceError(
        code="ACTION_REQUEST_EXPIRED",
        message="The action request has expired. Create a new preview.",
        status_code=410,
    )
