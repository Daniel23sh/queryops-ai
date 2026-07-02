from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext, build_user_access_context
from app.models.product import AppUser, QueryRun, RunStatus
from app.query_engine.domain_pack import DomainPack, QueryTemplate
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import LLMProvider
from app.query_engine.mock_llm_provider import MockLLMProvider
from app.query_engine.result_formatter import (
    QUERY_RESULT_CLARIFICATION_MESSAGE,
    QUERY_RESULT_FAILURE_MESSAGE,
    QueryEngineServiceResult,
    format_query_result,
)
from app.query_engine.schema_context import (
    SchemaContextOptions,
    build_schema_context,
)
from app.query_engine.sql_executor import (
    SQLExecutionOptions,
    SQLExecutionResult,
    execute_validated_sql,
)
from app.query_engine.sql_generator import SQLGenerator, SQLGeneratorResult
from app.query_engine.sql_validator import SQLValidationResult, validate_sql


VALIDATION_FAILURE_CODE = "validation_failed"
TEMPLATE_NOT_FOUND_MESSAGE = "Query template was not found."
TEMPLATE_PARAMETER_MESSAGE = "Query template parameters are not supported safely."


class SQLExecutorCallable(Protocol):
    def __call__(
        self,
        db: Session,
        access_context: UserAccessContext,
        validation_result: SQLValidationResult,
        *,
        options: SQLExecutionOptions | None = None,
    ) -> SQLExecutionResult:
        """Execute an already validated SQL statement."""


ValidatorCallable = Callable[[str, dict[str, Any]], SQLValidationResult]
DomainPackLoaderCallable = Callable[[], DomainPack]


@dataclass(frozen=True)
class QueryEngineRequest:
    question: str
    template_id: str | None = None
    saved_query_id: uuid.UUID | None = None
    execution_options: SQLExecutionOptions | None = None


class QueryEngineService:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        executor: SQLExecutorCallable = execute_validated_sql,
        validator: ValidatorCallable = validate_sql,
        domain_pack_loader: DomainPackLoaderCallable = load_it_operations_domain_pack,
    ) -> None:
        self._provider = provider
        self._executor = executor
        self._validator = validator
        self._domain_pack_loader = domain_pack_loader

    def run(
        self,
        db: Session,
        user: AppUser,
        request: QueryEngineRequest,
    ) -> QueryEngineServiceResult:
        started_at = datetime.now(UTC)
        access_context = build_user_access_context(user, db)
        domain_pack = self._domain_pack_loader()
        schema_context = build_schema_context(
            db,
            access_context,
            domain_pack=domain_pack,
            options=SchemaContextOptions(template_id=request.template_id),
        )

        generation_result = self._generate_sql(
            request,
            domain_pack,
            schema_context,
            access_context,
        )
        metadata = _base_metadata(
            request,
            access_context,
            generation_result,
        )

        if generation_result.clarification_required or not generation_result.generated_sql:
            public_error = generation_result.safe_error or QUERY_RESULT_CLARIFICATION_MESSAGE
            query_run = self._persist_query_run(
                db,
                user,
                request,
                RunStatus.FAILED.value,
                started_at=started_at,
                generated_sql=None,
                executed_sql=None,
                row_count=0,
                duration_ms=0,
                error_message=public_error,
                metadata={
                    **metadata,
                    "clarification_required": True,
                    "unsupported_reason": (
                        generation_result.unsupported_reason or "unsupported_question"
                    ),
                },
            )
            return format_query_result(
                status="clarification_required",
                query_run_id=str(query_run.id),
                public_error=public_error,
                error_code=generation_result.unsupported_reason or "unsupported_question",
                clarification_required=True,
                metadata=query_run.query_metadata,
            )

        validation_result = self._validator(
            generation_result.generated_sql,
            schema_context,
        )
        metadata = {
            **metadata,
            "referenced_tables": sorted(validation_result.referenced_tables),
            "validation": _validation_summary(validation_result),
        }
        if not validation_result.valid or validation_result.sanitized_sql is None:
            public_error = validation_result.public_error or QUERY_RESULT_FAILURE_MESSAGE
            query_run = self._persist_query_run(
                db,
                user,
                request,
                RunStatus.FAILED.value,
                started_at=started_at,
                generated_sql=generation_result.generated_sql,
                executed_sql=None,
                row_count=0,
                duration_ms=0,
                error_message=public_error,
                metadata=metadata,
            )
            return format_query_result(
                status="failed",
                query_run_id=str(query_run.id),
                public_error=public_error,
                error_code=VALIDATION_FAILURE_CODE,
                metadata=query_run.query_metadata,
            )

        execution_result = self._executor(
            db,
            access_context,
            validation_result,
            options=request.execution_options or SQLExecutionOptions(),
        )
        metadata = {
            **metadata,
            "execution": _execution_summary(execution_result),
        }

        if execution_result.status != "succeeded":
            public_error = execution_result.public_error or QUERY_RESULT_FAILURE_MESSAGE
            query_run = self._persist_query_run(
                db,
                user,
                request,
                RunStatus.FAILED.value,
                started_at=started_at,
                generated_sql=generation_result.generated_sql,
                executed_sql=validation_result.sanitized_sql,
                row_count=0,
                duration_ms=int(round(execution_result.duration_ms)),
                error_message=public_error,
                metadata=metadata,
            )
            return format_query_result(
                status="failed",
                query_run_id=str(query_run.id),
                execution_result=execution_result,
                public_error=public_error,
                error_code=execution_result.error_code,
                metadata=query_run.query_metadata,
            )

        query_run = self._persist_query_run(
            db,
            user,
            request,
            RunStatus.SUCCEEDED.value,
            started_at=started_at,
            generated_sql=generation_result.generated_sql,
            executed_sql=validation_result.sanitized_sql,
            row_count=execution_result.row_count,
            duration_ms=int(round(execution_result.duration_ms)),
            error_message=None,
            metadata=metadata,
        )
        return format_query_result(
            status="succeeded",
            query_run_id=str(query_run.id),
            execution_result=execution_result,
            metadata=query_run.query_metadata,
        )

    def _generate_sql(
        self,
        request: QueryEngineRequest,
        domain_pack: DomainPack,
        schema_context: dict[str, Any],
        access_context: UserAccessContext,
    ) -> SQLGeneratorResult:
        if request.template_id is not None:
            return _template_generation_result(domain_pack, request.template_id)

        provider = self._provider or MockLLMProvider(domain_pack)
        generator = SQLGenerator(provider)
        return generator.generate_sql(
            request.question,
            schema_context,
            _user_generation_context(access_context),
            {},
        )

    def _persist_query_run(
        self,
        db: Session,
        user: AppUser,
        request: QueryEngineRequest,
        status: str,
        *,
        started_at: datetime,
        generated_sql: str | None,
        executed_sql: str | None,
        row_count: int,
        duration_ms: int,
        error_message: str | None,
        metadata: dict[str, Any],
    ) -> QueryRun:
        completed_at = datetime.now(UTC)
        query_run = QueryRun(
            user_id=user.id,
            saved_query_id=request.saved_query_id,
            status=status,
            natural_language_question=request.question,
            generated_sql=generated_sql,
            executed_sql=executed_sql,
            row_count=row_count,
            duration_ms=duration_ms,
            error_message=error_message,
            query_metadata=metadata,
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(query_run)
        db.commit()
        db.refresh(query_run)
        return query_run


def _template_generation_result(
    domain_pack: DomainPack,
    template_id: str,
) -> SQLGeneratorResult:
    template = domain_pack.templates_by_id.get(template_id)
    if template is None or template.sql is None:
        return SQLGeneratorResult(
            generated_sql=None,
            provider_name="domain_pack_template",
            model_name="template-sql",
            generation_metadata={"template_id": template_id},
            clarification_required=True,
            unsupported_reason="template_not_found",
            safe_error=TEMPLATE_NOT_FOUND_MESSAGE,
        )

    rendered_sql = _render_template_sql(template)
    if rendered_sql is None:
        return SQLGeneratorResult(
            generated_sql=None,
            provider_name="domain_pack_template",
            model_name="template-sql",
            generation_metadata={
                "template_id": template_id,
                "referenced_tables": list(template.referenced_tables),
            },
            clarification_required=True,
            unsupported_reason="template_parameters_required",
            safe_error=TEMPLATE_PARAMETER_MESSAGE,
        )

    return SQLGeneratorResult(
        generated_sql=rendered_sql,
        provider_name="domain_pack_template",
        model_name="template-sql",
        generation_metadata={
            "template_id": template.id,
            "source": "domain_pack_template",
            "domain": domain_pack.domain_id,
            "referenced_tables": list(template.referenced_tables),
            "parameters_applied": [
                parameter.name for parameter in template.parameters if parameter.default is not None
            ],
        },
        clarification_required=False,
    )


def _render_template_sql(template: QueryTemplate) -> str | None:
    if template.sql is None:
        return None

    sql = template.sql
    for parameter in template.parameters:
        if parameter.default is None:
            return None
        sql = re.sub(
            rf":{re.escape(parameter.name)}\b",
            _sql_literal(parameter.default),
            sql,
        )
    return sql


def _sql_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _user_generation_context(access_context: UserAccessContext) -> dict[str, Any]:
    return {
        "user_id": str(access_context.user_id),
        "role": access_context.role,
        "scope_type": access_context.default_scope.type
        if access_context.default_scope is not None
        else ("global" if access_context.has_global_scope else "none"),
        "has_global_scope": access_context.has_global_scope,
    }


def _base_metadata(
    request: QueryEngineRequest,
    access_context: UserAccessContext,
    generation_result: SQLGeneratorResult,
) -> dict[str, Any]:
    generation_metadata = generation_result.generation_metadata
    referenced_tables = generation_metadata.get("referenced_tables", [])
    return {
        "provider": generation_result.provider_name,
        "model": generation_result.model_name,
        "template_id": request.template_id or generation_metadata.get("template_id"),
        "referenced_tables": sorted(str(table) for table in referenced_tables),
        "scope_type": _metadata_scope_type(access_context),
        "clarification_required": generation_result.clarification_required,
    }


def _metadata_scope_type(access_context: UserAccessContext) -> str:
    if access_context.has_global_scope:
        return "global"
    if access_context.default_scope is not None:
        return access_context.default_scope.type
    return "none"


def _validation_summary(validation_result: SQLValidationResult) -> dict[str, Any]:
    return {
        "valid": validation_result.valid,
        "error_code": validation_result.error_code,
        "referenced_tables": sorted(validation_result.referenced_tables),
    }


def _execution_summary(execution_result: SQLExecutionResult) -> dict[str, Any]:
    return {
        "status": execution_result.status,
        "error_code": execution_result.error_code,
        "referenced_tables": sorted(execution_result.referenced_tables),
        "row_count": execution_result.row_count,
        "duration_ms": execution_result.duration_ms,
        "truncated": execution_result.truncated,
    }
