from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.evaluation.contracts import (
    ActualOutcome,
    CanonicalExpressionIdentity,
    ComparisonMode,
    EvaluationCase,
    EvaluationComparisonProvenance,
    EvaluationOutputProvenance,
    EvaluationQueryProvenance,
    ExpectedOutcome,
    ProvenanceAuthorizationEvidence,
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
SAFE_SEMANTIC_FAILURE_REASONS = frozenset(
    {
        "required_concept_missing",
        "required_metric_mismatch",
        "required_rule_missing",
        "result_grain_mismatch",
        "required_output_missing",
        "aggregation_mismatch",
        "group_by_mismatch",
        "having_mismatch",
        "ordering_mismatch",
    }
)
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_MAX_PLAN_ITEMS = 64
_FieldKey = tuple[str, str]
_AggregationKey = tuple[str, _FieldKey | None, bool]
_OrderKey = tuple[str, _FieldKey | _AggregationKey, str]


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


@dataclass(frozen=True)
class EvaluationSemanticScore:
    evaluated: bool
    passed: bool | None
    concepts_correct: bool | None
    metric_correct: bool | None
    rules_correct: bool | None
    grain_correct: bool | None
    outputs_correct: bool | None
    aggregations_correct: bool | None
    group_by_correct: bool | None
    having_correct: bool | None
    ordering_correct: bool | None
    failure_reasons: tuple[str, ...]

    def as_safe_metrics(self) -> dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "passed": self.passed,
            "concepts_correct": self.concepts_correct,
            "metric_correct": self.metric_correct,
            "rules_correct": self.rules_correct,
            "grain_correct": self.grain_correct,
            "outputs_correct": self.outputs_correct,
            "aggregations_correct": self.aggregations_correct,
            "group_by_correct": self.group_by_correct,
            "having_correct": self.having_correct,
            "ordering_correct": self.ordering_correct,
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass(frozen=True)
class _PlanContractObservation:
    effective_concept_ids: frozenset[str]
    composition_rule_ids: frozenset[str]
    metric_id: str | None
    output_fields: frozenset[_FieldKey]
    aggregations_by_id: Mapping[str, _AggregationKey]
    group_by: frozenset[_FieldKey]
    having: frozenset[tuple[_AggregationKey, str, Decimal]]
    ordering: tuple[_OrderKey, ...]


def score_evaluation_semantic_contract(
    case: EvaluationCase,
    plan_observation: Mapping[str, Any] | None,
) -> EvaluationSemanticScore:
    """Score only V2 binding semantics from a validated bounded plan observation."""
    contract = case.semantic_contract
    if contract is None or case.expected_outcome is not ExpectedOutcome.SUCCESS:
        return _semantic_not_evaluated()
    plan = _parse_plan_contract_observation(plan_observation)
    if plan is None:
        return _semantic_not_evaluated()

    required_concepts = set(contract.required_concept_ids)
    concepts_correct = required_concepts <= plan.effective_concept_ids
    metric_correct = (
        contract.required_metric_id is None
        or contract.required_metric_id == plan.metric_id
    )
    rules_correct = set(contract.required_composition_rule_ids) <= (
        plan.composition_rule_ids
    )
    expected_outputs = {
        (item.entity_id, item.column) for item in contract.output_fields
    }
    outputs_correct = expected_outputs <= plan.output_fields
    expected_group_by = {
        (item.entity_id, item.column) for item in contract.group_by
    }
    group_by_correct = (
        expected_group_by == plan.group_by if expected_group_by else True
    )
    expected_grain = {
        (item.entity_id, item.column) for item in contract.grain_fields
    }
    if expected_group_by:
        grain_correct = expected_grain == plan.group_by
    elif expected_grain:
        grain_correct = (
            not plan.aggregations_by_id
            and not plan.group_by
            and expected_grain <= plan.output_fields
        )
    else:
        grain_correct = True

    expected_aggregations = {
        item.id: (
            item.function,
            (
                (item.field.entity_id, item.field.column)
                if item.field is not None
                else None
            ),
            item.distinct,
        )
        for item in contract.aggregations
    }
    actual_aggregation_keys = set(plan.aggregations_by_id.values())
    aggregations_correct = set(expected_aggregations.values()) <= (
        actual_aggregation_keys
    )

    expected_having = {
        (
            expected_aggregations[item.aggregation_id],
            item.operator,
            item.value,
        )
        for item in contract.having
    }
    having_correct = expected_having <= plan.having
    expected_ordering = tuple(
        _expected_order_key(item, expected_aggregations)
        for item in contract.ordering
    )
    ordering_correct = plan.ordering[: len(expected_ordering)] == expected_ordering

    components = (
        ("required_concept_missing", concepts_correct),
        ("required_metric_mismatch", metric_correct),
        ("required_rule_missing", rules_correct),
        ("result_grain_mismatch", grain_correct),
        ("required_output_missing", outputs_correct),
        ("aggregation_mismatch", aggregations_correct),
        ("group_by_mismatch", group_by_correct),
        ("having_mismatch", having_correct),
        ("ordering_mismatch", ordering_correct),
    )
    failures = tuple(reason for reason, passed in components if not passed)
    assert set(failures) <= SAFE_SEMANTIC_FAILURE_REASONS
    return EvaluationSemanticScore(
        evaluated=True,
        passed=not failures,
        concepts_correct=concepts_correct,
        metric_correct=metric_correct,
        rules_correct=rules_correct,
        grain_correct=grain_correct,
        outputs_correct=outputs_correct,
        aggregations_correct=aggregations_correct,
        group_by_correct=group_by_correct,
        having_correct=having_correct,
        ordering_correct=ordering_correct,
        failure_reasons=failures,
    )


def _semantic_not_evaluated() -> EvaluationSemanticScore:
    return EvaluationSemanticScore(
        evaluated=False,
        passed=None,
        concepts_correct=None,
        metric_correct=None,
        rules_correct=None,
        grain_correct=None,
        outputs_correct=None,
        aggregations_correct=None,
        group_by_correct=None,
        having_correct=None,
        ordering_correct=None,
        failure_reasons=(),
    )


def _expected_order_key(
    item: Any,
    aggregations: Mapping[str, _AggregationKey],
) -> _OrderKey:
    if item.target_kind == "field":
        assert item.field is not None
        return (
            "field",
            (item.field.entity_id, item.field.column),
            item.direction,
        )
    assert item.aggregation_id is not None
    return (
        "aggregation",
        aggregations[item.aggregation_id],
        item.direction,
    )


def _parse_plan_contract_observation(
    value: Mapping[str, Any] | None,
) -> _PlanContractObservation | None:
    if not isinstance(value, Mapping):
        return None
    effective_concepts = _safe_identifier_set(value.get("effective_concept_ids"))
    rules = _safe_identifier_set(value.get("composition_rule_ids"))
    metric_id = value.get("metric_id")
    output_fields = _safe_field_set(value.get("output_fields"))
    group_by = _safe_field_set(value.get("group_by"))
    if (
        effective_concepts is None
        or rules is None
        or output_fields is None
        or group_by is None
        or (
            metric_id is not None
            and (
                not isinstance(metric_id, str)
                or _SAFE_IDENTIFIER.fullmatch(metric_id) is None
            )
        )
    ):
        return None
    aggregations = _safe_aggregations(value.get("aggregations"))
    if aggregations is None:
        return None
    having = _safe_having(value.get("having"), aggregations)
    ordering = _safe_ordering(value.get("order_by"), aggregations)
    if having is None or ordering is None:
        return None
    return _PlanContractObservation(
        effective_concept_ids=effective_concepts,
        composition_rule_ids=rules,
        metric_id=metric_id,
        output_fields=output_fields,
        aggregations_by_id=aggregations,
        group_by=group_by,
        having=having,
        ordering=ordering,
    )


def _safe_identifier_set(value: Any) -> frozenset[str] | None:
    if not isinstance(value, list) or len(value) > _MAX_PLAN_ITEMS:
        return None
    if any(
        not isinstance(item, str) or _SAFE_IDENTIFIER.fullmatch(item) is None
        for item in value
    ):
        return None
    if len(value) != len(set(value)):
        return None
    return frozenset(value)


def _safe_field(value: Any) -> _FieldKey | None:
    if not isinstance(value, Mapping) or set(value) != {"entity_id", "column"}:
        return None
    entity_id = value.get("entity_id")
    column = value.get("column")
    if (
        not isinstance(entity_id, str)
        or _SAFE_IDENTIFIER.fullmatch(entity_id) is None
        or not isinstance(column, str)
        or _SAFE_IDENTIFIER.fullmatch(column) is None
    ):
        return None
    return entity_id, column


def _safe_field_set(value: Any) -> frozenset[_FieldKey] | None:
    if not isinstance(value, list) or len(value) > _MAX_PLAN_ITEMS:
        return None
    fields = tuple(_safe_field(item) for item in value)
    if any(item is None for item in fields):
        return None
    safe_fields = tuple(item for item in fields if item is not None)
    if len(safe_fields) != len(set(safe_fields)):
        return None
    return frozenset(safe_fields)


def _safe_aggregations(value: Any) -> dict[str, _AggregationKey] | None:
    if not isinstance(value, list) or len(value) > _MAX_PLAN_ITEMS:
        return None
    aggregations: dict[str, _AggregationKey] = {}
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "id",
            "function",
            "field",
            "distinct",
        }:
            return None
        aggregation_id = item.get("id")
        function = item.get("function")
        distinct = item.get("distinct")
        target = None if item.get("field") is None else _safe_field(item.get("field"))
        if (
            not isinstance(aggregation_id, str)
            or _SAFE_IDENTIFIER.fullmatch(aggregation_id) is None
            or aggregation_id in aggregations
            or function not in {"count", "sum"}
            or not isinstance(distinct, bool)
            or (item.get("field") is not None and target is None)
            or (function == "sum" and target is None)
        ):
            return None
        aggregations[aggregation_id] = (function, target, distinct)
    return aggregations


def _safe_having(
    value: Any,
    aggregations: Mapping[str, _AggregationKey],
) -> frozenset[tuple[_AggregationKey, str, Decimal]] | None:
    if not isinstance(value, list) or len(value) > _MAX_PLAN_ITEMS:
        return None
    safe: set[tuple[_AggregationKey, str, Decimal]] = set()
    operators = {
        "equals",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
    }
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "aggregation_id",
            "operator",
            "value",
        }:
            return None
        aggregation_id = item.get("aggregation_id")
        operator = item.get("operator")
        raw_number = item.get("value")
        if (
            not isinstance(aggregation_id, str)
            or aggregation_id not in aggregations
            or operator not in operators
            or isinstance(raw_number, bool)
            or not isinstance(raw_number, (int, float))
        ):
            return None
        number = Decimal(str(raw_number))
        if not number.is_finite():
            return None
        safe.add((aggregations[aggregation_id], str(operator), number))
    return frozenset(safe)


def _safe_ordering(
    value: Any,
    aggregations: Mapping[str, _AggregationKey],
) -> tuple[_OrderKey, ...] | None:
    if not isinstance(value, list) or len(value) > _MAX_PLAN_ITEMS:
        return None
    ordering: list[_OrderKey] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "target_kind",
            "field",
            "aggregation_id",
            "direction",
        }:
            return None
        target_kind = item.get("target_kind")
        direction = item.get("direction")
        if direction not in {"asc", "desc"}:
            return None
        if target_kind == "field":
            target = _safe_field(item.get("field"))
            if target is None or item.get("aggregation_id") is not None:
                return None
            ordering.append(("field", target, str(direction)))
        elif target_kind == "aggregation":
            aggregation_id = item.get("aggregation_id")
            if (
                item.get("field") is not None
                or not isinstance(aggregation_id, str)
                or aggregation_id not in aggregations
            ):
                return None
            ordering.append(
                ("aggregation", aggregations[aggregation_id], str(direction))
            )
        else:
            return None
    return tuple(ordering)


def score_evaluation_case(
    case: EvaluationCase,
    *,
    actual_outcome: ExpectedOutcome | ActualOutcome,
    execution_succeeded: bool,
    actual_referenced_tables: Sequence[str] = (),
    expected_rows: Sequence[Mapping[str, Any]] = (),
    actual_rows: Sequence[Mapping[str, Any]] = (),
    provenance: EvaluationComparisonProvenance | None = None,
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
        result_correct, result_failure = _compare_rows(
            case,
            expected_rows,
            actual_rows,
            provenance,
        )
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
    provenance: EvaluationComparisonProvenance | None,
) -> tuple[bool, str | None]:
    if len(expected_rows) != len(actual_rows):
        return False, "row_count_mismatch"
    try:
        canonical_rows = _canonicalize_rows(
            case,
            expected_rows,
            actual_rows,
            provenance,
        )
    except _ProvenanceComparisonFailure as exc:
        return False, exc.reason
    except (InvalidOperation, ValueError, OverflowError):
        return False, "invalid_numeric_value"
    if canonical_rows is not None:
        expected, actual = canonical_rows
        return _compare_normalized_rows(case, expected, actual)
    alias_insensitive_aggregate = _compare_single_grouped_aggregate(
        case,
        expected_rows,
        actual_rows,
    )
    if alias_insensitive_aggregate is not None:
        return (
            (True, None)
            if alias_insensitive_aggregate
            else (False, "result_semantics_mismatch")
        )
    try:
        expected = [_select_row_values(case, row) for row in expected_rows]
        actual = [_select_row_values(case, row) for row in actual_rows]
    except KeyError:
        return False, "missing_stable_key"
    except (InvalidOperation, ValueError, OverflowError):
        return False, "invalid_numeric_value"

    return _compare_normalized_rows(case, expected, actual)


def _compare_normalized_rows(
    case: EvaluationCase,
    expected: list[dict[Any, Any]],
    actual: list[dict[Any, Any]],
) -> tuple[bool, str | None]:
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


class _ProvenanceComparisonFailure(ValueError):
    def __init__(self, reason: str = "result_semantics_mismatch") -> None:
        super().__init__("Result provenance is inconsistent.")
        self.reason = reason


def _canonicalize_rows(
    case: EvaluationCase,
    expected_rows: Sequence[Mapping[str, Any]],
    actual_rows: Sequence[Mapping[str, Any]],
    provenance: EvaluationComparisonProvenance | None,
) -> tuple[list[dict[Any, Any]], list[dict[Any, Any]]] | None:
    if provenance is None or provenance.expected is None or provenance.actual is None:
        return None
    expected_provenance = provenance.expected
    actual_provenance = provenance.actual
    _require_unique_provenance(expected_provenance)
    _require_unique_provenance(actual_provenance)
    _require_rows_match_provenance(expected_rows, expected_provenance)
    _require_rows_match_provenance(actual_rows, actual_provenance)
    if case.comparison_mode is ComparisonMode.STABLE_KEYS:
        return _canonicalize_stable_keys(
            case,
            expected_rows,
            actual_rows,
            expected_provenance,
            actual_provenance,
        )
    if case.comparison_mode not in {
        ComparisonMode.GROUPED_ROWS,
        ComparisonMode.ORDERED_ROWS,
        ComparisonMode.UNORDERED_ROWS,
    }:
        return None
    if expected_provenance.row_grain != actual_provenance.row_grain:
        raise _ProvenanceComparisonFailure()
    return _canonicalize_tabular_rows(
        case,
        expected_rows,
        actual_rows,
        expected_provenance,
        actual_provenance,
    )


def _canonicalize_stable_keys(
    case: EvaluationCase,
    expected_rows: Sequence[Mapping[str, Any]],
    actual_rows: Sequence[Mapping[str, Any]],
    expected_provenance: EvaluationQueryProvenance,
    actual_provenance: EvaluationQueryProvenance,
) -> tuple[list[dict[Any, Any]], list[dict[Any, Any]]]:
    expected_by_name = {
        output.presentation_name: output for output in expected_provenance.outputs
    }
    actual_by_identity = _outputs_by_identity(actual_provenance.outputs)
    matches: list[tuple[EvaluationOutputProvenance, EvaluationOutputProvenance]] = []
    seen_identities: set[CanonicalExpressionIdentity] = set()
    for stable_key in case.stable_key_columns:
        expected_output = expected_by_name.get(stable_key)
        if (
            expected_output is None
            or expected_output.identity.kind != "field"
            or expected_output.identity in seen_identities
        ):
            raise _ProvenanceComparisonFailure("missing_stable_key")
        actual_candidates = actual_by_identity.get(expected_output.identity, ())
        if len(actual_candidates) != 1:
            raise _ProvenanceComparisonFailure("missing_stable_key")
        seen_identities.add(expected_output.identity)
        matches.append((expected_output, actual_candidates[0]))
    return (
        _project_rows(expected_rows, matches, side="expected"),
        _project_rows(actual_rows, matches, side="actual"),
    )


def _canonicalize_tabular_rows(
    case: EvaluationCase,
    expected_rows: Sequence[Mapping[str, Any]],
    actual_rows: Sequence[Mapping[str, Any]],
    expected_provenance: EvaluationQueryProvenance,
    actual_provenance: EvaluationQueryProvenance,
) -> tuple[list[dict[Any, Any]], list[dict[Any, Any]]]:
    expected_by_identity = _outputs_by_identity(expected_provenance.outputs)
    actual_by_identity = _outputs_by_identity(actual_provenance.outputs)
    actual_by_name = {
        output.presentation_name: output for output in actual_provenance.outputs
    }
    matches: list[tuple[EvaluationOutputProvenance, EvaluationOutputProvenance]] = []
    matched_actual_names: set[str] = set()
    for expected_output in expected_provenance.outputs:
        if expected_output.identity.kind == "aggregation":
            candidates = actual_by_identity.get(expected_output.identity, ())
        else:
            candidate = actual_by_name.get(expected_output.presentation_name)
            if candidate is not None:
                candidates = (
                    (candidate,) if candidate.identity == expected_output.identity else ()
                )
            else:
                candidates = _canonical_field_alias_candidates(
                    expected_output,
                    expected_by_identity,
                    actual_by_identity,
                    expected_provenance,
                    actual_provenance,
                )
        if len(candidates) != 1:
            raise _ProvenanceComparisonFailure()
        actual_output = candidates[0]
        if actual_output.presentation_name in matched_actual_names:
            raise _ProvenanceComparisonFailure()
        matched_actual_names.add(actual_output.presentation_name)
        matches.append((expected_output, actual_output))

    extras = tuple(
        output
        for output in actual_provenance.outputs
        if output.presentation_name not in matched_actual_names
    )
    if extras:
        if case.comparison_mode is not ComparisonMode.UNORDERED_ROWS or any(
            output.authorized is not True for output in extras
        ):
            raise _ProvenanceComparisonFailure()

    expected = _project_rows(expected_rows, matches, side="expected")
    actual = _project_rows(actual_rows, matches, side="actual")
    if extras and _projection_collapses_distinct_rows(actual_rows, actual):
        raise _ProvenanceComparisonFailure()
    return expected, actual


def _canonical_field_alias_candidates(
    expected_output: EvaluationOutputProvenance,
    expected_by_identity: Mapping[
        CanonicalExpressionIdentity,
        tuple[EvaluationOutputProvenance, ...],
    ],
    actual_by_identity: Mapping[
        CanonicalExpressionIdentity,
        tuple[EvaluationOutputProvenance, ...],
    ],
    expected_provenance: EvaluationQueryProvenance,
    actual_provenance: EvaluationQueryProvenance,
) -> tuple[EvaluationOutputProvenance, ...]:
    if (
        expected_output.identity.kind != "field"
        or expected_output.authorized is not True
        or not _has_validated_provenance(expected_provenance)
        or not _has_validated_provenance(actual_provenance)
    ):
        return ()
    expected_candidates = expected_by_identity.get(expected_output.identity, ())
    actual_candidates = actual_by_identity.get(expected_output.identity, ())
    if (
        len(expected_candidates) != 1
        or len(actual_candidates) != 1
        or actual_candidates[0].identity.kind != "field"
        or actual_candidates[0].authorized is not True
    ):
        return ()
    return actual_candidates


def _has_validated_provenance(provenance: EvaluationQueryProvenance) -> bool:
    return provenance.authorization_evidence in {
        ProvenanceAuthorizationEvidence.FROZEN_BASELINE_VALIDATED,
        ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED,
    }


def _require_unique_provenance(provenance: EvaluationQueryProvenance) -> None:
    names = [output.presentation_name for output in provenance.outputs]
    if len(names) != len(set(names)):
        raise _ProvenanceComparisonFailure()


def _require_rows_match_provenance(
    rows: Sequence[Mapping[str, Any]],
    provenance: EvaluationQueryProvenance,
) -> None:
    names = {output.presentation_name for output in provenance.outputs}
    if any(set(row) != names for row in rows):
        raise _ProvenanceComparisonFailure()


def _outputs_by_identity(
    outputs: Sequence[EvaluationOutputProvenance],
) -> dict[CanonicalExpressionIdentity, tuple[EvaluationOutputProvenance, ...]]:
    grouped: dict[
        CanonicalExpressionIdentity,
        list[EvaluationOutputProvenance],
    ] = {}
    for output in outputs:
        grouped.setdefault(output.identity, []).append(output)
    return {identity: tuple(items) for identity, items in grouped.items()}


def _project_rows(
    rows: Sequence[Mapping[str, Any]],
    matches: Sequence[tuple[EvaluationOutputProvenance, EvaluationOutputProvenance]],
    *,
    side: str,
) -> list[dict[Any, Any]]:
    projected: list[dict[Any, Any]] = []
    for row in rows:
        projected_row: dict[Any, Any] = {}
        for expected_output, actual_output in matches:
            source = expected_output if side == "expected" else actual_output
            projected_row[expected_output.identity] = _normalize_value(
                row[source.presentation_name]
            )
        projected.append(projected_row)
    return projected


def _projection_collapses_distinct_rows(
    actual_rows: Sequence[Mapping[str, Any]],
    projected_rows: Sequence[Mapping[Any, Any]],
) -> bool:
    full_signatures = {
        _mapping_signature(
            {str(key): _normalize_value(value) for key, value in row.items()}
        )
        for row in actual_rows
    }
    projected_signatures = {_mapping_signature(row) for row in projected_rows}
    return len(projected_signatures) < len(full_signatures)


def _mapping_signature(row: Mapping[Any, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(
        sorted(
            (
                _signature_key(key),
                _freeze_signature_value(value),
            )
            for key, value in row.items()
        )
    )


def _signature_key(key: Any) -> str:
    if isinstance(key, CanonicalExpressionIdentity):
        return repr(key.as_safe_dict())
    return str(key)


def _freeze_signature_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(
            sorted(
                (str(key), _freeze_signature_value(item))
                for key, item in value.items()
            )
        )
    if isinstance(value, tuple):
        return tuple(_freeze_signature_value(item) for item in value)
    return value


def _compare_single_grouped_aggregate(
    case: EvaluationCase,
    expected_rows: Sequence[Mapping[str, Any]],
    actual_rows: Sequence[Mapping[str, Any]],
) -> bool | None:
    """Ignore only a harmless alias on a one-row, one-value grouped aggregate."""
    if (
        case.comparison_mode is not ComparisonMode.GROUPED_ROWS
        or len(expected_rows) != 1
        or len(actual_rows) != 1
        or len(expected_rows[0]) != 1
        or len(actual_rows[0]) != 1
    ):
        return None
    try:
        expected_value = _normalize_value(next(iter(expected_rows[0].values())))
        actual_value = _normalize_value(next(iter(actual_rows[0].values())))
    except (InvalidOperation, ValueError, OverflowError):
        return False
    return _values_equal(expected_value, actual_value, case.numeric_tolerance)


def _select_row_values(case: EvaluationCase, row: Mapping[str, Any]) -> dict[str, Any]:
    if case.comparison_mode is ComparisonMode.STABLE_KEYS:
        return {key: _normalize_value(row[key]) for key in case.stable_key_columns}
    return {str(key): _normalize_value(value) for key, value in sorted(row.items())}


def _unordered_rows_equal(
    expected: list[dict[Any, Any]],
    actual: list[dict[Any, Any]],
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
    expected: Mapping[Any, Any],
    actual: Mapping[Any, Any],
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
