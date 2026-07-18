from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.action_engine.policy import evaluate_action_approval
from app.action_engine.presentation import action_presentation
from app.auth.access_context import build_user_access_context
from app.models.product import (
    ActionRequest,
    AppUser,
    ApprovalRequest,
    Notification,
    NotificationStatus,
    UserStatus,
)


PENDING_APPROVAL_NOTIFICATION = "action_pending_approval"


def eligible_approvers(
    db: Session,
    *,
    action_request: ActionRequest,
) -> tuple[AppUser, ...]:
    users = db.scalars(
        select(AppUser)
        .where(AppUser.status == UserStatus.ACTIVE.value)
        .order_by(AppUser.id)
    ).all()
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

    recipients: dict[str, AppUser] = {}
    for user in users:
        context = build_user_access_context(user, db)
        decision = evaluate_action_approval(
            context,
            requester_app_user_id=action_request.requested_by_app_user_id,
            scope_type=action_request.scope_type or "",
            scope_key=action_request.scope_key or "",
            record_count=action_request.record_count,
            crosses_scopes=crosses_scopes,
            requires_policy_override=requires_policy_override,
        )
        if decision.allowed:
            recipients[str(user.id)] = user
    return tuple(recipients[key] for key in sorted(recipients))


def build_pending_approval_notifications(
    *,
    action_request: ActionRequest,
    approval_request: ApprovalRequest,
    recipients: tuple[AppUser, ...],
) -> tuple[Notification, ...]:
    expires_at = approval_request.expires_at
    presentation = action_presentation(action_request.action_type)
    return tuple(
        Notification(
            recipient_user_id=recipient.id,
            actor_user_id=action_request.requested_by_app_user_id,
            notification_type=PENDING_APPROVAL_NOTIFICATION,
            title="Action request pending approval",
            body=presentation.pending_body,
            status=NotificationStatus.UNREAD.value,
            related_resource_type="action_request",
            related_resource_id=action_request.id,
            payload={
                "action_request_id": str(action_request.id),
                "approval_request_id": str(approval_request.id),
                "action_type": action_request.action_type,
                "priority": action_request.priority,
                "scope": {
                    "id": str(action_request.scope_id)
                    if action_request.scope_id is not None
                    else None,
                    "type": action_request.scope_type,
                    "key": action_request.scope_key,
                },
                "expires_at": _timestamp(expires_at) if expires_at else None,
            },
        )
        for recipient in recipients
    )


def build_action_notification(
    *,
    recipient_user_id,
    actor_user_id,
    notification_type: str,
    title: str,
    body: str,
    action_request: ActionRequest,
    approval_request: ApprovalRequest,
) -> Notification:
    return Notification(
        recipient_user_id=recipient_user_id,
        actor_user_id=actor_user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        status=NotificationStatus.UNREAD.value,
        related_resource_type="action_request",
        related_resource_id=action_request.id,
        payload={
            "action_request_id": str(action_request.id),
            "approval_request_id": str(approval_request.id),
            "action_type": action_request.action_type,
            "status": action_request.status,
        },
    )


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
