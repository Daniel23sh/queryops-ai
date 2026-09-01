from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.query_engine.llm_provider import (
    LLMProvider,
    LLMProviderFailure,
    PlanGenerationOutcome,
)
from app.query_engine.semantic_plan import SemanticPlan, ValidatedSemanticPlan


@dataclass(frozen=True)
class PlanGeneratorResult:
    provider_name: str
    model_name: str
    outcome: PlanGenerationOutcome = PlanGenerationOutcome.PLAN
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    semantic_plan: SemanticPlan | None = None
    validated_semantic_plan: ValidatedSemanticPlan | None = None
    unsupported_reason: str | None = None
    safe_error: str | None = None

    @property
    def clarification_required(self) -> bool:
        return self.outcome is PlanGenerationOutcome.CLARIFICATION

    @property
    def unsafe_request(self) -> bool:
        return self.outcome is PlanGenerationOutcome.UNSAFE_REQUEST

    @property
    def generation_failed(self) -> bool:
        return isinstance(
            self.generation_metadata.get("provider_failure_code"),
            str,
        )


class PlanGenerator:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def generate_plan(
        self,
        question: str,
        schema_context: Mapping[str, Any],
        user_context: Mapping[str, Any],
        options: Mapping[str, Any] | None = None,
    ) -> PlanGeneratorResult:
        request_options = options or {}
        try:
            provider_result = self.provider.generate_plan(
                question,
                schema_context,
                user_context,
                request_options,
            )
        except Exception as exc:
            return self._provider_error_result(exc)

        if not _provider_result_is_consistent(provider_result):
            return self._provider_error_result(
                LLMProviderFailure("provider_response_invalid")
            )

        if provider_result.outcome is PlanGenerationOutcome.CLARIFICATION:
            return PlanGeneratorResult(
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
                outcome=PlanGenerationOutcome.CLARIFICATION,
                generation_metadata=dict(provider_result.generation_metadata),
                semantic_plan=None,
                unsupported_reason=provider_result.unsupported_reason,
                safe_error=provider_result.safe_error,
            )

        if provider_result.outcome is PlanGenerationOutcome.UNSAFE_REQUEST:
            return PlanGeneratorResult(
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
                outcome=PlanGenerationOutcome.UNSAFE_REQUEST,
                generation_metadata=dict(provider_result.generation_metadata),
                semantic_plan=None,
                unsupported_reason="unsafe_request",
                safe_error=provider_result.safe_error,
            )

        return PlanGeneratorResult(
            provider_name=provider_result.provider_name,
            model_name=provider_result.model_name,
            outcome=PlanGenerationOutcome.PLAN,
            generation_metadata=dict(provider_result.generation_metadata),
            semantic_plan=provider_result.semantic_plan,
            unsupported_reason=None,
            safe_error=None,
        )

    def _provider_error_result(self, exc: Exception) -> PlanGeneratorResult:
        if isinstance(exc, LLMProviderFailure):
            metadata = {
                "provider_failure_code": exc.code,
                "provider_failure_fatal": exc.fatal,
            }
            unsupported_reason = exc.code
        else:
            metadata = {"provider_failure_code": "provider_unavailable"}
            unsupported_reason = "provider_error"
        return PlanGeneratorResult(
            provider_name=self.provider.provider_name,
            model_name=self.provider.model_name,
            outcome=PlanGenerationOutcome.CLARIFICATION,
            generation_metadata=metadata,
            unsupported_reason=unsupported_reason,
            safe_error="Semantic planning is unavailable.",
        )


def _provider_result_is_consistent(result: Any) -> bool:
    if result.outcome is PlanGenerationOutcome.PLAN:
        return (
            isinstance(result.semantic_plan, SemanticPlan)
            and result.unsupported_reason is None
            and result.safe_error is None
        )
    if result.outcome is PlanGenerationOutcome.CLARIFICATION:
        return (
            result.semantic_plan is None
            and isinstance(result.unsupported_reason, str)
            and bool(result.unsupported_reason)
        )
    if result.outcome is PlanGenerationOutcome.UNSAFE_REQUEST:
        return (
            result.semantic_plan is None
            and result.unsupported_reason == "unsafe_request"
        )
    return False
