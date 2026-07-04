from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.responses import error_response, success_response
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.models.product import AppUser, Dashboard, DashboardCard, VisibilityScope


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
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    access_context = build_user_access_context(current_user, db)
    dashboards = db.scalars(
        select(Dashboard)
        .options(selectinload(Dashboard.cards))
        .where(Dashboard.is_archived.is_(False))
        .order_by(Dashboard.created_at, Dashboard.id)
    ).all()
    visible_dashboards = [
        dashboard
        for dashboard in dashboards
        if _dashboard_visible_in_catalog(dashboard, current_user, access_context)
    ]

    return success_response(
        [_serialize_dashboard(dashboard) for dashboard in visible_dashboards]
    )


@router.get("/dashboards/my")
def my_dashboard(
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    dashboards = db.scalars(
        select(Dashboard)
        .options(selectinload(Dashboard.cards))
        .where(
            Dashboard.owner_user_id == current_user.id,
            Dashboard.visibility_scope == VisibilityScope.PERSONAL.value,
            Dashboard.is_archived.is_(False),
        )
        .order_by(Dashboard.created_at, Dashboard.id)
    ).all()

    return success_response([_serialize_dashboard(dashboard) for dashboard in dashboards])


@router.post("/dashboards")
def create_dashboard(
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    parsed_payload = _parse_dashboard_payload(payload)
    if not isinstance(parsed_payload, dict):
        return parsed_payload

    access_context = build_user_access_context(current_user, db)
    dashboard_values_or_error = _dashboard_create_values(
        parsed_payload,
        current_user,
        access_context,
    )
    if not isinstance(dashboard_values_or_error, dict):
        return dashboard_values_or_error

    dashboard = Dashboard(
        owner_user_id=current_user.id,
        title=dashboard_values_or_error["title"],
        description=dashboard_values_or_error.get("description"),
        visibility_scope=dashboard_values_or_error["visibility_scope"],
        department_id=dashboard_values_or_error.get("department_id"),
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)

    return success_response(_serialize_dashboard(dashboard), status_code=201)


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


def _dashboard_visible_in_catalog(
    dashboard: Dashboard,
    current_user: AppUser,
    access_context: UserAccessContext,
) -> bool:
    if dashboard.visibility_scope == VisibilityScope.PERSONAL.value:
        return dashboard.owner_user_id == current_user.id

    if dashboard.visibility_scope == VisibilityScope.GLOBAL.value:
        return access_context.has_global_scope

    if dashboard.visibility_scope == VisibilityScope.DEPARTMENT.value:
        if access_context.has_global_scope:
            return True
        if dashboard.department_id is None:
            return False
        if current_user.department_id == dashboard.department_id:
            return True
        return any(
            scope.type == "department" and scope.department_id == dashboard.department_id
            for scope in access_context.scopes
        )

    return False


def _dashboard_create_values(
    payload: dict[str, Any],
    current_user: AppUser,
    access_context: UserAccessContext,
):
    visibility_scope = payload.get("visibility_scope") or VisibilityScope.PERSONAL.value
    department_id = _department_uuid_from_payload(payload)

    if visibility_scope == VisibilityScope.PERSONAL.value:
        if not access_context.has_permission("can_create_personal_dashboard"):
            return _forbidden_response()
        department_id = None

    elif visibility_scope == VisibilityScope.DEPARTMENT.value:
        if not _has_any_permission(
            access_context,
            {"can_create_department_dashboard", "can_manage_department_dashboard"},
        ):
            return _forbidden_response()
        if department_id is None:
            department_id = current_user.department_id
        if department_id is None:
            return _invalid_dashboard_request_response()
        if not _department_allowed_for_user(department_id, current_user, access_context):
            return _forbidden_response()

    elif visibility_scope == VisibilityScope.GLOBAL.value:
        if not access_context.has_global_scope or not _has_any_permission(
            access_context,
            {"can_create_global_dashboard", "can_manage_global_dashboard"},
        ):
            return _forbidden_response()
        department_id = None

    else:
        return _invalid_dashboard_request_response()

    return {
        "title": payload["title"],
        "description": payload.get("description"),
        "visibility_scope": visibility_scope,
        "department_id": department_id,
    }


def _department_uuid_from_payload(payload: dict[str, Any]) -> UUID | None:
    department_id = payload.get("department_id")
    if department_id is None:
        return None
    return UUID(str(department_id))


def _department_allowed_for_user(
    department_id: UUID,
    current_user: AppUser,
    access_context: UserAccessContext,
) -> bool:
    if access_context.has_global_scope:
        return True
    if current_user.department_id == department_id:
        return True
    return any(
        scope.type == "department" and scope.department_id == department_id
        for scope in access_context.scopes
    )


def _has_any_permission(
    access_context: UserAccessContext,
    permission_keys: set[str],
) -> bool:
    return any(access_context.has_permission(permission) for permission in permission_keys)


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


def _forbidden_response():
    return error_response(
        code="FORBIDDEN",
        message="You are not authorized to perform this action.",
        status_code=403,
    )


def _serialize_dashboard(dashboard: Dashboard) -> dict[str, Any]:
    return {
        "id": str(dashboard.id),
        "title": dashboard.title,
        "description": dashboard.description,
        "visibility_scope": dashboard.visibility_scope,
        "department_id": str(dashboard.department_id)
        if dashboard.department_id is not None
        else None,
        "is_archived": dashboard.is_archived,
        "created_at": _serialize_datetime(dashboard.created_at),
        "updated_at": _serialize_datetime(dashboard.updated_at),
        "cards": [
            _serialize_dashboard_card(card)
            for card in sorted(
                dashboard.cards,
                key=lambda card: (card.position, card.created_at, str(card.id)),
            )
        ],
    }


def _serialize_dashboard_card(card: DashboardCard) -> dict[str, Any]:
    return {
        "id": str(card.id),
        "dashboard_id": str(card.dashboard_id),
        "saved_query_id": str(card.saved_query_id)
        if card.saved_query_id is not None
        else None,
        "title": card.title,
        "description": card.description,
        "card_type": card.card_type,
        "position": card.position,
        "layout": card.layout,
        "config": card.config,
        "created_at": _serialize_datetime(card.created_at),
        "updated_at": _serialize_datetime(card.updated_at),
    }


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is not None:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value.isoformat()


class _Invalid:
    pass


_INVALID = _Invalid()
