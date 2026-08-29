from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.query_engine.domain_pack import DomainPack, QueryTemplate
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import SQLGenerationOutcome, SQLGenerationResult
from app.query_engine.semantic_catalog import SemanticCatalogProjection
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticOrderIntent,
    SemanticPlan,
    SemanticRelationshipIntent,
)
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

        rendered_sql = (
            _mock_free_text_sql(template)
            if options.get("template_id") is None
            else render_template_sql(template)
        )
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
            semantic_plan=_mock_semantic_plan(
                template,
                options.get("semantic_catalog"),
                self._domain_pack,
            ),
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


def _mock_semantic_plan(
    template: QueryTemplate,
    raw_projection: Any,
    domain_pack: DomainPack,
) -> SemanticPlan:
    del raw_projection, domain_pack
    specification = _MOCK_PLAN_SPECIFICATIONS[template.id]
    return SemanticPlan(
        entity_ids=specification["entity_ids"],
        concept_ids=specification["concept_ids"],
        composition_rule_ids=specification.get("composition_rule_ids", ()),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=specification["relationships"],
        output_fields=specification["output_fields"],
        aggregations=specification["aggregations"],
        group_by=specification["group_by"],
        having=(),
        order_by=specification["order_by"],
        limit=None,
    )


def _field(entity_id: str, column: str) -> SemanticFieldRef:
    return SemanticFieldRef(entity_id=entity_id, column=column)


def _order(entity_id: str, column: str) -> SemanticOrderIntent:
    return SemanticOrderIntent(
        target_kind="field",
        field=_field(entity_id, column),
        aggregation_id=None,
        direction="asc",
    )


def _count() -> tuple[SemanticAggregationIntent, ...]:
    return (
        SemanticAggregationIntent(
            id="row_count",
            function="count",
            field=None,
            distinct=False,
        ),
    )


_MOCK_PLAN_SPECIFICATIONS: dict[str, dict[str, Any]] = {
    "high_severity_security_events_by_department": {
        "entity_ids": ("security_events",),
        "concept_ids": ("high_severity_open_security_event",),
        "relationships": (),
        "output_fields": (
            _field("security_events", "severity"),
            _field("security_events", "status"),
        ),
        "aggregations": _count(),
        "group_by": (
            _field("security_events", "severity"),
            _field("security_events", "status"),
        ),
        "order_by": (
            _order("security_events", "severity"),
            _order("security_events", "status"),
        ),
    },
    "inactive_users_by_department": {
        "entity_ids": ("directory_users",),
        "concept_ids": ("inactive_directory_user",),
        "relationships": (),
        "output_fields": tuple(
            _field("directory_users", column)
            for column in (
                "id",
                "email",
                "full_name",
                "account_status",
                "employee_status",
                "last_login_at",
            )
        ),
        "aggregations": (),
        "group_by": (),
        "order_by": (
            _order("directory_users", "last_login_at"),
            _order("directory_users", "email"),
        ),
    },
    "non_compliant_devices_by_department": {
        "entity_ids": ("devices",),
        "concept_ids": (),
        "composition_rule_ids": ("non_compliant_device_posture",),
        "relationships": (),
        "output_fields": tuple(
            _field("devices", column)
            for column in (
                "id",
                "hostname",
                "os",
                "os_version",
                "compliance_status",
                "antivirus_status",
                "encryption_enabled",
                "last_seen_at",
            )
        ),
        "aggregations": (),
        "group_by": (),
        "order_by": (_order("devices", "hostname"),),
    },
    "open_support_tickets_by_department": {
        "entity_ids": ("support_tickets",),
        "concept_ids": ("open_support_ticket",),
        "relationships": (),
        "output_fields": (_field("support_tickets", "priority"),),
        "aggregations": _count(),
        "group_by": (_field("support_tickets", "priority"),),
        "order_by": (_order("support_tickets", "priority"),),
    },
    "privileged_group_memberships_by_department": {
        "entity_ids": ("groups", "user_group_memberships"),
        "concept_ids": ("privileged_group",),
        "relationships": (
            SemanticRelationshipIntent(
                relationship_id="user_group_membership_group",
                join_type="inner",
            ),
        ),
        "output_fields": (
            _field("groups", "name"),
            _field("groups", "risk_level"),
        ),
        "aggregations": _count(),
        "group_by": (
            _field("groups", "name"),
            _field("groups", "risk_level"),
        ),
        "order_by": (
            _order("groups", "risk_level"),
            _order("groups", "name"),
        ),
    },
    "unused_licenses_by_department": {
        "entity_ids": ("license_assignments", "licenses"),
        "concept_ids": ("unused_license_assignment",),
        "relationships": (
            SemanticRelationshipIntent(
                relationship_id="license_assignment_license",
                join_type="inner",
            ),
        ),
        "output_fields": (
            _field("license_assignments", "id"),
            _field("license_assignments", "user_id"),
            _field("licenses", "product_name"),
            _field("licenses", "vendor"),
            _field("licenses", "monthly_cost_usd"),
            _field("license_assignments", "last_used_at"),
        ),
        "aggregations": (),
        "group_by": (),
        "order_by": (
            _order("licenses", "product_name"),
            _order("license_assignments", "last_used_at"),
        ),
    },
}


def _mock_free_text_sql(template: QueryTemplate) -> str | None:
    if template.id == "open_support_tickets_by_department":
        # Free text asks for priority grain only. Explicit template execution
        # retains the tracked priority-and-status template contract.
        return (
            "SELECT priority, COUNT(*) AS ticket_count FROM support_tickets "
            "WHERE status IN ('open', 'in_progress') "
            "GROUP BY priority ORDER BY priority"
        )
    return render_template_sql(template)
