from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext
from app.auth.access_policy import APPROVED_TEMPLATE_QUERY_ACTION
from app.evaluation.contracts import EvaluationCase
from app.query_engine.domain_pack import DomainPack
from app.query_engine.schema_context import SchemaContextOptions, build_schema_context
from app.query_engine.sql_executor import (
    SQLExecutionOptions,
    SQLExecutionResult,
    execute_validated_sql,
)
from app.query_engine.sql_validator import validate_sql


class EvaluationBaselineError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class EvaluationBaselineResult:
    rows: tuple[dict[str, Any], ...]
    row_count: int
    referenced_tables: tuple[str, ...]


def execute_evaluation_baseline(
    db: Session,
    access_context: UserAccessContext,
    case: EvaluationCase,
    domain_pack: DomainPack,
    *,
    executor=execute_validated_sql,
) -> EvaluationBaselineResult:
    """Execute evaluator-only SQL without exposing it to generation or product APIs."""
    if case.baseline_sql is None:
        raise EvaluationBaselineError(
            "baseline_not_defined",
            "Evaluation case does not define an executable baseline.",
        )

    query_action = (
        APPROVED_TEMPLATE_QUERY_ACTION
        if case.template_id is not None
        else "query:scoped_data"
    )
    schema_context = build_schema_context(
        db,
        access_context,
        domain_pack=domain_pack,
        options=SchemaContextOptions(query_action=query_action),
    )
    validation = validate_sql(case.baseline_sql, schema_context)
    if not validation.valid or validation.sanitized_sql is None:
        raise EvaluationBaselineError(
            "baseline_validation_failed",
            "Trusted evaluation baseline failed runtime validation.",
        )
    if set(validation.referenced_tables) != set(case.expected_tables):
        raise EvaluationBaselineError(
            "baseline_tables_mismatch",
            "Trusted evaluation baseline references unexpected resources.",
        )

    execution: SQLExecutionResult = executor(
        db,
        access_context,
        validation,
        options=SQLExecutionOptions(query_action=query_action),
    )
    if execution.status != "succeeded":
        code = (
            execution.error_code
            if execution.error_code
            in {
                "access_denied",
                "database_error",
                "invalid_sql",
                "missing_referenced_tables",
                "postgres_required",
                "resource_not_found",
                "resource_not_queryable",
                "unsafe_sql",
            }
            else "baseline_execution_failed"
        )
        raise EvaluationBaselineError(
            f"baseline_{code}",
            "Trusted evaluation baseline could not be executed safely.",
        )
    return EvaluationBaselineResult(
        rows=tuple(dict(row) for row in execution.rows),
        row_count=execution.row_count,
        referenced_tables=tuple(execution.referenced_tables),
    )
