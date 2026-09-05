"""Opt-in structural comparison; no SQL or relational equivalence rules."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from app.query_engine.structural_intent import (
    StructuralModel,
    StructuralResultIntent,
    StructuralRowGrain,
    StructuralValue,
)


CollectionMatch = Literal["exact", "required_subset", "ordered_prefix", "ignored"]
GrainMatch = Literal["exact", "required_subset", "ignored"]
ComparisonStatus = Literal["match", "mismatch", "unknown", "ignored"]
COMPONENTS = (
    "row_grain",
    "output_fields",
    "aggregations",
    "group_by",
    "having",
    "ordering",
    "distinct",
)


class StructuralComparisonPolicy(StructuralModel):
    row_grain: GrainMatch = "ignored"
    output_fields: CollectionMatch = "ignored"
    aggregations: CollectionMatch = "ignored"
    group_by: CollectionMatch = "ignored"
    having: CollectionMatch = "ignored"
    ordering: CollectionMatch = "ignored"
    distinct: Literal["exact", "ignored"] = "ignored"


class StructuralRequirement(StructuralModel):
    intent: StructuralResultIntent
    policy: StructuralComparisonPolicy
    binding: Literal["required", "suggested"]


@dataclass(frozen=True)
class StructuralComparison:
    components: tuple[tuple[str, ComparisonStatus], ...]

    @property
    def passed(self) -> bool | None:
        statuses = {status for _, status in self.components}
        if "mismatch" in statuses:
            return False
        if "unknown" in statuses or statuses == {"ignored"}:
            return None
        return True


def compare_structural_requirement(
    requirement: StructuralRequirement,
    observation: StructuralResultIntent,
) -> StructuralComparison:
    if requirement.binding != "required":
        raise ValueError("Suggested intent cannot be compared as a requirement")
    results: list[tuple[str, ComparisonStatus]] = []
    for name in COMPONENTS:
        mode = getattr(requirement.policy, name)
        expected = getattr(requirement.intent, name)
        actual = getattr(observation, name)
        presence = _presence_status(expected, actual, mode)
        if presence is not None:
            results.append((name, presence))
            continue
        if name == "row_grain":
            status = _compare_grain(expected.value, actual.value, observation, mode)
        elif name == "distinct":
            status = _status(expected.value == actual.value)
        else:
            left = structural_component_identities(requirement.intent, name)
            right = structural_component_identities(observation, name)
            if mode == "ordered_prefix":
                matches = right[: len(left)] == left
            elif mode == "required_subset":
                matches = set(left) <= set(right)
            elif name == "ordering":
                matches = left == right
            elif name == "aggregations":
                matches = Counter(left) == Counter(right)
            else:
                matches = set(left) == set(right)
            status = _status(matches)
        results.append((name, status))
    return StructuralComparison(tuple(results))


def _presence_status(
    expected: StructuralValue,
    actual: StructuralValue,
    mode: str,
) -> ComparisonStatus | None:
    if mode == "ignored":
        return "ignored"
    if expected.state == "unspecified":
        raise ValueError("Comparison policy enforces an unspecified component")
    if expected.state != "known" or actual.state != "known":
        return "unknown"
    return None


def _compare_grain(
    expected: StructuralRowGrain,
    actual: StructuralRowGrain,
    observation: StructuralResultIntent,
    mode: str,
) -> ComparisonStatus:
    if expected.mode != actual.mode:
        return "mismatch"
    expected_keys = expected.identity_fields
    actual_keys = actual.identity_fields
    # Existing detail contracts require keys to be projected; this is not proof
    # of row uniqueness. Exact identity comparison does not use this shortcut.
    if mode == "required_subset" and expected.mode == "detail":
        actual_keys = observation.output_fields
    presence = _presence_status(expected_keys, actual_keys, mode)
    if presence is not None:
        return presence
    left, right = set(expected_keys.value or ()), set(actual_keys.value or ())
    return _status(left <= right if mode == "required_subset" else left == right)


def structural_component_identities(
    intent: StructuralResultIntent,
    name: str,
) -> tuple:
    """Resolve local aggregation aliases without adding semantic equivalences."""
    aggregates = {
        item.id: (item.function, item.field, item.distinct)
        for item in intent.aggregations.value or ()
    }
    values = getattr(intent, name).value or ()
    if name == "aggregations":
        return tuple(aggregates[item.id] for item in values)
    if name == "having":
        return tuple(
            (aggregates[item.aggregation_id], item.operator, item.value)
            for item in values
        )
    if name == "ordering":
        return tuple(
            (
                item.target_kind,
                item.field
                if item.target_kind == "field"
                else aggregates[item.aggregation_id],
                item.direction,
            )
            for item in values
        )
    return values


def _status(matches: bool) -> ComparisonStatus:
    return "match" if matches else "mismatch"
