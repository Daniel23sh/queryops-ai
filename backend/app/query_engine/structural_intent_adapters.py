"""Pure adapters. Callers supply catalog identity, never execution authority."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from app.query_engine.result_intent import GroundedFieldIdentity, GroundedResultIntent
from app.query_engine.semantic_catalog import SemanticCatalog
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent,
    SemanticFieldRef,
    ValidatedSemanticPlan,
)
from app.query_engine.structural_intent import (
    StructuralHaving,
    StructuralResultIntent,
    StructuralRowGrain,
    empty_structural_intent,
    known,
    unknown,
    unspecified,
)
from app.query_engine.structural_intent_comparison import (
    StructuralComparisonPolicy,
    StructuralRequirement,
)


class StructuralMappingError(ValueError):
    """Bounded error: never echoes a supplied table, column, or payload."""


def grounded_to_structural_requirement(
    intent: GroundedResultIntent | None,
    catalog: SemanticCatalog,
    *,
    binding: Literal["required", "suggested"],
) -> StructuralRequirement:
    if intent is None:
        return StructuralRequirement(
            intent=empty_structural_intent(),
            policy=StructuralComparisonPolicy(),
            binding=binding,
        )
    entities: dict[str, list[str]] = {}
    for entity in catalog.entities:
        entities.setdefault(entity.table, []).append(entity.id)

    def field(item: GroundedFieldIdentity) -> SemanticFieldRef:
        candidates = entities.get(item.table, [])
        if len(candidates) != 1:
            raise StructuralMappingError(
                "Structural entity mapping is missing or ambiguous"
            )
        return SemanticFieldRef(entity_id=candidates[0], column=item.column)

    grain = intent.row_grain
    structural = StructuralResultIntent(
        row_grain=(
            known(
                StructuralRowGrain(
                    mode=grain.mode,
                    identity_fields=known(
                        tuple(field(item) for item in grain.identity_fields)
                    ),
                )
            )
            if grain is not None
            else unspecified()
        ),
        output_fields=(
            known(tuple(field(item) for item in intent.required_output_fields))
            if intent.required_output_fields
            else unspecified()
        ),
        aggregations=(
            known(
                tuple(
                    SemanticAggregationIntent(
                        id=item.id,
                        function=item.function,
                        field=field(item.target_field)
                        if item.target_field is not None
                        else None,
                        distinct=item.distinct,
                    )
                    for item in intent.aggregations
                )
            )
            if intent.aggregations
            else unspecified()
        ),
        group_by=(
            known(tuple(field(item) for item in intent.group_by))
            if intent.group_by
            else unspecified()
        ),
        having=(
            known(
                tuple(
                    StructuralHaving(
                        aggregation_id=item.aggregation_id,
                        operator=item.operator,
                        value=Decimal(str(item.value)),
                    )
                    for item in intent.having
                )
            )
            if intent.having
            else unspecified()
        ),
        ordering=unspecified(),
        distinct=known(intent.distinct)
        if intent.distinct is not None
        else unspecified(),
    )
    policy = StructuralComparisonPolicy(
        row_grain=("required_subset" if grain.mode == "detail" else "exact")
        if grain
        else "ignored",
        output_fields="required_subset" if intent.required_output_fields else "ignored",
        aggregations="exact" if intent.aggregations else "ignored",
        group_by="exact" if intent.group_by else "ignored",
        having="exact" if intent.having else "ignored",
        distinct="exact" if intent.distinct is not None else "ignored",
    )
    return StructuralRequirement(intent=structural, policy=policy, binding=binding)


def validated_plan_to_structural_observation(
    validated: ValidatedSemanticPlan,
) -> StructuralResultIntent:
    if not isinstance(validated, ValidatedSemanticPlan):
        raise TypeError("A validated semantic plan is required")
    plan = validated.plan
    if plan.group_by:
        grain = StructuralRowGrain(mode="grouped", identity_fields=known(plan.group_by))
    elif plan.aggregations or plan.metric_id is not None:
        grain = StructuralRowGrain(mode="scalar", identity_fields=known(()))
    else:
        grain = StructuralRowGrain(mode="detail", identity_fields=unknown())
    return StructuralResultIntent(
        row_grain=known(grain),
        output_fields=known(plan.output_fields),
        aggregations=known(plan.aggregations),
        group_by=known(plan.group_by),
        having=known(
            tuple(
                StructuralHaving(
                    aggregation_id=item.aggregation_id,
                    operator=item.operator,
                    value=Decimal(str(item.value)),
                )
                for item in plan.having
            )
        ),
        ordering=known(plan.order_by),
        distinct=known(plan.distinct),
    )
