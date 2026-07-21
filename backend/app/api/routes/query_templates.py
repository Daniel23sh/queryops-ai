from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.responses import error_response, success_response
from app.auth.access_context import build_user_access_context
from app.auth.permissions import require_authenticated_user
from app.db.session import get_db
from app.models.product import AppUser
from app.query_engine.domain_pack import DomainPack, QueryTemplateParameter
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.request_authorization import template_is_allowed


router = APIRouter(prefix="/api/v1")


@router.get("/query-templates")
def list_query_templates(
    can_suggest_action: bool | None = Query(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    access_context = build_user_access_context(current_user, db)
    domain_pack = load_it_operations_domain_pack()
    templates = [
        _serialize_template(template, domain_pack)
        for template in domain_pack.query_templates
        if template_is_allowed(template, access_context)
        and (
            can_suggest_action is None
            or (template.suggested_action is not None) is can_suggest_action
        )
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
    if template is None or not template_is_allowed(template, access_context):
        return _template_not_found_response()

    return success_response(_serialize_template(template, domain_pack))


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
        "can_suggest_action": template.suggested_action is not None,
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
