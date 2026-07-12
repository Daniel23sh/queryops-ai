from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.responses import error_response
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.dashboards.policy import dashboard_is_visible
from app.exports.csv_exporter import rows_to_csv
from app.models.product import (
    AppAuditLog,
    AppUser,
    DashboardCard,
    DataResource,
    QueryRun,
    RunStatus,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.schema_context import SchemaContextOptions, build_schema_context
from app.query_engine.sql_executor import (
    SQLExecutionOptions,
    SQLExecutionResult,
    execute_validated_sql,
)
from app.query_engine.sql_validator import SQLValidationResult, validate_sql


router = APIRouter(prefix="/api/v1")

EXPORT_PERMISSION = "can_export_results"
RESTRICTED_EXPORT_PERMISSION = "can_export_restricted_results"
ALLOWED_EXPORT_FIELDS = frozenset({"filename", "include_headers"})
EXPORT_QUERY_ACTION = "query:scoped_data"
EXPORT_ROW_LIMIT = 1_000
MAX_EXPORT_FILENAME_LENGTH = 255
SAFE_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ExportResourcePolicyDecision:
    allowed: bool
    restricted_tables: tuple[str, ...]
    override_used: bool


class ExportSQLExecutor(Protocol):
    def __call__(
        self,
        db: Session,
        access_context: UserAccessContext,
        validation_result: SQLValidationResult,
        *,
        options: SQLExecutionOptions | None = None,
    ) -> SQLExecutionResult:
        raise NotImplementedError


def get_export_sql_executor() -> ExportSQLExecutor:
    return execute_validated_sql


@router.post("/query-runs/{query_run_id}/export-csv")
def export_query_run_csv(
    query_run_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    sql_executor: ExportSQLExecutor = Depends(get_export_sql_executor),
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

    return _export_query_run_as_csv(
        db,
        access_context,
        query_run,
        parsed_payload,
        sql_executor,
        request=request,
        current_user=current_user,
        filename=_query_run_csv_filename(query_run.id, parsed_payload["filename"]),
        audit_entity_type="query_run_export",
        audit_entity_id=query_run.id,
        audit_summary=f"CSV export completed for query run {query_run.id}.",
        audit_metadata={
            "export_source": "query_run",
            "query_run_id": str(query_run.id),
        },
        not_exportable_response=_query_run_not_exportable_response,
    )


@router.post("/cards/{card_id}/export-csv")
def export_card_csv(
    card_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    sql_executor: ExportSQLExecutor = Depends(get_export_sql_executor),
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
        .options(
            selectinload(DashboardCard.dashboard),
            selectinload(DashboardCard.saved_query),
        )
        .where(DashboardCard.id == card_id)
    )
    if card is None or card.dashboard is None or card.dashboard.is_archived:
        return _card_not_found_response()
    if not dashboard_is_visible(card.dashboard, current_user, access_context):
        return _forbidden_response()
    if card.saved_query_id is None or card.saved_query is None:
        return _card_not_exportable_response()

    query_run = _query_run_for_card_export(db, card)
    if query_run is None:
        return _card_not_exportable_response()
    if not isinstance(query_run.executed_sql, str) or not query_run.executed_sql.strip():
        return _card_not_exportable_response()

    return _export_query_run_as_csv(
        db,
        access_context,
        query_run,
        parsed_payload,
        sql_executor,
        request=request,
        current_user=current_user,
        filename=_card_csv_filename(card.id, parsed_payload["filename"]),
        audit_entity_type="dashboard_card_export",
        audit_entity_id=card.id,
        audit_summary=f"CSV export completed for dashboard card {card.id}.",
        audit_metadata={
            "export_source": "dashboard_card",
            "card_id": str(card.id),
            "dashboard_id": str(card.dashboard_id),
            "saved_query_id": str(card.saved_query_id),
            "query_run_id": str(query_run.id),
        },
        not_exportable_response=_card_not_exportable_response,
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


def _export_query_run_as_csv(
    db: Session,
    access_context: UserAccessContext,
    query_run: QueryRun,
    parsed_payload: dict[str, Any],
    sql_executor: ExportSQLExecutor,
    *,
    request: Request,
    current_user: AppUser,
    filename: str,
    audit_entity_type: str,
    audit_entity_id: UUID,
    audit_summary: str,
    audit_metadata: dict[str, Any],
    not_exportable_response,
):
    if query_run.status != RunStatus.SUCCEEDED.value:
        return not_exportable_response()
    if not isinstance(query_run.executed_sql, str) or not query_run.executed_sql.strip():
        return not_exportable_response()

    referenced_tables_or_error = _referenced_tables_for_export(query_run)
    if not isinstance(referenced_tables_or_error, list):
        return referenced_tables_or_error
    referenced_tables = referenced_tables_or_error

    resource_policy = _evaluate_export_resource_policy(
        db,
        access_context,
        referenced_tables,
    )
    if not resource_policy.allowed:
        return _csv_export_not_allowed_response()

    validation_result = _validate_export_sql(
        db,
        access_context,
        query_run.executed_sql,
    )
    if not validation_result.valid or validation_result.sanitized_sql is None:
        return _csv_export_not_allowed_response()
    if sorted(validation_result.referenced_tables) != referenced_tables:
        return _csv_export_not_allowed_response()

    execution_result = sql_executor(
        db,
        access_context,
        validation_result,
        options=SQLExecutionOptions(
            row_limit=EXPORT_ROW_LIMIT,
            query_action=EXPORT_QUERY_ACTION,
        ),
    )
    if execution_result.status != "succeeded":
        return _csv_export_execution_error_response(execution_result)

    csv_body = rows_to_csv(
        execution_result.columns,
        execution_result.rows,
        include_headers=parsed_payload["include_headers"],
    )
    response = _csv_response(csv_body, filename=filename)
    _record_csv_export_audit(
        db,
        request=request,
        current_user=current_user,
        entity_type=audit_entity_type,
        entity_id=audit_entity_id,
        summary=audit_summary,
        metadata={
            **audit_metadata,
            "format": "csv",
            "filename": filename,
            "include_headers": parsed_payload["include_headers"],
            "row_count": execution_result.row_count,
            "referenced_tables": referenced_tables,
            "export_policy_override": resource_policy.override_used,
            "restricted_tables": list(resource_policy.restricted_tables),
            **(
                {"override_permission": RESTRICTED_EXPORT_PERMISSION}
                if resource_policy.override_used
                else {}
            ),
        },
    )
    return response


def _record_csv_export_audit(
    db: Session,
    *,
    request: Request,
    current_user: AppUser,
    entity_type: str,
    entity_id: UUID,
    summary: str,
    metadata: dict[str, Any],
) -> None:
    audit_log = AppAuditLog(
        actor_user_id=current_user.id,
        event_type="csv_export",
        action="export_csv",
        status="succeeded",
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        ip_address=request.client.host if request.client is not None else None,
        user_agent=request.headers.get("user-agent"),
        audit_metadata=metadata,
    )
    db.add(audit_log)
    db.commit()


def _query_run_for_card_export(db: Session, card: DashboardCard) -> QueryRun | None:
    if card.saved_query_id is None:
        return None

    return db.scalar(
        select(QueryRun)
        .where(
            QueryRun.saved_query_id == card.saved_query_id,
            QueryRun.status == RunStatus.SUCCEEDED.value,
        )
        .order_by(
            QueryRun.completed_at.desc(),
            QueryRun.created_at.desc(),
            QueryRun.id.desc(),
        )
        .limit(1)
    )


def _referenced_tables_for_export(query_run: QueryRun):
    metadata = query_run.query_metadata
    if not isinstance(metadata, dict):
        return _csv_export_not_allowed_response()

    raw_tables = metadata.get("referenced_tables")
    if not isinstance(raw_tables, list | tuple):
        return _csv_export_not_allowed_response()
    if not raw_tables:
        return _csv_export_not_allowed_response()

    tables: set[str] = set()
    for raw_table in raw_tables:
        if not isinstance(raw_table, str):
            return _csv_export_not_allowed_response()
        table_name = raw_table.strip().lower()
        if not table_name or SAFE_TABLE_NAME_RE.fullmatch(table_name) is None:
            return _csv_export_not_allowed_response()
        tables.add(table_name)

    if not tables:
        return _csv_export_not_allowed_response()
    return sorted(tables)


def _evaluate_export_resource_policy(
    db: Session,
    access_context: UserAccessContext,
    referenced_tables: list[str],
) -> ExportResourcePolicyDecision:
    resources = db.scalars(
        select(DataResource)
        .where(
            DataResource.domain == "it_operations",
            DataResource.resource_type == "table",
            DataResource.table_name.in_(referenced_tables),
        )
        .order_by(DataResource.table_name)
    ).all()
    resources_by_table = {resource.table_name: resource for resource in resources}

    restricted_tables: list[str] = []
    for table_name in referenced_tables:
        resource = resources_by_table.get(table_name)
        if resource is None:
            return ExportResourcePolicyDecision(False, (), False)
        if resource.is_queryable is not True:
            return ExportResourcePolicyDecision(False, (), False)
        if resource.is_exportable is not True:
            restricted_tables.append(table_name)

    normalized_restricted_tables = tuple(sorted(restricted_tables))
    if not normalized_restricted_tables:
        return ExportResourcePolicyDecision(True, (), False)
    if not access_context.has_permission(RESTRICTED_EXPORT_PERMISSION):
        return ExportResourcePolicyDecision(
            False,
            normalized_restricted_tables,
            False,
        )
    return ExportResourcePolicyDecision(
        True,
        normalized_restricted_tables,
        True,
    )


def _validate_export_sql(
    db: Session,
    access_context: UserAccessContext,
    executed_sql: str,
) -> SQLValidationResult:
    schema_context = build_schema_context(
        db,
        access_context,
        domain_pack=load_it_operations_domain_pack(),
        options=SchemaContextOptions(query_action=EXPORT_QUERY_ACTION),
    )
    return validate_sql(executed_sql, schema_context)


def _csv_response(csv_body: str, *, filename: str) -> Response:
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _query_run_csv_filename(query_run_id: UUID, filename: str | None) -> str:
    base_filename = filename or f"query-run-{query_run_id}"
    if base_filename.lower().endswith(".csv"):
        return base_filename
    return f"{base_filename}.csv"


def _card_csv_filename(card_id: UUID, filename: str | None) -> str:
    base_filename = filename or f"card-{card_id}"
    if base_filename.lower().endswith(".csv"):
        return base_filename
    return f"{base_filename}.csv"


def _export_filename(value: Any):
    if not isinstance(value, str):
        return _INVALID

    filename = value.strip()
    if not filename or filename in {".", ".."}:
        return _INVALID
    if any(ord(character) < 32 or ord(character) > 126 for character in filename):
        return _INVALID
    if "/" in filename or "\\" in filename or "\x00" in filename:
        return _INVALID
    if '"' in filename or ";" in filename:
        return _INVALID

    parts = filename.split(".")
    if len(parts) > 1:
        if len(parts) != 2 or parts[-1].lower() != "csv" or not parts[0]:
            return _INVALID

    final_filename_length = (
        len(filename) if filename.lower().endswith(".csv") else len(filename) + 4
    )
    if final_filename_length > MAX_EXPORT_FILENAME_LENGTH:
        return _INVALID

    return filename


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
        message="Only successful owned query runs with safe executed SQL can be exported.",
        status_code=400,
    )


def _card_not_found_response():
    return error_response(
        code="CARD_NOT_FOUND",
        message="Dashboard card was not found.",
        status_code=404,
    )


def _card_not_exportable_response():
    return error_response(
        code="CARD_NOT_EXPORTABLE",
        message="Dashboard card cannot be exported as CSV.",
        status_code=400,
    )


def _csv_export_not_allowed_response():
    return error_response(
        code="CSV_EXPORT_NOT_ALLOWED",
        message="CSV export is not allowed for this resource.",
        status_code=403,
    )


def _csv_export_execution_error_response(execution_result: SQLExecutionResult):
    if execution_result.error_code in {
        "access_denied",
        "invalid_sql",
        "missing_referenced_tables",
        "resource_not_found",
        "resource_not_queryable",
        "unsafe_sql",
    }:
        return _csv_export_not_allowed_response()

    return error_response(
        code="CSV_EXPORT_FAILED",
        message="CSV export failed safely.",
        status_code=500,
    )


class _Invalid:
    pass


_INVALID = _Invalid()
