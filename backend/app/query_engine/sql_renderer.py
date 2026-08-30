from __future__ import annotations

from collections.abc import Iterable
from math import isfinite
from typing import Any

from app.query_engine.domain_pack import DomainPack
from app.query_engine.semantic_catalog import SemanticPredicateOperator
from app.query_engine.semantic_plan import (
    EntitySemanticPredicate,
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticLiteralFilter,
    ValidatedSemanticPlan,
)


class SemanticSQLRenderError(RuntimeError):
    """Bounded failure raised when a validated plan is outside the V1 SQL algebra."""

    def __init__(self, reason: str) -> None:
        super().__init__("The validated semantic plan cannot be rendered.")
        self.reason = reason


def render_validated_semantic_plan(
    plan: ValidatedSemanticPlan,
    domain_pack: DomainPack,
) -> str:
    """Render an already validated semantic plan as deterministic PostgreSQL."""

    if not isinstance(plan, ValidatedSemanticPlan):
        raise TypeError("plan must be a ValidatedSemanticPlan")

    semantic_plan = plan.plan
    entity_tables = {
        entity.id: entity.table for entity in domain_pack.semantic_catalog.entities
    }
    if any(entity_id not in entity_tables for entity_id in semantic_plan.entity_ids):
        raise SemanticSQLRenderError("entity_unavailable")

    root_entity_id, joins = _render_join_tree(plan, domain_pack, entity_tables)
    select_items = _render_select_items(plan, domain_pack, entity_tables)
    distinct = "DISTINCT " if semantic_plan.distinct else ""
    sql_parts = [
        f"SELECT {distinct}{', '.join(select_items)}",
        f"FROM {entity_tables[root_entity_id]}",
        *joins,
    ]

    predicates = _render_predicates(plan, entity_tables)
    if predicates:
        sql_parts.append(f"WHERE {' AND '.join(predicates)}")
    if semantic_plan.group_by:
        sql_parts.append(
            "GROUP BY "
            + ", ".join(
                _render_field(field, entity_tables)
                for field in semantic_plan.group_by
            )
        )
    if semantic_plan.having:
        aggregations = {
            aggregation.id: aggregation
            for aggregation in semantic_plan.aggregations
        }
        sql_parts.append(
            "HAVING "
            + " AND ".join(
                _render_having(item, aggregations, entity_tables)
                for item in semantic_plan.having
            )
        )
    if semantic_plan.order_by:
        aggregations = {
            aggregation.id: aggregation
            for aggregation in semantic_plan.aggregations
        }
        sql_parts.append(
            "ORDER BY "
            + ", ".join(
                _render_order(item, aggregations, entity_tables)
                for item in semantic_plan.order_by
            )
        )
    if semantic_plan.limit is not None:
        sql_parts.append(f"LIMIT {semantic_plan.limit}")
    return " ".join(sql_parts)


def _render_join_tree(
    validated_plan: ValidatedSemanticPlan,
    domain_pack: DomainPack,
    entity_tables: dict[str, str],
) -> tuple[str, tuple[str, ...]]:
    plan = validated_plan.plan
    if not plan.entity_ids:
        raise SemanticSQLRenderError("entity_missing")
    if len(plan.entity_ids) == 1:
        if plan.relationships:
            raise SemanticSQLRenderError("relationship_unexpected")
        return plan.entity_ids[0], ()

    relationships_by_id = {
        relationship.id: relationship
        for relationship in domain_pack.semantic_catalog.relationships
    }
    selected: list[tuple[Any, str]] = []
    for intent in plan.relationships:
        relationship = relationships_by_id.get(intent.relationship_id)
        if relationship is None:
            raise SemanticSQLRenderError("relationship_unavailable")
        selected.append((relationship, intent.join_type))

    for root_entity_id in sorted(plan.entity_ids):
        available = {root_entity_id}
        pending = sorted(selected, key=lambda item: item[0].id)
        rendered: list[str] = []
        while pending:
            match_index: int | None = None
            new_entity_id: str | None = None
            for index, (relationship, join_type) in enumerate(pending):
                from_available = relationship.from_entity in available
                to_available = relationship.to_entity in available
                if join_type == "left":
                    if from_available and not to_available:
                        match_index = index
                        new_entity_id = relationship.to_entity
                        break
                elif join_type == "inner" and from_available != to_available:
                    match_index = index
                    new_entity_id = (
                        relationship.to_entity
                        if from_available
                        else relationship.from_entity
                    )
                    break
                elif join_type not in {"inner", "left"}:
                    raise SemanticSQLRenderError("join_type_unsupported")
            if match_index is None or new_entity_id is None:
                break
            relationship, join_type = pending.pop(match_index)
            join_keyword = "LEFT JOIN" if join_type == "left" else "INNER JOIN"
            rendered.append(
                f"{join_keyword} {entity_tables[new_entity_id]} ON "
                f"{entity_tables[relationship.from_entity]}.{relationship.from_column} = "
                f"{entity_tables[relationship.to_entity]}.{relationship.to_column}"
            )
            available.add(new_entity_id)
        if not pending and available == set(plan.entity_ids):
            return root_entity_id, tuple(rendered)

    raise SemanticSQLRenderError("left_join_orientation_unsupported")


def _render_select_items(
    validated_plan: ValidatedSemanticPlan,
    domain_pack: DomainPack,
    entity_tables: dict[str, str],
) -> tuple[str, ...]:
    plan = validated_plan.plan
    if plan.metric_id is not None:
        metric = domain_pack.semantic_catalog.metrics_by_id.get(plan.metric_id)
        if (
            metric is None
            or metric.entity_id not in entity_tables
            or validated_plan.metric_aggregation_function not in {"count", "sum"}
        ):
            raise SemanticSQLRenderError("metric_unsupported")
        if validated_plan.metric_aggregation_function == "count":
            return (f"COUNT(*) AS {plan.metric_id}",)
        raise SemanticSQLRenderError("metric_sum_target_missing")

    items = tuple(
        _render_field(field, entity_tables) for field in plan.output_fields
    ) + tuple(
        f"{_render_aggregation(aggregation, entity_tables)} AS {aggregation.id}"
        for aggregation in plan.aggregations
    )
    if not items:
        raise SemanticSQLRenderError("output_missing")
    return items


def _render_predicates(
    validated_plan: ValidatedSemanticPlan,
    entity_tables: dict[str, str],
) -> tuple[str, ...]:
    common = _deduplicate(
        _render_entity_predicate(predicate, entity_tables)
        for predicate in validated_plan.effective_predicates
    )
    literals = _deduplicate(
        _render_literal_filter(item, entity_tables)
        for item in validated_plan.plan.literal_filters
    )
    groups: list[str] = []
    for group in validated_plan.rule_or_predicate_groups:
        branches: list[str] = []
        for branch in group:
            branch_predicates = _deduplicate(
                _render_entity_predicate(predicate, entity_tables)
                for predicate in branch
            )
            if not branch_predicates:
                raise SemanticSQLRenderError("or_branch_empty")
            branches.append(f"({' AND '.join(branch_predicates)})")
        if not branches:
            raise SemanticSQLRenderError("or_group_empty")
        groups.append(f"({' OR '.join(branches)})")
    return (*common, *literals, *groups)


def _render_entity_predicate(
    predicate: EntitySemanticPredicate,
    entity_tables: dict[str, str],
) -> str:
    column = _render_column(predicate.entity_id, predicate.column, entity_tables)
    operator = predicate.operator
    if operator is SemanticPredicateOperator.EQUALS:
        return f"{column} = {_render_literal(predicate.value)}"
    if operator is SemanticPredicateOperator.IN:
        return f"{column} IN {_render_literal_collection(predicate.value)}"
    if operator is SemanticPredicateOperator.OLDER_THAN_DAYS:
        return f"{column} < {_render_day_boundary(predicate.value)}"
    if operator is SemanticPredicateOperator.WITHIN_LAST_DAYS:
        return f"{column} >= {_render_day_boundary(predicate.value)}"
    if operator is SemanticPredicateOperator.IS_NULL_OR_OLDER_THAN_DAYS:
        return (
            f"({column} IS NULL OR {column} < "
            f"{_render_day_boundary(predicate.value)})"
        )
    raise SemanticSQLRenderError("predicate_operator_unsupported")


def _render_literal_filter(
    literal_filter: SemanticLiteralFilter,
    entity_tables: dict[str, str],
) -> str:
    column = _render_field(literal_filter.field, entity_tables)
    if literal_filter.operator == "equals":
        return f"{column} = {_render_literal(literal_filter.value)}"
    if literal_filter.operator == "not_equals":
        return f"{column} <> {_render_literal(literal_filter.value)}"
    if literal_filter.operator == "in":
        return f"{column} IN {_render_literal_collection(literal_filter.value)}"
    if literal_filter.operator == "not_in":
        return f"{column} NOT IN {_render_literal_collection(literal_filter.value)}"
    raise SemanticSQLRenderError("literal_operator_unsupported")


def _render_having(
    having: Any,
    aggregations: dict[str, SemanticAggregationIntent],
    entity_tables: dict[str, str],
) -> str:
    aggregation = aggregations.get(having.aggregation_id)
    if aggregation is None:
        raise SemanticSQLRenderError("having_aggregation_missing")
    operators = {
        "equals": "=",
        "greater_than": ">",
        "greater_than_or_equal": ">=",
        "less_than": "<",
        "less_than_or_equal": "<=",
    }
    operator = operators.get(having.operator)
    if operator is None:
        raise SemanticSQLRenderError("having_operator_unsupported")
    return (
        f"{_render_aggregation(aggregation, entity_tables)} {operator} "
        f"{_render_literal(having.value)}"
    )


def _render_order(
    order: Any,
    aggregations: dict[str, SemanticAggregationIntent],
    entity_tables: dict[str, str],
) -> str:
    if order.target_kind == "field" and order.field is not None:
        target = _render_field(order.field, entity_tables)
    elif order.target_kind == "aggregation" and order.aggregation_id is not None:
        aggregation = aggregations.get(order.aggregation_id)
        if aggregation is None:
            raise SemanticSQLRenderError("order_aggregation_missing")
        target = _render_aggregation(aggregation, entity_tables)
    else:
        raise SemanticSQLRenderError("order_target_unsupported")
    return f"{target} {order.direction.upper()}"


def _render_aggregation(
    aggregation: SemanticAggregationIntent,
    entity_tables: dict[str, str],
) -> str:
    if aggregation.function == "count":
        if aggregation.field is None:
            if aggregation.distinct:
                raise SemanticSQLRenderError("count_distinct_target_missing")
            return "COUNT(*)"
        field = _render_field(aggregation.field, entity_tables)
        distinct = "DISTINCT " if aggregation.distinct else ""
        return f"COUNT({distinct}{field})"
    if aggregation.function == "sum" and aggregation.field is not None:
        if aggregation.distinct:
            raise SemanticSQLRenderError("sum_distinct_unsupported")
        return f"SUM({_render_field(aggregation.field, entity_tables)})"
    raise SemanticSQLRenderError("aggregation_unsupported")


def _render_field(
    field: SemanticFieldRef,
    entity_tables: dict[str, str],
) -> str:
    return _render_column(field.entity_id, field.column, entity_tables)


def _render_column(
    entity_id: str,
    column: str,
    entity_tables: dict[str, str],
) -> str:
    table = entity_tables.get(entity_id)
    if table is None:
        raise SemanticSQLRenderError("field_entity_unavailable")
    return f"{table}.{column}"


def _render_day_boundary(value: Any) -> str:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SemanticSQLRenderError("temporal_value_unsupported")
    return f"CURRENT_TIMESTAMP - INTERVAL '{value} days'"


def _render_literal_collection(value: Any) -> str:
    if not isinstance(value, tuple) or not value:
        raise SemanticSQLRenderError("literal_collection_invalid")
    return f"({', '.join(_render_literal(item) for item in value)})"


def _render_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not isfinite(value):
            raise SemanticSQLRenderError("literal_non_finite")
        return repr(value)
    if isinstance(value, str):
        return f"'{value.replace(chr(39), chr(39) * 2)}'"
    raise SemanticSQLRenderError("literal_type_unsupported")


def _deduplicate(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
