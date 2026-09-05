"""Internal structural semantics; neither a provider schema nor an execution gate.

Existing plan primitives are reused without moving or changing their definitions.
No production plan, grounding, or rendering path imports this module.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from app.query_engine.semantic_plan import (
    Identifier,
    MAX_PLAN_ITEMS,
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticOrderIntent,
)


T = TypeVar("T")


class StructuralModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class StructuralValue(StructuralModel, Generic[T]):
    """Known empty values are meaningful; unknown and unspecified have no value.

    Unknown means the source cannot establish the structure. Unspecified means
    the source makes no declaration for that component. Neither means empty.
    Enforcement belongs exclusively to the separate comparison policy.
    """

    state: Literal["known", "unknown", "unspecified"]
    value: T | None = None

    @model_validator(mode="after")
    def validate_presence(self) -> StructuralValue[T]:
        if (self.state == "known") != (self.value is not None):
            raise ValueError("Structural value and presence are inconsistent")
        if isinstance(self.value, tuple) and len(self.value) > MAX_PLAN_ITEMS:
            raise ValueError("Structural collection exceeds the item limit")
        return self


def known(value: T) -> StructuralValue[T]:
    return StructuralValue[T](state="known", value=value)


def unknown() -> StructuralValue:
    return StructuralValue(state="unknown")


def unspecified() -> StructuralValue:
    return StructuralValue(state="unspecified")


class StructuralRowGrain(StructuralModel):
    mode: Literal["detail", "grouped", "scalar"]
    identity_fields: StructuralValue[tuple[SemanticFieldRef, ...]]

    @model_validator(mode="after")
    def validate_identity(self) -> StructuralRowGrain:
        fields = self.identity_fields.value
        if self.mode == "scalar" and (
            self.identity_fields.state != "known" or fields != ()
        ):
            raise ValueError("Scalar grain has an explicitly empty identity")
        return self


class StructuralHaving(StructuralModel):
    aggregation_id: Identifier
    operator: Literal[
        "equals",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
    ]
    value: Decimal

    @model_validator(mode="after")
    def validate_number(self) -> StructuralHaving:
        if not self.value.is_finite():
            raise ValueError("HAVING threshold must be finite")
        return self


class StructuralResultIntent(StructuralModel):
    """Alias-addressable structural declarations, without matching policy.

    output_fields describes non-aggregate outputs. Aggregations carry their own
    local IDs, used only to resolve HAVING/ordering references, not equivalence.
    Named-metric observations have scalar grain and known empty aggregate
    declarations. Their implicit expression is not synthesized here.
    """

    row_grain: StructuralValue[StructuralRowGrain]
    output_fields: StructuralValue[tuple[SemanticFieldRef, ...]]
    aggregations: StructuralValue[tuple[SemanticAggregationIntent, ...]]
    group_by: StructuralValue[tuple[SemanticFieldRef, ...]]
    having: StructuralValue[tuple[StructuralHaving, ...]]
    ordering: StructuralValue[tuple[SemanticOrderIntent, ...]]
    distinct: StructuralValue[bool]

    @model_validator(mode="after")
    def validate_references(self) -> StructuralResultIntent:
        aggregations = self.aggregations.value or ()
        ids = {item.id for item in aggregations}
        if len(ids) != len(aggregations):
            raise ValueError("Aggregation IDs must be unique")
        references: list[str | None] = [
            item.aggregation_id for item in self.having.value or ()
        ]
        references.extend(
            item.aggregation_id
            for item in self.ordering.value or ()
            if item.target_kind == "aggregation"
        )
        if any(reference not in ids for reference in references):
            raise ValueError("Structural reference has no declared aggregation")
        return self


def empty_structural_intent() -> StructuralResultIntent:
    """No declarations, not a declaration of an empty result."""
    return StructuralResultIntent(
        row_grain=unspecified(),
        output_fields=unspecified(),
        aggregations=unspecified(),
        group_by=unspecified(),
        having=unspecified(),
        ordering=unspecified(),
        distinct=unspecified(),
    )
