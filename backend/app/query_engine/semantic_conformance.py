from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError
from sqlglot.expressions.core import Expression

from app.query_engine.domain_pack import DomainPack
from app.query_engine.semantic_plan import (
    EntitySemanticPredicate,
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticLiteralFilter,
    SemanticOrderIntent,
    ValidatedSemanticPlan,
)
from app.query_engine.sql_validator import SQLValidationResult


class SemanticConformanceReason(str, Enum):
    SQL_PARSE_FAILED = "semantic_sql_parse_failed"
    SQL_SHAPE_UNSUPPORTED = "semantic_sql_shape_unsupported"
    TABLE_MISMATCH = "semantic_table_mismatch"
    COLUMN_UNRESOLVED = "semantic_column_unresolved"
    RELATIONSHIP_MISSING = "semantic_relationship_missing"
    RELATIONSHIP_MISMATCH = "semantic_relationship_mismatch"
    PREDICATE_MISSING = "semantic_predicate_missing"
    PREDICATE_CONFLICT = "semantic_predicate_conflict"
    OR_STRUCTURE_MISMATCH = "semantic_or_structure_mismatch"
    OUTPUT_MISMATCH = "semantic_output_mismatch"
    AGGREGATION_MISMATCH = "semantic_aggregation_mismatch"
    GROUP_BY_MISMATCH = "semantic_group_by_mismatch"
    HAVING_MISMATCH = "semantic_having_mismatch"
    ORDER_BY_MISMATCH = "semantic_order_by_mismatch"
    LIMIT_MISMATCH = "semantic_limit_mismatch"
    EXTRA_FILTER = "semantic_extra_filter"


@dataclass(frozen=True)
class SemanticConformanceResult:
    valid: bool
    reason_code: SemanticConformanceReason | None
    checked_entity_count: int
    checked_predicate_count: int
    checked_relationship_count: int
    checked_aggregation_count: int

    def as_observation(self) -> dict[str, str | int | None]:
        return {
            "status": "passed" if self.valid else "failed",
            "reason_code": self.reason_code.value if self.reason_code else None,
            "checked_entity_count": self.checked_entity_count,
            "checked_predicate_count": self.checked_predicate_count,
            "checked_relationship_count": self.checked_relationship_count,
            "checked_aggregation_count": self.checked_aggregation_count,
        }


@dataclass(frozen=True, order=True)
class _Field:
    entity_id: str
    column: str


@dataclass(frozen=True)
class _Predicate:
    field: _Field
    operator: str
    value: Any


@dataclass(frozen=True)
class _Aggregate:
    function: str
    field: _Field | None
    distinct: bool


@dataclass(frozen=True)
class _Having:
    aggregation: _Aggregate
    operator: str
    value: int | float


@dataclass(frozen=True)
class _Order:
    field: _Field | None
    aggregation: _Aggregate | None
    direction: str


@dataclass(frozen=True)
class _AtomNode:
    predicate: _Predicate


@dataclass(frozen=True)
class _AndNode:
    items: tuple[_BooleanNode, ...]


@dataclass(frozen=True)
class _OrNode:
    items: tuple[_BooleanNode, ...]


_BooleanNode = _AtomNode | _AndNode | _OrNode


@dataclass(frozen=True)
class _ParsedQuery:
    entity_ids: frozenset[str]
    relationships: frozenset[tuple[str, str, str | None]]
    predicates: frozenset[_Predicate]
    or_groups: tuple[tuple[frozenset[_Predicate], ...], ...]
    distinct: bool
    output_fields: frozenset[_Field]
    aggregations: tuple[_Aggregate, ...]
    group_by: frozenset[_Field]
    having: frozenset[_Having]
    order_by: tuple[_Order, ...]
    limit: int | None


class _ConformanceFailure(ValueError):
    def __init__(self, reason: SemanticConformanceReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def check_semantic_conformance(
    *,
    plan: ValidatedSemanticPlan,
    candidate_sql: str,
    safety_result: SQLValidationResult,
    domain_pack: DomainPack,
    schema_context: Mapping[str, Any],
) -> SemanticConformanceResult:
    """Prove that a safety-approved SQL candidate implements its semantic plan."""

    counts = {
        "checked_entity_count": len(plan.plan.entity_ids),
        "checked_predicate_count": len(plan.effective_predicates)
        + len(plan.plan.literal_filters)
        + sum(
            len(branch)
            for group in plan.rule_or_predicate_groups
            for branch in group
        ),
        "checked_relationship_count": len(plan.plan.relationships),
        "checked_aggregation_count": (
            1 if plan.plan.metric_id is not None else len(plan.plan.aggregations)
        ),
    }
    try:
        if not safety_result.valid or safety_result.sanitized_sql is None:
            raise _ConformanceFailure(
                SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED
            )
        # Inspect the exact SQL that the executor will receive.  The original
        # candidate is parsed separately only to distinguish a provider/user
        # LIMIT from the validator's deterministic safety cap.
        candidate = _parse_query(candidate_sql, domain_pack, schema_context)
        parsed = _parse_query(
            safety_result.sanitized_sql,
            domain_pack,
            schema_context,
        )
        if set(safety_result.referenced_tables) != {
            domain_pack.semantic_catalog.entities_by_id[entity_id].table
            for entity_id in parsed.entity_ids
        }:
            raise _ConformanceFailure(SemanticConformanceReason.TABLE_MISMATCH)
        _check_entities(plan, parsed)
        _check_relationships(plan, parsed, domain_pack)
        _check_predicates(plan, parsed)
        _check_outputs(plan, parsed, domain_pack)
        _check_grouping(plan, parsed)
        _check_having(plan, parsed)
        _check_ordering(plan, parsed)
        _check_limit(plan, candidate, parsed)
    except _ConformanceFailure as exc:
        return SemanticConformanceResult(
            valid=False,
            reason_code=exc.reason,
            **counts,
        )
    return SemanticConformanceResult(valid=True, reason_code=None, **counts)


def _parse_query(
    sql: str,
    domain_pack: DomainPack,
    schema_context: Mapping[str, Any],
) -> _ParsedQuery:
    try:
        statement = parse_one(sql, dialect="postgres")
    except (ParseError, ValueError, TypeError):
        raise _ConformanceFailure(SemanticConformanceReason.SQL_PARSE_FAILED) from None
    if not isinstance(statement, exp.Select):
        raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)
    if statement.args.get("with_") is not None:
        raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)
    if len(list(statement.find_all(exp.Select))) != 1 or any(
        statement.find(node_type) is not None
        for node_type in (
            exp.Subquery,
            exp.Union,
            exp.Intersect,
            exp.Except,
            exp.Window,
            exp.Lateral,
        )
    ):
        raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)

    from_clause = statement.args.get("from_")
    if from_clause is None or not isinstance(from_clause.this, exp.Table):
        raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)
    table_nodes = [from_clause.this]
    joins = tuple(statement.args.get("joins") or ())
    for join in joins:
        if not isinstance(join, exp.Join) or not isinstance(join.this, exp.Table):
            raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)
        table_nodes.append(join.this)

    table_to_entity = {
        entity.table: entity.id for entity in domain_pack.semantic_catalog.entities
    }
    alias_to_table: dict[str, str] = {}
    actual_tables: list[str] = []
    for table_node in table_nodes:
        table_name = table_node.name
        alias = table_node.alias_or_name
        if table_name not in table_to_entity or alias in alias_to_table:
            raise _ConformanceFailure(SemanticConformanceReason.TABLE_MISMATCH)
        if table_name in actual_tables:
            raise _ConformanceFailure(
                SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED
            )
        actual_tables.append(table_name)
        alias_to_table[alias] = table_name
        alias_to_table.setdefault(table_name, table_name)

    resolver = _ColumnResolver(
        alias_to_table=alias_to_table,
        actual_tables=tuple(actual_tables),
        domain_pack=domain_pack,
        schema_context=schema_context,
    )
    relationship_by_id = {
        relationship.id: relationship
        for relationship in domain_pack.semantic_catalog.relationships
    }
    selected_relationships: set[tuple[str, str, str | None]] = set()
    residual_nodes: list[_BooleanNode] = []
    for join in joins:
        join_type = _join_type(join)
        joined_table = join.this.name
        joined_entity_id = table_to_entity[joined_table]
        on_expression = join.args.get("on")
        if on_expression is None:
            raise _ConformanceFailure(SemanticConformanceReason.RELATIONSHIP_MISSING)
        relationship_id: str | None = None
        for term in _flatten_sql_and(on_expression):
            candidate_id = _relationship_for_expression(
                term,
                resolver,
                relationship_by_id,
            )
            if candidate_id is not None:
                if relationship_id is not None:
                    raise _ConformanceFailure(
                        SemanticConformanceReason.RELATIONSHIP_MISMATCH
                    )
                relationship_id = candidate_id
            else:
                residual_nodes.append(_normalize_boolean(term, resolver))
        if relationship_id is None:
            raise _ConformanceFailure(SemanticConformanceReason.RELATIONSHIP_MISSING)
        # INNER joins are direction-independent.  LEFT joins are not: the
        # relationship's ``from_entity`` is the preserved side and its
        # ``to_entity`` must be the newly joined nullable side.
        nullable_entity_id = joined_entity_id if join_type == "left" else None
        selected_relationships.add(
            (relationship_id, join_type, nullable_entity_id)
        )

    where = statement.args.get("where")
    if where is not None:
        residual_nodes.append(_normalize_boolean(where.this, resolver))
    combined = _AndNode(tuple(residual_nodes)) if residual_nodes else None
    predicates, or_groups = _extract_filter_requirements(combined)

    output_fields: set[_Field] = set()
    aggregations: list[_Aggregate] = []
    aliases: dict[str, _Field | _Aggregate] = {}
    for expression in statement.expressions:
        alias = expression.alias if isinstance(expression, exp.Alias) else ""
        inner = expression.this if isinstance(expression, exp.Alias) else expression
        if isinstance(inner, exp.Column):
            field = resolver.resolve(inner)
            output_fields.add(field)
            if alias:
                aliases[alias] = field
        else:
            aggregate = _parse_aggregate(inner, resolver)
            aggregations.append(aggregate)
            if alias:
                aliases[alias] = aggregate
    if len(output_fields) + len(aggregations) != len(statement.expressions):
        raise _ConformanceFailure(SemanticConformanceReason.OUTPUT_MISMATCH)

    group = statement.args.get("group")
    group_by = frozenset(
        resolver.resolve(item)
        for item in (group.expressions if group is not None else ())
        if isinstance(item, exp.Column)
    )
    if group is not None and len(group_by) != len(group.expressions):
        raise _ConformanceFailure(SemanticConformanceReason.GROUP_BY_MISMATCH)

    having = statement.args.get("having")
    having_items = frozenset(
        _parse_having(item, resolver)
        for item in (_flatten_sql_and(having.this) if having is not None else ())
    )

    order = statement.args.get("order")
    order_by = tuple(
        _parse_order(item, resolver, aliases)
        for item in (order.expressions if order is not None else ())
    )

    limit_node = statement.args.get("limit")
    limit: int | None = None
    if limit_node is not None:
        literal = limit_node.expression
        if not isinstance(literal, exp.Literal) or literal.is_string:
            raise _ConformanceFailure(SemanticConformanceReason.LIMIT_MISMATCH)
        try:
            limit = int(literal.this)
        except (TypeError, ValueError):
            raise _ConformanceFailure(
                SemanticConformanceReason.LIMIT_MISMATCH
            ) from None

    return _ParsedQuery(
        entity_ids=frozenset(table_to_entity[table] for table in actual_tables),
        relationships=frozenset(selected_relationships),
        predicates=frozenset(predicates),
        or_groups=or_groups,
        distinct=statement.args.get("distinct") is not None,
        output_fields=frozenset(output_fields),
        aggregations=tuple(aggregations),
        group_by=group_by,
        having=having_items,
        order_by=order_by,
        limit=limit,
    )


class _ColumnResolver:
    def __init__(
        self,
        *,
        alias_to_table: Mapping[str, str],
        actual_tables: tuple[str, ...],
        domain_pack: DomainPack,
        schema_context: Mapping[str, Any],
    ) -> None:
        self._alias_to_table = alias_to_table
        self._actual_tables = actual_tables
        self._domain_pack = domain_pack
        allowed = schema_context.get("allowed_columns")
        self._allowed_columns = allowed if isinstance(allowed, Mapping) else {}
        self._entity_by_table = {
            entity.table: entity.id
            for entity in domain_pack.semantic_catalog.entities
        }

    def resolve(self, column: exp.Column) -> _Field:
        column_name = column.name
        if not column_name:
            raise _ConformanceFailure(SemanticConformanceReason.COLUMN_UNRESOLVED)
        qualifier = column.table
        if qualifier:
            table = self._alias_to_table.get(qualifier)
            if table is None:
                raise _ConformanceFailure(
                    SemanticConformanceReason.COLUMN_UNRESOLVED
                )
        else:
            candidates = [
                table
                for table in self._actual_tables
                if column_name in self._domain_pack.tables_by_name[table].columns_by_name
            ]
            if len(candidates) != 1:
                raise _ConformanceFailure(
                    SemanticConformanceReason.COLUMN_UNRESOLVED
                )
            table = candidates[0]
        allowed = self._allowed_columns.get(table)
        if not isinstance(allowed, list | tuple) or column_name not in allowed:
            raise _ConformanceFailure(SemanticConformanceReason.COLUMN_UNRESOLVED)
        return _Field(self._entity_by_table[table], column_name)


def _join_type(join: exp.Join) -> str:
    side = str(join.args.get("side") or "").upper()
    kind = str(join.args.get("kind") or "").upper()
    if side == "LEFT":
        return "left"
    if not side and kind not in {"CROSS", "NATURAL"}:
        return "inner"
    raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)


def _relationship_for_expression(
    expression: Expression,
    resolver: _ColumnResolver,
    relationships: Mapping[str, Any],
) -> str | None:
    if not isinstance(expression, exp.EQ):
        return None
    if not isinstance(expression.this, exp.Column) or not isinstance(
        expression.expression, exp.Column
    ):
        return None
    left = resolver.resolve(expression.this)
    right = resolver.resolve(expression.expression)
    matches = [
        relationship_id
        for relationship_id, relationship in relationships.items()
        if {
            (relationship.from_entity, relationship.from_column),
            (relationship.to_entity, relationship.to_column),
        }
        == {(left.entity_id, left.column), (right.entity_id, right.column)}
    ]
    if len(matches) != 1:
        raise _ConformanceFailure(SemanticConformanceReason.RELATIONSHIP_MISMATCH)
    return matches[0]


def _normalize_boolean(
    expression: Expression,
    resolver: _ColumnResolver,
) -> _BooleanNode:
    if isinstance(expression, exp.Paren):
        return _normalize_boolean(expression.this, resolver)
    if isinstance(expression, exp.And):
        return _AndNode(
            (
                _normalize_boolean(expression.this, resolver),
                _normalize_boolean(expression.expression, resolver),
            )
        )
    if isinstance(expression, exp.Or):
        node = _OrNode(
            (
                _normalize_boolean(expression.this, resolver),
                _normalize_boolean(expression.expression, resolver),
            )
        )
        return _collapse_special_or(node)
    return _AtomNode(_parse_predicate(expression, resolver))


def _parse_predicate(
    expression: Expression,
    resolver: _ColumnResolver,
) -> _Predicate:
    if isinstance(expression, exp.Not):
        inner = expression.this
        while isinstance(inner, exp.Paren):
            inner = inner.this
        if isinstance(inner, exp.EQ):
            return _binary_literal_predicate(inner, resolver, "not_equals")
        if isinstance(inner, exp.In):
            return _in_predicate(inner, resolver, "not_in")
        raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)
    if isinstance(expression, exp.EQ):
        return _binary_literal_predicate(expression, resolver, "equals")
    if isinstance(expression, exp.NEQ):
        return _binary_literal_predicate(expression, resolver, "not_equals")
    if isinstance(expression, exp.In):
        return _in_predicate(expression, resolver, "in")
    if isinstance(expression, exp.Is) and isinstance(expression.this, exp.Column):
        field = resolver.resolve(expression.this)
        if isinstance(expression.expression, exp.Null):
            return _Predicate(field, "is_null", None)
        if isinstance(expression.expression, exp.Boolean):
            return _Predicate(field, "equals", bool(expression.expression.this))
    if isinstance(expression, exp.LT):
        temporal = _temporal_predicate(expression, resolver, "older_than_days")
        if temporal is not None:
            return temporal
    if isinstance(expression, exp.GTE):
        temporal = _temporal_predicate(expression, resolver, "within_last_days")
        if temporal is not None:
            return temporal
    raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)


def _binary_literal_predicate(
    expression: exp.Binary,
    resolver: _ColumnResolver,
    operator: str,
) -> _Predicate:
    left, right = expression.this, expression.expression
    if isinstance(left, exp.Column):
        return _Predicate(resolver.resolve(left), operator, _literal_value(right))
    if isinstance(right, exp.Column):
        return _Predicate(resolver.resolve(right), operator, _literal_value(left))
    raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)


def _in_predicate(
    expression: exp.In,
    resolver: _ColumnResolver,
    operator: str,
) -> _Predicate:
    if not isinstance(expression.this, exp.Column) or expression.args.get("query"):
        raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)
    values = tuple(sorted((_literal_value(item) for item in expression.expressions), key=repr))
    if not values:
        raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)
    if operator == "not_in" and len(values) == 1:
        return _Predicate(resolver.resolve(expression.this), "not_equals", values[0])
    return _Predicate(resolver.resolve(expression.this), operator, values)


def _temporal_predicate(
    expression: exp.Binary,
    resolver: _ColumnResolver,
    operator: str,
) -> _Predicate | None:
    if not isinstance(expression.this, exp.Column):
        return None
    right = expression.expression
    if not isinstance(right, exp.Sub) or not isinstance(
        right.this, exp.CurrentTimestamp
    ):
        return None
    days = _interval_days(right.expression)
    if days is None:
        return None
    return _Predicate(resolver.resolve(expression.this), operator, days)


def _interval_days(expression: Expression) -> int | None:
    interval = expression.this if isinstance(expression, exp.Paren) else expression
    multiplier = 1
    if isinstance(interval, exp.Mul):
        if not isinstance(interval.this, exp.Literal) or interval.this.is_string:
            return None
        try:
            multiplier = int(interval.this.this)
        except (TypeError, ValueError):
            return None
        interval = interval.expression
    if not isinstance(interval, exp.Interval):
        return None
    unit = str(interval.args.get("unit") or "").lower()
    if unit not in {"day", "days"} or not isinstance(interval.this, exp.Literal):
        return None
    try:
        days = int(interval.this.this) * multiplier
    except (TypeError, ValueError):
        return None
    return days


def _literal_value(expression: Expression) -> str | int | float | bool:
    if isinstance(expression, exp.Boolean):
        return bool(expression.this)
    if not isinstance(expression, exp.Literal):
        raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)
    if expression.is_string:
        return str(expression.this)
    text = str(expression.this)
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            raise _ConformanceFailure(
                SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED
            ) from None


def _collapse_special_or(node: _OrNode) -> _BooleanNode:
    branches = _or_branches(node)
    atoms = [next(iter(branch)) for branch in branches if len(branch) == 1]
    if len(atoms) == len(branches) and atoms:
        fields = {atom.field for atom in atoms}
        if len(fields) == 1 and all(atom.operator == "equals" for atom in atoms):
            values = tuple(sorted((atom.value for atom in atoms), key=repr))
            return _AtomNode(_Predicate(atoms[0].field, "in", values))
        if len(atoms) == 2:
            null_atom = next(
                (atom for atom in atoms if atom.operator == "is_null"), None
            )
            older_atom = next(
                (atom for atom in atoms if atom.operator == "older_than_days"),
                None,
            )
            if null_atom is not None and older_atom is not None and (
                null_atom.field == older_atom.field
            ):
                return _AtomNode(
                    _Predicate(
                        older_atom.field,
                        "is_null_or_older_than_days",
                        older_atom.value,
                    )
                )
    return node


def _extract_filter_requirements(
    node: _BooleanNode | None,
) -> tuple[set[_Predicate], tuple[tuple[frozenset[_Predicate], ...], ...]]:
    if node is None:
        return set(), ()
    top_items = node.items if isinstance(node, _AndNode) else (node,)
    predicates: set[_Predicate] = set()
    groups: list[tuple[frozenset[_Predicate], ...]] = []
    for item in top_items:
        if isinstance(item, _AtomNode):
            predicates.add(item.predicate)
        elif isinstance(item, _OrNode):
            groups.append(_or_branches(item))
        elif isinstance(item, _AndNode):
            nested_predicates, nested_groups = _extract_filter_requirements(item)
            predicates.update(nested_predicates)
            groups.extend(nested_groups)
        else:
            raise _ConformanceFailure(
                SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED
            )
    return predicates, tuple(sorted(groups, key=repr))


def _or_branches(node: _OrNode) -> tuple[frozenset[_Predicate], ...]:
    raw_branches: list[_BooleanNode] = []

    def collect(item: _BooleanNode) -> None:
        if isinstance(item, _OrNode):
            for nested in item.items:
                collect(nested)
        else:
            raw_branches.append(item)

    collect(node)
    branches: list[frozenset[_Predicate]] = []
    for branch in raw_branches:
        branches.append(frozenset(_and_branch_predicates(branch)))
    return tuple(sorted(branches, key=repr))


def _and_branch_predicates(node: _BooleanNode) -> tuple[_Predicate, ...]:
    if isinstance(node, _AtomNode):
        return (node.predicate,)
    if isinstance(node, _AndNode):
        return tuple(
            predicate
            for item in node.items
            for predicate in _and_branch_predicates(item)
        )
    raise _ConformanceFailure(SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED)


def _flatten_sql_and(expression: Expression) -> tuple[Expression, ...]:
    if isinstance(expression, exp.Paren):
        return _flatten_sql_and(expression.this)
    if isinstance(expression, exp.And):
        return (*_flatten_sql_and(expression.this), *_flatten_sql_and(expression.expression))
    return (expression,)


def _parse_aggregate(
    expression: Expression,
    resolver: _ColumnResolver,
) -> _Aggregate:
    if isinstance(expression, exp.Count):
        target = expression.this
        distinct = isinstance(target, exp.Distinct)
        if distinct:
            expressions = target.expressions
            if len(expressions) != 1 or not isinstance(expressions[0], exp.Column):
                raise _ConformanceFailure(
                    SemanticConformanceReason.AGGREGATION_MISMATCH
                )
            return _Aggregate("count", resolver.resolve(expressions[0]), True)
        if isinstance(target, exp.Column):
            return _Aggregate("count", resolver.resolve(target), False)
        if isinstance(target, exp.Star) or (
            isinstance(target, exp.Literal)
            and not target.is_string
            and str(target.this) == "1"
        ):
            return _Aggregate("count", None, False)
    if isinstance(expression, exp.Sum) and isinstance(expression.this, exp.Column):
        return _Aggregate("sum", resolver.resolve(expression.this), False)
    raise _ConformanceFailure(SemanticConformanceReason.AGGREGATION_MISMATCH)


def _parse_having(
    expression: Expression,
    resolver: _ColumnResolver,
) -> _Having:
    operators: tuple[tuple[type[exp.Binary], str, str], ...] = (
        (exp.EQ, "equals", "equals"),
        (exp.GT, "greater_than", "less_than"),
        (exp.GTE, "greater_than_or_equal", "less_than_or_equal"),
        (exp.LT, "less_than", "greater_than"),
        (exp.LTE, "less_than_or_equal", "greater_than_or_equal"),
    )
    for expression_type, direct, reversed_operator in operators:
        if isinstance(expression, expression_type):
            if isinstance(expression.this, exp.AggFunc):
                aggregate = _parse_aggregate(
                    cast(Expression, expression.this),
                    resolver,
                )
                value = _literal_value(expression.expression)
                operator = direct
            elif isinstance(expression.expression, exp.AggFunc):
                aggregate = _parse_aggregate(
                    cast(Expression, expression.expression),
                    resolver,
                )
                value = _literal_value(expression.this)
                operator = reversed_operator
            else:
                break
            if not isinstance(value, int | float) or isinstance(value, bool):
                break
            return _Having(aggregate, operator, value)
    raise _ConformanceFailure(SemanticConformanceReason.HAVING_MISMATCH)


def _parse_order(
    expression: Expression,
    resolver: _ColumnResolver,
    aliases: Mapping[str, _Field | _Aggregate],
) -> _Order:
    if not isinstance(expression, exp.Ordered):
        raise _ConformanceFailure(SemanticConformanceReason.ORDER_BY_MISMATCH)
    target = expression.this
    direction = "desc" if expression.args.get("desc") is True else "asc"
    if isinstance(target, exp.Column) and not target.table and target.name in aliases:
        resolved = aliases[target.name]
        if isinstance(resolved, _Field):
            return _Order(resolved, None, direction)
        return _Order(None, resolved, direction)
    if isinstance(target, exp.Column):
        return _Order(resolver.resolve(target), None, direction)
    if isinstance(target, exp.AggFunc):
        return _Order(
            None,
            _parse_aggregate(cast(Expression, target), resolver),
            direction,
        )
    raise _ConformanceFailure(SemanticConformanceReason.ORDER_BY_MISMATCH)


def _check_entities(plan: ValidatedSemanticPlan, parsed: _ParsedQuery) -> None:
    if frozenset(plan.plan.entity_ids) != parsed.entity_ids:
        raise _ConformanceFailure(SemanticConformanceReason.TABLE_MISMATCH)


def _check_relationships(
    plan: ValidatedSemanticPlan,
    parsed: _ParsedQuery,
    domain_pack: DomainPack,
) -> None:
    catalog_relationships = {
        relationship.id: relationship
        for relationship in domain_pack.semantic_catalog.relationships
    }
    expected = frozenset(
        (
            item.relationship_id,
            item.join_type,
            catalog_relationships[item.relationship_id].to_entity
            if item.join_type == "left"
            else None,
        )
        for item in plan.plan.relationships
    )
    if expected == parsed.relationships:
        return
    if {item[0] for item in expected} - {item[0] for item in parsed.relationships}:
        raise _ConformanceFailure(SemanticConformanceReason.RELATIONSHIP_MISSING)
    raise _ConformanceFailure(SemanticConformanceReason.RELATIONSHIP_MISMATCH)


def _check_predicates(plan: ValidatedSemanticPlan, parsed: _ParsedQuery) -> None:
    expected = {
        _catalog_predicate(predicate) for predicate in plan.effective_predicates
    }
    expected.update(_literal_filter(item) for item in plan.plan.literal_filters)
    missing = expected - parsed.predicates
    if missing:
        actual_fields = {item.field for item in parsed.predicates}
        reason = (
            SemanticConformanceReason.PREDICATE_CONFLICT
            if any(item.field in actual_fields for item in missing)
            else SemanticConformanceReason.PREDICATE_MISSING
        )
        raise _ConformanceFailure(reason)

    expected_groups = tuple(
        sorted(
            (
                tuple(
                    sorted(
                        (
                            frozenset(_catalog_predicate(item) for item in branch)
                            for branch in group
                        ),
                        key=repr,
                    )
                )
                for group in plan.rule_or_predicate_groups
            ),
            key=repr,
        )
    )
    if expected_groups != parsed.or_groups:
        raise _ConformanceFailure(SemanticConformanceReason.OR_STRUCTURE_MISMATCH)
    extras = parsed.predicates - expected
    if extras:
        raise _ConformanceFailure(SemanticConformanceReason.EXTRA_FILTER)


def _catalog_predicate(predicate: EntitySemanticPredicate) -> _Predicate:
    value = tuple(predicate.value) if isinstance(predicate.value, tuple) else predicate.value
    return _Predicate(
        _Field(predicate.entity_id, predicate.column),
        predicate.operator.value,
        value,
    )


def _literal_filter(literal_filter: SemanticLiteralFilter) -> _Predicate:
    value = (
        tuple(literal_filter.value)
        if isinstance(literal_filter.value, tuple)
        else literal_filter.value
    )
    return _Predicate(
        _Field(literal_filter.field.entity_id, literal_filter.field.column),
        literal_filter.operator,
        value,
    )


def _check_outputs(
    plan: ValidatedSemanticPlan,
    parsed: _ParsedQuery,
    domain_pack: DomainPack,
) -> None:
    if parsed.distinct is not plan.plan.distinct:
        raise _ConformanceFailure(SemanticConformanceReason.OUTPUT_MISMATCH)
    if plan.plan.metric_id is not None:
        if parsed.output_fields or len(parsed.aggregations) != 1:
            raise _ConformanceFailure(SemanticConformanceReason.AGGREGATION_MISMATCH)
        metric = domain_pack.semantic_catalog.metrics_by_id[plan.plan.metric_id]
        aggregate = parsed.aggregations[0]
        if aggregate.function != metric.aggregation.function or aggregate.distinct:
            raise _ConformanceFailure(SemanticConformanceReason.AGGREGATION_MISMATCH)
        if aggregate.field is not None:
            entity = domain_pack.semantic_catalog.entities_by_id[metric.entity_id]
            column = domain_pack.tables_by_name[entity.table].columns_by_name.get(
                aggregate.field.column
            )
            if aggregate.field.entity_id != metric.entity_id or column is None or column.nullable:
                raise _ConformanceFailure(
                    SemanticConformanceReason.AGGREGATION_MISMATCH
                )
        return

    expected_fields = frozenset(_plan_field(item) for item in plan.plan.output_fields)
    if expected_fields != parsed.output_fields:
        raise _ConformanceFailure(SemanticConformanceReason.OUTPUT_MISMATCH)
    expected_aggregations = tuple(
        sorted((_plan_aggregate(item) for item in plan.plan.aggregations), key=repr)
    )
    if expected_aggregations != tuple(sorted(parsed.aggregations, key=repr)):
        raise _ConformanceFailure(SemanticConformanceReason.AGGREGATION_MISMATCH)


def _check_grouping(plan: ValidatedSemanticPlan, parsed: _ParsedQuery) -> None:
    expected = frozenset(_plan_field(item) for item in plan.plan.group_by)
    if expected != parsed.group_by:
        raise _ConformanceFailure(SemanticConformanceReason.GROUP_BY_MISMATCH)


def _check_having(plan: ValidatedSemanticPlan, parsed: _ParsedQuery) -> None:
    by_id = {item.id: _plan_aggregate(item) for item in plan.plan.aggregations}
    expected = frozenset(
        _Having(by_id[item.aggregation_id], item.operator, item.value)
        for item in plan.plan.having
    )
    if expected != parsed.having:
        raise _ConformanceFailure(SemanticConformanceReason.HAVING_MISMATCH)


def _check_ordering(plan: ValidatedSemanticPlan, parsed: _ParsedQuery) -> None:
    by_id = {item.id: _plan_aggregate(item) for item in plan.plan.aggregations}
    expected = tuple(_plan_order(item, by_id) for item in plan.plan.order_by)
    if expected != parsed.order_by:
        raise _ConformanceFailure(SemanticConformanceReason.ORDER_BY_MISMATCH)


def _check_limit(
    plan: ValidatedSemanticPlan,
    candidate: _ParsedQuery,
    execution: _ParsedQuery,
) -> None:
    requested = plan.plan.limit
    if requested is None:
        # A provider-added limit changes the requested semantics.  A limit
        # appearing only in the safety-approved execution SQL is the existing
        # validator's bounded result cap and is intentionally allowed.
        if candidate.limit is not None:
            raise _ConformanceFailure(SemanticConformanceReason.LIMIT_MISMATCH)
        return
    if candidate.limit != requested or execution.limit != requested:
        raise _ConformanceFailure(SemanticConformanceReason.LIMIT_MISMATCH)


def _plan_field(field: SemanticFieldRef) -> _Field:
    return _Field(field.entity_id, field.column)


def _plan_aggregate(aggregation: SemanticAggregationIntent) -> _Aggregate:
    return _Aggregate(
        aggregation.function,
        _plan_field(aggregation.field) if aggregation.field is not None else None,
        aggregation.distinct,
    )


def _plan_order(
    order: SemanticOrderIntent,
    aggregations: Mapping[str, _Aggregate],
) -> _Order:
    if order.field is not None:
        return _Order(_plan_field(order.field), None, order.direction)
    if order.aggregation_id is None or order.aggregation_id not in aggregations:
        raise _ConformanceFailure(SemanticConformanceReason.ORDER_BY_MISMATCH)
    return _Order(None, aggregations[order.aggregation_id], order.direction)
