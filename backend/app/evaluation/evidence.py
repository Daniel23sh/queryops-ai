"""Governed, evaluator-only evidence for bounded result comparison."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from app.evaluation.contracts import (
    ComparisonState,
    DeliveryCompleteness,
    EvaluationAnswerBound,
)
from app.query_engine.sql_executor import SQLExecutionResult, normalized_json_size
from app.query_engine.sql_validator import (
    SQLValidationOptions,
    SQLValidationResult,
    validate_sql,
)


EVIDENCE_POLICY_ID = "queryops-bounded-result-evidence-v1"
EVIDENCE_ROW_LIMIT = 1_000
EVIDENCE_SQL_LIMIT = EVIDENCE_ROW_LIMIT + 1
EVIDENCE_STATEMENT_TIMEOUT_MS = 5_000
EVIDENCE_TOTAL_TIMEOUT_MS = 10_000
EVIDENCE_PAYLOAD_LIMIT_BYTES = 8 * 1024 * 1024
EVIDENCE_MAX_AUXILIARY_EXECUTIONS = 2
COMPARISON_STATE_VALUES = tuple(state.value for state in ComparisonState)

SAFE_LIMITATION_REASONS = frozenset(
    {
        "bounded_selection_unestablished",
        "comparison_context_unestablished",
        "comparison_proof_unavailable",
        "completeness_evidence_missing",
        "evidence_payload_exceeded",
        "evidence_row_budget_exceeded",
        "evidence_timeout",
        "evidence_execution_failed",
        "evidence_validation_failed",
        "nonsemantic_bound_reached",
        "ranking_tie_unestablished",
        "unsupported_query_shape",
    }
)
ACQUISITION_LIMITATION_REASONS = frozenset(
    {
        "evidence_execution_failed",
        "evidence_row_budget_exceeded",
        "evidence_timeout",
        "evidence_validation_failed",
        "nonsemantic_bound_reached",
        "unsupported_query_shape",
    }
)


def comparison_state_counts(
    states: Sequence[ComparisonState],
) -> dict[str, int]:
    counts = {state: 0 for state in COMPARISON_STATE_VALUES}
    for state in states:
        counts[state.value] += 1
    return counts


def comparison_state_counts_match(
    value: object,
    states: Sequence[ComparisonState],
) -> bool:
    expected = comparison_state_counts(states)
    return bool(
        isinstance(value, Mapping)
        and set(value) == set(expected)
        and all(
            type(value[key]) is int and value[key] == expected[key]
            for key in expected
        )
    )


@dataclass(frozen=True)
class EvaluationEvidenceSide:
    rows: tuple[Mapping[str, Any], ...]
    complete: bool
    limitation_reason: str | None
    delivery_completeness: DeliveryCompleteness
    comparison_eligible: bool = True
    exhausted: bool = False
    observed_execution_count: int = 1
    observed_duration_ms: float = 0.0
    auxiliary_execution_count: int = 0
    auxiliary_duration_ms: float = 0.0


@dataclass(frozen=True)
class EvaluationComparisonEvidence:
    expected: EvaluationEvidenceSide
    actual: EvaluationEvidenceSide
    actual_delivery_completeness: DeliveryCompleteness
    actual_delivery_row_limit: int | None = None
    context_compatible: bool = True

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "policy_id": EVIDENCE_POLICY_ID,
            "budget": {
                "row_limit_per_side": EVIDENCE_ROW_LIMIT,
                "sql_lookahead_limit": EVIDENCE_SQL_LIMIT,
                "statement_timeout_ms": EVIDENCE_STATEMENT_TIMEOUT_MS,
                "total_timeout_ms": EVIDENCE_TOTAL_TIMEOUT_MS,
                "payload_limit_bytes": EVIDENCE_PAYLOAD_LIMIT_BYTES,
                "max_auxiliary_executions": EVIDENCE_MAX_AUXILIARY_EXECUTIONS,
            },
            "expected": _side_safe_dict(self.expected),
            "actual": _side_safe_dict(self.actual),
            "actual_delivery_completeness": self.actual_delivery_completeness.value,
            "actual_delivery_row_limit": self.actual_delivery_row_limit,
            "context_compatible": self.context_compatible,
        }


@dataclass(frozen=True)
class ValidatedComparisonContract:
    comparison_state: ComparisonState
    delivery_completeness: DeliveryCompleteness
    limitation_reason: str | None
    current_policy: bool


def observed_evidence_side(
    rows: Sequence[Mapping[str, Any]],
    validation: SQLValidationResult,
    execution: SQLExecutionResult,
    answer_bound: EvaluationAnswerBound,
) -> EvaluationEvidenceSide:
    exhausted = _execution_exhausted(validation, execution)
    delivery_complete = _executed_answer_is_complete(
        validation, execution, answer_bound, exhausted=exhausted
    )
    comparison_supported = _validation_supports_comparison(validation)
    complete = delivery_complete and comparison_supported
    safety_limited = (
        validation.limit_source in {"safety_added", "safety_clamped"}
        and not delivery_complete
    )
    return EvaluationEvidenceSide(
        rows=tuple(dict(row) for row in rows),
        complete=complete,
        comparison_eligible=comparison_supported,
        exhausted=exhausted if comparison_supported else False,
        limitation_reason=(
            None
            if complete
            else "unsupported_query_shape"
            if not comparison_supported
            else "nonsemantic_bound_reached"
        ),
        delivery_completeness=(
            DeliveryCompleteness.COMPLETE
            if delivery_complete
            else DeliveryCompleteness.SAFETY_LIMITED
            if safety_limited
            else DeliveryCompleteness.UNKNOWN
        ),
        observed_duration_ms=execution.duration_ms,
    )


def auxiliary_evidence_side(
    validation: SQLValidationResult,
    execution: SQLExecutionResult,
    answer_bound: EvaluationAnswerBound,
) -> EvaluationEvidenceSide:
    timed_out = execution.execution_metadata.get("timeout") is True
    if execution.status != "succeeded":
        reason = (
            "evidence_timeout"
            if timed_out
            else "completeness_evidence_missing"
        )
        return EvaluationEvidenceSide(
            rows=(),
            complete=False,
            comparison_eligible=_validation_supports_comparison(validation),
            exhausted=False,
            limitation_reason=reason,
            delivery_completeness=DeliveryCompleteness.UNKNOWN,
            auxiliary_execution_count=1,
            auxiliary_duration_ms=execution.duration_ms,
        )
    payload_limited = execution.execution_metadata.get("payload_limited") is True
    comparison_supported = _validation_supports_comparison(validation)
    exhausted = (
        _execution_exhausted(validation, execution)
        and not payload_limited
        and not timed_out
        and comparison_supported
    )
    complete = _executed_answer_is_complete(
        validation, execution, answer_bound, exhausted=exhausted
    ) and not payload_limited and not timed_out and comparison_supported
    reason = (
        None
        if complete
        else "unsupported_query_shape"
        if not comparison_supported
        else "evidence_timeout"
        if timed_out
        else "evidence_payload_exceeded"
        if payload_limited
        else "evidence_row_budget_exceeded"
        if execution.truncated
        else "nonsemantic_bound_reached"
    )
    return EvaluationEvidenceSide(
        rows=tuple(dict(row) for row in execution.rows),
        complete=complete,
        comparison_eligible=comparison_supported,
        exhausted=exhausted,
        limitation_reason=reason,
        delivery_completeness=(
            DeliveryCompleteness.COMPLETE
            if complete
            else DeliveryCompleteness.UNKNOWN
        ),
        auxiliary_execution_count=1,
        auxiliary_duration_ms=execution.duration_ms,
    )


def build_auxiliary_validation(
    validation: SQLValidationResult,
    schema_context: dict[str, Any],
) -> SQLValidationResult | None:
    """Widen only a proven outer safety limit, then validate the result normally."""
    if (
        not validation.valid
        or validation.sanitized_sql is None
        or validation.limit_source not in {"safety_added", "safety_clamped"}
    ):
        return None
    statement = _validated_select(validation)
    if statement is None or not _validation_supports_comparison(validation):
        return None
    limits = list(statement.find_all(exp.Limit))
    outer_limit = statement.args.get("limit")
    if len(limits) != 1 or outer_limit is None or limits[0] is not outer_limit:
        return None
    limit_expression = outer_limit.expression
    if (
        validation.effective_limit is None
        or not isinstance(limit_expression, exp.Literal)
        or not limit_expression.is_int
        or int(limit_expression.this) != validation.effective_limit
    ):
        return None
    target = (
        EVIDENCE_SQL_LIMIT
        if validation.input_limit is None
        else min(validation.input_limit, EVIDENCE_SQL_LIMIT)
    )
    widened = statement.limit(target, copy=True).sql(dialect="postgres")
    result = validate_sql(
        widened,
        schema_context,
        options=SQLValidationOptions(
            default_limit=EVIDENCE_SQL_LIMIT,
            max_limit=EVIDENCE_SQL_LIMIT,
        ),
    )
    if not result.valid or result.sanitized_sql is None:
        return None
    return replace(
        result,
        input_limit=validation.input_limit,
        effective_limit=target,
        limit_source=validation.limit_source,
    )


def comparison_payload_size(
    expected: Sequence[Mapping[str, Any]],
    actual: Sequence[Mapping[str, Any]],
    *,
    delivered: Sequence[Mapping[str, Any]] | None = None,
    maximum: int | None = None,
) -> int:
    row_sets = (expected, actual) if delivered is None else (expected, actual, delivered)
    size = 2 + max(0, len(row_sets) - 1) + 2 * len(row_sets)
    for rows in row_sets:
        size += max(0, len(rows) - 1)
        for row in rows:
            size += normalized_json_size(
                row,
                maximum=(None if maximum is None else maximum - size),
            )
            if maximum is not None and size > maximum:
                return maximum + 1
    return size


def distinct_delivery_payload_rows(
    actual_evidence: EvaluationEvidenceSide,
    delivered_rows: Sequence[Mapping[str, Any]],
) -> Sequence[Mapping[str, Any]] | None:
    """Include delivery only when auxiliary actual evidence made it a third set."""
    return delivered_rows if actual_evidence.auxiliary_execution_count else None


def is_safe_evidence_summary(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "policy_id",
        "budget",
        "expected",
        "actual",
        "actual_delivery_completeness",
        "actual_delivery_row_limit",
        "context_compatible",
    }:
        return False
    if value.get("policy_id") != EVIDENCE_POLICY_ID or value.get("budget") != {
        "row_limit_per_side": EVIDENCE_ROW_LIMIT,
        "sql_lookahead_limit": EVIDENCE_SQL_LIMIT,
        "statement_timeout_ms": EVIDENCE_STATEMENT_TIMEOUT_MS,
        "total_timeout_ms": EVIDENCE_TOTAL_TIMEOUT_MS,
        "payload_limit_bytes": EVIDENCE_PAYLOAD_LIMIT_BYTES,
        "max_auxiliary_executions": EVIDENCE_MAX_AUXILIARY_EXECUTIONS,
    }:
        return False
    if value.get("actual_delivery_completeness") not in {
        item.value for item in DeliveryCompleteness
    }:
        return False
    if not isinstance(value.get("context_compatible"), bool):
        return False
    delivery_limit = value.get("actual_delivery_row_limit")
    if delivery_limit is not None and (
        not isinstance(delivery_limit, int)
        or isinstance(delivery_limit, bool)
        or delivery_limit < 1
    ):
        return False
    if not all(_safe_side_summary(value.get(side)) for side in ("expected", "actual")):
        return False
    return sum(
        int(value[side]["auxiliary_execution_count"])
        for side in ("expected", "actual")
    ) <= EVIDENCE_MAX_AUXILIARY_EXECUTIONS


def evidence_summary_supports_judgment(
    value: Any,
    comparison_state: ComparisonState,
    delivery_completeness: DeliveryCompleteness,
    limitation_reason: str | None,
) -> bool:
    """Validate the persisted evidence shape and the judgment it claims to support."""
    if not is_safe_evidence_summary(value):
        return False
    assert isinstance(value, Mapping)
    if value["actual_delivery_completeness"] != delivery_completeness.value:
        return False
    delivery_limit = value["actual_delivery_row_limit"]
    if (delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED) is not (
        delivery_limit is not None
    ):
        return False
    if comparison_state is ComparisonState.CORRECT:
        return bool(
            limitation_reason is None
            and value["context_compatible"]
            and value["expected"]["complete"]
            and value["actual"]["complete"]
            and delivery_completeness
            in {DeliveryCompleteness.COMPLETE, DeliveryCompleteness.SAFETY_LIMITED}
            and _auxiliary_duration_ms(value) <= EVIDENCE_TOTAL_TIMEOUT_MS
        )
    if comparison_state is ComparisonState.UNESTABLISHED:
        return bool(
            limitation_reason in SAFE_LIMITATION_REASONS
            and _limitation_is_supported(value, limitation_reason)
        )
    return comparison_state is ComparisonState.INCORRECT


def validate_persisted_comparison_contract(
    metrics: Mapping[str, Any],
    *,
    expects_result: bool,
    execution_succeeded: bool,
    passed: bool,
    allow_legacy: bool = False,
) -> ValidatedComparisonContract | None:
    """Parse the shared comparison contract; consumers own policy and projection."""
    raw_state = metrics.get("comparison_state")
    if raw_state is None and allow_legacy:
        result_correct = metrics.get("result_correct")
        state = (
            ComparisonState.NOT_APPLICABLE
            if not expects_result
            else ComparisonState.CORRECT
            if result_correct is True
            else ComparisonState.INCORRECT
            if result_correct is False
            else ComparisonState.NOT_REACHED
        )
        return ValidatedComparisonContract(
            comparison_state=state,
            delivery_completeness=(
                DeliveryCompleteness.NOT_APPLICABLE
                if not expects_result
                else DeliveryCompleteness.UNKNOWN
            ),
            limitation_reason=None,
            current_policy=False,
        )
    try:
        state = ComparisonState(raw_state)
        delivery = DeliveryCompleteness(metrics.get("delivery_completeness"))
    except (TypeError, ValueError):
        return None
    result_correct = metrics.get("result_correct")
    limitation = metrics.get("comparison_limitation_reason")
    if (
        (state is ComparisonState.UNESTABLISHED) != (limitation is not None)
        or (limitation is not None and limitation not in SAFE_LIMITATION_REASONS)
    ):
        return None
    if expects_result:
        if (
            (execution_succeeded and state is ComparisonState.NOT_REACHED)
            or (not execution_succeeded and state is not ComparisonState.NOT_REACHED)
            or (state is ComparisonState.CORRECT and result_correct is not True)
            or (state is ComparisonState.INCORRECT and result_correct is not False)
            or (
                state in {ComparisonState.UNESTABLISHED, ComparisonState.NOT_REACHED}
                and result_correct is not None
            )
            or state is ComparisonState.NOT_APPLICABLE
            or delivery is DeliveryCompleteness.NOT_APPLICABLE
            or (
                state is ComparisonState.CORRECT
                and delivery
                not in {
                    DeliveryCompleteness.COMPLETE,
                    DeliveryCompleteness.SAFETY_LIMITED,
                }
            )
            or (state is not ComparisonState.CORRECT and passed)
        ):
            return None
    elif (
        result_correct is not None
        or state is not ComparisonState.NOT_APPLICABLE
        or delivery is not DeliveryCompleteness.NOT_APPLICABLE
    ):
        return None
    summary = metrics.get("comparison_evidence")
    if state in {
        ComparisonState.CORRECT,
        ComparisonState.INCORRECT,
        ComparisonState.UNESTABLISHED,
    } and not evidence_summary_supports_judgment(
        summary, state, delivery, limitation
    ):
        return None
    if state in {ComparisonState.NOT_REACHED, ComparisonState.NOT_APPLICABLE} and (
        summary is not None
    ):
        return None
    return ValidatedComparisonContract(
        comparison_state=state,
        delivery_completeness=delivery,
        limitation_reason=limitation,
        current_policy=True,
    )


def _safe_side_summary(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "complete",
        "comparison_eligible",
        "exhausted",
        "limitation_reason",
        "delivery_completeness",
        "row_count",
        "observed_execution_count",
        "observed_duration_ms",
        "auxiliary_execution_count",
        "auxiliary_duration_ms",
    }:
        return False
    reason = value.get("limitation_reason")
    observed_duration = value.get("observed_duration_ms")
    auxiliary_duration = value.get("auxiliary_duration_ms")
    observed_count = value.get("observed_execution_count")
    auxiliary_count = value.get("auxiliary_execution_count")
    return (
        isinstance(value.get("complete"), bool)
        and isinstance(value.get("comparison_eligible"), bool)
        and (not value["complete"] or value["comparison_eligible"])
        and isinstance(value.get("exhausted"), bool)
        and (value["complete"] is (reason is None))
        and (reason is None or reason in SAFE_LIMITATION_REASONS)
        and value.get("delivery_completeness")
        in {item.value for item in DeliveryCompleteness}
        and isinstance(value.get("row_count"), int)
        and not isinstance(value.get("row_count"), bool)
        and 0 <= value["row_count"] <= EVIDENCE_ROW_LIMIT
        and type(observed_count) is int
        and observed_count in {0, 1}
        and isinstance(observed_duration, int | float)
        and not isinstance(observed_duration, bool)
        and math.isfinite(float(observed_duration))
        and 0 <= float(observed_duration)
        and type(auxiliary_count) is int
        and auxiliary_count in {0, 1}
        and isinstance(auxiliary_duration, int | float)
        and not isinstance(auxiliary_duration, bool)
        and math.isfinite(float(auxiliary_duration))
        and 0 <= float(auxiliary_duration)
        and (observed_count == 1 or float(observed_duration) == 0)
        and (auxiliary_count == 1 or float(auxiliary_duration) == 0)
        and (
            not value["complete"]
            or observed_count + auxiliary_count >= 1
        )
        and (value["row_count"] == 0 or observed_count + auxiliary_count >= 1)
        and (
            float(auxiliary_duration) <= EVIDENCE_STATEMENT_TIMEOUT_MS
            or (
                value.get("complete") is False
                and reason == "evidence_timeout"
            )
        )
    )


def _limitation_is_supported(
    value: Mapping[str, Any],
    limitation_reason: str,
) -> bool:
    incomplete_reasons = {
        value[side]["limitation_reason"]
        for side in ("expected", "actual")
        if not value[side]["complete"]
    }
    if limitation_reason in ACQUISITION_LIMITATION_REASONS:
        return limitation_reason in incomplete_reasons
    if limitation_reason == "evidence_payload_exceeded":
        return True
    if limitation_reason in {
        "bounded_selection_unestablished",
        "ranking_tie_unestablished",
    }:
        return not incomplete_reasons
    if limitation_reason == "completeness_evidence_missing":
        return bool(incomplete_reasons) or value["actual_delivery_completeness"] == (
            DeliveryCompleteness.UNKNOWN.value
        )
    if limitation_reason == "comparison_proof_unavailable":
        return bool(
            value["context_compatible"]
            and value["expected"]["comparison_eligible"]
            and value["actual"]["comparison_eligible"]
        )
    return bool(
        limitation_reason == "comparison_context_unestablished"
        and not value["context_compatible"]
    )


def _auxiliary_duration_ms(value: Mapping[str, Any]) -> float:
    return sum(
        float(value[side]["auxiliary_duration_ms"])
        for side in ("expected", "actual")
    )


def _executed_answer_is_complete(
    validation: SQLValidationResult,
    execution: SQLExecutionResult,
    answer_bound: EvaluationAnswerBound,
    *,
    exhausted: bool,
) -> bool:
    if execution.status != "succeeded" or execution.truncated:
        return False
    return (
        exhausted
        and validation.limit_source in {"safety_added", "safety_clamped"}
    ) or (
        answer_bound.limit is not None
        and validation.input_limit == answer_bound.limit
        and validation.effective_limit == answer_bound.limit
    )


def _execution_exhausted(
    validation: SQLValidationResult,
    execution: SQLExecutionResult,
) -> bool:
    return bool(
        execution.status == "succeeded"
        and not execution.truncated
        and validation.effective_limit is not None
        and execution.row_count < validation.effective_limit
    )


def _side_safe_dict(side: EvaluationEvidenceSide) -> dict[str, Any]:
    return {
        "complete": side.complete,
        "comparison_eligible": side.comparison_eligible,
        "exhausted": side.exhausted,
        "limitation_reason": side.limitation_reason,
        "delivery_completeness": side.delivery_completeness.value,
        "row_count": len(side.rows),
        "observed_execution_count": side.observed_execution_count,
        "observed_duration_ms": round(side.observed_duration_ms, 3),
        "auxiliary_execution_count": side.auxiliary_execution_count,
        "auxiliary_duration_ms": round(side.auxiliary_duration_ms, 3),
    }


def _contains_unsupported_comparison_expression(statement: exp.Select) -> bool:
    """Allow only expression functions stable under the shared transaction."""
    stable_types = (
        exp.And,
        exp.Cast,
        exp.Count,
        exp.CurrentDate,
        exp.CurrentTime,
        exp.CurrentTimestamp,
        exp.Or,
        exp.RowNumber,
        exp.Sum,
    )
    for function in statement.find_all(exp.Func):
        if isinstance(function, exp.Anonymous):
            if function.name.lower() != "transaction_timestamp":
                return True
        elif not isinstance(function, stable_types):
            return True
    return False


def _validated_select(validation: SQLValidationResult) -> exp.Select | None:
    if not validation.valid or validation.sanitized_sql is None:
        return None
    try:
        statement = parse_one(validation.sanitized_sql, dialect="postgres")
    except (ParseError, TypeError, ValueError):
        return None
    return statement if isinstance(statement, exp.Select) else None


def _validation_supports_comparison(validation: SQLValidationResult) -> bool:
    statement = _validated_select(validation)
    if statement is None or _contains_unsupported_comparison_expression(statement):
        return False
    outer_limit = statement.args.get("limit")
    return bool(
        statement.args.get("offset") is None
        and all(limit is outer_limit for limit in statement.find_all(exp.Limit))
        and not any(statement.find_all(exp.Offset))
    )
