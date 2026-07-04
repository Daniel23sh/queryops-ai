from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request

from app.api.responses import error_response, success_response
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.models.product import AppUser


router = APIRouter(prefix="/api/v1")

ALLOWED_DASHBOARD_FIELDS = frozenset(
    {"title", "description", "visibility_scope", "department_id"}
)
ALLOWED_SAVE_CARD_FIELDS = frozenset(
    {"dashboard_id", "title", "description", "card_type"}
)
ALLOWED_VISIBILITY_SCOPES = frozenset({"personal", "department", "global"})


@router.get("/dashboards/catalog")
def dashboard_catalog(
    _current_user: AppUser = Depends(require_authenticated_user),
):
    return success_response([])


@router.get("/dashboards/my")
def my_dashboard(
    _current_user: AppUser = Depends(require_authenticated_user),
):
    return success_response([])


@router.post("/dashboards")
def create_dashboard(
    request: Request,
    payload: Any = Body(default=None),
    _current_user: AppUser = Depends(require_authenticated_user),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    parsed_payload = _parse_dashboard_payload(payload)
    if not isinstance(parsed_payload, dict):
        return parsed_payload

    return success_response(
        {
            "status": "not_persisted",
            "message": "Dashboard persistence is not implemented in this checkpoint.",
            "dashboard": parsed_payload,
        },
        status_code=202,
    )


@router.post("/query-runs/{query_run_id}/save-card")
def save_query_run_as_card(
    query_run_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    _current_user: AppUser = Depends(require_authenticated_user),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    parsed_payload = _parse_save_card_payload(payload)
    if not isinstance(parsed_payload, dict):
        return parsed_payload

    return success_response(
        {
            "status": "not_persisted",
            "message": "Save-card persistence is not implemented in this checkpoint.",
            "query_run_id": str(query_run_id),
            "card": parsed_payload,
        },
        status_code=202,
    )


def _csrf_error_response(request: Request):
    session_data = session_from_request(request)
    if session_data is None or not csrf_is_valid(request, session_data):
        return error_response(
            code="CSRF_TOKEN_MISSING",
            message="A valid CSRF token is required for this request.",
            status_code=403,
        )
    return None


def _parse_dashboard_payload(payload: Any):
    if not isinstance(payload, dict):
        return _invalid_dashboard_request_response()

    if set(payload) - ALLOWED_DASHBOARD_FIELDS:
        return _invalid_dashboard_request_response()

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return _invalid_dashboard_request_response()

    parsed: dict[str, Any] = {"title": title.strip()}

    description_or_error = _optional_string(payload, "description")
    if description_or_error is _INVALID:
        return _invalid_dashboard_request_response()
    if "description" in payload:
        parsed["description"] = description_or_error

    visibility_scope_or_error = _optional_visibility_scope(payload)
    if visibility_scope_or_error is _INVALID:
        return _invalid_dashboard_request_response()
    if "visibility_scope" in payload:
        parsed["visibility_scope"] = visibility_scope_or_error

    department_id_or_error = _optional_uuid_string(payload, "department_id")
    if department_id_or_error is _INVALID:
        return _invalid_dashboard_request_response()
    if "department_id" in payload:
        parsed["department_id"] = department_id_or_error

    return parsed


def _parse_save_card_payload(payload: Any):
    if not isinstance(payload, dict):
        return _invalid_save_card_request_response()

    if set(payload) - ALLOWED_SAVE_CARD_FIELDS:
        return _invalid_save_card_request_response()

    parsed: dict[str, Any] = {}

    dashboard_id_or_error = _optional_uuid_string(payload, "dashboard_id")
    if dashboard_id_or_error is _INVALID:
        return _invalid_save_card_request_response()
    if "dashboard_id" in payload:
        parsed["dashboard_id"] = dashboard_id_or_error

    title_or_error = _optional_non_empty_string(payload, "title")
    if title_or_error is _INVALID:
        return _invalid_save_card_request_response()
    if "title" in payload:
        parsed["title"] = title_or_error

    description_or_error = _optional_string(payload, "description")
    if description_or_error is _INVALID:
        return _invalid_save_card_request_response()
    if "description" in payload:
        parsed["description"] = description_or_error

    card_type_or_error = _optional_non_empty_string(payload, "card_type")
    if card_type_or_error is _INVALID:
        return _invalid_save_card_request_response()
    if "card_type" in payload:
        parsed["card_type"] = card_type_or_error

    return parsed


def _optional_visibility_scope(payload: dict[str, Any]):
    if "visibility_scope" not in payload:
        return None

    visibility_scope = payload["visibility_scope"]
    if visibility_scope is None:
        return None
    if not isinstance(visibility_scope, str):
        return _INVALID

    safe_visibility_scope = visibility_scope.strip().lower()
    if safe_visibility_scope not in ALLOWED_VISIBILITY_SCOPES:
        return _INVALID
    return safe_visibility_scope


def _optional_uuid_string(payload: dict[str, Any], key: str):
    if key not in payload:
        return None

    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return _INVALID

    try:
        return str(UUID(value.strip()))
    except ValueError:
        return _INVALID


def _optional_non_empty_string(payload: dict[str, Any], key: str):
    if key not in payload:
        return None

    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return _INVALID
    return value.strip()


def _optional_string(payload: dict[str, Any], key: str):
    if key not in payload:
        return None

    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, str):
        return _INVALID
    return value.strip()


def _invalid_dashboard_request_response():
    return error_response(
        code="INVALID_DASHBOARD_REQUEST",
        message="Dashboard request is invalid or unsupported.",
        status_code=400,
    )


def _invalid_save_card_request_response():
    return error_response(
        code="INVALID_SAVE_CARD_REQUEST",
        message="Save-card request is invalid or unsupported.",
        status_code=400,
    )


class _Invalid:
    pass


_INVALID = _Invalid()
