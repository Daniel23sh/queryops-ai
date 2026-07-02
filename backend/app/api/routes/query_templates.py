from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.responses import error_response, success_response
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.auth.access_policy import (
    APPROVED_TEMPLATE_QUERY_ACTION,
    authorize_resource_access,
)
from app.auth.permissions import require_authenticated_user
from app.db.session import get_db
from app.models.product import AppUser
from app.query_engine.domain_pack import (
    DomainPack,
    QueryTemplate,
    QueryTemplateParameter,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack


router = APIRouter(prefix="/api/v1")


@router.get("/query-templates")
def list_query_templates(
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    access_context = build_user_access_context(current_user, db)
    domain_pack = load_it_operations_domain_pack()
    templates = [
        _serialize_template(template, domain_pack)
        for template in domain_pack.query_templates
        if _template_is_allowed(template, access_context)
    ]

    return success_response(templates)


@router.get("/query-templates/{template_id}")
def get_query_template(
    template_id: str,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    access_context = build_user_access_context(current_user, db)
    domain_pack = load_it_operations_domain_pack()
    template = domain_pack.templates_by_id.get(template_id)
    if template is None or not _template_is_allowed(template, access_context):
        return _template_not_found_response()

    return success_response(_serialize_template(template, domain_pack))


def _template_is_allowed(
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


def _serialize_template(template: QueryTemplate, domain_pack: DomainPack) -> dict:
    return {
        "id": template.id,
        "title": template.title,
        "description": template.description,
        "domain": domain_pack.domain_id,
        "category": template.category,
        "natural_language_question": template.natural_language_question,
        "parameters": [
            _serialize_parameter(parameter) for parameter in template.parameters
        ],
        "scope_type": template.scope_type,
        "required_permission": template.required_permission,
    }


def _serialize_parameter(parameter: QueryTemplateParameter) -> dict:
    return {
        "name": parameter.name,
        "data_type": parameter.data_type,
        "description": parameter.description,
        "required": parameter.required,
        "default": parameter.default,
    }


def _template_not_found_response():
    return error_response(
        code="QUERY_TEMPLATE_NOT_FOUND",
        message="Query template was not found.",
        status_code=404,
    )
