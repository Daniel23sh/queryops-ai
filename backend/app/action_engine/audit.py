from __future__ import annotations

import uuid
from typing import Any

from app.models.product import ActionRequest, AppAuditLog, AppUser, ApprovalRequest


def build_action_audit_log(
    *,
    actor: AppUser,
    action_request: ActionRequest,
    event_type: str,
    action: str,
    status: str,
    summary: str,
    approval_request: ApprovalRequest | None = None,
    metadata: dict[str, Any] | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
) -> AppAuditLog:
    return AppAuditLog(
        id=uuid.uuid4(),
        actor_user_id=actor.id,
        action_request_id=action_request.id,
        approval_request_id=(
            approval_request.id if approval_request is not None else None
        ),
        department_id=action_request.department_id,
        scope_id=action_request.scope_id,
        scope_type=action_request.scope_type,
        scope_key=action_request.scope_key,
        severity="info",
        event_type=event_type,
        action=action,
        status=status,
        entity_type="action_request",
        entity_id=action_request.id,
        summary=summary,
        audit_metadata=_safe_audit_metadata(action_request, metadata or {}),
        before_state_json=before_state,
        after_state_json=after_state,
        self_approved=None,
    )


def _safe_audit_metadata(
    action_request: ActionRequest,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    safe = {
        "action_type": action_request.action_type,
        "record_count": action_request.record_count,
        "skipped_count": action_request.skipped_count,
        "requires_admin": action_request.requires_admin,
    }
    for key in (
        "approval_request_id",
        "source_query_run_id",
        "notification_count",
        "cancellation_reason",
        "expiration_kind",
    ):
        value = metadata.get(key)
        if isinstance(value, uuid.UUID):
            safe[key] = str(value)
        elif isinstance(value, str | int) and not isinstance(value, bool):
            safe[key] = value
    flag_codes = metadata.get("policy_flag_codes")
    if isinstance(flag_codes, list | tuple):
        safe["policy_flag_codes"] = [
            code for code in flag_codes if isinstance(code, str)
        ]
    return safe
