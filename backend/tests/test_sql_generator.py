from __future__ import annotations

from typing import Any

from app.query_engine.llm_provider import SQLGenerationResult
from app.query_engine.mock_llm_provider import MockLLMProvider
from app.query_engine.sql_generator import SQLGenerator


SCHEMA_CONTEXT = {
    "domain": "it_operations",
    "allowed_tables": ["directory_users", "license_assignments", "licenses"],
}
USER_CONTEXT = {
    "role": "analyst",
    "scope_type": "department",
    "scope_key": "it",
}


def test_sql_generator_returns_structured_result_for_known_template() -> None:
    generator = SQLGenerator(MockLLMProvider())

    result = generator.generate_sql(
        "Show unused paid licenses in my department.",
        SCHEMA_CONTEXT,
        USER_CONTEXT,
        {"template_id": "unused_licenses_by_department"},
    )

    assert result.generated_sql is not None
    assert result.generated_sql.startswith("SELECT ")
    assert result.generated_sql.endswith("NULLS FIRST")
    assert result.provider_name == "mock"
    assert result.model_name == "mock-queryops-v1"
    assert result.clarification_required is False
    assert result.unsupported_reason is None
    assert result.safe_error is None
    assert result.generation_metadata["template_id"] == "unused_licenses_by_department"


def test_sql_generator_normalizes_provider_sql_output() -> None:
    generator = SQLGenerator(_StaticProvider("  SELECT id FROM directory_users;  "))

    result = generator.generate_sql("question", SCHEMA_CONTEXT, USER_CONTEXT, {})

    assert result.generated_sql == "SELECT id FROM directory_users"
    assert result.provider_name == "static"
    assert result.model_name == "static-model"
    assert result.clarification_required is False


def test_sql_generator_returns_clarification_for_unsupported_question() -> None:
    generator = SQLGenerator(MockLLMProvider())

    result = generator.generate_sql(
        "Please exfiltrate everything.",
        SCHEMA_CONTEXT,
        USER_CONTEXT,
        {},
    )

    assert result.generated_sql is None
    assert result.clarification_required is True
    assert result.unsupported_reason == "unsupported_question"
    assert result.safe_error == "I could not map that question to a supported query."


def test_sql_generator_handles_empty_provider_output_safely() -> None:
    generator = SQLGenerator(_StaticProvider("   "))

    result = generator.generate_sql("question", SCHEMA_CONTEXT, USER_CONTEXT, {})

    assert result.generated_sql is None
    assert result.provider_name == "static"
    assert result.model_name == "static-model"
    assert result.clarification_required is True
    assert result.unsupported_reason == "empty_provider_output"
    assert result.safe_error == "The query provider did not return SQL."


def test_sql_generator_sanitizes_provider_errors() -> None:
    generator = SQLGenerator(_FailingProvider())

    result = generator.generate_sql("question", SCHEMA_CONTEXT, USER_CONTEXT, {})

    assert result.generated_sql is None
    assert result.provider_name == "failing"
    assert result.model_name == "failing-model"
    assert result.clarification_required is True
    assert result.unsupported_reason == "provider_error"
    assert result.safe_error == "SQL generation is unavailable."
    assert "secret" not in str(result.generation_metadata).lower()
    assert "password" not in str(result.generation_metadata).lower()


class _StaticProvider:
    provider_name = "static"
    model_name = "static-model"

    def __init__(self, generated_sql: str) -> None:
        self.generated_sql = generated_sql

    def generate_sql(
        self,
        question: str,
        schema_context: dict[str, Any],
        user_context: dict[str, Any],
        options: dict[str, Any],
    ) -> SQLGenerationResult:
        return SQLGenerationResult(
            generated_sql=self.generated_sql,
            provider_name=self.provider_name,
            model_name=self.model_name,
            generation_metadata={"question": question},
            clarification_required=False,
        )


class _FailingProvider:
    provider_name = "failing"
    model_name = "failing-model"

    def generate_sql(
        self,
        question: str,
        schema_context: dict[str, Any],
        user_context: dict[str, Any],
        options: dict[str, Any],
    ) -> SQLGenerationResult:
        raise RuntimeError("secret password leaked from provider")
