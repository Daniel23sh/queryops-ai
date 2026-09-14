from __future__ import annotations

import json
from dataclasses import replace

import pytest
from sqlglot import parse_one

from app.evaluation.contracts import (
    ActualOutcome,
    ComparisonMode,
    ComparisonState,
    DeliveryCompleteness,
    EvaluationAnswerBound,
    EvaluationAnswerBoundKind,
    ExpectedOutcome,
)
from app.evaluation.evidence import (
    EVIDENCE_PAYLOAD_LIMIT_BYTES,
    EvaluationComparisonEvidence,
    EvaluationEvidenceSide,
    auxiliary_evidence_side,
    build_auxiliary_validation,
    comparison_payload_size,
    distinct_delivery_payload_rows,
    evidence_summary_supports_judgment,
    is_safe_evidence_summary,
    observed_evidence_side,
)
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.provenance import build_evaluation_comparison_provenance
from app.evaluation.scoring import score_evaluation_case
from app.query_engine.sql_executor import SQLExecutionResult
from app.query_engine.sql_validator import validate_sql


SCHEMA = {
    "domain": "it_operations",
    "allowed_tables": ["license_assignments"],
    "allowed_columns": {"license_assignments": ["id"]},
    "tables": [
        {
            "name": "license_assignments",
            "display_name": "License Assignments",
            "description": "Synthetic assignments.",
            "scope_type": "department",
            "scope_column": "department_id",
            "columns": [
                {
                    "name": "id",
                    "data_type": "uuid",
                    "description": "Synthetic identifier.",
                    "nullable": False,
                }
            ],
            "resource": {
                "resource_type": "table",
                "schema_name": "public",
                "table_name": "license_assignments",
                "sensitivity_level": "scoped_restricted",
                "scope_type": "department",
                "scope_column": "department_id",
                "is_queryable": True,
                "llm_exposure_level": "aggregate_safe",
            },
        }
    ],
}


def test_only_a_proven_outer_safety_limit_can_be_widened() -> None:
    safety = validate_sql("SELECT id FROM license_assignments", SCHEMA)
    widened = build_auxiliary_validation(safety, SCHEMA)
    explicit = validate_sql("SELECT id FROM license_assignments LIMIT 10", SCHEMA)
    offset = validate_sql("SELECT id FROM license_assignments OFFSET 1", SCHEMA)
    nested = replace(
        safety,
        sanitized_sql=(
            "SELECT id FROM (SELECT id FROM license_assignments LIMIT 5) bounded "
            "LIMIT 100"
        ),
    )
    mismatched = replace(safety, sanitized_sql="SELECT id FROM license_assignments LIMIT 99")

    assert safety.limit_source == "safety_added"
    assert widened is not None
    assert widened.sanitized_sql.endswith("LIMIT 1001")
    assert build_auxiliary_validation(explicit, SCHEMA) is None
    assert build_auxiliary_validation(offset, SCHEMA) is None
    assert build_auxiliary_validation(nested, SCHEMA) is None
    assert build_auxiliary_validation(mismatched, SCHEMA) is None


@pytest.mark.parametrize(
    "sql",
    (
        "SELECT DISTINCT id FROM license_assignments ORDER BY id",
        "SELECT id, COUNT(*) AS amount FROM license_assignments "
        "GROUP BY id HAVING COUNT(*) > 0 ORDER BY amount DESC",
        "SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rank "
        "FROM license_assignments ORDER BY id",
    ),
)
def test_auxiliary_widening_preserves_distinct_grouping_ranking_and_order(
    sql: str,
) -> None:
    validation = validate_sql(sql, SCHEMA)
    widened = build_auxiliary_validation(validation, SCHEMA)
    assert widened is not None
    original_tree = parse_one(validation.sanitized_sql, dialect="postgres")
    widened_tree = parse_one(widened.sanitized_sql, dialect="postgres")
    original_tree.set("limit", None)
    widened_tree.set("limit", None)

    assert widened_tree == original_tree


def test_exact_bound_needs_eof_and_lookahead_proves_budget_exhaustion() -> None:
    validation = validate_sql("SELECT id FROM license_assignments", SCHEMA)
    exactly_cap = observed_evidence_side(
        ({"id": index} for index in range(100)),
        validation,
        _execution(100, truncated=False),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )
    widened = build_auxiliary_validation(validation, SCHEMA)
    assert widened is not None
    exactly_budget = auxiliary_evidence_side(
        widened,
        _execution(1000, truncated=False),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )
    beyond_budget = auxiliary_evidence_side(
        widened,
        _execution(1000, truncated=True),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )

    assert exactly_cap.complete is False
    assert exactly_cap.delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED
    assert exactly_budget.complete is True
    assert beyond_budget.complete is False
    assert beyond_budget.limitation_reason == "evidence_row_budget_exceeded"


def test_population_below_safety_cap_is_complete_without_auxiliary_execution() -> None:
    validation = validate_sql("SELECT id FROM license_assignments", SCHEMA)
    side = observed_evidence_side(
        ({"id": index} for index in range(99)),
        validation,
        _execution(99, truncated=False),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )

    assert side.complete is True
    assert side.delivery_completeness is DeliveryCompleteness.COMPLETE
    assert side.auxiliary_execution_count == 0


def test_sql_exhaustion_without_population_completeness_persists_unestablished() -> None:
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    validation = validate_sql(
        "SELECT id FROM license_assignments LIMIT 10", SCHEMA
    )
    rows = tuple({"id": index} for index in range(3))
    side = observed_evidence_side(
        rows,
        validation,
        _execution(3, truncated=False),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )
    evidence = EvaluationComparisonEvidence(
        expected=side,
        actual=side,
        actual_delivery_completeness=DeliveryCompleteness.UNKNOWN,
    )
    score = score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=rows,
        actual_rows=rows,
        comparison_evidence=evidence,
        semantic_contract_passed=True,
    )

    assert side.exhausted is True
    assert side.complete is False
    assert score.comparison_state is ComparisonState.UNESTABLISHED
    assert evidence_summary_supports_judgment(
        evidence.as_safe_dict(),
        score.comparison_state,
        score.delivery_completeness,
        score.comparison_limitation_reason,
    )


def test_nested_limit_cannot_masquerade_as_population_exhaustion() -> None:
    validation = validate_sql(
        "SELECT id FROM (SELECT id FROM license_assignments LIMIT 5) bounded",
        SCHEMA,
    )
    side = observed_evidence_side(
        ({"id": index} for index in range(5)),
        validation,
        _execution(5, truncated=False),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )

    assert side.complete is False
    assert side.exhausted is False
    assert side.limitation_reason == "unsupported_query_shape"


def test_failed_actual_execution_is_not_reached_with_unknown_delivery() -> None:
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]

    score = score_evaluation_case(
        case,
        actual_outcome=ActualOutcome.EXECUTION_FAILED,
        execution_succeeded=False,
    )

    assert score.comparison_state is ComparisonState.NOT_REACHED
    assert score.delivery_completeness is DeliveryCompleteness.UNKNOWN
    assert score.result_correct is None


def test_restored_nonsemantic_limit_does_not_masquerade_as_eof() -> None:
    clamped = validate_sql("SELECT id FROM license_assignments LIMIT 200", SCHEMA)
    widened = build_auxiliary_validation(clamped, SCHEMA)
    assert clamped.limit_source == "input"
    assert widened is None

    clamped = validate_sql("SELECT id FROM license_assignments LIMIT 2000", SCHEMA)
    widened = build_auxiliary_validation(clamped, SCHEMA)
    assert widened is not None
    side = auxiliary_evidence_side(
        widened,
        _execution(1000, truncated=True),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )
    assert side.complete is False


def test_full_auxiliary_population_can_qualify_different_delivered_subsets() -> None:
    population = tuple({"id": index} for index in range(205))
    score = _score_with_evidence(
        expected_rows=population[:100],
        actual_rows=population[100:200],
        expected_population=population,
        actual_population=population,
    )

    assert score.comparison_state is ComparisonState.CORRECT
    assert score.result_correct is True
    assert score.passed is True
    assert score.delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED


def test_complete_evidence_rejects_identical_visible_subsets_of_different_populations() -> None:
    visible = tuple({"id": index} for index in range(100))
    score = _score_with_evidence(
        expected_rows=visible,
        actual_rows=visible,
        expected_population=(*visible, {"id": 100}),
        actual_population=(*visible, {"id": 101}),
    )

    assert score.comparison_state is ComparisonState.INCORRECT
    assert score.result_correct is False


def test_incomplete_equal_count_evidence_is_nonqualifying() -> None:
    visible = tuple({"id": index} for index in range(100))
    side = EvaluationEvidenceSide(
        rows=visible,
        complete=False,
        limitation_reason="evidence_row_budget_exceeded",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
        auxiliary_execution_count=1,
    )
    score = _score_with_evidence(
        expected_rows=visible,
        actual_rows=visible,
        expected_population=visible,
        actual_population=visible,
        expected_side=side,
        actual_side=side,
    )

    assert score.comparison_state is ComparisonState.UNESTABLISHED
    assert score.result_correct is None
    assert score.passed is False
    assert score.score == 0.75


def test_unsupported_partial_side_cannot_create_a_false_difference_witness() -> None:
    expected = ({"id": 1},)
    unsupported_actual = EvaluationEvidenceSide(
        rows=({"id": 999},),
        complete=False,
        comparison_eligible=False,
        limitation_reason="unsupported_query_shape",
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    score = _score_with_evidence(
        expected_rows=expected,
        actual_rows=unsupported_actual.rows,
        expected_population=expected,
        actual_population=unsupported_actual.rows,
        actual_side=unsupported_actual,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    assert score.comparison_state is ComparisonState.UNESTABLISHED
    assert score.result_correct is None


def test_later_context_failure_does_not_make_unsupported_evidence_eligible() -> None:
    expected = EvaluationEvidenceSide(
        rows=({"id": 1},),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    unsupported_actual = EvaluationEvidenceSide(
        rows=({"id": 999},),
        complete=False,
        comparison_eligible=False,
        limitation_reason="unsupported_query_shape",
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    score = _score_with_evidence(
        expected_rows=expected.rows,
        actual_rows=unsupported_actual.rows,
        expected_population=expected.rows,
        actual_population=unsupported_actual.rows,
        expected_side=expected,
        actual_side=unsupported_actual,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
        context_compatible=False,
    )

    assert score.comparison_state is ComparisonState.UNESTABLISHED
    assert score.comparison_limitation_reason == (
        "comparison_context_unestablished"
    )


def test_complete_actual_side_uses_expected_to_actual_provenance_direction() -> None:
    incomplete_expected = EvaluationEvidenceSide(
        rows=({"id": 1},),
        complete=False,
        limitation_reason="evidence_row_budget_exceeded",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
    )
    complete_actual = EvaluationEvidenceSide(
        rows=({"assignment_id": 1}, {"assignment_id": 2}),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    provenance = build_evaluation_comparison_provenance(
        baseline_sql="SELECT id FROM license_assignments",
        final_sql="SELECT id AS assignment_id FROM license_assignments",
    )

    score = score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=incomplete_expected.rows,
        actual_rows=complete_actual.rows,
        provenance=provenance,
        comparison_evidence=EvaluationComparisonEvidence(
            expected=incomplete_expected,
            actual=complete_actual,
            actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
        ),
        semantic_contract_passed=True,
    )

    assert score.comparison_state is ComparisonState.UNESTABLISHED
    assert score.result_correct is None


def test_missing_provenance_does_not_compare_unordered_alias_names_as_values() -> None:
    base = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    case = replace(base, comparison_mode=ComparisonMode.UNORDERED_ROWS)
    incomplete_expected = EvaluationEvidenceSide(
        rows=({"id": 1},),
        complete=False,
        limitation_reason="evidence_row_budget_exceeded",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
    )
    complete_actual = EvaluationEvidenceSide(
        rows=({"assignment_id": 1},),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    score = score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=incomplete_expected.rows,
        actual_rows=complete_actual.rows,
        comparison_evidence=EvaluationComparisonEvidence(
            expected=incomplete_expected,
            actual=complete_actual,
            actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
        ),
        semantic_contract_passed=True,
    )

    assert score.comparison_state is ComparisonState.UNESTABLISHED
    assert score.result_correct is None

    complete_expected = replace(
        incomplete_expected,
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    complete_score = score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=complete_expected.rows,
        actual_rows=complete_actual.rows,
        comparison_evidence=EvaluationComparisonEvidence(
            expected=complete_expected,
            actual=complete_actual,
            actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
        ),
        semantic_contract_passed=True,
    )

    assert complete_score.comparison_state is ComparisonState.UNESTABLISHED
    assert complete_score.result_correct is None
    assert complete_score.comparison_limitation_reason == (
        "comparison_proof_unavailable"
    )
    complete_evidence = EvaluationComparisonEvidence(
        expected=complete_expected,
        actual=complete_actual,
        actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    assert evidence_summary_supports_judgment(
        complete_evidence.as_safe_dict(),
        complete_score.comparison_state,
        complete_score.delivery_completeness,
        complete_score.comparison_limitation_reason,
    )


def test_one_sided_alias_without_provenance_is_not_a_proven_difference() -> None:
    incomplete_expected = EvaluationEvidenceSide(
        rows=({"id": 1},),
        complete=False,
        limitation_reason="comparison_proof_unavailable",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
    )
    complete_actual = EvaluationEvidenceSide(
        rows=({"assignment_id": 1}, {"assignment_id": 2}),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]

    score = score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=incomplete_expected.rows,
        actual_rows=complete_actual.rows,
        comparison_evidence=EvaluationComparisonEvidence(
            expected=incomplete_expected,
            actual=complete_actual,
            actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
        ),
        semantic_contract_passed=True,
    )

    assert score.comparison_state is ComparisonState.UNESTABLISHED
    assert score.result_correct is None


def test_budget_exhaustion_keeps_an_independent_membership_witness() -> None:
    expected = tuple({"id": index} for index in range(10))
    actual_side = EvaluationEvidenceSide(
        rows=(),
        complete=False,
        limitation_reason="evidence_timeout",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
        auxiliary_execution_count=1,
    )

    score = _score_with_evidence(
        expected_rows=expected,
        actual_rows=(*expected[:9], {"id": 999}),
        expected_population=expected,
        actual_population=actual_side.rows,
        actual_side=actual_side,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    assert score.comparison_state is ComparisonState.INCORRECT
    assert score.failure_reasons == ("result_semantics_mismatch",)


def test_complete_reference_rejects_wrong_known_delivery_cardinality() -> None:
    expected = tuple({"id": index} for index in range(10))
    incomplete_actual = EvaluationEvidenceSide(
        rows=(),
        complete=False,
        limitation_reason="evidence_timeout",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
        auxiliary_execution_count=1,
    )

    score = _score_with_evidence(
        expected_rows=expected,
        actual_rows=expected[:9],
        expected_population=expected,
        actual_population=(),
        actual_side=incomplete_actual,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    assert score.comparison_state is ComparisonState.INCORRECT
    assert score.failure_reasons == ("result_semantics_mismatch",)


def test_timeout_and_payload_exhaustion_are_explicit_limitations() -> None:
    validation = validate_sql("SELECT id FROM license_assignments", SCHEMA)
    widened = build_auxiliary_validation(validation, SCHEMA)
    assert widened is not None
    timeout = auxiliary_evidence_side(
        widened,
        replace(
            _execution(0, truncated=False),
            status="failed",
            execution_metadata={"timeout": True},
        ),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )
    payload = auxiliary_evidence_side(
        widened,
        replace(
            _execution(10, truncated=False),
            execution_metadata={"payload_limited": True},
        ),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )

    assert timeout.limitation_reason == "evidence_timeout"
    assert payload.limitation_reason == "evidence_payload_exceeded"


def test_matching_populations_do_not_excuse_an_invalid_delivered_row() -> None:
    population = tuple({"id": index} for index in range(205))
    score = _score_with_evidence(
        expected_rows=population[:100],
        actual_rows=(*population[:99], {"id": 999}),
        expected_population=population,
        actual_population=population,
    )

    assert score.comparison_state is ComparisonState.INCORRECT
    assert score.result_correct is False


def test_matching_populations_do_not_excuse_incomplete_safety_delivery() -> None:
    population = tuple({"id": index} for index in range(205))
    score = _score_with_evidence(
        expected_rows=population[:100],
        actual_rows=population[:50],
        expected_population=population,
        actual_population=population,
    )

    assert score.comparison_state is ComparisonState.INCORRECT
    assert score.result_correct is False


def test_semantic_contract_must_be_proven_before_complete_evidence_can_pass() -> None:
    population = tuple({"id": index} for index in range(20))

    failed = _score_with_evidence(
        expected_rows=population,
        actual_rows=population,
        expected_population=population,
        actual_population=population,
        semantic_contract_passed=False,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    unavailable = _score_with_evidence(
        expected_rows=population,
        actual_rows=population,
        expected_population=population,
        actual_population=population,
        semantic_contract_passed=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    assert failed.comparison_state is ComparisonState.INCORRECT
    assert failed.failure_reasons == ("result_semantics_mismatch",)
    assert unavailable.comparison_state is ComparisonState.UNESTABLISHED
    assert unavailable.comparison_limitation_reason == (
        "comparison_proof_unavailable"
    )


def test_declared_top_n_preserves_its_semantic_bound() -> None:
    validation = validate_sql("SELECT id FROM license_assignments LIMIT 10", SCHEMA)
    side = observed_evidence_side(
        ({"id": index} for index in range(10)),
        validation,
        _execution(10, truncated=False),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.TOP_N, 10),
    )

    assert side.complete is True
    assert build_auxiliary_validation(validation, SCHEMA) is None


def test_semantic_bound_above_evidence_budget_remains_representable() -> None:
    bound = EvaluationAnswerBound(EvaluationAnswerBoundKind.TOP_N, 1500)
    validation = validate_sql("SELECT id FROM license_assignments LIMIT 1500", SCHEMA)
    widened = build_auxiliary_validation(validation, SCHEMA)

    assert widened is not None
    assert widened.input_limit == 1500
    assert widened.effective_limit == 1001
    assert widened.limit_source == "safety_clamped"
    side = auxiliary_evidence_side(
        widened,
        _execution(1000, truncated=True),
        bound,
    )
    assert side.complete is False
    assert side.limitation_reason == "evidence_row_budget_exceeded"


def test_safety_clamped_semantic_bound_is_not_complete_until_restored() -> None:
    bound = EvaluationAnswerBound(EvaluationAnswerBoundKind.TOP_N, 600)
    observed_validation = validate_sql(
        "SELECT id FROM license_assignments ORDER BY id LIMIT 600", SCHEMA
    )
    observed = observed_evidence_side(
        ({"id": index} for index in range(500)),
        observed_validation,
        _execution(500, truncated=False),
        bound,
    )

    assert observed_validation.limit_source == "safety_clamped"
    assert observed.complete is False
    assert observed.delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED

    restored_validation = build_auxiliary_validation(observed_validation, SCHEMA)
    assert restored_validation is not None
    restored = auxiliary_evidence_side(
        restored_validation,
        _execution(600, truncated=False),
        bound,
    )
    assert restored.complete is True


def test_unresolved_top_n_cutoff_ties_are_unestablished() -> None:
    base = load_it_operations_evaluation_v2_set().cases_by_id["itops-hard-006"]
    assert base.semantic_contract is not None
    case = replace(
        base,
        semantic_contract=replace(
            base.semantic_contract,
            answer_bound=EvaluationAnswerBound(EvaluationAnswerBoundKind.TOP_N, 2),
        ),
    )
    expected = ({"product_name": "A", "monthly_savings": 10}, {"product_name": "B", "monthly_savings": 5})
    actual = ({"product_name": "A", "monthly_savings": 10}, {"product_name": "C", "monthly_savings": 5})
    evidence = EvaluationComparisonEvidence(
        expected=EvaluationEvidenceSide(
            rows=expected,
            complete=True,
            limitation_reason=None,
            delivery_completeness=DeliveryCompleteness.COMPLETE,
        ),
        actual=EvaluationEvidenceSide(
            rows=actual,
            complete=True,
            limitation_reason=None,
            delivery_completeness=DeliveryCompleteness.COMPLETE,
        ),
        actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    score = score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=expected,
        actual_rows=actual,
        comparison_evidence=evidence,
        semantic_contract_passed=True,
    )

    assert score.comparison_state is ComparisonState.UNESTABLISHED
    assert score.comparison_limitation_reason == "ranking_tie_unestablished"


def test_unordered_semantic_limit_does_not_claim_one_arbitrary_selection() -> None:
    base = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    assert base.semantic_contract is not None
    case = replace(
        base,
        semantic_contract=replace(
            base.semantic_contract,
            answer_bound=EvaluationAnswerBound(EvaluationAnswerBoundKind.LIMIT, 2),
        ),
    )
    expected = ({"id": 1}, {"id": 2})
    actual = ({"id": 3}, {"id": 4})
    evidence = EvaluationComparisonEvidence(
        expected=EvaluationEvidenceSide(
            rows=expected,
            complete=True,
            limitation_reason=None,
            delivery_completeness=DeliveryCompleteness.COMPLETE,
            exhausted=False,
        ),
        actual=EvaluationEvidenceSide(
            rows=actual,
            complete=True,
            limitation_reason=None,
            delivery_completeness=DeliveryCompleteness.COMPLETE,
            exhausted=False,
        ),
        actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    score = score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=expected,
        actual_rows=actual,
        comparison_evidence=evidence,
        semantic_contract_passed=True,
    )

    assert score.comparison_state is ComparisonState.UNESTABLISHED
    assert score.comparison_limitation_reason == "bounded_selection_unestablished"
    assert evidence_summary_supports_judgment(
        evidence.as_safe_dict(),
        score.comparison_state,
        score.delivery_completeness,
        score.comparison_limitation_reason,
    )


def test_streamed_payload_size_matches_the_canonical_json_shape() -> None:
    expected = ({"id": 1, "name": "A"},)
    actual = ({"id": 2, "name": "B"}, {"id": 3, "name": "C"})

    assert comparison_payload_size(expected, actual) == len(
        json.dumps(
            [list(expected), list(actual)],
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    assert comparison_payload_size(expected, actual, maximum=1) == 2
    assert comparison_payload_size(expected, actual, delivered=actual) == len(
        json.dumps(
            [list(expected), list(actual), list(actual)],
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def test_auxiliary_evidence_rejects_volatile_expressions() -> None:
    validation = validate_sql(
        "SELECT id, random() AS sample FROM license_assignments",
        SCHEMA,
    )

    assert validation.valid is True
    assert build_auxiliary_validation(validation, SCHEMA) is None
    observed = observed_evidence_side(
        ({"id": 1, "sample": 0.5},),
        validation,
        _execution(1, truncated=False),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )
    assert observed.complete is False
    assert observed.exhausted is False
    assert observed.delivery_completeness is DeliveryCompleteness.COMPLETE
    assert observed.limitation_reason == "unsupported_query_shape"
    auxiliary = auxiliary_evidence_side(
        validation,
        _execution(1, truncated=False),
        EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
    )
    assert auxiliary.complete is False
    assert auxiliary.limitation_reason == "unsupported_query_shape"


def test_timeout_overrun_remains_a_valid_nonqualifying_summary() -> None:
    side = EvaluationEvidenceSide(
        rows=(),
        complete=False,
        limitation_reason="evidence_timeout",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
        auxiliary_execution_count=1,
        auxiliary_duration_ms=5_001,
    )
    evidence = EvaluationComparisonEvidence(
        expected=side,
        actual=side,
        actual_delivery_completeness=DeliveryCompleteness.UNKNOWN,
    )

    summary = evidence.as_safe_dict()
    assert is_safe_evidence_summary(summary) is True
    assert evidence_summary_supports_judgment(
        summary,
        ComparisonState.UNESTABLISHED,
        DeliveryCompleteness.UNKNOWN,
        "evidence_timeout",
    )


def test_complete_payload_limited_comparison_remains_a_valid_limitation() -> None:
    side = EvaluationEvidenceSide(
        rows=({"id": 1},),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    evidence = EvaluationComparisonEvidence(
        expected=side,
        actual=side,
        actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    assert evidence_summary_supports_judgment(
        evidence.as_safe_dict(),
        ComparisonState.UNESTABLISHED,
        DeliveryCompleteness.COMPLETE,
        "evidence_payload_exceeded",
    )


def test_comparison_payload_limitation_can_preserve_an_earlier_side_limitation() -> None:
    complete = EvaluationEvidenceSide(
        rows=({"id": 1},),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    incomplete = EvaluationEvidenceSide(
        rows=({"id": 1},),
        complete=False,
        limitation_reason="nonsemantic_bound_reached",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
    )
    evidence = EvaluationComparisonEvidence(
        expected=complete,
        actual=incomplete,
        actual_delivery_completeness=DeliveryCompleteness.UNKNOWN,
    )

    assert evidence_summary_supports_judgment(
        evidence.as_safe_dict(),
        ComparisonState.UNESTABLISHED,
        DeliveryCompleteness.UNKNOWN,
        "evidence_payload_exceeded",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("observed_execution_count", True),
        ("auxiliary_execution_count", False),
        ("observed_duration_ms", float("inf")),
        ("auxiliary_duration_ms", float("nan")),
    ),
)
def test_safe_evidence_summary_rejects_noncanonical_counts_and_durations(
    field: str,
    value,
) -> None:
    side = EvaluationEvidenceSide(
        rows=(),
        complete=False,
        limitation_reason="evidence_timeout",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
    )
    summary = EvaluationComparisonEvidence(
        expected=side,
        actual=side,
        actual_delivery_completeness=DeliveryCompleteness.UNKNOWN,
    ).as_safe_dict()
    summary["actual"][field] = value

    assert is_safe_evidence_summary(summary) is False


def test_payload_exhaustion_does_not_hide_a_small_delivery_witness() -> None:
    expected = ({"id": 1},)
    incomplete_actual = EvaluationEvidenceSide(
        rows=({"id": 1, "value": "x" * (8 * 1024 * 1024)},),
        complete=False,
        limitation_reason="evidence_payload_exceeded",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
        auxiliary_execution_count=1,
    )

    score = _score_with_evidence(
        expected_rows=expected,
        actual_rows=({"id": 999},),
        expected_population=expected,
        actual_population=incomplete_actual.rows,
        actual_side=incomplete_actual,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    assert score.comparison_state is ComparisonState.INCORRECT
    assert score.result_correct is False


def test_exact_payload_boundary_uses_one_shared_two_or_three_set_definition() -> None:
    empty = ({"id": 1, "value": ""},)
    fixed_size = comparison_payload_size(empty, empty)
    padding = (EVIDENCE_PAYLOAD_LIMIT_BYTES - 1 - fixed_size) // 2
    rows = ({"id": 1, "value": "x" * padding},)
    observed_actual = EvaluationEvidenceSide(
        rows=rows,
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    observed_score = _score_with_evidence(
        expected_rows=rows,
        actual_rows=rows,
        expected_population=rows,
        actual_population=rows,
        actual_side=observed_actual,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    oversized_rows = ({"id": 1, "value": "x" * (padding + 1)},)
    oversized_score = _score_with_evidence(
        expected_rows=oversized_rows,
        actual_rows=oversized_rows,
        expected_population=oversized_rows,
        actual_population=oversized_rows,
        actual_side=replace(observed_actual, rows=oversized_rows),
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    auxiliary_score = _score_with_evidence(
        expected_rows=rows,
        actual_rows=rows,
        expected_population=rows,
        actual_population=rows,
        actual_side=replace(observed_actual, auxiliary_execution_count=1),
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    assert comparison_payload_size(rows, rows) == EVIDENCE_PAYLOAD_LIMIT_BYTES - 1
    assert comparison_payload_size(rows, rows, delivered=()) == (
        EVIDENCE_PAYLOAD_LIMIT_BYTES + 2
    )
    assert distinct_delivery_payload_rows(observed_actual, rows) is None
    assert observed_score.comparison_state is ComparisonState.CORRECT
    assert oversized_score.comparison_state is ComparisonState.UNESTABLISHED
    assert oversized_score.comparison_limitation_reason == "evidence_payload_exceeded"
    assert distinct_delivery_payload_rows(
        replace(observed_actual, auxiliary_execution_count=1), rows
    ) is rows
    assert auxiliary_score.comparison_state is ComparisonState.UNESTABLISHED
    assert auxiliary_score.comparison_limitation_reason == (
        "evidence_payload_exceeded"
    )


def test_payload_exhaustion_does_not_hide_complete_population_count_difference() -> None:
    wide = "x" * (3 * 1024 * 1024)
    expected = ({"id": 1, "value": wide},)
    actual = (*expected, {"id": 2, "value": wide})

    score = _score_with_evidence(
        expected_rows=expected,
        actual_rows=actual,
        expected_population=expected,
        actual_population=actual,
    )

    assert score.comparison_state is ComparisonState.INCORRECT
    assert score.failure_reasons == ("row_count_mismatch",)


def test_payload_exhaustion_does_not_hide_delivery_cardinality_difference() -> None:
    wide = "x" * (3 * 1024 * 1024)
    expected = tuple({"id": index, "value": wide} for index in range(3))
    incomplete_actual = EvaluationEvidenceSide(
        rows=expected,
        complete=False,
        limitation_reason="evidence_payload_exceeded",
        delivery_completeness=DeliveryCompleteness.UNKNOWN,
        auxiliary_execution_count=1,
    )

    score = _score_with_evidence(
        expected_rows=expected[:2],
        actual_rows=expected[:2],
        expected_population=expected,
        actual_population=expected,
        actual_side=incomplete_actual,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )

    assert score.comparison_state is ComparisonState.INCORRECT
    assert score.failure_reasons == ("result_semantics_mismatch",)


def test_complete_evidence_can_support_context_unestablished_without_qualifying() -> None:
    rows = ({"id": 1},)
    side = EvaluationEvidenceSide(
        rows=rows,
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    evidence = EvaluationComparisonEvidence(
        expected=side,
        actual=side,
        actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
        context_compatible=False,
    )

    assert evidence_summary_supports_judgment(
        evidence.as_safe_dict(),
        ComparisonState.UNESTABLISHED,
        DeliveryCompleteness.COMPLETE,
        "comparison_context_unestablished",
    )


def test_complete_evidence_requires_an_execution_on_each_side() -> None:
    side = EvaluationEvidenceSide(
        rows=(),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    summary = EvaluationComparisonEvidence(
        expected=side,
        actual=side,
        actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
    ).as_safe_dict()
    for name in ("expected", "actual"):
        summary[name]["observed_execution_count"] = 0
        summary[name]["observed_duration_ms"] = 1.0

    assert is_safe_evidence_summary(summary) is False


@pytest.mark.parametrize(
    "limitation",
    (
        "evidence_timeout",
        "evidence_validation_failed",
        "unsupported_query_shape",
    ),
)
def test_complete_evidence_rejects_unobserved_acquisition_limitations(
    limitation: str,
) -> None:
    side = EvaluationEvidenceSide(
        rows=(),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
    )
    summary = EvaluationComparisonEvidence(
        expected=side,
        actual=side,
        actual_delivery_completeness=DeliveryCompleteness.COMPLETE,
    ).as_safe_dict()

    assert not evidence_summary_supports_judgment(
        summary,
        ComparisonState.UNESTABLISHED,
        DeliveryCompleteness.COMPLETE,
        limitation,
    )


@pytest.mark.parametrize("function", ("statement_timestamp()", "clock_timestamp()"))
def test_auxiliary_evidence_rejects_nontransaction_time(function: str) -> None:
    validation = validate_sql(
        f"SELECT id, {function} AS observed_at FROM license_assignments",
        SCHEMA,
    )

    assert validation.valid is True
    assert build_auxiliary_validation(validation, SCHEMA) is None


def _score_with_evidence(
    *,
    expected_rows,
    actual_rows,
    expected_population,
    actual_population,
    expected_side=None,
    actual_side=None,
    semantic_contract_passed=True,
    delivery_completeness=DeliveryCompleteness.SAFETY_LIMITED,
    context_compatible=True,
):
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    complete_expected = expected_side or EvaluationEvidenceSide(
        rows=tuple(expected_population),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
        auxiliary_execution_count=1,
    )
    complete_actual = actual_side or EvaluationEvidenceSide(
        rows=tuple(actual_population),
        complete=True,
        limitation_reason=None,
        delivery_completeness=DeliveryCompleteness.COMPLETE,
        auxiliary_execution_count=1,
    )
    return score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=expected_rows,
        actual_rows=actual_rows,
        comparison_evidence=EvaluationComparisonEvidence(
            expected=complete_expected,
            actual=complete_actual,
            actual_delivery_completeness=delivery_completeness,
            actual_delivery_row_limit=(
                100
                if delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED
                else None
            ),
            context_compatible=context_compatible,
        ),
        semantic_contract_passed=semantic_contract_passed,
    )


def _execution(row_count: int, *, truncated: bool) -> SQLExecutionResult:
    return SQLExecutionResult(
        status="succeeded",
        columns=["id"],
        rows=[{"id": index} for index in range(row_count)],
        row_count=row_count,
        duration_ms=1.0,
        truncated=truncated,
    )
