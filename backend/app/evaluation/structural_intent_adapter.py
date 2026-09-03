"""V2 contract mapping only. Existing scoring and release policy remain owners."""

from __future__ import annotations

from app.evaluation.contracts import EvaluationAnswerability, EvaluationSemanticContract
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticOrderIntent,
)
from app.query_engine.structural_intent import (
    StructuralHaving,
    StructuralResultIntent,
    StructuralRowGrain,
    known,
    unspecified,
)
from app.query_engine.structural_intent_comparison import (
    StructuralComparisonPolicy,
    StructuralRequirement,
)


def evaluation_contract_to_structural_requirement(
    contract: EvaluationSemanticContract,
) -> StructuralRequirement | None:
    if contract.answerability is not EvaluationAnswerability.ANSWERABLE:
        return None
    grain_fields = tuple(
        SemanticFieldRef(
            entity_id=item.entity_id,
            column=item.column,
        )
        for item in contract.grain_fields
    )
    structural = StructuralResultIntent(
        row_grain=(
            known(
                StructuralRowGrain(
                    mode="grouped" if contract.group_by else "detail",
                    identity_fields=known(grain_fields),
                )
            )
            if grain_fields or contract.group_by
            else unspecified()
        ),
        output_fields=known(
            tuple(
                SemanticFieldRef(
                    entity_id=item.entity_id,
                    column=item.column,
                )
                for item in contract.output_fields
            )
        ),
        aggregations=known(
            tuple(
                SemanticAggregationIntent(
                    id=item.id,
                    function=item.function,
                    distinct=item.distinct,
                    field=SemanticFieldRef(
                        entity_id=item.field.entity_id, column=item.field.column
                    )
                    if item.field is not None
                    else None,
                )
                for item in contract.aggregations
            )
        ),
        group_by=known(
            tuple(
                SemanticFieldRef(
                    entity_id=item.entity_id,
                    column=item.column,
                )
                for item in contract.group_by
            )
        ),
        having=known(
            tuple(
                StructuralHaving(
                    aggregation_id=item.aggregation_id,
                    operator=item.operator,
                    value=item.value,
                )
                for item in contract.having
            )
        ),
        ordering=known(
            tuple(
                SemanticOrderIntent(
                    target_kind=item.target_kind,
                    aggregation_id=item.aggregation_id,
                    direction=item.direction,
                    field=SemanticFieldRef(
                        entity_id=item.field.entity_id, column=item.field.column
                    )
                    if item.field is not None
                    else None,
                )
                for item in contract.ordering
            )
        ),
        distinct=unspecified(),
    )
    return StructuralRequirement(
        intent=structural,
        policy=StructuralComparisonPolicy(
            row_grain="exact"
            if contract.group_by
            else ("required_subset" if grain_fields else "ignored"),
            output_fields="required_subset" if contract.output_fields else "ignored",
            aggregations="required_subset" if contract.aggregations else "ignored",
            group_by="exact" if contract.group_by else "ignored",
            having="required_subset" if contract.having else "ignored",
            ordering="ordered_prefix" if contract.ordering else "ignored",
        ),
        binding="required",
    )
