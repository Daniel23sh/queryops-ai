from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.responses import error_response, success_response
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.dashboards.policy import dashboard_is_visible
from app.models.product import (
    AppUser,
    Dashboard,
    DashboardCard,
    QueryRun,
    RunStatus,
    SavedQuery,
    VisibilityScope,
)
from app.query_engine.card_refresh import (
    CardRefreshError,
    CardRefreshSQLExecutor,
    get_card_refresh_sql_executor,
    refresh_dashboard_card,
)


router = APIRouter(prefix="/api/v1")

ALLOWED_DASHBOARD_FIELDS = frozenset(
    {"title", "description", "visibility_scope", "department_id"}
)
ALLOWED_SAVE_CARD_FIELDS = frozenset(
    {"dashboard_id", "title", "description", "card_type"}
)
ALLOWED_VISIBILITY_SCOPES = frozenset({"personal", "department", "global"})
ALLOWED_CARD_TYPES = frozenset({"table"})


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
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    parsed_payload = _parse_save_card_payload(payload)
    if not isinstance(parsed_payload, dict):
        return parsed_payload

    access_context = build_user_access_context(current_user, db)
    if not access_context.has_permission("can_create_card"):
        return _forbidden_response()

    query_run = db.get(QueryRun, query_run_id)
    if query_run is None or query_run.user_id != current_user.id:
        return _query_run_not_found_response()
    if not _query_run_can_be_saved(query_run):
        return _query_run_not_saveable_response()

    dashboard = db.get(Dashboard, UUID(parsed_payload["dashboard_id"]))
    if dashboard is None or dashboard.is_archived:
        return _dashboard_not_found_response()
    if not _can_save_card_to_dashboard(dashboard, current_user, access_context):
        return _forbidden_response()

    title = _title_for_saved_card(parsed_payload, query_run)
    description = parsed_payload.get("description")
    saved_query = SavedQuery(
        owner_user_id=current_user.id,
        name=title,
        description=description,
        natural_language_question=_natural_language_question_for_saved_query(
            query_run,
            fallback=title,
        ),
        generated_sql=query_run.generated_sql,
        visibility_scope=dashboard.visibility_scope,
        department_id=dashboard.department_id,
        parameters={},
        result_schema=None,
    )
    db.add(saved_query)
    db.flush()

    query_run.saved_query_id = saved_query.id
    card = DashboardCard(
        dashboard_id=dashboard.id,
        saved_query_id=saved_query.id,
        title=title,
        description=description,
        card_type=parsed_payload["card_type"],
        position=_next_card_position(db, dashboard.id),
        layout=None,
        config=None,
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    return success_response(_serialize_dashboard_card(card), status_code=201)


@router.post("/cards/{card_id}/refresh")
def refresh_card(
    card_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    sql_executor: CardRefreshSQLExecutor = Depends(get_card_refresh_sql_executor),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    if not isinstance(payload, dict) or payload:
        return _invalid_card_refresh_request_response()

    access_context = build_user_access_context(current_user, db)
    card = db.scalar(
        select(DashboardCard)
        .options(
            selectinload(DashboardCard.dashboard),
            selectinload(DashboardCard.saved_query),
        )
        .where(DashboardCard.id == card_id)
    )
    if card is None or card.dashboard is None or card.dashboard.is_archived:
        return _card_not_found_response()
    if not dashboard_is_visible(card.dashboard, current_user, access_context):
        return _card_refresh_not_allowed_response()

    try:
        result = refresh_dashboard_card(
            db,
            card=card,
            current_user=current_user,
            access_context=access_context,
            sql_executor=sql_executor,
        )
    except CardRefreshError as error:
        return error_response(
            code=error.code,
            message=error.message,
            status_code=error.status_code,
        )

    return success_response(jsonable_encoder(result))


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
    return dashboard_is_visible(dashboard, current_user, access_context)


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


def _can_save_card_to_dashboard(
    dashboard: Dashboard,
    current_user: AppUser,
    access_context: UserAccessContext,
) -> bool:
    if dashboard.visibility_scope == VisibilityScope.PERSONAL.value:
        return dashboard.owner_user_id == current_user.id

    if dashboard.visibility_scope == VisibilityScope.DEPARTMENT.value:
        if dashboard.department_id is None:
            return False
        if not _has_any_permission(
            access_context,
            {"can_create_department_dashboard", "can_manage_department_dashboard"},
        ):
            return False
        return _department_allowed_for_user(
            dashboard.department_id,
            current_user,
            access_context,
        )

    if dashboard.visibility_scope == VisibilityScope.GLOBAL.value:
        return access_context.has_global_scope and _has_any_permission(
            access_context,
            {"can_create_global_dashboard", "can_manage_global_dashboard"},
        )

    return False


def _query_run_can_be_saved(query_run: QueryRun) -> bool:
    if query_run.status != RunStatus.SUCCEEDED.value:
        return False

    metadata = query_run.query_metadata or {}
    if not isinstance(metadata, dict):
        return True
    if metadata.get("clarification_required") is True:
        return False
    if metadata.get("unsupported_reason") is not None:
        return False
    return True


def _title_for_saved_card(
    payload: dict[str, Any],
    query_run: QueryRun,
) -> str:
    title = payload.get("title")
    if isinstance(title, str) and title:
        return title
    return _natural_language_question_for_saved_query(query_run, fallback="Saved query")


def _natural_language_question_for_saved_query(
    query_run: QueryRun,
    *,
    fallback: str,
) -> str:
    question = query_run.natural_language_question
    if isinstance(question, str) and question.strip():
        return question.strip()
    return fallback


def _next_card_position(db: Session, dashboard_id: UUID) -> int:
    max_position = db.scalar(
        select(func.max(DashboardCard.position)).where(
            DashboardCard.dashboard_id == dashboard_id
        )
    )
    if max_position is None:
        return 0
    return int(max_position) + 1


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

    parsed: dict[str, Any] = {"card_type": "table"}

    dashboard_id_or_error = _optional_uuid_string(payload, "dashboard_id")
    if dashboard_id_or_error is _INVALID or dashboard_id_or_error is None:
        return _invalid_save_card_request_response()
    parsed["dashboard_id"] = dashboard_id_or_error

    if "title" in payload:
        title_or_error = _optional_non_empty_string(payload, "title")
        if title_or_error is _INVALID or title_or_error is None:
            return _invalid_save_card_request_response()
        parsed["title"] = title_or_error

    description_or_error = _optional_string(payload, "description")
    if description_or_error is _INVALID:
        return _invalid_save_card_request_response()
    if "description" in payload:
        parsed["description"] = description_or_error

    if "card_type" in payload:
        card_type_or_error = _optional_non_empty_string(payload, "card_type")
        if card_type_or_error is _INVALID or card_type_or_error is None:
            return _invalid_save_card_request_response()
        safe_card_type = card_type_or_error.lower()
        if safe_card_type not in ALLOWED_CARD_TYPES:
            return _invalid_save_card_request_response()
        parsed["card_type"] = safe_card_type

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


def _invalid_card_refresh_request_response():
    return error_response(
        code="INVALID_CARD_REFRESH_REQUEST",
        message="Card refresh request is invalid or unsupported.",
        status_code=400,
    )


def _card_not_found_response():
    return error_response(
        code="CARD_NOT_FOUND",
        message="Dashboard card was not found.",
        status_code=404,
    )


def _card_refresh_not_allowed_response():
    return error_response(
        code="CARD_REFRESH_NOT_ALLOWED",
        message="Dashboard card cannot be refreshed with your current permissions.",
        status_code=403,
    )


def _forbidden_response():
    return error_response(
        code="FORBIDDEN",
        message="You are not authorized to perform this action.",
        status_code=403,
    )


def _query_run_not_found_response():
    return error_response(
        code="QUERY_RUN_NOT_FOUND",
        message="Query run was not found.",
        status_code=404,
    )


def _query_run_not_saveable_response():
    return error_response(
        code="QUERY_RUN_NOT_SAVEABLE",
        message="Only successful owned query runs can be saved as dashboard cards.",
        status_code=400,
    )


def _dashboard_not_found_response():
    return error_response(
        code="DASHBOARD_NOT_FOUND",
        message="Dashboard was not found.",
        status_code=404,
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
