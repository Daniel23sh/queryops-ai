from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.query_engine.llm_provider import (
    LLMProvider,
    LLMProviderFailure,
    SQLGenerationOutcome,
)


@dataclass(frozen=True)
class SQLGeneratorResult:
    generated_sql: str | None
    provider_name: str
    model_name: str
    outcome: SQLGenerationOutcome = SQLGenerationOutcome.SQL
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    unsupported_reason: str | None = None
    safe_error: str | None = None

    @property
    def clarification_required(self) -> bool:
        return self.outcome is SQLGenerationOutcome.CLARIFICATION

    @property
    def unsafe_request(self) -> bool:
        return self.outcome is SQLGenerationOutcome.UNSAFE_REQUEST


class SQLGenerator:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def generate_sql(
        self,
        question: str,
        schema_context: Mapping[str, Any],
        user_context: Mapping[str, Any],
        options: Mapping[str, Any] | None = None,
    ) -> SQLGeneratorResult:
        request_options = options or {}
        try:
            provider_result = self.provider.generate_sql(
                question,
                schema_context,
                user_context,
                request_options,
            )
        except Exception as exc:
            return self._provider_error_result(exc)

        generated_sql = _normalize_sql(provider_result.generated_sql)
        if not _provider_result_is_consistent(provider_result, generated_sql):
            return self._provider_error_result(
                LLMProviderFailure("provider_response_invalid")
            )

        if provider_result.outcome is SQLGenerationOutcome.CLARIFICATION:
            return SQLGeneratorResult(
                generated_sql=generated_sql,
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
                outcome=SQLGenerationOutcome.CLARIFICATION,
                generation_metadata=dict(provider_result.generation_metadata),
                unsupported_reason=provider_result.unsupported_reason,
                safe_error=provider_result.safe_error,
            )

        if provider_result.outcome is SQLGenerationOutcome.UNSAFE_REQUEST:
            return SQLGeneratorResult(
                generated_sql=None,
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
                outcome=SQLGenerationOutcome.UNSAFE_REQUEST,
                generation_metadata=dict(provider_result.generation_metadata),
                unsupported_reason="unsafe_request",
                safe_error=provider_result.safe_error,
            )

        if generated_sql is None:
            return SQLGeneratorResult(
                generated_sql=None,
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
                outcome=SQLGenerationOutcome.CLARIFICATION,
                generation_metadata=dict(provider_result.generation_metadata),
                unsupported_reason="empty_provider_output",
                safe_error="The query provider did not return SQL.",
            )

        return SQLGeneratorResult(
            generated_sql=generated_sql,
            provider_name=provider_result.provider_name,
            model_name=provider_result.model_name,
            outcome=SQLGenerationOutcome.SQL,
            generation_metadata=dict(provider_result.generation_metadata),
            unsupported_reason=None,
            safe_error=None,
        )

    def _provider_error_result(self, exc: Exception) -> SQLGeneratorResult:
        if isinstance(exc, LLMProviderFailure):
            metadata = {
                "provider_failure_code": exc.code,
                "provider_failure_fatal": exc.fatal,
            }
            unsupported_reason = exc.code
        else:
            metadata = {"provider_failure_code": "provider_unavailable"}
            unsupported_reason = "provider_error"
        return SQLGeneratorResult(
            generated_sql=None,
            provider_name=self.provider.provider_name,
            model_name=self.provider.model_name,
            outcome=SQLGenerationOutcome.CLARIFICATION,
            generation_metadata=metadata,
            unsupported_reason=unsupported_reason,
            safe_error="SQL generation is unavailable.",
        )


def _normalize_sql(generated_sql: str | None) -> str | None:
    if generated_sql is None:
        return None

    normalized = generated_sql.strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].strip()
    return normalized or None


def _provider_result_is_consistent(
    result: Any,
    normalized_sql: str | None,
) -> bool:
    if result.outcome is SQLGenerationOutcome.SQL:
        return normalized_sql is not None and result.unsupported_reason is None
    if result.outcome is SQLGenerationOutcome.CLARIFICATION:
        return normalized_sql is None and result.unsupported_reason is not None
    if result.outcome is SQLGenerationOutcome.UNSAFE_REQUEST:
        return normalized_sql is None and result.unsupported_reason == "unsafe_request"
    return False
