from __future__ import annotations

import uuid

from app.action_engine.policy import (
    GLOBAL_APPROVAL_PERMISSION,
    OVERRIDE_APPROVAL_PERMISSION,
    POLICY_DENIED_REASON,
    REQUEST_PERMISSION,
    SCOPED_APPROVAL_PERMISSION,
    SELF_APPROVAL_PERMISSION,
    evaluate_action_approval,
    evaluate_action_request,
)
from app.auth.access_context import AccessScopeContext, UserAccessContext


FINANCE_SCOPE = ("department", "finance")
SALES_SCOPE = ("department", "sales")


def test_user_cannot_request_action() -> None:
    subject = _subject(permissions=set(), scope=FINANCE_SCOPE)

    decision = evaluate_action_request(
        subject,
        scope_type="department",
        scope_key="finance",
    )

    assert decision.allowed is False
    assert decision.code == "request_permission_required"
    assert decision.required_permission == REQUEST_PERMISSION


def test_manager_can_request_action_in_assigned_scope() -> None:
    subject = _subject(permissions={REQUEST_PERMISSION}, scope=FINANCE_SCOPE)

    decision = evaluate_action_request(
        subject,
        scope_type="department",
        scope_key="finance",
    )

    assert decision.allowed is True
    assert decision.matched_scopes == ("department:finance",)


def test_manager_cannot_approve_action() -> None:
    subject = _subject(permissions={REQUEST_PERMISSION}, scope=FINANCE_SCOPE)

    decision = _approve(subject, record_count=5)

    assert decision.allowed is False
    assert decision.code == "scoped_approval_permission_required"
    assert decision.required_permission == SCOPED_APPROVAL_PERMISSION


def test_analyst_can_approve_matching_scope_at_twenty_records() -> None:
    subject = _analyst()

    decision = _approve(subject, record_count=20)

    assert decision.allowed is True
    assert decision.required_permission == SCOPED_APPROVAL_PERMISSION
    assert decision.matched_scopes == ("department:finance",)
    assert decision.requires_admin is False


def test_analyst_cannot_self_approve() -> None:
    subject = _analyst()

    decision = _approve(
        subject,
        requester_app_user_id=subject.user_id,
        record_count=5,
    )

    assert decision.allowed is False
    assert decision.code == "self_approval_permission_required"
    assert decision.required_permission == SELF_APPROVAL_PERMISSION
    assert decision.self_approved is False


def test_analyst_cannot_approve_more_than_twenty_records() -> None:
    decision = _approve(_analyst(), record_count=21)

    assert decision.allowed is False
    assert decision.code == "global_approval_permission_required"
    assert decision.required_permission == GLOBAL_APPROVAL_PERMISSION
    assert decision.requires_admin is True


def test_analyst_cannot_approve_policy_override() -> None:
    decision = _approve(
        _analyst(),
        record_count=5,
        requires_policy_override=True,
    )

    assert decision.allowed is False
    assert decision.code == "override_permission_required"
    assert decision.required_permission == OVERRIDE_APPROVAL_PERMISSION
    assert decision.requires_admin is True


def test_analyst_cannot_approve_another_scope() -> None:
    decision = _approve(
        _analyst(),
        scope_type="department",
        scope_key="sales",
        record_count=5,
    )

    assert decision.allowed is False
    assert decision.code == "approval_scope_required"
    assert decision.matched_scopes == ()


def test_admin_global_permission_can_approve_cross_scope_work() -> None:
    subject = _admin()

    decision = _approve(
        subject,
        scope_type="department",
        scope_key="finance",
        record_count=5,
        crosses_scopes=True,
    )

    assert decision.allowed is True
    assert decision.required_permission == GLOBAL_APPROVAL_PERMISSION
    assert decision.matched_scopes == ("global:global",)
    assert decision.requires_admin is True


def test_admin_global_permission_can_approve_over_threshold_work() -> None:
    decision = _approve(_admin(), record_count=21)

    assert decision.allowed is True
    assert decision.required_permission == GLOBAL_APPROVAL_PERMISSION
    assert decision.matched_scopes == ("global:global",)
    assert decision.requires_admin is True


def test_policy_override_requires_override_permission() -> None:
    subject = _admin(permissions={GLOBAL_APPROVAL_PERMISSION, SCOPED_APPROVAL_PERMISSION})

    decision = _approve(
        subject,
        record_count=5,
        requires_policy_override=True,
    )

    assert decision.allowed is False
    assert decision.code == "override_permission_required"


def test_self_approval_requires_dedicated_permission() -> None:
    subject = _admin(
        permissions={
            GLOBAL_APPROVAL_PERMISSION,
            SCOPED_APPROVAL_PERMISSION,
            OVERRIDE_APPROVAL_PERMISSION,
        }
    )

    decision = _approve(
        subject,
        requester_app_user_id=subject.user_id,
        record_count=5,
    )

    assert decision.allowed is False
    assert decision.required_permission == SELF_APPROVAL_PERMISSION


def test_self_approved_decision_is_explicitly_marked() -> None:
    subject = _admin()

    decision = _approve(
        subject,
        requester_app_user_id=subject.user_id,
        record_count=5,
    )

    assert decision.allowed is True
    assert decision.self_approved is True


def test_deny_decision_returns_stable_safe_reason() -> None:
    decision = _approve(_analyst(), record_count=21)

    assert decision.allowed is False
    assert decision.reason == POLICY_DENIED_REASON
    assert "permission" not in decision.reason.lower()
    assert "scope" not in decision.reason.lower()


def _analyst() -> UserAccessContext:
    return _subject(
        permissions={REQUEST_PERMISSION, SCOPED_APPROVAL_PERMISSION},
        scope=FINANCE_SCOPE,
    )


def _admin(
    *,
    permissions: set[str] | None = None,
) -> UserAccessContext:
    return _subject(
        permissions=permissions
        or {
            REQUEST_PERMISSION,
            SCOPED_APPROVAL_PERMISSION,
            GLOBAL_APPROVAL_PERMISSION,
            OVERRIDE_APPROVAL_PERMISSION,
            SELF_APPROVAL_PERMISSION,
        },
        scope=("global", "global"),
    )


def _subject(
    *,
    permissions: set[str],
    scope: tuple[str, str],
) -> UserAccessContext:
    user_id = uuid.uuid4()
    scope_context = AccessScopeContext(
        id=uuid.uuid4(),
        type=scope[0],
        key=scope[1],
        display_name=scope[1].title(),
        access_level="manage",
        is_default=True,
        department_id=uuid.uuid4() if scope[0] == "department" else None,
    )
    return UserAccessContext(
        user_id=user_id,
        role=None,
        permissions=frozenset(permissions),
        scopes=(scope_context,),
        default_scope=scope_context,
        has_global_scope=scope == ("global", "global"),
        subject_attributes={},
    )


def _approve(
    subject: UserAccessContext,
    *,
    requester_app_user_id: uuid.UUID | None = None,
    scope_type: str = "department",
    scope_key: str = "finance",
    record_count: int,
    crosses_scopes: bool = False,
    requires_policy_override: bool = False,
):
    return evaluate_action_approval(
        subject,
        requester_app_user_id=requester_app_user_id or uuid.uuid4(),
        scope_type=scope_type,
        scope_key=scope_key,
        record_count=record_count,
        crosses_scopes=crosses_scopes,
        requires_policy_override=requires_policy_override,
    )
