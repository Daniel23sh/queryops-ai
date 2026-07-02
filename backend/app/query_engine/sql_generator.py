from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.query_engine.llm_provider import LLMProvider


@dataclass(frozen=True)
class SQLGeneratorResult:
    generated_sql: str | None
    provider_name: str
    model_name: str
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    clarification_required: bool = False
    unsupported_reason: str | None = None
    safe_error: str | None = None


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
        if provider_result.clarification_required:
            return SQLGeneratorResult(
                generated_sql=generated_sql,
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
                generation_metadata=dict(provider_result.generation_metadata),
                clarification_required=True,
                unsupported_reason=provider_result.unsupported_reason,
                safe_error=provider_result.safe_error,
            )

        if generated_sql is None:
            return SQLGeneratorResult(
                generated_sql=None,
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
                generation_metadata=dict(provider_result.generation_metadata),
                clarification_required=True,
                unsupported_reason="empty_provider_output",
                safe_error="The query provider did not return SQL.",
            )

        return SQLGeneratorResult(
            generated_sql=generated_sql,
            provider_name=provider_result.provider_name,
            model_name=provider_result.model_name,
            generation_metadata=dict(provider_result.generation_metadata),
            clarification_required=False,
            unsupported_reason=None,
            safe_error=None,
        )

    def _provider_error_result(self, exc: Exception) -> SQLGeneratorResult:
        return SQLGeneratorResult(
            generated_sql=None,
            provider_name=self.provider.provider_name,
            model_name=self.provider.model_name,
            generation_metadata={"provider_error_type": type(exc).__name__},
            clarification_required=True,
            unsupported_reason="provider_error",
            safe_error="SQL generation is unavailable.",
        )


def _normalize_sql(generated_sql: str | None) -> str | None:
    if generated_sql is None:
        return None

    normalized = generated_sql.strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].strip()
    return normalized or None

