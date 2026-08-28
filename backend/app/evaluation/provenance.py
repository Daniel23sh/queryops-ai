from __future__ import annotations

import re
from collections.abc import Sequence

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from app.evaluation.contracts import (
    CanonicalAggregationIdentity,
    CanonicalExpressionIdentity,
    CanonicalFieldIdentity,
    EvaluationComparisonProvenance,
    EvaluationOrderingProvenance,
    EvaluationOutputProvenance,
    EvaluationQueryProvenance,
    EvaluationRowGrainProvenance,
    ProvenanceAuthorizationEvidence,
)


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class EvaluationProvenanceError(ValueError):
    """Raised when safe structural provenance cannot be derived."""

    def __init__(self, reason: str) -> None:
        super().__init__("Evaluation query provenance could not be derived safely.")
        self.reason = reason


def extract_evaluation_query_provenance(
    sql: str,
    *,
    authorization_evidence: ProvenanceAuthorizationEvidence = (
        ProvenanceAuthorizationEvidence.UNVERIFIED
    ),
) -> EvaluationQueryProvenance:
    """Extract sanitized structural identities without retaining SQL or literals."""
    try:
        statement = parse_one(sql, dialect="postgres")
    except (ParseError, TypeError, ValueError):
        raise EvaluationProvenanceError("sql_parse_failed") from None
    if not isinstance(statement, exp.Select):
        raise EvaluationProvenanceError("sql_shape_unsupported")
    if statement.args.get("with_") is not None or len(
        list(statement.find_all(exp.Select))
    ) != 1:
        raise EvaluationProvenanceError("sql_shape_unsupported")

    resolver = _FieldResolver.from_select(statement)
    grouping_fields = _extract_grouping_fields(statement, resolver)
    outputs = _extract_outputs(
        statement.expressions,
        resolver,
        grouping_fields,
        authorization_evidence,
    )
    if len({output.presentation_name for output in outputs}) != len(outputs):
        raise EvaluationProvenanceError("output_name_duplicated")
    output_identities = {
        output.presentation_name: output.identity for output in outputs
    }
    ordering = _extract_ordering(statement, resolver, grouping_fields, output_identities)
    row_grain = _extract_row_grain(
        statement,
        resolver,
        grouping_fields,
        outputs,
    )
    return EvaluationQueryProvenance(
        outputs=outputs,
        grouping_fields=grouping_fields,
        ordering=ordering,
        row_grain=row_grain,
        authorization_evidence=authorization_evidence,
        # The frozen case contract currently records ORDERED_ROWS and baseline SQL,
        # but not which ORDER BY positions are business-significant.
        ordering_significance_explicit=False,
    )


def build_evaluation_comparison_provenance(
    *,
    baseline_sql: str | None,
    final_sql: str | None,
    actual_authorization_evidence: ProvenanceAuthorizationEvidence = (
        ProvenanceAuthorizationEvidence.UNVERIFIED
    ),
) -> EvaluationComparisonProvenance:
    expected = (
        extract_evaluation_query_provenance(
            baseline_sql,
            authorization_evidence=(
                ProvenanceAuthorizationEvidence.FROZEN_BASELINE_VALIDATED
            ),
        )
        if baseline_sql is not None
        else None
    )
    actual = (
        extract_evaluation_query_provenance(
            final_sql,
            authorization_evidence=actual_authorization_evidence,
        )
        if final_sql is not None
        else None
    )
    return EvaluationComparisonProvenance(expected=expected, actual=actual)


class _FieldResolver:
    def __init__(self, *, alias_to_table: dict[str, str], source_tables: tuple[str, ...]):
        self.alias_to_table = alias_to_table
        self.source_tables = source_tables

    @classmethod
    def from_select(cls, statement: exp.Select) -> _FieldResolver:
        from_clause = statement.args.get("from_")
        if from_clause is None or not isinstance(from_clause.this, exp.Table):
            raise EvaluationProvenanceError("source_table_missing")
        table_nodes = [from_clause.this]
        for join in statement.args.get("joins") or ():
            if not isinstance(join, exp.Join) or not isinstance(join.this, exp.Table):
                raise EvaluationProvenanceError("sql_shape_unsupported")
            table_nodes.append(join.this)

        alias_to_table: dict[str, str] = {}
        source_tables: list[str] = []
        for table_node in table_nodes:
            table = _safe_identifier(table_node.name, "table_identifier_invalid")
            alias = _safe_identifier(
                table_node.alias_or_name,
                "table_alias_invalid",
            )
            if alias in alias_to_table:
                raise EvaluationProvenanceError("table_alias_duplicated")
            alias_to_table[alias] = table
            alias_to_table.setdefault(table, table)
            source_tables.append(table)
        return cls(
            alias_to_table=alias_to_table,
            source_tables=tuple(sorted(set(source_tables))),
        )

    def field(self, column: exp.Column) -> CanonicalFieldIdentity:
        column_name = _safe_identifier(column.name, "column_identifier_invalid")
        if column.table:
            qualifier = _safe_identifier(column.table, "column_qualifier_invalid")
            table = self.alias_to_table.get(qualifier)
            if table is None:
                raise EvaluationProvenanceError("column_source_unresolved")
        elif len(self.source_tables) == 1:
            table = self.source_tables[0]
        else:
            raise EvaluationProvenanceError("column_source_ambiguous")
        return CanonicalFieldIdentity(table=table, column=column_name)


def _extract_grouping_fields(
    statement: exp.Select,
    resolver: _FieldResolver,
) -> tuple[CanonicalFieldIdentity, ...]:
    group = statement.args.get("group")
    if group is None:
        return ()
    fields: list[CanonicalFieldIdentity] = []
    for item in group.expressions:
        if not isinstance(item, exp.Column):
            raise EvaluationProvenanceError("grouping_identity_unsupported")
        fields.append(resolver.field(item))
    return tuple(sorted(set(fields)))


def _extract_outputs(
    expressions: Sequence[exp.Expression],
    resolver: _FieldResolver,
    grouping_fields: tuple[CanonicalFieldIdentity, ...],
    authorization_evidence: ProvenanceAuthorizationEvidence,
) -> tuple[EvaluationOutputProvenance, ...]:
    authorized = (
        True
        if authorization_evidence
        in {
            ProvenanceAuthorizationEvidence.FROZEN_BASELINE_VALIDATED,
            ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED,
        }
        else None
    )
    outputs: list[EvaluationOutputProvenance] = []
    for expression in expressions:
        inner = expression.this if isinstance(expression, exp.Alias) else expression
        presentation_name = _presentation_name(expression, inner)
        identity = _expression_identity(inner, resolver, grouping_fields)
        outputs.append(
            EvaluationOutputProvenance(
                presentation_name=presentation_name,
                identity=identity,
                authorized=authorized,
            )
        )
    return tuple(outputs)


def _extract_ordering(
    statement: exp.Select,
    resolver: _FieldResolver,
    grouping_fields: tuple[CanonicalFieldIdentity, ...],
    output_identities: dict[str, CanonicalExpressionIdentity],
) -> tuple[EvaluationOrderingProvenance, ...]:
    order = statement.args.get("order")
    if order is None:
        return ()
    items: list[EvaluationOrderingProvenance] = []
    for position, ordered in enumerate(order.expressions, start=1):
        inner = ordered.this if isinstance(ordered, exp.Ordered) else ordered
        identity: CanonicalExpressionIdentity
        if (
            isinstance(inner, exp.Column)
            and not inner.table
            and inner.name in output_identities
        ):
            identity = output_identities[inner.name]
        else:
            identity = _expression_identity(inner, resolver, grouping_fields)
        items.append(
            EvaluationOrderingProvenance(
                position=position,
                direction=(
                    "desc"
                    if isinstance(ordered, exp.Ordered) and ordered.args.get("desc")
                    else "asc"
                ),
                identity=identity,
            )
        )
    return tuple(items)


def _extract_row_grain(
    statement: exp.Select,
    resolver: _FieldResolver,
    grouping_fields: tuple[CanonicalFieldIdentity, ...],
    outputs: tuple[EvaluationOutputProvenance, ...],
) -> EvaluationRowGrainProvenance:
    if grouping_fields:
        mode = "grouped"
        identities = tuple(_field_identity(field) for field in grouping_fields)
    elif statement.args.get("distinct") is not None:
        mode = "distinct_output"
        identities = tuple(output.identity for output in outputs)
    else:
        mode = "detail"
        identities = ()
    return EvaluationRowGrainProvenance(
        mode=mode,
        identities=identities,
        source_tables=resolver.source_tables,
    )


def _expression_identity(
    expression: exp.Expression,
    resolver: _FieldResolver,
    grouping_fields: tuple[CanonicalFieldIdentity, ...],
) -> CanonicalExpressionIdentity:
    if isinstance(expression, exp.Column):
        return _field_identity(resolver.field(expression))
    if isinstance(expression, exp.AggFunc):
        columns = tuple(resolver.field(column) for column in expression.find_all(exp.Column))
        if len(columns) > 1:
            raise EvaluationProvenanceError("aggregation_target_ambiguous")
        aggregation = CanonicalAggregationIdentity(
            function=_safe_identifier(
                expression.key.lower(),
                "aggregation_function_invalid",
            ),
            target_field=columns[0] if columns else None,
            distinct=expression.find(exp.Distinct) is not None,
            grouping_fields=grouping_fields,
        )
        return CanonicalExpressionIdentity(
            kind="aggregation",
            aggregation=aggregation,
        )
    raise EvaluationProvenanceError("output_identity_unsupported")


def _field_identity(field: CanonicalFieldIdentity) -> CanonicalExpressionIdentity:
    return CanonicalExpressionIdentity(kind="field", field=field)


def _presentation_name(
    expression: exp.Expression,
    inner: exp.Expression,
) -> str:
    alias = expression.alias if isinstance(expression, exp.Alias) else ""
    if alias:
        return _safe_identifier(alias, "output_alias_invalid")
    if isinstance(inner, exp.Column):
        return _safe_identifier(inner.name, "output_name_invalid")
    if isinstance(inner, exp.AggFunc):
        return _safe_identifier(inner.key.lower(), "output_name_invalid")
    raise EvaluationProvenanceError("output_name_unsupported")


def _safe_identifier(value: str, reason: str) -> str:
    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
        raise EvaluationProvenanceError(reason)
    return value
