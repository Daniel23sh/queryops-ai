from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.responses import error_response, success_response
from app.api.routes.query_templates import _template_is_allowed
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.models.product import AppUser, QueryRun, UserAccessScope
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.service import QueryEngineRequest, QueryEngineService


router = APIRouter(prefix="/api/v1")

ALLOWED_QUERY_RUN_FIELDS = frozenset({"question", "template_id", "parameters"})
ALLOWED_QUERY_CLARIFY_FIELDS = frozenset({"question"})
SCOPE_HISTORY_PERMISSIONS = frozenset(
    {"can_view_query_history_scope", "can_view_query_history_department"}
)
MAX_HISTORY_LIMIT = 100
DEFAULT_HISTORY_LIMIT = 25


def get_query_engine_service() -> QueryEngineService:
    return QueryEngineService()


@router.post("/queries/run")
def run_query(
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: QueryEngineService = Depends(get_query_engine_service),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    access_context = build_user_access_context(current_user, db)
    request_payload_or_error = _parse_query_run_payload(payload)
    if not isinstance(request_payload_or_error, dict):
        return request_payload_or_error

    question = request_payload_or_error["question"]
    template_id = request_payload_or_error.get("template_id")
    parameters = request_payload_or_error.get("parameters")
    if parameters not in (None, {}):
        return _parameters_not_supported_response()

    if template_id:
        template_error = _template_request_error(template_id, access_context)
        if template_error is not None:
            return template_error
    elif not access_context.has_permission("can_run_free_query"):
        return _forbidden_response()

    result = service.run(
        db,
        current_user,
        QueryEngineRequest(
            question=question,
            template_id=template_id,
        ),
    )
    query_run = _query_run_for_result(db, result.query_run_id)
    return success_response(
        _safe_json(
            _serialize_query_result(
                result,
                query_run,
                can_view_sql=access_context.has_permission("can_view_sql"),
                suggested_actions=_suggested_actions(
                    result,
                    query_run=query_run,
                    template_id=template_id,
                    access_context=access_context,
                ),
            )
        )
    )


@router.post("/queries/{query_run_id}/clarify")
def clarify_query(
    query_run_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: QueryEngineService = Depends(get_query_engine_service),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    request_payload_or_error = _parse_query_clarify_payload(payload)
    if not isinstance(request_payload_or_error, dict):
        return request_payload_or_error

    original_query_run = db.get(QueryRun, query_run_id)
    if original_query_run is None or original_query_run.user_id != current_user.id:
        return _query_run_not_found_response()

    access_context = build_user_access_context(current_user, db)
    if not access_context.has_permission("can_run_free_query"):
        return _forbidden_response()

    result = service.run(
        db,
        current_user,
        QueryEngineRequest(
            question=request_payload_or_error["question"],
            metadata={"clarified_from_query_run_id": str(original_query_run.id)},
        ),
    )
    query_run = _query_run_for_result(db, result.query_run_id)
    return success_response(
        _safe_json(
            _serialize_query_result(
                result,
                query_run,
                can_view_sql=access_context.has_permission("can_view_sql"),
                suggested_actions=[],
            )
        )
    )


@router.get("/queries/history")
def query_history(
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    limit: int = DEFAULT_HISTORY_LIMIT,
    offset: int = 0,
    include_sql: bool = True,
):
    access_context = build_user_access_context(current_user, db)
    safe_limit = max(1, min(int(limit), MAX_HISTORY_LIMIT))
    safe_offset = max(0, int(offset))
    query_runs = db.scalars(
        select(QueryRun)
        .where(QueryRun.user_id == current_user.id)
        .order_by(QueryRun.created_at.desc(), QueryRun.id.desc())
        .limit(safe_limit)
        .offset(safe_offset)
    ).all()

    return success_response(
        _safe_json(
            [
                _serialize_query_run(
                    query_run,
                    can_view_sql=include_sql
                    and access_context.has_permission("can_view_sql"),
                    include_save_capability=True,
                )
                for query_run in query_runs
            ]
        )
    )


@router.get("/queries/scope-history")
def query_scope_history(
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    limit: int = DEFAULT_HISTORY_LIMIT,
    offset: int = 0,
):
    return _scope_history_response(current_user, db, limit=limit, offset=offset)


@router.get("/queries/department-history")
def query_department_history(
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    limit: int = DEFAULT_HISTORY_LIMIT,
    offset: int = 0,
):
    return _scope_history_response(current_user, db, limit=limit, offset=offset)


@router.get("/queries/{query_run_id}")
def get_query_run(
    query_run_id: UUID,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    query_run = db.get(QueryRun, query_run_id)
    if query_run is None or query_run.user_id != current_user.id:
        return _query_run_not_found_response()

    access_context = build_user_access_context(current_user, db)
    return success_response(
        _safe_json(
            _serialize_query_run(
                query_run,
                can_view_sql=access_context.has_permission("can_view_sql"),
            )
        )
    )


def _scope_history_response(
    current_user: AppUser,
    db: Session,
    *,
    limit: int,
    offset: int,
):
    access_context = build_user_access_context(current_user, db)
    if not _can_view_scope_history(access_context):
        return _forbidden_response()

    safe_limit = max(1, min(int(limit), MAX_HISTORY_LIMIT))
    safe_offset = max(0, int(offset))
    query_runs = _scope_history_query_runs(
        db,
        access_context,
        limit=safe_limit,
        offset=safe_offset,
    )

    return success_response(
        _safe_json(
            [
                _serialize_query_run(
                    query_run,
                    can_view_sql=access_context.has_permission("can_view_sql"),
                )
                for query_run in query_runs
            ]
        )
    )


def _can_view_scope_history(access_context: UserAccessContext) -> bool:
    return access_context.has_global_scope or any(
        access_context.has_permission(permission)
        for permission in SCOPE_HISTORY_PERMISSIONS
    )


def _scope_history_query_runs(
    db: Session,
    access_context: UserAccessContext,
    *,
    limit: int,
    offset: int,
) -> list[QueryRun]:
    query = select(QueryRun).order_by(QueryRun.created_at.desc(), QueryRun.id.desc())

    if not access_context.has_global_scope:
        scope_ids = [scope.id for scope in access_context.scopes]
        if not scope_ids:
            return []
        visible_user_ids = select(UserAccessScope.user_id).where(
            UserAccessScope.scope_id.in_(scope_ids)
        )
        query = query.where(QueryRun.user_id.in_(visible_user_ids))

    return list(db.scalars(query.limit(limit).offset(offset)).all())


def _csrf_error_response(request: Request):
    session_data = session_from_request(request)
    if session_data is None or not csrf_is_valid(request, session_data):
        return error_response(
            code="CSRF_TOKEN_MISSING",
            message="A valid CSRF token is required for this request.",
            status_code=403,
        )
    return None


def _parse_query_run_payload(payload: Any):
    if not isinstance(payload, dict):
        return _invalid_query_request_response()

    unknown_fields = sorted(set(payload) - ALLOWED_QUERY_RUN_FIELDS)
    if unknown_fields:
        return _invalid_query_request_response()

    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        return _invalid_query_request_response()

    parsed: dict[str, Any] = {"question": question.strip()}
    if "template_id" in payload:
        template_id = payload["template_id"]
        if template_id is not None:
            if not isinstance(template_id, str) or not template_id.strip():
                return _invalid_query_request_response()
            parsed["template_id"] = template_id.strip()
        else:
            parsed["template_id"] = None

    if "parameters" in payload:
        parameters = payload["parameters"]
        if parameters is not None and not isinstance(parameters, dict):
            return _invalid_query_request_response()
        parsed["parameters"] = parameters

    return parsed


def _parse_query_clarify_payload(payload: Any):
    if not isinstance(payload, dict):
        return _invalid_query_request_response()

    unknown_fields = sorted(set(payload) - ALLOWED_QUERY_CLARIFY_FIELDS)
    if unknown_fields:
        return _invalid_query_request_response()

    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        return _invalid_query_request_response()

    return {"question": question.strip()}


def _template_request_error(
    template_id: str,
    access_context: UserAccessContext,
):
    if not access_context.has_permission("can_use_query_templates"):
        return _forbidden_response()

    domain_pack = load_it_operations_domain_pack()
    template = domain_pack.templates_by_id.get(template_id)
    if template is None or not _template_is_allowed(template, access_context):
        return _query_template_not_found_response()
    return None


def _query_run_for_result(db: Session, query_run_id: str | None) -> QueryRun | None:
    if query_run_id is None:
        return None
    try:
        return db.get(QueryRun, UUID(query_run_id))
    except ValueError:
        return None


def _serialize_query_result(
    result: Any,
    query_run: QueryRun | None,
    *,
    can_view_sql: bool,
    suggested_actions: list[dict[str, str]],
) -> dict[str, Any]:
    data = {
        "query_run_id": result.query_run_id,
        "status": result.status,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "duration_ms": result.duration_ms,
        "truncated": result.truncated,
        "message": result.message,
        "warnings": result.warnings,
        "clarification_required": result.clarification_required,
        "metadata": _safe_metadata(result.metadata),
        "suggested_actions": suggested_actions,
    }
    if result.error_code is not None:
        data["error_code"] = result.error_code
    if can_view_sql and query_run is not None:
        data["generated_sql"] = query_run.generated_sql
        data["executed_sql"] = query_run.executed_sql
    return data


def _suggested_actions(
    result: Any,
    *,
    query_run: QueryRun | None,
    template_id: str | None,
    access_context: UserAccessContext,
) -> list[dict[str, str]]:
    if (
        not access_context.has_permission("can_request_action")
        or template_id is None
        or query_run is None
        or result.status != "succeeded"
        or result.clarification_required
        or result.truncated
        or not result.rows
    ):
        return []
    template = load_it_operations_domain_pack().templates_by_id.get(template_id)
    suggestion = template.suggested_action if template is not None else None
    if suggestion is None or not _valid_result_selectors(
        result.rows,
        suggestion.result_identifier_column,
    ):
        return []
    return [
        {
            "action_type": suggestion.action_type,
            "label": suggestion.label,
            "selector_kind": suggestion.selector_kind,
            "result_identifier_column": suggestion.result_identifier_column,
        }
    ]


def _valid_result_selectors(rows: Any, identifier_column: str) -> bool:
    if not isinstance(rows, list) or not rows:
        return False
    selector_ids: set[UUID] = set()
    for row in rows:
        if not isinstance(row, dict):
            return False
        raw_selector = row.get(identifier_column)
        try:
            selector_ids.add(UUID(str(raw_selector)))
        except (TypeError, ValueError, AttributeError):
            return False
    return 1 <= len(selector_ids) <= 100


def _serialize_query_run(
    query_run: QueryRun,
    *,
    can_view_sql: bool,
    include_save_capability: bool = False,
) -> dict[str, Any]:
    data = {
        "id": str(query_run.id),
        "status": query_run.status,
        "natural_language_question": query_run.natural_language_question,
        "row_count": query_run.row_count,
        "duration_ms": query_run.duration_ms,
        "error_message": query_run.error_message,
        "created_at": query_run.created_at,
        "started_at": query_run.started_at,
        "completed_at": query_run.completed_at,
        "metadata": _safe_metadata(query_run.query_metadata or {}),
    }
    if include_save_capability:
        data["can_save_as_card"] = _query_run_can_be_saved_as_card(query_run)
    if can_view_sql:
        data["generated_sql"] = query_run.generated_sql
        data["executed_sql"] = query_run.executed_sql
    return data


def _query_run_can_be_saved_as_card(query_run: QueryRun) -> bool:
    if query_run.status != "succeeded" or query_run.saved_query_id is not None:
        return False
    metadata = query_run.query_metadata
    if not isinstance(metadata, dict):
        return True
    return not (
        metadata.get("clarification_required") is True
        or metadata.get("unsupported_reason") is not None
    )


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    if not isinstance(metadata, dict):
        return safe

    for key in (
        "provider",
        "model",
        "template_id",
        "scope_type",
        "clarified_from_query_run_id",
    ):
        _copy_optional_string_metadata(safe, metadata, key)

    if "referenced_tables" in metadata:
        referenced_tables = _safe_string_list(metadata["referenced_tables"])
        if referenced_tables is not None:
            safe["referenced_tables"] = referenced_tables

    if isinstance(metadata.get("clarification_required"), bool):
        safe["clarification_required"] = metadata["clarification_required"]

    validation = metadata.get("validation")
    if isinstance(validation, dict):
        safe["validation"] = {
            "valid": _safe_optional_bool(validation.get("valid")),
            "error_code": _safe_optional_string(validation.get("error_code")),
        }

    execution = metadata.get("execution")
    if isinstance(execution, dict):
        safe["execution"] = {
            "status": _safe_optional_string(execution.get("status")),
            "error_code": _safe_optional_string(execution.get("error_code")),
            "row_count": _safe_optional_int(execution.get("row_count")),
            "duration_ms": _safe_optional_number(execution.get("duration_ms")),
            "truncated": _safe_optional_bool(execution.get("truncated")),
        }

    self_correction = metadata.get("self_correction")
    if isinstance(self_correction, dict):
        safe["self_correction"] = {
            "attempted": _safe_optional_bool(self_correction.get("attempted")),
            "succeeded": _safe_optional_bool(self_correction.get("succeeded")),
            "original_error_code": _safe_optional_string(
                self_correction.get("original_error_code")
            ),
        }
        if "final_error_code" in self_correction:
            safe["self_correction"]["final_error_code"] = _safe_optional_string(
                self_correction.get("final_error_code")
            )

    return safe


def _copy_optional_string_metadata(
    safe: dict[str, Any],
    metadata: dict[str, Any],
    key: str,
) -> None:
    if key not in metadata:
        return
    value = metadata[key]
    if value is None or isinstance(value, str):
        safe[key] = value


def _safe_optional_string(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return None


def _safe_optional_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    return None


def _safe_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _safe_optional_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    return None


def _safe_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list | tuple | set):
        return None

    items = [item for item in value if isinstance(item, str)]
    if isinstance(value, set):
        return sorted(items)
    return items


def _safe_json(data: Any) -> Any:
    return jsonable_encoder(
        data,
        custom_encoder={
            Decimal: str,
            datetime: _encode_datetime,
        },
    )


def _encode_datetime(value: datetime) -> str:
    if value.tzinfo is not None:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value.isoformat()


def _forbidden_response():
    return error_response(
        code="FORBIDDEN",
        message="You are not authorized to perform this action.",
        status_code=403,
    )


def _query_template_not_found_response():
    return error_response(
        code="QUERY_TEMPLATE_NOT_FOUND",
        message="Query template was not found.",
        status_code=404,
    )


def _query_run_not_found_response():
    return error_response(
        code="QUERY_RUN_NOT_FOUND",
        message="Query run was not found.",
        status_code=404,
    )


def _parameters_not_supported_response():
    return error_response(
        code="QUERY_PARAMETERS_NOT_SUPPORTED",
        message="Query template parameters are not supported yet.",
        status_code=400,
    )


def _invalid_query_request_response():
    return error_response(
        code="INVALID_QUERY_REQUEST",
        message="Query request is invalid or unsupported.",
        status_code=400,
    )
