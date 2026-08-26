from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.query_engine.domain_pack import DomainPack, QueryTemplate
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import SQLGenerationOutcome, SQLGenerationResult
from app.query_engine.semantic_catalog import SemanticCatalogProjection
from app.query_engine.template_sql import render_template_sql


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
        if _is_unsafe_request(question):
            semantic_projection = options.get("semantic_catalog")
            referenced_tables = (
                sorted(
                    str(entity["table"])
                    for entity in semantic_projection.entities
                    if isinstance(entity.get("table"), str)
                )
                if isinstance(semantic_projection, SemanticCatalogProjection)
                else []
            )
            return SQLGenerationResult(
                generated_sql=None,
                provider_name=self.provider_name,
                model_name=self.model_name,
                outcome=SQLGenerationOutcome.UNSAFE_REQUEST,
                generation_metadata={
                    "source": "mock_unsafe_intent",
                    "question_fingerprint": _normalize_question(question),
                    "referenced_tables": referenced_tables,
                },
                unsupported_reason="unsafe_request",
                safe_error="The request is not allowed for safe read-only querying.",
            )

        template = self._template_for_request(question, options)
        if template is None or template.sql is None:
            return self._unsupported_result(question, schema_context, user_context)

        rendered_sql = render_template_sql(template)
        if rendered_sql is None:
            return self._unsupported_result(question, schema_context, user_context)

        return SQLGenerationResult(
            generated_sql=rendered_sql,
            provider_name=self.provider_name,
            model_name=self.model_name,
            outcome=SQLGenerationOutcome.SQL,
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
                "parameters_applied": [
                    parameter.name
                    for parameter in template.parameters
                    if parameter.default is not None
                ],
            },
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
            outcome=SQLGenerationOutcome.CLARIFICATION,
            generation_metadata={
                "supported_template_ids": [
                    template.id for template in self._domain_pack.query_templates
                ],
                "question_fingerprint": _normalize_question(question),
                "schema_context_domain": schema_context.get("domain"),
                "user_role": user_context.get("role"),
            },
            unsupported_reason="unsupported_question",
            safe_error="I could not map that question to a supported query.",
        )


def _normalize_question(question: str) -> str:
    return " ".join(question.strip().lower().rstrip(".?").split())


_DIRECT_WRITE_REQUEST = re.compile(
    r"^(?:please\s+)?(?:alter|delete|disable|drop|grant|insert|revoke|"
    r"truncate|update)\b"
)
_DIRECT_CREATE_DDL_REQUEST = re.compile(
    r"^(?:please\s+)?create\s+(?:database|index|role|schema|table|user|view)\b"
)
_AUTHORIZATION_BYPASS_REQUEST = re.compile(
    r"\b(?:bypass|disable|ignore)\b.*\b(?:authorization|permission|rls)\b"
)


def _is_unsafe_request(question: str) -> bool:
    normalized = _normalize_question(question)
    return bool(
        _DIRECT_WRITE_REQUEST.search(normalized)
        or _DIRECT_CREATE_DDL_REQUEST.search(normalized)
        or _AUTHORIZATION_BYPASS_REQUEST.search(normalized)
    )
