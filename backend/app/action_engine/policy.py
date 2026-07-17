from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.auth.access_context import UserAccessContext


REQUEST_PERMISSION = "can_request_action"
SCOPED_APPROVAL_PERMISSION = "can_approve_scoped_action"
GLOBAL_APPROVAL_PERMISSION = "can_approve_global_action"
OVERRIDE_APPROVAL_PERMISSION = "can_approve_policy_override"
SELF_APPROVAL_PERMISSION = "can_self_approve_admin_action"
SCOPED_APPROVAL_RECORD_LIMIT = 20

POLICY_ALLOWED_REASON = "The action is allowed by the current policy."
POLICY_DENIED_REASON = "The action is not authorized by the current policy."


@dataclass(frozen=True, kw_only=True)
class ActionPolicyDecision:
    allowed: bool
    code: str
    reason: str
    required_permission: str | None
    matched_scopes: tuple[str, ...]
    requires_admin: bool
    self_approved: bool


def evaluate_action_request(
    subject: UserAccessContext,
    *,
    scope_type: str,
    scope_key: str,
) -> ActionPolicyDecision:
    if not subject.has_permission(REQUEST_PERMISSION):
        return _deny(
            code="request_permission_required",
            required_permission=REQUEST_PERMISSION,
        )

    matched_scopes = _match_required_scope(subject, scope_type, scope_key)
    if not matched_scopes:
        return _deny(
            code="request_scope_required",
            required_permission=REQUEST_PERMISSION,
        )

    return _allow(
        code="request_allowed",
        required_permission=REQUEST_PERMISSION,
        matched_scopes=matched_scopes,
    )


def evaluate_action_approval(
    subject: UserAccessContext,
    *,
    requester_app_user_id: uuid.UUID,
    scope_type: str,
    scope_key: str,
    record_count: int,
    crosses_scopes: bool = False,
    requires_policy_override: bool = False,
) -> ActionPolicyDecision:
    if record_count < 0:
        return _deny(code="invalid_record_count")

    is_self_approval = subject.user_id == requester_app_user_id
    if is_self_approval and not subject.has_permission(SELF_APPROVAL_PERMISSION):
        return _deny(
            code="self_approval_permission_required",
            required_permission=SELF_APPROVAL_PERMISSION,
        )

    if requires_policy_override and not subject.has_permission(
        OVERRIDE_APPROVAL_PERMISSION
    ):
        return _deny(
            code="override_permission_required",
            required_permission=OVERRIDE_APPROVAL_PERMISSION,
            requires_admin=True,
        )

    requires_global_approval = (
        crosses_scopes
        or record_count > SCOPED_APPROVAL_RECORD_LIMIT
        or scope_type == "global"
    )
    requires_admin = requires_global_approval or requires_policy_override

    if requires_global_approval:
        if not subject.has_permission(GLOBAL_APPROVAL_PERMISSION):
            return _deny(
                code="global_approval_permission_required",
                required_permission=GLOBAL_APPROVAL_PERMISSION,
                requires_admin=True,
            )
        if not subject.has_global_scope:
            return _deny(
                code="global_scope_required",
                required_permission=GLOBAL_APPROVAL_PERMISSION,
                requires_admin=True,
            )
        matched_scopes = ("global:global",)
        required_permission = GLOBAL_APPROVAL_PERMISSION
    else:
        if not subject.has_permission(SCOPED_APPROVAL_PERMISSION):
            return _deny(
                code="scoped_approval_permission_required",
                required_permission=SCOPED_APPROVAL_PERMISSION,
            )
        matched_scopes = _match_required_scope(subject, scope_type, scope_key)
        if not matched_scopes:
            return _deny(
                code="approval_scope_required",
                required_permission=SCOPED_APPROVAL_PERMISSION,
            )
        required_permission = SCOPED_APPROVAL_PERMISSION

    return _allow(
        code="approval_allowed",
        required_permission=required_permission,
        matched_scopes=matched_scopes,
        requires_admin=requires_admin,
        self_approved=is_self_approval,
    )


def _match_required_scope(
    subject: UserAccessContext,
    scope_type: str,
    scope_key: str,
) -> tuple[str, ...]:
    if not scope_type or not scope_key:
        return ()
    if subject.has_global_scope:
        return ("global:global",)
    if subject.has_scope(scope_type, scope_key):
        return (f"{scope_type}:{scope_key}",)
    return ()


def _allow(
    *,
    code: str,
    required_permission: str | None,
    matched_scopes: tuple[str, ...],
    requires_admin: bool = False,
    self_approved: bool = False,
) -> ActionPolicyDecision:
    return ActionPolicyDecision(
        allowed=True,
        code=code,
        reason=POLICY_ALLOWED_REASON,
        required_permission=required_permission,
        matched_scopes=matched_scopes,
        requires_admin=requires_admin,
        self_approved=self_approved,
    )


def _deny(
    *,
    code: str,
    required_permission: str | None = None,
    requires_admin: bool = False,
) -> ActionPolicyDecision:
    return ActionPolicyDecision(
        allowed=False,
        code=code,
        reason=POLICY_DENIED_REASON,
        required_permission=required_permission,
        matched_scopes=(),
        requires_admin=requires_admin,
        self_approved=False,
    )
