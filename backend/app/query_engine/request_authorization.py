from __future__ import annotations

from dataclasses import dataclass

from app.auth.access_context import UserAccessContext
from app.auth.access_policy import (
    APPROVED_TEMPLATE_QUERY_ACTION,
    authorize_resource_access,
)
from app.query_engine.domain_pack import DomainPack, QueryTemplate


@dataclass(frozen=True)
class QueryRequestAuthorization:
    allowed: bool
    error_code: str | None = None


def authorize_query_request(
    access_context: UserAccessContext,
    domain_pack: DomainPack,
    *,
    template_id: str | None,
) -> QueryRequestAuthorization:
    """Apply the product's pre-generation query-request policy.

    QueryEngineService remains the governed generation/validation/execution
    boundary. This policy is shared by HTTP and internal evaluation callers so
    neither can enter that boundary with a request the product would reject.
    """
    if template_id is None:
        if access_context.has_permission("can_run_free_query"):
            return QueryRequestAuthorization(allowed=True)
        return QueryRequestAuthorization(allowed=False, error_code="forbidden")

    if not access_context.has_permission("can_use_query_templates"):
        return QueryRequestAuthorization(allowed=False, error_code="forbidden")
    template = domain_pack.templates_by_id.get(template_id)
    if template is None or not template_is_allowed(template, access_context):
        return QueryRequestAuthorization(
            allowed=False,
            error_code="query_template_not_found",
        )
    return QueryRequestAuthorization(allowed=True)


def template_is_allowed(
    template: QueryTemplate,
    access_context: UserAccessContext,
) -> bool:
    decision = authorize_resource_access(
        access_context,
        APPROVED_TEMPLATE_QUERY_ACTION,
        {
            "resource_type": "query_template",
            "domain": "it_operations",
            "table_name": template.id,
            "scope_type": template.scope_type,
            "scope_key": _scope_key_for_template(template, access_context),
            "is_queryable": True,
        },
    )
    return decision.allowed


def _scope_key_for_template(
    template: QueryTemplate,
    access_context: UserAccessContext,
) -> str | None:
    if template.scope_type is None:
        return None
    if access_context.has_global_scope:
        return "global"

    default_scope = access_context.default_scope
    if default_scope is not None and default_scope.type == template.scope_type:
        return default_scope.key

    matching_scope = next(
        (scope for scope in access_context.scopes if scope.type == template.scope_type),
        None,
    )
    return matching_scope.key if matching_scope is not None else None
