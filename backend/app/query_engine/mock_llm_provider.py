from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.query_engine.domain_pack import DomainPack, QueryTemplate
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import SQLGenerationResult


class MockLLMProvider:
    provider_name = "mock"
    model_name = "mock-queryops-v1"

    def __init__(self, domain_pack: DomainPack | None = None) -> None:
        self._domain_pack = domain_pack or load_it_operations_domain_pack()
        self._templates_by_question = {
            _normalize_question(template.natural_language_question): template
            for template in self._domain_pack.query_templates
        }

    def generate_sql(
        self,
        question: str,
        schema_context: Mapping[str, Any],
        user_context: Mapping[str, Any],
        options: Mapping[str, Any],
    ) -> SQLGenerationResult:
        template = self._template_for_request(question, options)
        if template is None or template.sql is None:
            return self._unsupported_result(question, schema_context, user_context)

        return SQLGenerationResult(
            generated_sql=template.sql,
            provider_name=self.provider_name,
            model_name=self.model_name,
            generation_metadata={
                "template_id": template.id,
                "source": "domain_pack_template",
                "domain": self._domain_pack.domain_id,
                "referenced_tables": list(template.referenced_tables),
                "question_fingerprint": _normalize_question(question),
                "schema_context_tables": sorted(
                    str(table)
                    for table in schema_context.get("allowed_tables", [])
                ),
                "user_scope_type": user_context.get("scope_type"),
            },
            clarification_required=False,
        )

    def _template_for_request(
        self,
        question: str,
        options: Mapping[str, Any],
    ) -> QueryTemplate | None:
        template_id = options.get("template_id")
        if isinstance(template_id, str) and template_id:
            return self._domain_pack.templates_by_id.get(template_id)

        return self._templates_by_question.get(_normalize_question(question))

    def _unsupported_result(
        self,
        question: str,
        schema_context: Mapping[str, Any],
        user_context: Mapping[str, Any],
    ) -> SQLGenerationResult:
        return SQLGenerationResult(
            generated_sql=None,
            provider_name=self.provider_name,
            model_name=self.model_name,
            generation_metadata={
                "supported_template_ids": [
                    template.id for template in self._domain_pack.query_templates
                ],
                "question_fingerprint": _normalize_question(question),
                "schema_context_domain": schema_context.get("domain"),
                "user_role": user_context.get("role"),
            },
            clarification_required=True,
            unsupported_reason="unsupported_question",
            safe_error="I could not map that question to a supported query.",
        )


def _normalize_question(question: str) -> str:
    return " ".join(question.strip().lower().rstrip(".?").split())

