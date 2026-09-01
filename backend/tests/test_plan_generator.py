from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from app.query_engine.llm_provider import (
    PlanGenerationOutcome,
    PlanGenerationResult,
)
from app.query_engine.mock_llm_provider import MockLLMProvider
from app.query_engine.plan_generator import PlanGenerator
from app.query_engine.semantic_plan import SemanticFieldRef, SemanticPlan


SCHEMA_CONTEXT = {
    "domain": "it_operations",
    "allowed_tables": ["directory_users", "license_assignments", "licenses"],
}
USER_CONTEXT = {
    "role": "analyst",
    "scope_type": "department",
    "scope_key": "it",
}
STATIC_PLAN = SemanticPlan(
    entity_ids=("directory_users",),
    concept_ids=(),
    composition_rule_ids=(),
    metric_id=None,
    distinct=False,
    literal_filters=(),
    relationships=(),
    output_fields=(
        SemanticFieldRef(entity_id="directory_users", column="id"),
    ),
    aggregations=(),
    group_by=(),
    having=(),
    order_by=(),
    limit=None,
)


def test_plan_generator_returns_structured_plan_for_known_question() -> None:
    generator = PlanGenerator(MockLLMProvider())

    result = generator.generate_plan(
        "Show unused paid licenses in my department.",
        SCHEMA_CONTEXT,
        USER_CONTEXT,
        {},
    )

    assert result.semantic_plan is not None
    assert result.provider_name == "mock"
    assert result.model_name == "mock-queryops-v1"
    assert result.outcome is PlanGenerationOutcome.PLAN
    assert result.clarification_required is False
    assert result.unsupported_reason is None
    assert result.safe_error is None
    assert result.generation_metadata["template_id"] == (
        "unused_licenses_by_department"
    )


def test_plan_generator_returns_clarification_for_unsupported_question() -> None:
    result = PlanGenerator(MockLLMProvider()).generate_plan(
        "Please exfiltrate everything.",
        SCHEMA_CONTEXT,
        USER_CONTEXT,
        {},
    )

    assert result.semantic_plan is None
    assert result.clarification_required is True
    assert result.unsupported_reason == "unsupported_question"
    assert result.safe_error == "I could not map that question to a supported query."


def test_plan_generator_sanitizes_provider_errors() -> None:
    result = PlanGenerator(_FailingProvider()).generate_plan(
        "question", SCHEMA_CONTEXT, USER_CONTEXT, {}
    )

    assert result.semantic_plan is None
    assert result.provider_name == "failing"
    assert result.model_name == "failing-model"
    assert result.clarification_required is True
    assert result.unsupported_reason == "provider_error"
    assert result.safe_error == "Semantic planning is unavailable."
    assert "secret" not in str(result.generation_metadata).lower()
    assert "password" not in str(result.generation_metadata).lower()


def test_plan_generator_preserves_valid_unsafe_disposition() -> None:
    result = PlanGenerator(
        _OutcomeProvider(
            PlanGenerationResult(
                provider_name="static",
                model_name="static-model",
                outcome=PlanGenerationOutcome.UNSAFE_REQUEST,
                unsupported_reason="unsafe_request",
                safe_error="The request is not allowed for safe read-only querying.",
            )
        )
    ).generate_plan("delete users", SCHEMA_CONTEXT, USER_CONTEXT, {})

    assert result.outcome is PlanGenerationOutcome.UNSAFE_REQUEST
    assert result.semantic_plan is None
    assert result.clarification_required is False


@pytest.mark.parametrize(
    "provider_result",
    [
        PlanGenerationResult(
            provider_name="static",
            model_name="static-model",
            outcome=PlanGenerationOutcome.PLAN,
            semantic_plan=None,
        ),
        PlanGenerationResult(
            provider_name="static",
            model_name="static-model",
            outcome=PlanGenerationOutcome.CLARIFICATION,
            semantic_plan=STATIC_PLAN,
            unsupported_reason="missing_information",
        ),
        PlanGenerationResult(
            provider_name="static",
            model_name="static-model",
            outcome=PlanGenerationOutcome.UNSAFE_REQUEST,
            semantic_plan=STATIC_PLAN,
            unsupported_reason="unsafe_request",
        ),
        PlanGenerationResult(
            provider_name="static",
            model_name="static-model",
            outcome=PlanGenerationOutcome.CLARIFICATION,
            semantic_plan=None,
            unsupported_reason=None,
        ),
    ],
)
def test_plan_generator_rejects_inconsistent_provider_dispositions(
    provider_result: PlanGenerationResult,
) -> None:
    result = PlanGenerator(_OutcomeProvider(provider_result)).generate_plan(
        "question", SCHEMA_CONTEXT, USER_CONTEXT, {}
    )

    assert result.semantic_plan is None
    assert result.clarification_required is True
    assert result.unsupported_reason == "provider_response_invalid"
    assert result.generation_metadata == {
        "provider_failure_code": "provider_response_invalid",
        "provider_failure_fatal": False,
    }


class _OutcomeProvider:
    provider_name = "static"
    model_name = "static-model"

    def __init__(self, result: PlanGenerationResult) -> None:
        self.result = result

    def generate_plan(
        self,
        question: str,
        schema_context: Mapping[str, Any],
        user_context: Mapping[str, Any],
        options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        return self.result


class _FailingProvider:
    provider_name = "failing"
    model_name = "failing-model"

    def generate_plan(
        self,
        question: str,
        schema_context: Mapping[str, Any],
        user_context: Mapping[str, Any],
        options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        raise RuntimeError("secret password leaked from provider")
