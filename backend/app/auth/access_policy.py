from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.api.responses import ApiError
from app.auth.access_context import UserAccessContext
from app.core.rls import RLSExecutable, build_rls_context, set_rls_context
from app.models.product import DataResource


AUTHORIZATION_DENIED_MESSAGE = "You are not authorized to access this resource."

ACTION_REQUIRED_PERMISSIONS = {
    "query:scoped_data": "can_query_scoped_data",
    "view:scoped_data": "can_view_scoped_data",
    "query:global_data": "can_query_global_data",
    "view:global_data": "can_view_global_data",
    "query:product_tables": "can_query_product_tables",
    "dashboard:create_scope": "can_create_scope_dashboard",
    "dashboard:manage_scope": "can_manage_scope_dashboard",
    "action:approve_scoped": "can_approve_scoped_action",
    "audit:view_scope": "can_view_scope_audit",
    "evaluation:view_scope": "can_view_scope_evaluation",
    "query_history:view_scope": "can_view_query_history_scope",
}

SCOPED_DATA_ACTIONS = frozenset({"query:scoped_data", "view:scoped_data"})


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    effect: str
    reason: str
    action: str
    resource: dict[str, Any]
    required_permission: str | None
    matched_scopes: list[str]
    context_snapshot: dict[str, Any] | None = None


def evaluate_access(
    subject: UserAccessContext,
    action: str,
    resource: DataResource | dict[str, Any],
    context: dict[str, Any] | None = None,
) -> AccessDecision:
    runtime_context = context or {}
    resource_dict = _resource_to_dict(resource)
    required_permission = ACTION_REQUIRED_PERMISSIONS.get(action)

    if required_permission is None:
        return _deny(
            subject,
            action,
            resource_dict,
            None,
            "unknown_action",
            [],
        )

    if not subject.has_permission(required_permission):
        return _deny(
            subject,
            action,
            resource_dict,
            required_permission,
            "missing_permission",
            [],
        )

    scope_type = runtime_context.get("scope_type") or resource_dict.get("scope_type")
    scope_key = runtime_context.get("scope_key") or resource_dict.get("scope_key")
    if not scope_type:
        return _allow(
            subject,
            action,
            resource_dict,
            required_permission,
            "allow_reference_resource",
            [],
        )

    if action in SCOPED_DATA_ACTIONS and not scope_key:
        return _deny(
            subject,
            action,
            resource_dict,
            required_permission,
            "missing_scope_key",
            [],
        )

    if subject.has_global_scope:
        return _allow(
            subject,
            action,
            resource_dict,
            required_permission,
            "allow_global_scope",
            ["global:global"],
        )

    if scope_key:
        if subject.has_scope(str(scope_type), str(scope_key)):
            return _allow(
                subject,
                action,
                resource_dict,
                required_permission,
                "allow_matching_scope",
                [f"{scope_type}:{scope_key}"],
            )
        return _deny(
            subject,
            action,
            resource_dict,
            required_permission,
            "missing_scope",
            [],
        )

    matched_scopes = [
        f"{scope.type}:{scope.key}" for scope in subject.scopes if scope.type == scope_type
    ]
    if matched_scopes:
        return _allow(
            subject,
            action,
            resource_dict,
            required_permission,
            "allow_scope_type",
            matched_scopes,
        )

    return _deny(
        subject,
        action,
        resource_dict,
        required_permission,
        "missing_scope",
        [],
    )


def authorize_resource_access(
    subject: UserAccessContext,
    action: str,
    resource: DataResource | dict[str, Any],
    context: dict[str, Any] | None = None,
) -> AccessDecision:
    return evaluate_access(subject, action, resource, context)


def require_access_decision(decision: AccessDecision) -> None:
    if decision.allowed:
        return

    raise ApiError(
        code="FORBIDDEN",
        message=AUTHORIZATION_DENIED_MESSAGE,
        status_code=403,
    )


def prepare_scoped_data_access(
    db: RLSExecutable,
    subject: UserAccessContext,
    action: str,
    resource: DataResource | dict[str, Any],
    context: dict[str, Any] | None = None,
) -> AccessDecision:
    decision = authorize_resource_access(subject, action, resource, context)
    require_access_decision(decision)
    set_rls_context(db, build_rls_context(subject))
    return decision


def _allow(
    subject: UserAccessContext,
    action: str,
    resource: dict[str, Any],
    required_permission: str | None,
    reason: str,
    matched_scopes: list[str],
) -> AccessDecision:
    return AccessDecision(
        allowed=True,
        effect="allow",
        reason=reason,
        action=action,
        resource=resource,
        required_permission=required_permission,
        matched_scopes=matched_scopes,
        context_snapshot=_snapshot(subject),
    )


def _deny(
    subject: UserAccessContext,
    action: str,
    resource: dict[str, Any],
    required_permission: str | None,
    reason: str,
    matched_scopes: list[str],
) -> AccessDecision:
    return AccessDecision(
        allowed=False,
        effect="deny",
        reason=reason,
        action=action,
        resource=resource,
        required_permission=required_permission,
        matched_scopes=matched_scopes,
        context_snapshot=_snapshot(subject),
    )


def _resource_to_dict(resource: DataResource | dict[str, Any]) -> dict[str, Any]:
    if isinstance(resource, dict):
        return dict(resource)

    return {
        "id": str(resource.id),
        "resource_type": resource.resource_type,
        "domain": resource.domain,
        "schema_name": resource.schema_name,
        "table_name": resource.table_name,
        "column_name": resource.column_name,
        "display_name": resource.display_name,
        "sensitivity_level": resource.sensitivity_level,
        "scope_type": resource.scope_type,
        "scope_column": resource.scope_column,
        "is_queryable": resource.is_queryable,
        "is_exportable": resource.is_exportable,
        "llm_exposure_level": resource.llm_exposure_level,
    }


def _snapshot(subject: UserAccessContext) -> dict[str, Any]:
    return {
        "user_id": str(subject.user_id),
        "role": subject.role,
        "permissions": sorted(subject.permissions),
        "scopes": [f"{scope.type}:{scope.key}" for scope in subject.scopes],
        "has_global_scope": subject.has_global_scope,
    }
