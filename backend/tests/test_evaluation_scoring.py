from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.evaluation.contracts import ComparisonMode, ExpectedOutcome
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.scoring import score_evaluation_case


def _successful_case():
    return load_it_operations_evaluation_set().cases_by_id["itops-easy-005"]


def _score(case, expected_rows, actual_rows, *, tables=None):
    return score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables if tables is None else tables,
        expected_rows=expected_rows,
        actual_rows=actual_rows,
    )


def test_equal_unordered_results_pass_in_different_order() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    score = _score(case, [{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 1}])
    assert score.passed is True
    assert score.score == 1.0


def test_ordered_comparison_detects_order_mismatch() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.ORDERED_ROWS)
    score = _score(case, [{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 1}])
    assert score.result_correct is False
    assert score.failure_reasons == ("result_semantics_mismatch",)


def test_aggregation_group_comparison_is_semantic() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.GROUPED_ROWS)
    score = _score(
        case,
        [{"priority": "high", "count": Decimal("2")}, {"priority": "low", "count": 3}],
        [{"count": 3.0, "priority": "low"}, {"count": 2, "priority": "high"}],
    )
    assert score.passed is True


def test_duplicate_row_multiplicity_is_not_discarded() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    score = _score(case, [{"id": 1}, {"id": 1}], [{"id": 1}, {"id": 2}])
    assert score.result_correct is False


def test_uuid_datetime_decimal_integer_and_float_normalization() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    identifier = uuid.uuid4()
    instant = datetime(2026, 1, 2, 12, 30, tzinfo=timezone.utc)
    score = _score(
        case,
        [{"id": identifier, "at": instant, "value": Decimal("4.0")}],
        [{"id": str(identifier), "at": instant.astimezone(timezone(timedelta(hours=2))), "value": 4}],
    )
    assert score.passed is True


def test_numeric_tolerance_is_explicit_and_case_controlled() -> None:
    exact_case = replace(
        _successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS, numeric_tolerance=None
    )
    tolerant_case = replace(exact_case, numeric_tolerance=Decimal("0.01"))
    expected = [{"amount": Decimal("10.00")}]
    actual = [{"amount": 10.009}]

    assert _score(exact_case, expected, actual).passed is False
    assert _score(tolerant_case, expected, actual).passed is True


def test_nulls_compare_only_to_nulls() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    assert _score(case, [{"value": None}], [{"value": None}]).passed is True
    assert _score(case, [{"value": None}], [{"value": ""}]).passed is False


def test_expected_denial_unsafe_block_and_clarification_score_without_execution() -> None:
    cases = load_it_operations_evaluation_set().cases_by_id
    denial = cases["itops-security-001"]
    unsafe = cases["itops-security-003"]
    clarification = cases["itops-security-005"]

    denied_score = score_evaluation_case(
        denial,
        actual_outcome=ExpectedOutcome.DENIED,
        execution_succeeded=False,
    )
    clarification_score = score_evaluation_case(
        clarification,
        actual_outcome=ExpectedOutcome.CLARIFICATION,
        execution_succeeded=False,
    )
    unsafe_score = score_evaluation_case(
        unsafe,
        actual_outcome=ExpectedOutcome.UNSAFE_BLOCKED,
        execution_succeeded=False,
        actual_referenced_tables=unsafe.expected_tables,
    )
    assert denied_score.passed is True
    assert denied_score.result_correct is None
    assert unsafe_score.passed is True
    assert clarification_score.passed is True


def test_wrong_referenced_tables_fail_even_when_rows_match() -> None:
    case = _successful_case()
    score = _score(case, [{"count": 1}], [{"count": 1}], tables=["devices"])
    assert score.tables_correct is False
    assert "referenced_tables_mismatch" in score.failure_reasons


def test_stable_key_comparison_and_missing_key_are_safe() -> None:
    case = replace(
        _successful_case(),
        comparison_mode=ComparisonMode.STABLE_KEYS,
        stable_key_columns=("id",),
    )
    assert _score(case, [{"id": 1, "name": "old"}], [{"id": 1, "name": "new"}]).passed
    missing = _score(case, [{"id": 1}], [{"name": "not-returned"}])
    assert missing.passed is False
    assert missing.failure_reasons == ("missing_stable_key",)


def test_score_diagnostics_never_include_raw_rows() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    secret = "raw-row-secret@example.invalid"
    score = _score(case, [{"value": secret}], [{"value": "different"}])
    serialized = json.dumps(score.as_safe_metrics(), sort_keys=True)

    assert secret not in serialized
    assert "different" not in serialized
    assert set(score.as_safe_metrics()) == {
        "score",
        "passed",
        "outcome_correct",
        "execution_correct",
        "tables_correct",
        "result_correct",
        "expected_row_count",
        "actual_row_count",
        "failure_reasons",
    }
