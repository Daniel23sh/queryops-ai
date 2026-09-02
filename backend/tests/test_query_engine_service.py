from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator, Mapping
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.access_context import UserAccessContext, build_user_access_context
from app.db.base import Base
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser, QueryRun
from app.query_engine.llm_provider import PlanGenerationOutcome, PlanGenerationResult
from app.query_engine.result_formatter import format_query_result
from app.query_engine.semantic_conformance import (
    SemanticConformanceReason,
    SemanticConformanceResult,
)
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticHavingIntent,
    SemanticOrderIntent,
    SemanticPlan,
    SemanticRelationshipIntent,
)
from app.query_engine.service import (
    QueryEngineRequest,
    QueryEngineService,
    QueryEngineServiceResult,
    _safe_field_mismatch_observation,
)
from app.query_engine.sql_executor import SQLExecutionResult
from app.query_engine.sql_renderer import SemanticSQLRenderError
from app.query_engine.sql_validator import SQLValidationResult, validate_sql


def test_successful_template_query_creates_succeeded_query_run(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(
            question="How many open support tickets exist in my department by priority?",
            template_id="open_support_tickets_by_department",
        ),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert result.query_run_id == str(query_run.id)
    assert query_run.status == "succeeded"
    assert query_run.generated_sql is not None
    assert query_run.generated_sql.startswith("SELECT priority, status")
    assert query_run.executed_sql == executor.seen_sql[0]
    assert query_run.row_count == 1
    assert query_run.error_message is None
    assert query_run.query_metadata["template_id"] == "open_support_tickets_by_department"
    assert query_run.query_metadata["provider"] == "domain_pack_template"
    assert query_run.query_metadata["validation"]["valid"] is True
    assert query_run.query_metadata["execution"]["status"] == "succeeded"


def test_template_user_can_run_approved_template_without_free_query_permission(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.user@queryops.local")
    access_context = build_user_access_context(user, db_session)

    assert access_context.has_permission("can_use_query_templates")
    assert not access_context.has_permission("can_run_free_query")
    assert not access_context.has_permission("can_query_scoped_data")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(
            question="How many open support tickets exist in my department by priority?",
            template_id="open_support_tickets_by_department",
        ),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert query_run.status == "succeeded"
    assert query_run.generated_sql is not None
    assert query_run.executed_sql == executor.seen_sql[0]
    assert query_run.query_metadata["template_id"] == "open_support_tickets_by_department"
    assert query_run.query_metadata["validation"]["valid"] is True
    assert query_run.query_metadata["execution"]["status"] == "succeeded"


def test_successful_known_mock_free_text_query_creates_succeeded_query_run(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show non-compliant devices in my department."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert query_run.status == "succeeded"
    assert query_run.generated_sql is not None
    assert "FROM devices" in query_run.generated_sql
    assert query_run.executed_sql == executor.seen_sql[0]
    assert query_run.query_metadata["provider"] == "mock"
    assert query_run.query_metadata["model"] == "mock-queryops-v1"


def test_mock_grouped_count_free_text_matches_grounded_result_intent(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(
            question=(
                "How many open support tickets exist in my department by priority?"
            )
        ),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert query_run.status == "succeeded"
    assert query_run.generated_sql is not None
    assert query_run.generated_sql.startswith(
        "SELECT support_tickets.priority, COUNT(*) AS row_count"
    )
    assert query_run.query_metadata["semantic_plan_validation"] == {
        "status": "passed",
        "reason_code": None,
        "required_intent_status": "passed",
    }
    assert query_run.query_metadata["template_id"] == (
        "open_support_tickets_by_department"
    )


def test_mock_free_text_template_query_applies_default_parameters(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show inactive users in my department."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert query_run.status == "succeeded"
    assert query_run.query_metadata["template_id"] == "inactive_users_by_department"
    assert query_run.generated_sql is not None
    assert ":inactive_days" not in query_run.generated_sql
    assert "CURRENT_TIMESTAMP - INTERVAL '90 days'" in query_run.generated_sql
    assert query_run.executed_sql == executor.seen_sql[0]
    assert ":inactive_days" not in query_run.executed_sql


def test_unsupported_question_creates_clarification_query_run_without_execution(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Can you forecast next year's laptop budget?"),
    )

    query_run = only_query_run(db_session)
    assert result.status == "clarification_required"
    assert result.clarification_required is True
    assert query_run.status == "failed"
    assert query_run.generated_sql is None
    assert query_run.executed_sql is None
    assert query_run.error_message == "I could not map that question to a supported query."
    assert query_run.query_metadata["clarification_required"] is True
    assert query_run.query_metadata["unsupported_reason"] == "unsupported_question"
    assert executor.seen_sql == []


def test_validation_failure_creates_failed_query_run_with_sanitized_error(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(
        executor=executor,
        validator=lambda _sql, _schema_context: SQLValidationResult(
            valid=False,
            sanitized_sql=None,
            referenced_tables=[],
            error_code="table_not_allowed",
            reason="internal parser detail for sensitive_table",
            public_error="SQL is not allowed for safe read-only querying.",
        ),
    )
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(
            question="Show non-compliant devices in my department.",
        ),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "validation_failed"
    assert query_run.status == "failed"
    assert query_run.error_message == "SQL is not allowed for safe read-only querying."
    assert "sensitive_table" not in query_run.error_message
    assert query_run.executed_sql is None
    assert query_run.query_metadata["validation"]["error_code"] == "table_not_allowed"
    assert executor.seen_sql == []


def test_execution_failure_creates_failed_query_run_with_sanitized_error(
    db_session: Session,
) -> None:
    executor = FakeExecutor(
        result=SQLExecutionResult(
            status="failed",
            columns=[],
            rows=[],
            row_count=0,
            duration_ms=4.2,
            truncated=False,
            execution_metadata={"internal_error_type": "UndefinedColumn"},
            referenced_tables=["devices"],
            error_code="database_error",
            public_error="Query execution failed safely.",
        )
    )
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show non-compliant devices in my department."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "database_error"
    assert query_run.status == "failed"
    assert query_run.executed_sql == executor.seen_sql[0]
    assert query_run.error_message == "Query execution failed safely."
    assert "UndefinedColumn" not in query_run.error_message
    assert "missing_column" not in query_run.error_message


def test_generated_and_executed_sql_follow_security_storage_expectations(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(
        executor=executor,
        validator=lambda sql, _schema_context: SQLValidationResult(
            valid=True,
            sanitized_sql=f"{sql} LIMIT 25",
            referenced_tables=["devices"],
        ),
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show non-compliant devices in my department."),
    )

    query_run = only_query_run(db_session)
    assert query_run.generated_sql is not None
    assert "ORDER BY devices.hostname ASC" in query_run.generated_sql
    assert query_run.executed_sql == f"{query_run.generated_sql} LIMIT 25"
    assert executor.seen_sql == [query_run.executed_sql]


def test_valid_plan_is_rendered_once_without_self_correction(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    validator = RecordingValidator()
    service = QueryEngineService(
        provider=StaticSQLProvider(
            "SELECT id, hostname FROM devices "
            "WHERE compliance_status = 'non_compliant' "
            "OR antivirus_status IN ('outdated', 'missing') "
            "OR encryption_enabled = false "
            "ORDER BY hostname LIMIT 25"
        ),
        executor=executor,
        validator=validator,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show non-compliant devices in my department."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert len(validator.seen_sql) == 1
    assert validator.seen_sql[0] == query_run.generated_sql
    assert validator.seen_sql[0].startswith("SELECT devices.hostname, devices.id")
    assert "self_correction" not in query_run.query_metadata
    assert executor.seen_sql == [validator.seen_sql[0]]
    assert query_run.query_metadata["semantic_sql_render"] == {
        "status": "passed",
        "reason_code": None,
    }
    plan_observation = query_run.query_metadata["semantic_plan"]
    assert plan_observation["output_fields"]
    assert "aggregations" in plan_observation
    assert "group_by" in plan_observation
    assert "having" in plan_observation
    assert "order_by" in plan_observation
    assert "literal_filters" not in plan_observation


def test_single_entity_count_star_continues_through_query_service(
    db_session: Session,
) -> None:
    plan = SemanticPlan(
        entity_ids=("devices",),
        concept_ids=(),
        composition_rule_ids=(),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(),
        output_fields=(),
        aggregations=(
            SemanticAggregationIntent(
                id="row_count",
                function="count",
                field=None,
                distinct=False,
            ),
        ),
        group_by=(),
        having=(),
        order_by=(),
        limit=None,
    )
    executor = FakeExecutor()
    validator = RecordingValidator()
    service = QueryEngineService(
        provider=StaticPlanProvider(plan),
        executor=executor,
        validator=validator,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="How many devices are there?"),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert query_run.generated_sql == "SELECT COUNT(*) AS row_count FROM devices"
    assert validator.seen_sql == [query_run.generated_sql]
    assert query_run.executed_sql == (
        "SELECT COUNT(*) AS row_count FROM devices LIMIT 100"
    )
    assert executor.seen_sql == [query_run.executed_sql]
    assert query_run.query_metadata["semantic_plan_validation"] == {
        "status": "passed",
        "reason_code": None,
        "required_intent_status": "passed",
    }
    assert query_run.query_metadata["semantic_sql_render"] == {
        "status": "passed",
        "reason_code": None,
    }


def test_free_query_renderer_output_that_fails_safety_is_not_corrected(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    validator = RecordingValidator()
    service = QueryEngineService(
        provider=StaticSQLProvider("SELECT id FROM devices"),
        executor=executor,
        validator=validator,
        semantic_sql_renderer=lambda _plan, _pack: "SELECT * FROM devices",
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show non-compliant devices in my department."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "validation_failed"
    assert validator.seen_sql == ["SELECT * FROM devices"]
    assert query_run.generated_sql == "SELECT * FROM devices"
    assert query_run.executed_sql is None
    assert "self_correction" not in query_run.query_metadata
    assert executor.seen_sql == []


def test_renderer_failure_skips_sql_validation_and_execution(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    validator = RecordingValidator()

    def fail_render(_plan: Any, _pack: Any) -> str:
        raise SemanticSQLRenderError("left_join_orientation_unsupported")

    service = QueryEngineService(
        provider=StaticSQLProvider("SELECT id FROM devices"),
        executor=executor,
        validator=validator,
        semantic_sql_renderer=fail_render,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show non-compliant devices in my department."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "semantic_sql_render_failed"
    assert query_run.generated_sql is None
    assert query_run.executed_sql is None
    assert executor.seen_sql == []
    assert validator.seen_sql == []
    assert query_run.query_metadata["semantic_sql_render"] == {
        "status": "failed",
        "reason_code": "left_join_orientation_unsupported",
    }


def _privileged_grouped_count_plan(
    *,
    output_fields: tuple[SemanticFieldRef, ...],
    group_by: tuple[SemanticFieldRef, ...] | None = None,
) -> SemanticPlan:
    department_name = SemanticFieldRef(entity_id="departments", column="name")
    return SemanticPlan(
        entity_ids=(
            "departments",
            "directory_users",
            "groups",
            "user_group_memberships",
        ),
        concept_ids=("privileged_group",),
        composition_rule_ids=(),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(
            SemanticRelationshipIntent(
                relationship_id="directory_user_department",
                join_type="inner",
            ),
            SemanticRelationshipIntent(
                relationship_id="user_group_membership_group",
                join_type="inner",
            ),
            SemanticRelationshipIntent(
                relationship_id="user_group_membership_user",
                join_type="inner",
            ),
        ),
        output_fields=output_fields,
        aggregations=(
            SemanticAggregationIntent(
                id="provider_alias_not_persisted",
                function="count",
                field=SemanticFieldRef(
                    entity_id="directory_users",
                    column="id",
                ),
                distinct=True,
            ),
        ),
        group_by=(department_name,) if group_by is None else group_by,
        having=(),
        order_by=(),
        limit=None,
    )


def test_provider_sql_like_attribute_cannot_influence_free_query_execution(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    validator = RecordingValidator()
    provider = StaticSQLProvider("SELECT id FROM devices; DROP TABLE devices")
    service = QueryEngineService(
        provider=provider,
        executor=executor,
        validator=validator,
    )
    user = user_by_email(db_session, "demo.admin@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show devices."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert query_run.generated_sql == validator.seen_sql[0]
    assert "DROP" not in query_run.generated_sql
    assert ";" not in query_run.generated_sql
    assert "self_correction" not in query_run.query_metadata
    assert executor.seen_sql == [query_run.executed_sql]


def test_request_metadata_persists_safe_clarification_link_only(
    db_session: Session,
) -> None:
    clarified_from_id = str(uuid.uuid4())
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    service.run(
        db_session,
        user,
        QueryEngineRequest(
            question="Show non-compliant devices in my department.",
            metadata={
                "clarified_from_query_run_id": clarified_from_id,
                "unsafe_internal_detail": "do not persist",
            },
        ),
    )

    query_run = only_query_run(db_session)
    assert query_run.query_metadata["clarified_from_query_run_id"] == clarified_from_id
    assert "unsafe_internal_detail" not in query_run.query_metadata


def test_provider_clarification_never_renders_or_executes(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(
        provider=UnsupportedSqlProvider(),
        executor=executor,
        semantic_sql_renderer=_unexpected_renderer,
    )
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Try something unsafe."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "clarification_required"
    assert result.clarification_required is True
    assert result.error_code == "unsupported_question"
    assert query_run.generated_sql is None
    assert query_run.executed_sql is None
    assert executor.seen_sql == []


def test_unsafe_request_is_persisted_safely_without_validation_or_execution(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    validator = RecordingValidator()
    service = QueryEngineService(
        provider=UnsafeRequestProvider(),
        executor=executor,
        validator=validator,
        semantic_sql_renderer=_unexpected_renderer,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Delete every directory user."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "unsafe_sql_blocked"
    assert result.clarification_required is False
    assert query_run.status == "failed"
    assert query_run.generated_sql is None
    assert query_run.executed_sql is None
    assert query_run.row_count == 0
    assert query_run.query_metadata["safety_blocked"] is True
    assert query_run.query_metadata["safety_reason"] == "unsafe_request"
    assert query_run.query_metadata["clarification_required"] is False
    assert query_run.query_metadata["referenced_tables"] == ["directory_users"]
    assert "raw-provider-payload" not in str(query_run.query_metadata)
    assert validator.seen_sql == []
    assert executor.seen_sql == []


def test_mandatory_metric_cannot_be_downgraded_before_sql_validation(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    validator = RecordingValidator()
    conformance = RecordingConformanceChecker()
    provider = WeakActiveUsersProvider()
    service = QueryEngineService(
        provider=provider,
        executor=executor,
        validator=validator,
        conformance_checker=conformance,
        semantic_sql_renderer=_unexpected_renderer,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="How many active users are there?"),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "provider_response_invalid"
    assert result.clarification_required is False
    assert query_run.query_metadata["semantic_plan_validation"] == {
        "status": "failed",
        "reason_code": "mandatory_metric_missing",
        "required_intent_status": "failed",
    }
    assert "aggregation_mismatch" not in query_run.query_metadata[
        "semantic_plan_validation"
    ]
    assert validator.seen_sql == []
    assert conformance.calls == []
    assert executor.seen_sql == []
    assert provider.calls == 1


def test_grounded_aggregation_mismatch_persists_only_safe_identities(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    validator = RecordingValidator()
    provider = WrongGroundedAggregationProvider()
    service = QueryEngineService(
        provider=provider,
        executor=executor,
        validator=validator,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="How many privileged users by department?"),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "provider_response_invalid"
    assert query_run.query_metadata["semantic_plan_validation"] == {
        "status": "failed",
        "reason_code": "grounded_aggregation_mismatch",
        "required_intent_status": "failed",
        "aggregation_mismatch": {
            "expected": [
                {
                    "function": "count",
                    "target": "directory_users.id",
                    "distinct": True,
                }
            ],
            "actual": [
                {
                    "function": "count",
                    "target": "groups.id",
                    "distinct": True,
                }
            ],
        },
    }
    observation = str(
        query_run.query_metadata["semantic_plan_validation"][
            "aggregation_mismatch"
        ]
    ).lower()
    assert "provider_aggregation_alias" not in observation
    assert "select " not in observation
    assert "prompt" not in observation
    assert "literal" not in observation
    assert "rows" not in observation
    assert validator.seen_sql == []
    assert executor.seen_sql == []


@pytest.mark.parametrize(
    ("plan", "expected_validation"),
    [
        (
            _privileged_grouped_count_plan(output_fields=()),
                {
                    "status": "failed",
                    "reason_code": "required_output_missing",
                    "required_intent_status": "failed",
                "required_output_mismatch": {
                    "expected": ["departments.name"],
                    "actual": [],
                },
            },
        ),
        (
            _privileged_grouped_count_plan(
                output_fields=(
                    SemanticFieldRef(entity_id="departments", column="name"),
                    SemanticFieldRef(entity_id="groups", column="name"),
                ),
                group_by=(
                    SemanticFieldRef(entity_id="departments", column="name"),
                    SemanticFieldRef(entity_id="groups", column="name"),
                ),
            ),
                {
                    "status": "failed",
                    "reason_code": "grounded_group_by_mismatch",
                    "required_intent_status": "failed",
                "group_by_mismatch": {
                    "expected": ["departments.name"],
                    "actual": ["departments.name", "groups.name"],
                },
            },
        ),
    ],
)
def test_result_intent_field_mismatch_persists_only_relevant_canonical_fields(
    db_session: Session,
    plan: SemanticPlan,
    expected_validation: dict[str, Any],
) -> None:
    executor = FakeExecutor()
    validator = RecordingValidator()
    service = QueryEngineService(
        provider=StaticPlanProvider(plan),
        executor=executor,
        validator=validator,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="How many privileged users by department?"),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "provider_response_invalid"
    assert query_run.query_metadata["semantic_plan_validation"] == expected_validation
    serialized = json.dumps(query_run.query_metadata, sort_keys=True)
    for forbidden in ("SELECT provider", "prompt", "rows", '"value"'):
        assert forbidden not in serialized
    assert validator.seen_sql == []
    assert executor.seen_sql == []


def test_result_intent_field_observation_bound_is_fail_closed() -> None:
    oversized = [f"table_{index}.column" for index in range(65)]

    assert (
        _safe_field_mismatch_observation(
            {"expected": oversized, "actual": []}
        )
        is None
    )


def test_grounded_having_mismatch_persists_only_structural_shape(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    validator = RecordingValidator()
    provider = WrongGroundedHavingProvider()
    service = QueryEngineService(
        provider=provider,
        executor=executor,
        validator=validator,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(
            question=(
                "Show users with more than five failed logins in the last 30 days."
            )
        ),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "provider_response_invalid"
    plan_validation = query_run.query_metadata["semantic_plan_validation"]
    assert plan_validation == {
        "status": "failed",
        "reason_code": "grounded_having_mismatch",
        "required_intent_status": "failed",
        "having_mismatch": {
            "expected": [
                {
                    "aggregation": {
                        "function": "count",
                        "target": "login_events.id",
                        "distinct": False,
                    },
                    "operator": "greater_than",
                }
            ],
            "actual": [
                {
                    "aggregation": {
                        "function": "count",
                        "target": "login_events.id",
                        "distinct": False,
                    },
                    "operator": "greater_than",
                }
            ],
        },
    }
    serialized = json.dumps(plan_validation, sort_keys=True)
    for forbidden in (
        "provider_having_alias",
        '"value"',
        "SELECT ",
        "prompt",
        "rows",
    ):
        assert forbidden not in serialized
    assert validator.seen_sql == []
    assert executor.seen_sql == []


def test_sql_safety_failure_never_invokes_conformance(
    db_session: Session,
) -> None:
    conformance = RecordingConformanceChecker()
    executor = FakeExecutor()
    service = QueryEngineService(
        provider=StaticSQLProvider("SELECT id FROM devices"),
        executor=executor,
        conformance_checker=conformance,
        semantic_sql_renderer=lambda _plan, _pack: (
            "UPDATE devices SET hostname = 'bad'"
        ),
    )
    user = user_by_email(db_session, "demo.admin@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show devices, then try unsafe SQL."),
    )

    assert result.error_code == "validation_failed"
    assert conformance.calls == []
    assert executor.seen_sql == []


def test_conformance_failure_never_executes_and_persists_controlled_reason(
    db_session: Session,
) -> None:
    conformance = RecordingConformanceChecker(
        result=SemanticConformanceResult(
            valid=False,
            reason_code=SemanticConformanceReason.PREDICATE_MISSING,
            checked_entity_count=1,
            checked_predicate_count=1,
            checked_relationship_count=0,
            checked_aggregation_count=0,
        )
    )
    executor = FakeExecutor()
    service = QueryEngineService(
        provider=StaticSQLProvider("SELECT id FROM devices"),
        executor=executor,
        conformance_checker=conformance,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show devices."),
    )

    query_run = only_query_run(db_session)
    assert result.error_code == "semantic_conformance_failed"
    assert query_run.executed_sql is None
    assert query_run.query_metadata["semantic_conformance"] == {
        "status": "failed",
        "reason_code": "semantic_predicate_missing",
        "checked_entity_count": 1,
        "checked_predicate_count": 1,
        "checked_relationship_count": 0,
        "checked_aggregation_count": 0,
    }
    assert query_run.query_metadata["repair_attempted"] is False
    assert executor.seen_sql == []


def test_conformance_receives_candidate_and_exact_executed_sanitized_sql(
    db_session: Session,
) -> None:
    conformance = RecordingConformanceChecker()
    executor = FakeExecutor()
    candidate = "SELECT id, hostname FROM devices ORDER BY hostname"
    service = QueryEngineService(
        provider=StaticSQLProvider(candidate),
        executor=executor,
        conformance_checker=conformance,
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show devices."),
    )

    assert result.status == "succeeded"
    assert len(conformance.calls) == 1
    call = conformance.calls[0]
    query_run = only_query_run(db_session)
    assert call["candidate_sql"] == query_run.generated_sql
    assert call["candidate_sql"] == (
        "SELECT devices.hostname, devices.id FROM devices "
        "ORDER BY devices.hostname ASC"
    )
    safety_result = call["safety_result"]
    assert isinstance(safety_result, SQLValidationResult)
    assert safety_result.sanitized_sql == f"{call['candidate_sql']} LIMIT 100"
    assert executor.seen_sql == [safety_result.sanitized_sql]


def test_selected_provider_receives_authorized_context_and_persists_only_safe_usage(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    provider = RecordingMeasuredProvider()
    service = QueryEngineService(provider=provider, executor=executor)
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show device operating systems."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert provider.calls == 1
    assert provider.user_context == {
        "scope_type": "department",
        "has_global_scope": False,
        "scope_reference_resolved": True,
    }
    assert provider.semantic_catalog.catalog_id == "it_operations_semantic_catalog"
    assert "it_audit_events" not in provider.schema_context["allowed_tables"]
    assert query_run.query_metadata["provider"] == "openai"
    assert query_run.query_metadata["model"] == "gpt-5.6-terra"
    assert query_run.query_metadata["provider_measurement"] == {
        "provider": "openai",
        "model_label": "gpt-5.6-terra",
        "duration_ms": 7.5,
        "attempt_count": 1,
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "output_tokens": 15,
        "total_tokens": 115,
    }
    assert query_run.query_metadata["semantic_catalog"] == (
        provider.semantic_catalog.as_observation()
    )
    persisted = str(query_run.query_metadata)
    assert "raw-provider-payload" not in persisted
    assert str(user.id) not in persisted
    assert user.email not in persisted


def test_template_request_bypasses_selected_real_provider(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    provider = RecordingMeasuredProvider()
    service = QueryEngineService(
        provider=provider,
        executor=executor,
        semantic_sql_renderer=_unexpected_renderer,
    )
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(
            question="How many open support tickets exist in my department by priority?",
            template_id="open_support_tickets_by_department",
        ),
    )

    assert result.status == "succeeded"
    assert provider.calls == 0
    assert only_query_run(db_session).query_metadata["provider"] == (
        "domain_pack_template"
    )


def test_result_formatter_is_deterministic() -> None:
    execution_result = SQLExecutionResult(
        status="succeeded",
        columns=["name"],
        rows=[{"name": "Finance"}],
        row_count=1,
        duration_ms=3.6,
        truncated=False,
        execution_metadata={"runtime_role": "queryops_query_runtime"},
        referenced_tables=["departments"],
    )

    first = format_query_result(
        status="succeeded",
        query_run_id="run-1",
        execution_result=execution_result,
        warnings=["beta", "alpha"],
    )
    second = format_query_result(
        status="succeeded",
        query_run_id="run-1",
        execution_result=execution_result,
        warnings=["beta", "alpha"],
    )

    assert isinstance(first, QueryEngineServiceResult)
    assert first == second
    assert first.message == "Query completed successfully."
    assert first.warnings == ["alpha", "beta"]


def _unexpected_renderer(_plan: Any, _domain_pack: Any) -> str:
    raise AssertionError("Semantic SQL renderer must not be called")


class FakeExecutor:
    def __init__(self, result: SQLExecutionResult | None = None) -> None:
        self.result = result or SQLExecutionResult(
            status="succeeded",
            columns=["status", "ticket_count"],
            rows=[{"status": "open", "ticket_count": 2}],
            row_count=1,
            duration_ms=2.4,
            truncated=False,
            execution_metadata={"runtime_role": "queryops_query_runtime"},
            referenced_tables=["support_tickets"],
        )
        self.seen_sql: list[str] = []

    def __call__(
        self,
        _db: Session,
        _access_context: UserAccessContext,
        validation_result: SQLValidationResult,
        *,
        options: Any = None,
    ) -> SQLExecutionResult:
        assert options is not None
        self.seen_sql.append(validation_result.sanitized_sql or "")
        return self.result


class UnsupportedSqlProvider:
    provider_name = "unsupported-test-provider"
    model_name = "unsupported-test-model"

    def generate_plan(
        self,
        question: str,
        _schema_context: Mapping[str, Any],
        _user_context: Mapping[str, Any],
        _options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            outcome=PlanGenerationOutcome.CLARIFICATION,
            generation_metadata={"source": "test"},
            unsupported_reason="unsupported_question",
            safe_error="I could not map that question to a supported query.",
        )


class StaticSQLProvider:
    provider_name = "static-service-test-provider"
    model_name = "static-service-test-model"

    def __init__(self, generated_sql: str) -> None:
        self.generated_sql = generated_sql

    def generate_plan(
        self,
        question: str,
        schema_context: Mapping[str, Any],
        _user_context: Mapping[str, Any],
        _options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            generation_metadata={"source": "self_correction_test"},
            semantic_plan=_device_plan(dict(schema_context), self.generated_sql, question),
        )


class UnsafeRequestProvider:
    provider_name = "openai"
    model_name = "gpt-5.6-luna"

    def generate_plan(
        self,
        _question: str,
        _schema_context: Mapping[str, Any],
        _user_context: Mapping[str, Any],
        options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        semantic_catalog = options["semantic_catalog"]
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            outcome=PlanGenerationOutcome.UNSAFE_REQUEST,
            generation_metadata={
                "referenced_tables": ["directory_users"],
                "semantic_catalog": semantic_catalog.as_observation(),
                "raw_payload": "raw-provider-payload",
            },
            unsupported_reason="unsafe_request",
            safe_error="The request is not allowed for safe read-only querying.",
        )


class RecordingMeasuredProvider:
    provider_name = "openai"
    model_name = "gpt-5.6-terra"

    def __init__(self) -> None:
        self.calls = 0
        self.schema_context: dict[str, Any] = {}
        self.user_context: dict[str, Any] = {}
        self.semantic_catalog: Any = None

    def generate_plan(
        self,
        _question: str,
        schema_context: Mapping[str, Any],
        user_context: Mapping[str, Any],
        options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        self.calls += 1
        self.schema_context = dict(schema_context)
        self.user_context = dict(user_context)
        self.semantic_catalog = options.get("semantic_catalog")
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            generation_metadata={
                "provider_measurement": {
                    "provider": "openai",
                    "model_label": "gpt-5.6-terra",
                    "duration_ms": 7.5,
                    "attempt_count": 1,
                    "input_tokens": 100,
                    "cached_input_tokens": 20,
                    "output_tokens": 15,
                    "total_tokens": 115,
                    "response_id": "raw-provider-payload",
                },
                "semantic_catalog": self.semantic_catalog.as_observation(),
                "raw_payload": "raw-provider-payload",
            },
            semantic_plan=_device_plan(
                schema_context,
                "SELECT id, os FROM devices ORDER BY os, id LIMIT 25",
            ),
        )


class WeakActiveUsersProvider:
    provider_name = "weak-test-provider"
    model_name = "weak-test-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_plan(
        self,
        _question: str,
        _schema_context: Mapping[str, Any],
        _user_context: Mapping[str, Any],
        _options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        self.calls += 1
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            semantic_plan=SemanticPlan(
                entity_ids=("directory_users",),
                concept_ids=("active_directory_account",),
                composition_rule_ids=(),
                metric_id=None,
                distinct=False,
                literal_filters=(),
                relationships=(),
                output_fields=(),
                aggregations=(
                    SemanticAggregationIntent(
                        id="row_count",
                        function="count",
                        field=None,
                        distinct=False,
                    ),
                ),
                group_by=(),
                having=(),
                order_by=(),
                limit=None,
            ),
        )


class WrongGroundedAggregationProvider:
    provider_name = "grounded-mismatch-test-provider"
    model_name = "grounded-mismatch-test-model"

    def generate_plan(
        self,
        _question: str,
        _schema_context: Mapping[str, Any],
        _user_context: Mapping[str, Any],
        _options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            semantic_plan=SemanticPlan(
                entity_ids=(
                    "departments",
                    "directory_users",
                    "groups",
                    "user_group_memberships",
                ),
                concept_ids=("privileged_group",),
                composition_rule_ids=(),
                metric_id=None,
                distinct=False,
                literal_filters=(),
                relationships=(
                    SemanticRelationshipIntent(
                        relationship_id="directory_user_department",
                        join_type="inner",
                    ),
                    SemanticRelationshipIntent(
                        relationship_id="user_group_membership_group",
                        join_type="inner",
                    ),
                    SemanticRelationshipIntent(
                        relationship_id="user_group_membership_user",
                        join_type="inner",
                    ),
                ),
                output_fields=(
                    SemanticFieldRef(entity_id="departments", column="name"),
                ),
                aggregations=(
                    SemanticAggregationIntent(
                        id="provider_aggregation_alias",
                        function="count",
                        field=SemanticFieldRef(entity_id="groups", column="id"),
                        distinct=True,
                    ),
                ),
                group_by=(
                    SemanticFieldRef(entity_id="departments", column="name"),
                ),
                having=(),
                order_by=(),
                limit=None,
            ),
        )


class WrongGroundedHavingProvider:
    provider_name = "grounded-having-mismatch-test-provider"
    model_name = "grounded-having-mismatch-test-model"

    def generate_plan(
        self,
        _question: str,
        _schema_context: Mapping[str, Any],
        _user_context: Mapping[str, Any],
        _options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            semantic_plan=SemanticPlan(
                entity_ids=("login_events",),
                concept_ids=("failed_login_within_30_days",),
                composition_rule_ids=(),
                metric_id=None,
                distinct=False,
                literal_filters=(),
                relationships=(),
                output_fields=(
                    SemanticFieldRef(entity_id="login_events", column="user_id"),
                ),
                aggregations=(
                    SemanticAggregationIntent(
                        id="provider_having_alias",
                        function="count",
                        field=SemanticFieldRef(
                            entity_id="login_events",
                            column="id",
                        ),
                        distinct=False,
                    ),
                ),
                group_by=(
                    SemanticFieldRef(entity_id="login_events", column="user_id"),
                ),
                having=(
                    SemanticHavingIntent(
                        aggregation_id="provider_having_alias",
                        operator="greater_than",
                        value=6,
                    ),
                ),
                order_by=(),
                limit=None,
            ),
        )


class StaticPlanProvider:
    provider_name = "static-plan-test-provider"
    model_name = "static-plan-test-model"

    def __init__(self, plan: SemanticPlan) -> None:
        self.plan = plan

    def generate_plan(
        self,
        _question: str,
        _schema_context: Mapping[str, Any],
        _user_context: Mapping[str, Any],
        _options: Mapping[str, Any],
    ) -> PlanGenerationResult:
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            semantic_plan=self.plan,
        )


class RecordingConformanceChecker:
    def __init__(
        self,
        result: SemanticConformanceResult | None = None,
    ) -> None:
        self.result = result or SemanticConformanceResult(
            valid=True,
            reason_code=None,
            checked_entity_count=1,
            checked_predicate_count=0,
            checked_relationship_count=0,
            checked_aggregation_count=0,
        )
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> SemanticConformanceResult:
        self.calls.append(dict(kwargs))
        return self.result


class RecordingValidator:
    def __init__(self) -> None:
        self.seen_sql: list[str] = []

    def __call__(
        self,
        sql: str,
        schema_context: dict[str, Any],
    ) -> SQLValidationResult:
        self.seen_sql.append(sql)
        return validate_sql(sql, schema_context)


class SequenceValidator:
    def __init__(self, results: list[SQLValidationResult]) -> None:
        self.results = list(results)
        self.seen_sql: list[str] = []

    def __call__(
        self,
        sql: str,
        _schema_context: dict[str, Any],
    ) -> SQLValidationResult:
        self.seen_sql.append(sql)
        assert self.results
        return self.results.pop(0)


def _device_plan(
    schema_context: dict[str, Any],
    sql: str,
    question: str = "",
) -> SemanticPlan:
    raw_columns = schema_context.get("allowed_columns", {}).get("devices", [])
    allowed_columns = tuple(
        sorted(column for column in raw_columns if isinstance(column, str))
    )
    if "SELECT *" in sql.upper():
        output_columns = allowed_columns
    elif "operating_system" in sql:
        output_columns = ("id", "operating_system")
    elif "SELECT id, os" in sql:
        output_columns = ("id", "os")
    elif "SELECT id, hostname" in sql:
        output_columns = ("id", "hostname")
    else:
        output_columns = ("id",) if "id" in allowed_columns else allowed_columns[:1]
    order_columns: list[str] = []
    if "ORDER BY hostname" in sql:
        order_columns.append("hostname")
    if "ORDER BY os, id" in sql:
        order_columns.extend(("os", "id"))
    return SemanticPlan(
        entity_ids=("devices",),
        concept_ids=(),
        composition_rule_ids=(
            ("non_compliant_device_posture",)
            if "non-compliant devices" in question.lower()
            else ()
        ),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(),
        output_fields=tuple(
            SemanticFieldRef(entity_id="devices", column=column)
            for column in output_columns
        ),
        aggregations=(),
        group_by=(),
        having=(),
        order_by=tuple(
            SemanticOrderIntent(
                target_kind="field",
                field=SemanticFieldRef(entity_id="devices", column=column),
                aggregation_id=None,
                direction="asc",
            )
            for column in order_columns
        ),
        limit=25 if "LIMIT 25" in sql else None,
    )


def only_query_run(session: Session) -> QueryRun:
    query_runs = session.scalars(select(QueryRun)).all()
    assert len(query_runs) == 1
    return query_runs[0]


def user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_database(session, profile_name="small", reset=True)
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("GROQ_API_KEY", None)

    try:
        yield session
    finally:
        session.close()
        engine.dispose()
