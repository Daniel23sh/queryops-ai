from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.responses import error_response
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.models.product import (
    AppUser,
    Dashboard,
    DashboardCard,
    QueryRun,
    RunStatus,
    VisibilityScope,
)


router = APIRouter(prefix="/api/v1")

EXPORT_PERMISSION = "can_export_results"
ALLOWED_EXPORT_FIELDS = frozenset({"filename", "include_headers"})


@router.post("/query-runs/{query_run_id}/export-csv")
def export_query_run_csv(
    query_run_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    parsed_payload = _parse_export_payload(payload)
    if not isinstance(parsed_payload, dict):
        return parsed_payload

    access_context = build_user_access_context(current_user, db)
    if not access_context.has_permission(EXPORT_PERMISSION):
        return _forbidden_response()

    query_run = db.get(QueryRun, query_run_id)
    if query_run is None or query_run.user_id != current_user.id:
        return _query_run_not_found_response()
    if query_run.status != RunStatus.SUCCEEDED.value:
        return _query_run_not_exportable_response()

    return _export_not_implemented_response(
        resource_type="query_run",
        resource_id=query_run.id,
        filename=parsed_payload["filename"],
        include_headers=parsed_payload["include_headers"],
    )


@router.post("/cards/{card_id}/export-csv")
def export_card_csv(
    card_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    parsed_payload = _parse_export_payload(payload)
    if not isinstance(parsed_payload, dict):
        return parsed_payload

    access_context = build_user_access_context(current_user, db)
    if not access_context.has_permission(EXPORT_PERMISSION):
        return _forbidden_response()

    card = db.scalar(
        select(DashboardCard)
        .options(selectinload(DashboardCard.dashboard))
        .where(DashboardCard.id == card_id)
    )
    if card is None or card.dashboard is None or card.dashboard.is_archived:
        return _card_not_found_response()
    if not _dashboard_visible(card.dashboard, current_user, access_context):
        return _forbidden_response()

    return _export_not_implemented_response(
        resource_type="dashboard_card",
        resource_id=card.id,
        filename=parsed_payload["filename"],
        include_headers=parsed_payload["include_headers"],
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


def _parse_export_payload(payload: Any):
    if not isinstance(payload, dict):
        return _invalid_export_request_response()

    if set(payload) - ALLOWED_EXPORT_FIELDS:
        return _invalid_export_request_response()

    parsed: dict[str, Any] = {"filename": None, "include_headers": True}

    if "filename" in payload:
        filename_or_error = _export_filename(payload["filename"])
        if filename_or_error is _INVALID:
            return _invalid_export_request_response()
        parsed["filename"] = filename_or_error

    if "include_headers" in payload:
        include_headers = payload["include_headers"]
        if not isinstance(include_headers, bool):
            return _invalid_export_request_response()
        parsed["include_headers"] = include_headers

    return parsed


def _export_filename(value: Any):
    if not isinstance(value, str):
        return _INVALID

    filename = value.strip()
    if not filename or filename in {".", ".."}:
        return _INVALID
    if "/" in filename or "\\" in filename or "\x00" in filename:
        return _INVALID
    if any(ord(character) < 32 for character in filename):
        return _INVALID

    parts = filename.split(".")
    if len(parts) > 1:
        if len(parts) != 2 or parts[-1].lower() != "csv" or not parts[0]:
            return _INVALID

    return filename


def _dashboard_visible(
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


def _invalid_export_request_response():
    return error_response(
        code="INVALID_EXPORT_REQUEST",
        message="Export request is invalid or unsupported.",
        status_code=400,
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


def _query_run_not_exportable_response():
    return error_response(
        code="QUERY_RUN_NOT_EXPORTABLE",
        message="Only successful owned query runs can be prepared for CSV export.",
        status_code=400,
    )


def _card_not_found_response():
    return error_response(
        code="CARD_NOT_FOUND",
        message="Dashboard card was not found.",
        status_code=404,
    )


def _export_not_implemented_response(
    *,
    resource_type: str,
    resource_id: UUID,
    filename: str | None,
    include_headers: bool,
):
    return error_response(
        code="CSV_EXPORT_NOT_IMPLEMENTED",
        message="CSV export execution is not implemented in this checkpoint.",
        status_code=501,
        details={
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "filename": filename,
            "include_headers": include_headers,
        },
    )


class _Invalid:
    pass


_INVALID = _Invalid()
