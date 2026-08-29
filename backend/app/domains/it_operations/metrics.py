from __future__ import annotations

from sqlalchemy.sql.elements import ColumnElement

from app.domains.it_operations.models import DirectoryUser
from app.query_engine.domain_pack import DomainPack
from app.query_engine.errors import DomainPackValidationError
from app.query_engine.semantic_catalog import (
    SemanticPredicateOperator,
    effective_semantic_predicates,
)


ACTIVE_HUMAN_USERS_METRIC_ID = "active_human_users"


def metric_table_dependencies(
    domain_pack: DomainPack,
    metric_id: str,
) -> frozenset[str]:
    metric = domain_pack.semantic_catalog.metrics_by_id.get(metric_id)
    if metric is None:
        raise DomainPackValidationError(f"Unknown semantic metric: {metric_id}")
    entity = domain_pack.semantic_catalog.entities_by_id[metric.entity_id]
    return frozenset({entity.table})


def active_human_users_predicates(
    domain_pack: DomainPack,
) -> tuple[ColumnElement[bool], ...]:
    """Build the Home metric from the catalog-owned business definition."""

    catalog = domain_pack.semantic_catalog
    metric = catalog.metrics_by_id.get(ACTIVE_HUMAN_USERS_METRIC_ID)
    if metric is None or metric.entity_id != "directory_users":
        raise DomainPackValidationError(
            "The active-human-users metric has an invalid catalog definition"
        )

    expressions: list[ColumnElement[bool]] = []
    for predicate in effective_semantic_predicates(
        catalog,
        metric.required_concept_ids,
    ):
        column = DirectoryUser.__table__.columns.get(predicate.column)
        if column is None:
            raise DomainPackValidationError(
                "The active-human-users metric references an unknown column"
            )
        if predicate.operator is SemanticPredicateOperator.EQUALS:
            expressions.append(column == predicate.value)
        elif predicate.operator is SemanticPredicateOperator.IN and isinstance(
            predicate.value, tuple
        ):
            expressions.append(column.in_(predicate.value))
        else:
            raise DomainPackValidationError(
                "The active-human-users metric uses an unsupported predicate"
            )
    if not expressions:
        raise DomainPackValidationError(
            "The active-human-users metric has no effective predicates"
        )
    return tuple(expressions)
