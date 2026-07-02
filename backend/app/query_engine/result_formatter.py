from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.query_engine.sql_executor import SQLExecutionResult


QUERY_RESULT_SUCCESS_MESSAGE = "Query completed successfully."
QUERY_RESULT_FAILURE_MESSAGE = "Query could not be completed safely."
QUERY_RESULT_CLARIFICATION_MESSAGE = "I could not map that question to a supported query."


@dataclass(frozen=True)
class QueryEngineServiceResult:
    status: str
    query_run_id: str | None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    duration_ms: float = 0
    truncated: bool = False
    message: str = QUERY_RESULT_FAILURE_MESSAGE
    warnings: list[str] = field(default_factory=list)
    clarification_required: bool = False
    error_code: str | None = None
    public_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def format_query_result(
    *,
    status: str,
    query_run_id: str | None,
    execution_result: SQLExecutionResult | None = None,
    public_error: str | None = None,
    error_code: str | None = None,
    clarification_required: bool = False,
    metadata: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> QueryEngineServiceResult:
    if execution_result is None:
        columns: list[str] = []
        rows: list[dict[str, Any]] = []
        row_count = 0
        duration_ms = 0.0
        truncated = False
    else:
        columns = list(execution_result.columns)
        rows = [dict(row) for row in execution_result.rows]
        row_count = execution_result.row_count
        duration_ms = execution_result.duration_ms
        truncated = execution_result.truncated

    message = _message_for_status(
        status,
        public_error,
        clarification_required,
    )
    return QueryEngineServiceResult(
        status=status,
        query_run_id=query_run_id,
        columns=columns,
        rows=rows,
        row_count=row_count,
        duration_ms=duration_ms,
        truncated=truncated,
        message=message,
        warnings=sorted(set(warnings or [])),
        clarification_required=clarification_required,
        error_code=error_code,
        public_error=public_error,
        metadata=dict(metadata or {}),
    )


def _message_for_status(
    status: str,
    public_error: str | None,
    clarification_required: bool,
) -> str:
    if status == "succeeded":
        return QUERY_RESULT_SUCCESS_MESSAGE
    if clarification_required:
        return public_error or QUERY_RESULT_CLARIFICATION_MESSAGE
    return public_error or QUERY_RESULT_FAILURE_MESSAGE
