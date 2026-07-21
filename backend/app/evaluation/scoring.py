from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.evaluation.contracts import (
    ActualOutcome,
    ComparisonMode,
    EvaluationCase,
    ExpectedOutcome,
)


SAFE_FAILURE_REASONS = frozenset(
    {
        "unexpected_outcome",
        "execution_state_mismatch",
        "referenced_tables_mismatch",
        "row_count_mismatch",
        "result_semantics_mismatch",
        "missing_stable_key",
        "invalid_numeric_value",
    }
)


@dataclass(frozen=True)
class EvaluationScore:
    score: float
    passed: bool
    outcome_correct: bool
    execution_correct: bool
    tables_correct: bool
    result_correct: bool | None
    expected_row_count: int
    actual_row_count: int
    failure_reasons: tuple[str, ...]

    def as_safe_metrics(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "outcome_correct": self.outcome_correct,
            "execution_correct": self.execution_correct,
            "tables_correct": self.tables_correct,
            "result_correct": self.result_correct,
            "expected_row_count": self.expected_row_count,
            "actual_row_count": self.actual_row_count,
            "failure_reasons": list(self.failure_reasons),
        }


def score_evaluation_case(
    case: EvaluationCase,
    *,
    actual_outcome: ExpectedOutcome | ActualOutcome,
    execution_succeeded: bool,
    actual_referenced_tables: Sequence[str] = (),
    expected_rows: Sequence[Mapping[str, Any]] = (),
    actual_rows: Sequence[Mapping[str, Any]] = (),
) -> EvaluationScore:
    outcome_correct = actual_outcome.value == case.expected_outcome.value
    execution_correct = execution_succeeded == (
        case.expected_outcome is ExpectedOutcome.SUCCESS
    )
    tables_correct = set(actual_referenced_tables) == set(case.expected_tables)
    result_correct: bool | None = None
    failures: list[str] = []

    if not outcome_correct:
        failures.append("unexpected_outcome")
    if not execution_correct:
        failures.append("execution_state_mismatch")
    if not tables_correct:
        failures.append("referenced_tables_mismatch")

    if case.expected_outcome is ExpectedOutcome.SUCCESS:
        result_correct, result_failure = _compare_rows(case, expected_rows, actual_rows)
        if result_failure is not None:
            failures.append(result_failure)

    components = [outcome_correct, execution_correct, tables_correct]
    if result_correct is not None:
        components.append(result_correct)
    score = sum(1 for component in components if component) / len(components)
    deduplicated_failures = tuple(dict.fromkeys(failures))
    assert set(deduplicated_failures) <= SAFE_FAILURE_REASONS
    return EvaluationScore(
        score=score,
        passed=all(components),
        outcome_correct=outcome_correct,
        execution_correct=execution_correct,
        tables_correct=tables_correct,
        result_correct=result_correct,
        expected_row_count=len(expected_rows),
        actual_row_count=len(actual_rows),
        failure_reasons=deduplicated_failures,
    )


def _compare_rows(
    case: EvaluationCase,
    expected_rows: Sequence[Mapping[str, Any]],
    actual_rows: Sequence[Mapping[str, Any]],
) -> tuple[bool, str | None]:
    if len(expected_rows) != len(actual_rows):
        return False, "row_count_mismatch"
    try:
        expected = [_select_row_values(case, row) for row in expected_rows]
        actual = [_select_row_values(case, row) for row in actual_rows]
    except KeyError:
        return False, "missing_stable_key"
    except (InvalidOperation, ValueError, OverflowError):
        return False, "invalid_numeric_value"

    tolerance = case.numeric_tolerance
    if case.comparison_mode is ComparisonMode.ORDERED_ROWS:
        matches = all(
            _rows_equal(expected_row, actual_row, tolerance)
            for expected_row, actual_row in zip(expected, actual, strict=True)
        )
    elif case.comparison_mode in {
        ComparisonMode.UNORDERED_ROWS,
        ComparisonMode.GROUPED_ROWS,
        ComparisonMode.STABLE_KEYS,
    }:
        matches = _unordered_rows_equal(expected, actual, tolerance)
    else:
        matches = True
    return (True, None) if matches else (False, "result_semantics_mismatch")


def _select_row_values(case: EvaluationCase, row: Mapping[str, Any]) -> dict[str, Any]:
    if case.comparison_mode is ComparisonMode.STABLE_KEYS:
        return {key: _normalize_value(row[key]) for key in case.stable_key_columns}
    return {str(key): _normalize_value(value) for key, value in sorted(row.items())}


def _unordered_rows_equal(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    tolerance: Decimal | None,
) -> bool:
    unmatched = list(actual)
    for expected_row in expected:
        match_index = next(
            (
                index
                for index, actual_row in enumerate(unmatched)
                if _rows_equal(expected_row, actual_row, tolerance)
            ),
            None,
        )
        if match_index is None:
            return False
        unmatched.pop(match_index)
    return not unmatched


def _rows_equal(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    tolerance: Decimal | None,
) -> bool:
    if set(expected) != set(actual):
        return False
    return all(
        _values_equal(expected[key], actual[key], tolerance) for key in expected
    )


def _values_equal(expected: Any, actual: Any, tolerance: Decimal | None) -> bool:
    if isinstance(expected, Decimal) and isinstance(actual, Decimal):
        if tolerance is None:
            return expected == actual
        return abs(expected - actual) <= tolerance
    return expected == actual


def _normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value).lower()
    if isinstance(value, datetime):
        normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return normalized.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise InvalidOperation
        return value.normalize()
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numeric value")
        return Decimal(str(value)).normalize()
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return tuple(_normalize_value(item) for item in value)
    return value
