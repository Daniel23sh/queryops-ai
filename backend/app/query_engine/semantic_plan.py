from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from sqlalchemy import UniqueConstraint

from app.db.base import Base
from app.query_engine.domain_pack import DomainPack
from app.query_engine.result_intent import (
    GroundedAggregationIntent,
    GroundedFieldIdentity,
    GroundedResultIntent,
)
from app.query_engine.semantic_catalog import (
    SemanticCatalogProjection,
    SemanticPredicate,
    SemanticPredicateOperator,
    expand_semantic_concept_ids,
)


Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128),
]
SemanticScalar = str | int | float | bool
MAX_PLAN_ITEMS = 64


class SemanticFieldRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entity_id: Identifier
    column: Identifier


class SemanticLiteralFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    field: SemanticFieldRef
    operator: Literal["equals", "not_equals", "in", "not_in"]
    value: SemanticScalar | tuple[SemanticScalar, ...]

    @model_validator(mode="after")
    def validate_value_shape(self) -> SemanticLiteralFilter:
        is_collection = isinstance(self.value, tuple)
        if self.operator in {"in", "not_in"}:
            if not is_collection or not self.value:
                raise ValueError("Set comparison requires a non-empty value tuple")
        elif is_collection:
            raise ValueError("Scalar comparison cannot use a value tuple")
        return self


class SemanticRelationshipIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    relationship_id: Identifier
    join_type: Literal["inner", "left"]


class SemanticAggregationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: Identifier
    function: Literal["count", "sum"]
    field: SemanticFieldRef | None
    distinct: bool

    @model_validator(mode="after")
    def validate_function(self) -> SemanticAggregationIntent:
        if self.function == "sum" and self.field is None:
            raise ValueError("Sum aggregation requires a field")
        return self


class SemanticHavingIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    aggregation_id: Identifier
    operator: Literal[
        "equals",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
    ]
    value: int | float

    @model_validator(mode="after")
    def validate_finite_value(self) -> SemanticHavingIntent:
        if isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("Having value must be finite")
        return self


class SemanticOrderIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_kind: Literal["field", "aggregation"]
    field: SemanticFieldRef | None
    aggregation_id: Identifier | None
    direction: Literal["asc", "desc"]

    @model_validator(mode="after")
    def validate_target(self) -> SemanticOrderIntent:
        if self.target_kind == "field":
            if self.field is None or self.aggregation_id is not None:
                raise ValueError("Field ordering has an inconsistent target")
        elif self.field is not None or self.aggregation_id is None:
            raise ValueError("Aggregation ordering has an inconsistent target")
        return self


class SemanticPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entity_ids: tuple[Identifier, ...] = Field(max_length=MAX_PLAN_ITEMS)
    concept_ids: tuple[Identifier, ...] = Field(max_length=MAX_PLAN_ITEMS)
    composition_rule_ids: tuple[Identifier, ...] = Field(max_length=MAX_PLAN_ITEMS)
    metric_id: Identifier | None
    distinct: bool
    literal_filters: tuple[SemanticLiteralFilter, ...] = Field(
        max_length=MAX_PLAN_ITEMS
    )
    relationships: tuple[SemanticRelationshipIntent, ...] = Field(
        max_length=MAX_PLAN_ITEMS
    )
    output_fields: tuple[SemanticFieldRef, ...] = Field(max_length=MAX_PLAN_ITEMS)
    aggregations: tuple[SemanticAggregationIntent, ...] = Field(
        max_length=MAX_PLAN_ITEMS
    )
    group_by: tuple[SemanticFieldRef, ...] = Field(max_length=MAX_PLAN_ITEMS)
    having: tuple[SemanticHavingIntent, ...] = Field(max_length=MAX_PLAN_ITEMS)
    order_by: tuple[SemanticOrderIntent, ...] = Field(max_length=MAX_PLAN_ITEMS)
    limit: Annotated[int, Field(ge=1, le=500)] | None


@dataclass(frozen=True)
class EntitySemanticPredicate:
    entity_id: str
    column: str
    operator: SemanticPredicateOperator
    value: SemanticScalar | tuple[SemanticScalar, ...]


@dataclass(frozen=True)
class ValidatedSemanticPlan:
    plan: SemanticPlan
    effective_concept_ids: tuple[str, ...]
    effective_predicates: tuple[EntitySemanticPredicate, ...]
    rule_or_predicate_groups: tuple[
        tuple[tuple[EntitySemanticPredicate, ...], ...], ...
    ]
    rule_all_of_concept_ids: tuple[str, ...]
    rule_or_concept_groups: tuple[tuple[str, ...], ...]
    metric_aggregation_function: str | None

    def as_observation(self) -> dict[str, Any]:
        return {
            "entity_ids": list(self.plan.entity_ids),
            "concept_ids": list(self.plan.concept_ids),
            "effective_concept_ids": list(self.effective_concept_ids),
            "composition_rule_ids": list(self.plan.composition_rule_ids),
            "metric_id": self.plan.metric_id,
            "distinct": self.plan.distinct,
            "relationship_ids": [
                item.relationship_id for item in self.plan.relationships
            ],
            "relationship_join_types": [
                {
                    "relationship_id": item.relationship_id,
                    "join_type": item.join_type,
                }
                for item in self.plan.relationships
            ],
            "output_fields": [
                item.model_dump(mode="json") for item in self.plan.output_fields
            ],
            "aggregation_ids": [item.id for item in self.plan.aggregations],
            "aggregations": [
                item.model_dump(mode="json") for item in self.plan.aggregations
            ],
            "group_by": [
                item.model_dump(mode="json") for item in self.plan.group_by
            ],
            "having": [item.model_dump(mode="json") for item in self.plan.having],
            "order_by": [
                item.model_dump(mode="json") for item in self.plan.order_by
            ],
        }


class SemanticPlanValidationError(ValueError):
    code = "provider_response_invalid"

    def __init__(
        self,
        reason: str,
        *,
        safe_observation: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("The semantic plan is invalid.")
        self.reason = reason
        self.safe_observation = safe_observation


def validate_semantic_plan(
    plan: SemanticPlan,
    *,
    domain_pack: DomainPack,
    projection: SemanticCatalogProjection,
    schema_context: Mapping[str, Any],
    scope_reference_resolved: bool,
) -> ValidatedSemanticPlan:
    catalog = domain_pack.semantic_catalog
    _require_unique(plan.entity_ids, "duplicate_entity")
    _require_unique(plan.concept_ids, "duplicate_concept")
    _require_unique(plan.composition_rule_ids, "duplicate_rule")
    _require_unique(
        (item.relationship_id for item in plan.relationships),
        "duplicate_relationship",
    )
    _require_unique((item.id for item in plan.aggregations), "duplicate_aggregation")
    if not plan.entity_ids:
        raise SemanticPlanValidationError("entity_missing")

    projected_entity_ids = {item["id"] for item in projection.entities}
    projected_concept_ids = {item["id"] for item in projection.concepts}
    projected_metric_ids = {item["id"] for item in projection.metrics}
    projected_rule_ids = {item["id"] for item in projection.composition_rules}
    projected_relationship_ids = {item["id"] for item in projection.relationships}
    mandatory = projection.mandatory_evidence()

    _require_subset(plan.entity_ids, projected_entity_ids, "entity_not_candidate")
    _require_subset(plan.concept_ids, projected_concept_ids, "concept_not_candidate")
    _require_subset(
        plan.composition_rule_ids,
        projected_rule_ids,
        "rule_not_candidate",
    )
    _require_subset(
        (item.relationship_id for item in plan.relationships),
        projected_relationship_ids,
        "relationship_not_candidate",
    )
    if plan.metric_id is not None and plan.metric_id not in projected_metric_ids:
        raise SemanticPlanValidationError("metric_not_candidate")
    if not set(mandatory["entity_ids"]) <= set(plan.entity_ids):
        raise SemanticPlanValidationError("mandatory_entity_missing")
    if not set(mandatory["rule_ids"]) <= set(plan.composition_rule_ids):
        raise SemanticPlanValidationError("mandatory_rule_missing")
    mandatory_metric_ids = set(mandatory["metric_ids"])
    if len(mandatory_metric_ids) > 1:
        raise SemanticPlanValidationError("mandatory_metric_ambiguous")
    if mandatory_metric_ids and plan.metric_id not in mandatory_metric_ids:
        raise SemanticPlanValidationError("mandatory_metric_missing")

    conjunctive_concept_ids = set(plan.concept_ids)
    metric_aggregation_function: str | None = None
    if plan.metric_id is not None:
        metric = catalog.metrics_by_id[plan.metric_id]
        conjunctive_concept_ids.update(metric.required_concept_ids)
        metric_aggregation_function = metric.aggregation.function
        if plan.aggregations:
            raise SemanticPlanValidationError("metric_aggregation_duplicated")
        if (
            plan.output_fields
            or plan.group_by
            or plan.having
            or plan.order_by
            or plan.limit is not None
        ):
            # V1 canonical metrics are scalar definitions. Grouped or ranked
            # variants must use an explicit ad-hoc aggregation plan instead of
            # silently changing the named metric's contract.
            raise SemanticPlanValidationError("metric_shape_unsupported")

    rules_by_id = {rule.id: rule for rule in catalog.composition_rules}
    # Only unconditional deterministic requirements can justify selecting every
    # OR alternative as a top-level conjunction. OR branches are not themselves
    # mandatory conjuncts, even though they appear in the candidate projection.
    mandatory_conjuncts = set(mandatory["concept_ids"])
    for metric_id in mandatory_metric_ids:
        mandatory_conjuncts.update(catalog.metrics_by_id[metric_id].required_concept_ids)
    for rule_id in mandatory["rule_ids"]:
        mandatory_conjuncts.update(rules_by_id[rule_id].all_of_concept_ids)
    mandatory_conjuncts = set(expand_semantic_concept_ids(catalog, mandatory_conjuncts))
    explicit_concept_ids = set(plan.concept_ids)
    rule_all_of: set[str] = set()
    rule_or_groups: list[tuple[str, ...]] = []
    for rule_id in plan.composition_rule_ids:
        rule = rules_by_id[rule_id]
        rule_all_of.update(rule.all_of_concept_ids)
        if rule.or_concept_ids:
            branches = set(rule.or_concept_ids)
            if branches <= explicit_concept_ids and not branches <= mandatory_conjuncts:
                raise SemanticPlanValidationError("composition_rule_overconstraint")
            rule_or_groups.append(tuple(sorted(rule.or_concept_ids)))
        conjunctive_concept_ids.update(rule.all_of_concept_ids)

    conjunctive_effective_concept_ids = expand_semantic_concept_ids(
        catalog,
        conjunctive_concept_ids,
    )
    rule_or_effective_groups = tuple(
        tuple(
            expand_semantic_concept_ids(catalog, (concept_id,))
            for concept_id in group
        )
        for group in rule_or_groups
    )
    effective_concept_ids = tuple(
        sorted(
            set(conjunctive_effective_concept_ids)
            | {
                concept_id
                for group in rule_or_effective_groups
                for branch in group
                for concept_id in branch
            }
        )
    )
    _require_subset(
        effective_concept_ids,
        projected_concept_ids,
        "concept_dependency_not_candidate",
    )
    if not set(mandatory["concept_ids"]) <= set(effective_concept_ids):
        raise SemanticPlanValidationError("mandatory_concept_missing")

    entities_by_id = catalog.entities_by_id
    required_entity_ids = {
        catalog.concepts_by_id[concept_id].entity_id
        for concept_id in effective_concept_ids
    }
    if plan.metric_id is not None:
        required_entity_ids.add(catalog.metrics_by_id[plan.metric_id].entity_id)

    allowed_columns = _safe_allowed_columns(schema_context.get("allowed_columns"))
    scope_columns = _scope_columns(schema_context)
    field_refs = _all_field_refs(plan)
    for field in field_refs:
        if field.entity_id not in plan.entity_ids:
            raise SemanticPlanValidationError("field_entity_not_selected")
        entity = entities_by_id.get(field.entity_id)
        if entity is None or field.column not in allowed_columns.get(
            entity.table,
            frozenset(),
        ):
            raise SemanticPlanValidationError("field_not_authorized")
        required_entity_ids.add(field.entity_id)

    if len(plan.entity_ids) == 1 and any(
        aggregation.function == "count"
        and aggregation.field is None
        and not aggregation.distinct
        for aggregation in plan.aggregations
    ):
        required_entity_ids.add(plan.entity_ids[0])

    for literal_filter in plan.literal_filters:
        entity = entities_by_id[literal_filter.field.entity_id]
        if (
            scope_reference_resolved
            and literal_filter.field.column in scope_columns.get(entity.table, frozenset())
        ):
            raise SemanticPlanValidationError("scope_filter_not_allowed")
        _validate_literal_filter(literal_filter, domain_pack)

    if not required_entity_ids <= set(plan.entity_ids):
        raise SemanticPlanValidationError("required_entity_missing")

    if not plan.metric_id and not plan.output_fields and not plan.aggregations:
        raise SemanticPlanValidationError("output_intent_missing")

    selected_relationships = {
        relationship.id: relationship
        for relationship in catalog.relationships
        if relationship.id
        in {item.relationship_id for item in plan.relationships}
    }
    for relationship in selected_relationships.values():
        if not {relationship.from_entity, relationship.to_entity} <= set(
            plan.entity_ids
        ):
            raise SemanticPlanValidationError("relationship_endpoint_missing")
        required_entity_ids.update(
            {relationship.from_entity, relationship.to_entity}
        )
    _validate_relationship_graph(plan.entity_ids, plan.relationships, selected_relationships)

    if set(plan.entity_ids) != required_entity_ids:
        raise SemanticPlanValidationError("unused_entity")

    aggregation_ids = {aggregation.id for aggregation in plan.aggregations}
    if any(item.aggregation_id not in aggregation_ids for item in plan.having):
        raise SemanticPlanValidationError("having_aggregation_missing")
    if any(
        item.target_kind == "aggregation"
        and item.aggregation_id not in aggregation_ids
        for item in plan.order_by
    ):
        raise SemanticPlanValidationError("order_aggregation_missing")
    if plan.aggregations and plan.output_fields:
        group_fields = {_field_key(field) for field in plan.group_by}
        if {_field_key(field) for field in plan.output_fields} != group_fields:
            raise SemanticPlanValidationError("group_by_incomplete")
    if plan.group_by and not plan.aggregations:
        raise SemanticPlanValidationError("group_by_without_aggregation")
    if projection.grounded_result_intent is not None:
        # Only the grounded required contract is fail-closed. The sibling
        # suggested_result_intent is deliberately not consumed by validation.
        _validate_grounded_result_intent(
            plan,
            projection.grounded_result_intent,
            domain_pack,
        )
    effective_predicates = tuple(
        sorted(
            (
                _entity_predicate(catalog.concepts_by_id[concept_id].entity_id, predicate)
                for concept_id in conjunctive_effective_concept_ids
                for predicate in catalog.concepts_by_id[
                    concept_id
                ].required_predicates
            ),
            key=lambda item: (
                item.entity_id,
                item.column,
                item.operator.value,
                json.dumps(item.value, sort_keys=True, separators=(",", ":")),
            ),
        )
    )
    rule_or_predicate_groups = tuple(
        tuple(
            tuple(
                sorted(
                    (
                        _entity_predicate(
                            catalog.concepts_by_id[concept_id].entity_id,
                            predicate,
                        )
                        for concept_id in branch
                        for predicate in catalog.concepts_by_id[
                            concept_id
                        ].required_predicates
                    ),
                    key=_entity_predicate_key,
                )
            )
            for branch in group
        )
        for group in rule_or_effective_groups
    )
    _validate_predicate_consistency(effective_predicates, plan.literal_filters)
    for group in rule_or_predicate_groups:
        for branch in group:
            _validate_predicate_consistency(
                (*effective_predicates, *branch),
                plan.literal_filters,
            )

    canonical_plan = plan.model_copy(
        update={
            "entity_ids": tuple(sorted(plan.entity_ids)),
            "concept_ids": tuple(sorted(plan.concept_ids)),
            "composition_rule_ids": tuple(sorted(plan.composition_rule_ids)),
            "relationships": tuple(
                sorted(
                    plan.relationships,
                    key=lambda item: item.relationship_id,
                )
            ),
            "literal_filters": tuple(
                sorted(plan.literal_filters, key=_literal_filter_key)
            ),
            "output_fields": tuple(sorted(plan.output_fields, key=_field_key)),
            "group_by": tuple(sorted(plan.group_by, key=_field_key)),
            "aggregations": tuple(sorted(plan.aggregations, key=lambda item: item.id)),
            "having": tuple(
                sorted(
                    plan.having,
                    key=lambda item: (item.aggregation_id, item.operator, item.value),
                )
            ),
            "order_by": plan.order_by,
        }
    )
    return ValidatedSemanticPlan(
        plan=canonical_plan,
        effective_concept_ids=effective_concept_ids,
        effective_predicates=effective_predicates,
        rule_or_predicate_groups=rule_or_predicate_groups,
        rule_all_of_concept_ids=tuple(sorted(rule_all_of)),
        rule_or_concept_groups=tuple(sorted(rule_or_groups)),
        metric_aggregation_function=metric_aggregation_function,
    )


def _validate_grounded_result_intent(
    plan: SemanticPlan,
    intent: GroundedResultIntent,
    domain_pack: DomainPack,
) -> None:
    table_to_entity_id = {
        entity.table: entity.id
        for entity in domain_pack.semantic_catalog.entities
    }
    required_output_fields = _grounded_field_keys(
        intent.required_output_fields,
        table_to_entity_id,
    )
    plan_output_fields = {_field_key(field) for field in plan.output_fields}
    if required_output_fields is None or not required_output_fields <= plan_output_fields:
        raise SemanticPlanValidationError(
            "required_output_missing",
            safe_observation=_field_mismatch_observation(
                intent.required_output_fields,
                plan.output_fields,
                domain_pack,
            ),
        )

    expected_group_by = _grounded_field_keys(
        intent.group_by,
        table_to_entity_id,
    )
    actual_group_by = {_field_key(field) for field in plan.group_by}
    aggregation_key_normalization: dict[
        tuple[str, str], tuple[str, str]
    ] = {}
    if expected_group_by is not None and expected_group_by == actual_group_by:
        aggregation_key_normalization = _distinct_count_identity_normalization(
            plan,
            domain_pack,
        )

    expected_aggregations: tuple[
        tuple[str, tuple[str, str] | None, bool], ...
    ] | None = None
    actual_aggregations: tuple[
        tuple[str, tuple[str, str] | None, bool], ...
    ] = ()
    if intent.aggregations:
        expected_aggregations = _grounded_aggregation_keys(
            intent.aggregations,
            table_to_entity_id,
        )
        actual_aggregations = tuple(
            sorted(
                (_plan_aggregation_key(item) for item in plan.aggregations),
                key=repr,
            )
        )
        aggregations_match = expected_aggregations == actual_aggregations
        if (
            not aggregations_match
            and expected_aggregations is not None
            and aggregation_key_normalization
        ):
            aggregations_match = _normalize_aggregation_keys(
                expected_aggregations,
                aggregation_key_normalization,
            ) == _normalize_aggregation_keys(
                actual_aggregations,
                aggregation_key_normalization,
            ) and _having_semantics_match(
                intent,
                plan,
                table_to_entity_id,
                aggregation_key_normalization,
            )
        if not aggregations_match:
            raise SemanticPlanValidationError(
                "grounded_aggregation_mismatch",
                safe_observation=_aggregation_mismatch_observation(
                    intent.aggregations,
                    plan.aggregations,
                    domain_pack,
                ),
            )

    if intent.group_by:
        if expected_group_by is None or expected_group_by != actual_group_by:
            raise SemanticPlanValidationError(
                "grounded_group_by_mismatch",
                safe_observation=_field_mismatch_observation(
                    intent.group_by,
                    plan.group_by,
                    domain_pack,
                ),
            )

    if intent.having:
        expected_aggregations_by_id = {
            item.id: _grounded_aggregation_key(item, table_to_entity_id)
            for item in intent.aggregations
        }
        actual_aggregations_by_id = {
            item.id: _plan_aggregation_key(item) for item in plan.aggregations
        }
        expected_having = {
            (
                _normalize_aggregation_key(
                    expected_aggregations_by_id[item.aggregation_id],
                    aggregation_key_normalization,
                ),
                item.operator,
                item.value,
            )
            for item in intent.having
        }
        actual_having = {
            (
                _normalize_aggregation_key(
                    actual_aggregations_by_id.get(item.aggregation_id),
                    aggregation_key_normalization,
                ),
                item.operator,
                item.value,
            )
            for item in plan.having
        }
        if (
            None in expected_aggregations_by_id.values()
            or expected_having != actual_having
        ):
            raise SemanticPlanValidationError(
                "grounded_having_mismatch",
                safe_observation=_having_mismatch_observation(
                    intent,
                    plan,
                    domain_pack,
                ),
            )

    if intent.distinct is not None and plan.distinct is not intent.distinct:
        raise SemanticPlanValidationError(
            "grounded_distinct_mismatch",
            safe_observation={
                "expected": intent.distinct,
                "actual": plan.distinct,
            },
        )

    if intent.row_grain is None:
        return
    grain_fields = _grounded_field_keys(
        intent.row_grain.identity_fields,
        table_to_entity_id,
    )
    if grain_fields is None:
        raise SemanticPlanValidationError(
            "result_grain_mismatch",
            safe_observation=_grain_mismatch_observation(
                intent,
                plan,
                domain_pack,
            ),
        )
    if intent.row_grain.mode == "grouped":
        if grain_fields != {_field_key(field) for field in plan.group_by}:
            raise SemanticPlanValidationError(
                "result_grain_mismatch",
                safe_observation=_grain_mismatch_observation(
                    intent,
                    plan,
                    domain_pack,
                ),
            )
        return
    if plan.aggregations or plan.group_by or not grain_fields <= plan_output_fields:
        raise SemanticPlanValidationError(
            "result_grain_mismatch",
            safe_observation=_grain_mismatch_observation(
                intent,
                plan,
                domain_pack,
            ),
        )


def _grounded_field_keys(
    fields: tuple[GroundedFieldIdentity, ...],
    table_to_entity_id: Mapping[str, str],
) -> set[tuple[str, str]] | None:
    keys: set[tuple[str, str]] = set()
    for field in fields:
        entity_id = table_to_entity_id.get(field.table)
        if entity_id is None:
            return None
        keys.add((entity_id, field.column))
    return keys


def _grounded_aggregation_keys(
    aggregations: tuple[GroundedAggregationIntent, ...],
    table_to_entity_id: Mapping[str, str],
) -> tuple[tuple[str, tuple[str, str] | None, bool], ...] | None:
    keys = [
        _grounded_aggregation_key(item, table_to_entity_id)
        for item in aggregations
    ]
    if any(item is None for item in keys):
        return None
    return tuple(sorted((item for item in keys if item is not None), key=repr))


def _grounded_aggregation_key(
    aggregation: GroundedAggregationIntent,
    table_to_entity_id: Mapping[str, str],
) -> tuple[str, tuple[str, str] | None, bool] | None:
    field_key: tuple[str, str] | None = None
    if aggregation.target_field is not None:
        entity_id = table_to_entity_id.get(aggregation.target_field.table)
        if entity_id is None:
            return None
        field_key = (entity_id, aggregation.target_field.column)
    return aggregation.function, field_key, aggregation.distinct


def _plan_aggregation_key(
    aggregation: SemanticAggregationIntent,
) -> tuple[str, tuple[str, str] | None, bool]:
    return (
        aggregation.function,
        _field_key(aggregation.field) if aggregation.field is not None else None,
        aggregation.distinct,
    )


def _distinct_count_identity_normalization(
    plan: SemanticPlan,
    domain_pack: DomainPack,
) -> dict[tuple[str, str], tuple[str, str]]:
    catalog = domain_pack.semantic_catalog
    entities_by_id = catalog.entities_by_id
    relationships_by_id = {
        relationship.id: relationship for relationship in catalog.relationships
    }
    candidates: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for selected in plan.relationships:
        relationship = relationships_by_id.get(selected.relationship_id)
        if (
            relationship is None
            or selected.join_type != "inner"
            or relationship.cardinality.value != "many_to_one"
            or relationship.optional
        ):
            continue
        source_entity = entities_by_id.get(relationship.from_entity)
        target_entity = entities_by_id.get(relationship.to_entity)
        if source_entity is None or target_entity is None:
            continue
        if not _is_proven_fk_to_unique_identity(
            source_entity.table,
            relationship.from_column,
            target_entity.table,
            relationship.to_column,
        ):
            continue
        source_key = (relationship.from_entity, relationship.from_column)
        target_key = (relationship.to_entity, relationship.to_column)
        candidates.setdefault(source_key, set()).add(target_key)
    return {
        source_key: next(iter(target_keys))
        for source_key, target_keys in candidates.items()
        if len(target_keys) == 1
    }


def _is_proven_fk_to_unique_identity(
    source_table_name: str,
    source_column_name: str,
    target_table_name: str,
    target_column_name: str,
) -> bool:
    source_table = Base.metadata.tables.get(source_table_name)
    target_table = Base.metadata.tables.get(target_table_name)
    if source_table is None or target_table is None:
        return False
    source_column = source_table.columns.get(source_column_name)
    target_column = target_table.columns.get(target_column_name)
    if source_column is None or target_column is None or source_column.nullable:
        return False
    if not any(
        foreign_key.column.table is target_table
        and foreign_key.column is target_column
        for foreign_key in source_column.foreign_keys
    ):
        return False
    primary_key_columns = tuple(target_table.primary_key.columns)
    if len(primary_key_columns) == 1 and primary_key_columns[0] is target_column:
        return True
    if target_column.unique is True:
        return True
    return any(
        isinstance(constraint, UniqueConstraint)
        and len(constraint.columns) == 1
        and next(iter(constraint.columns)) is target_column
        for constraint in target_table.constraints
    )


def _normalize_aggregation_keys(
    keys: tuple[tuple[str, tuple[str, str] | None, bool], ...],
    field_normalization: Mapping[tuple[str, str], tuple[str, str]],
) -> tuple[tuple[str, tuple[str, str] | None, bool], ...]:
    normalized: list[tuple[str, tuple[str, str] | None, bool]] = []
    for key in keys:
        normalized_key = _normalize_aggregation_key(key, field_normalization)
        if normalized_key is not None:
            normalized.append(normalized_key)
    return tuple(sorted(normalized, key=repr))


def _normalize_aggregation_key(
    key: tuple[str, tuple[str, str] | None, bool] | None,
    field_normalization: Mapping[tuple[str, str], tuple[str, str]],
) -> tuple[str, tuple[str, str] | None, bool] | None:
    if key is None:
        return None
    function, field, distinct = key
    if function != "count" or not distinct or field is None:
        return key
    return function, field_normalization.get(field, field), distinct


def _having_semantics_match(
    intent: GroundedResultIntent,
    plan: SemanticPlan,
    table_to_entity_id: Mapping[str, str],
    field_normalization: Mapping[tuple[str, str], tuple[str, str]],
) -> bool:
    expected_aggregations_by_id = {
        item.id: _grounded_aggregation_key(item, table_to_entity_id)
        for item in intent.aggregations
    }
    actual_aggregations_by_id = {
        item.id: _plan_aggregation_key(item) for item in plan.aggregations
    }
    expected_having = {
        (
            _normalize_aggregation_key(
                expected_aggregations_by_id.get(item.aggregation_id),
                field_normalization,
            ),
            item.operator,
            item.value,
        )
        for item in intent.having
    }
    actual_having = {
        (
            _normalize_aggregation_key(
                actual_aggregations_by_id.get(item.aggregation_id),
                field_normalization,
            ),
            item.operator,
            item.value,
        )
        for item in plan.having
    }
    return None not in expected_aggregations_by_id.values() and (
        expected_having == actual_having
    )


def _aggregation_mismatch_observation(
    expected: tuple[GroundedAggregationIntent, ...],
    actual: tuple[SemanticAggregationIntent, ...],
    domain_pack: DomainPack,
) -> dict[str, Any]:
    entities_by_id = domain_pack.semantic_catalog.entities_by_id
    expected_items = [
        {
            "function": item.function,
            "target": (
                f"{item.target_field.table}.{item.target_field.column}"
                if item.target_field is not None
                else None
            ),
            "distinct": item.distinct,
        }
        for item in expected
    ]
    actual_items = [
        {
            "function": item.function,
            "target": (
                f"{entities_by_id[item.field.entity_id].table}.{item.field.column}"
                if item.field is not None
                and item.field.entity_id in entities_by_id
                else None
            ),
            "distinct": item.distinct,
        }
        for item in actual
    ]

    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item["function"],
            item["target"] or "",
            item["distinct"],
        )

    return {
        "expected": sorted(expected_items, key=sort_key),
        "actual": sorted(actual_items, key=sort_key),
    }


def _field_mismatch_observation(
    expected: tuple[GroundedFieldIdentity, ...],
    actual: tuple[SemanticFieldRef, ...],
    domain_pack: DomainPack,
) -> dict[str, Any]:
    entities_by_id = domain_pack.semantic_catalog.entities_by_id
    return {
        "expected": sorted(f"{field.table}.{field.column}" for field in expected)[
            :MAX_PLAN_ITEMS
        ],
        "actual": sorted(
            f"{entities_by_id[field.entity_id].table}.{field.column}"
            for field in actual
            if field.entity_id in entities_by_id
        )[:MAX_PLAN_ITEMS],
    }


def _safe_aggregation_shape(
    aggregation: GroundedAggregationIntent | SemanticAggregationIntent | None,
    domain_pack: DomainPack,
) -> dict[str, Any] | None:
    if aggregation is None:
        return None
    if isinstance(aggregation, GroundedAggregationIntent):
        target = (
            f"{aggregation.target_field.table}.{aggregation.target_field.column}"
            if aggregation.target_field is not None
            else None
        )
    else:
        entities_by_id = domain_pack.semantic_catalog.entities_by_id
        target = (
            f"{entities_by_id[aggregation.field.entity_id].table}."
            f"{aggregation.field.column}"
            if aggregation.field is not None
            and aggregation.field.entity_id in entities_by_id
            else None
        )
    return {
        "function": aggregation.function,
        "target": target,
        "distinct": aggregation.distinct,
    }


def _having_mismatch_observation(
    intent: GroundedResultIntent,
    plan: SemanticPlan,
    domain_pack: DomainPack,
) -> dict[str, Any]:
    expected_aggregations = {item.id: item for item in intent.aggregations}
    actual_aggregations = {item.id: item for item in plan.aggregations}
    expected = [
        {
            "aggregation": _safe_aggregation_shape(
                expected_aggregations.get(item.aggregation_id),
                domain_pack,
            ),
            "operator": item.operator,
        }
        for item in intent.having
    ]
    actual = [
        {
            "aggregation": _safe_aggregation_shape(
                actual_aggregations.get(item.aggregation_id),
                domain_pack,
            ),
            "operator": item.operator,
        }
        for item in plan.having
    ]

    def sort_key(item: dict[str, Any]) -> str:
        return repr(item)

    return {
        "expected": sorted(expected, key=sort_key)[:MAX_PLAN_ITEMS],
        "actual": sorted(actual, key=sort_key)[:MAX_PLAN_ITEMS],
    }


def _grain_mismatch_observation(
    intent: GroundedResultIntent,
    plan: SemanticPlan,
    domain_pack: DomainPack,
) -> dict[str, Any]:
    assert intent.row_grain is not None
    if plan.group_by:
        actual_mode = "grouped"
        actual_fields = plan.group_by
    elif plan.aggregations:
        actual_mode = "aggregated"
        actual_fields = plan.output_fields
    else:
        actual_mode = "detail"
        actual_fields = plan.output_fields
    identities = _field_mismatch_observation(
        intent.row_grain.identity_fields,
        actual_fields,
        domain_pack,
    )
    return {
        "expected": {
            "mode": intent.row_grain.mode,
            "identities": identities["expected"],
        },
        "actual": {
            "mode": actual_mode,
            "identities": identities["actual"],
        },
    }


def _validate_literal_filter(
    literal_filter: SemanticLiteralFilter,
    domain_pack: DomainPack,
) -> None:
    entity = domain_pack.semantic_catalog.entities_by_id[literal_filter.field.entity_id]
    column = domain_pack.tables_by_name[entity.table].columns_by_name[
        literal_filter.field.column
    ]
    values = (
        literal_filter.value
        if isinstance(literal_filter.value, tuple)
        else (literal_filter.value,)
    )
    for value in values:
        if not _value_matches_type(value, column.data_type):
            raise SemanticPlanValidationError("literal_type_invalid")
    known_values = {
        item.column: set(item.values) for item in entity.known_values
    }.get(literal_filter.field.column)
    if known_values is not None and not set(values) <= known_values:
        raise SemanticPlanValidationError("literal_value_not_known")


def _value_matches_type(value: SemanticScalar, data_type: str) -> bool:
    if isinstance(value, float) and not isfinite(value):
        return False
    if data_type == "boolean":
        return isinstance(value, bool)
    if data_type in {"integer", "numeric", "decimal"}:
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, str) and 1 <= len(value) <= 120


def _validate_relationship_graph(
    entity_ids: tuple[str, ...],
    relationship_intents: tuple[SemanticRelationshipIntent, ...],
    relationships: Mapping[str, Any],
) -> None:
    if len(entity_ids) == 1:
        if relationships:
            raise SemanticPlanValidationError("relationship_unused")
        return
    adjacency: dict[str, set[str]] = {entity_id: set() for entity_id in entity_ids}
    parent = {entity_id: entity_id for entity_id in entity_ids}

    def find(entity_id: str) -> str:
        while parent[entity_id] != entity_id:
            parent[entity_id] = parent[parent[entity_id]]
            entity_id = parent[entity_id]
        return entity_id

    for intent in relationship_intents:
        relationship = relationships[intent.relationship_id]
        left = find(relationship.from_entity)
        right = find(relationship.to_entity)
        if left == right:
            raise SemanticPlanValidationError("relationship_graph_cycle")
        parent[left] = right
        adjacency[relationship.from_entity].add(relationship.to_entity)
        adjacency[relationship.to_entity].add(relationship.from_entity)
    visited: set[str] = set()
    frontier = [min(entity_ids)]
    while frontier:
        current = frontier.pop()
        if current in visited:
            continue
        visited.add(current)
        frontier.extend(sorted(adjacency[current] - visited, reverse=True))
    if visited != set(entity_ids):
        raise SemanticPlanValidationError("relationship_graph_disconnected")
    if len(relationships) != len(entity_ids) - 1:
        raise SemanticPlanValidationError("relationship_graph_not_tree")


def _validate_predicate_consistency(
    concept_predicates: tuple[EntitySemanticPredicate, ...],
    literal_filters: tuple[SemanticLiteralFilter, ...],
) -> None:
    equals: dict[tuple[str, str], Any] = {}
    allowed_sets: dict[tuple[str, str], set[Any]] = {}
    excluded_sets: dict[tuple[str, str], set[Any]] = {}
    for predicate in concept_predicates:
        key = (predicate.entity_id, predicate.column)
        if predicate.operator is SemanticPredicateOperator.EQUALS:
            _add_equal_constraint(equals, key, predicate.value)
        elif predicate.operator is SemanticPredicateOperator.IN:
            if not isinstance(predicate.value, tuple):
                raise SemanticPlanValidationError("predicate_value_invalid")
            _add_allowed_constraint(allowed_sets, key, set(predicate.value))
    for literal_filter in literal_filters:
        key = (literal_filter.field.entity_id, literal_filter.field.column)
        if literal_filter.operator == "equals":
            _add_equal_constraint(equals, key, literal_filter.value)
        elif literal_filter.operator == "not_equals":
            excluded_sets.setdefault(key, set()).add(literal_filter.value)
        elif literal_filter.operator == "in":
            if not isinstance(literal_filter.value, tuple):
                raise SemanticPlanValidationError("predicate_value_invalid")
            _add_allowed_constraint(
                allowed_sets,
                key,
                set(literal_filter.value),
            )
        elif literal_filter.operator == "not_in":
            if not isinstance(literal_filter.value, tuple):
                raise SemanticPlanValidationError("predicate_value_invalid")
            excluded_sets.setdefault(key, set()).update(literal_filter.value)
    for key, value in equals.items():
        if value in excluded_sets.get(key, set()):
            raise SemanticPlanValidationError("predicate_contradiction")
        allowed = allowed_sets.get(key)
        if allowed is not None and value not in allowed:
            raise SemanticPlanValidationError("predicate_contradiction")
    for key, allowed in allowed_sets.items():
        if not allowed - excluded_sets.get(key, set()):
            raise SemanticPlanValidationError("predicate_contradiction")


def _add_equal_constraint(
    equals: dict[tuple[str, str], Any],
    key: tuple[str, str],
    value: Any,
) -> None:
    if key in equals and equals[key] != value:
        raise SemanticPlanValidationError("predicate_contradiction")
    equals[key] = value


def _add_allowed_constraint(
    allowed_sets: dict[tuple[str, str], set[Any]],
    key: tuple[str, str],
    values: set[Any],
) -> None:
    existing = allowed_sets.get(key)
    narrowed = values if existing is None else existing & values
    if not narrowed:
        raise SemanticPlanValidationError("predicate_contradiction")
    allowed_sets[key] = narrowed


def _entity_predicate(
    entity_id: str,
    predicate: SemanticPredicate,
) -> EntitySemanticPredicate:
    return EntitySemanticPredicate(
        entity_id=entity_id,
        column=predicate.column,
        operator=predicate.operator,
        value=predicate.value,
    )


def _entity_predicate_key(
    predicate: EntitySemanticPredicate,
) -> tuple[str, str, str, str]:
    return (
        predicate.entity_id,
        predicate.column,
        predicate.operator.value,
        json.dumps(predicate.value, sort_keys=True, separators=(",", ":")),
    )


def _literal_filter_key(
    literal_filter: SemanticLiteralFilter,
) -> tuple[str, str, str, str]:
    return (
        literal_filter.field.entity_id,
        literal_filter.field.column,
        literal_filter.operator,
        json.dumps(literal_filter.value, sort_keys=True, separators=(",", ":")),
    )


def _all_field_refs(plan: SemanticPlan) -> tuple[SemanticFieldRef, ...]:
    fields = [item.field for item in plan.literal_filters]
    fields.extend(item.field for item in plan.aggregations if item.field is not None)
    fields.extend(plan.output_fields)
    fields.extend(plan.group_by)
    fields.extend(item.field for item in plan.order_by if item.field is not None)
    return tuple(fields)


def _scope_columns(schema_context: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    tables = schema_context.get("tables")
    if not isinstance(tables, list):
        return result
    for table in tables:
        if not isinstance(table, Mapping):
            continue
        name = table.get("name")
        scope_column = table.get("scope_column")
        if isinstance(name, str) and isinstance(scope_column, str):
            result[name] = frozenset({scope_column})
    return result


def _safe_allowed_columns(value: Any) -> dict[str, frozenset[str]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        table: frozenset(column for column in columns if isinstance(column, str))
        for table, columns in value.items()
        if isinstance(table, str) and isinstance(columns, list | tuple)
    }


def _require_unique(values: Any, reason: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise SemanticPlanValidationError(reason)


def _require_subset(values: Any, allowed: set[str], reason: str) -> None:
    if not set(values) <= allowed:
        raise SemanticPlanValidationError(reason)


def _field_key(field: SemanticFieldRef) -> tuple[str, str]:
    return field.entity_id, field.column
