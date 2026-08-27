from __future__ import annotations

from dataclasses import replace

import pytest

from app.domains.it_operations.metrics import (
    ACTIVE_HUMAN_USERS_METRIC_ID,
    active_human_users_predicates,
    metric_table_dependencies,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.errors import DomainPackValidationError
from app.query_engine.semantic_catalog import (
    SemanticPredicate,
    SemanticPredicateOperator,
    effective_semantic_predicates,
)


def test_active_users_metric_is_the_canonical_three_predicate_definition() -> None:
    pack = load_it_operations_domain_pack()
    metric = pack.semantic_catalog.metrics_by_id[ACTIVE_HUMAN_USERS_METRIC_ID]

    assert {
        (predicate.column, predicate.operator.value, predicate.value)
        for predicate in effective_semantic_predicates(
            pack.semantic_catalog,
            metric.required_concept_ids,
        )
    } == {
        ("account_type", "equals", "human"),
        ("employee_status", "equals", "active"),
        ("account_status", "equals", "active"),
    }
    assert len(active_human_users_predicates(pack)) == 3
    assert metric_table_dependencies(pack, ACTIVE_HUMAN_USERS_METRIC_ID) == {
        "directory_users"
    }


def test_metric_adapter_fails_closed_for_unknown_or_unsupported_definition() -> None:
    pack = load_it_operations_domain_pack()
    with pytest.raises(DomainPackValidationError, match="Unknown semantic metric"):
        metric_table_dependencies(pack, "missing_metric")

    catalog = pack.semantic_catalog
    active_account = catalog.concepts_by_id["active_directory_account"]
    concepts = tuple(
        replace(
            concept,
            required_predicates=(
                SemanticPredicate(
                    column="account_status",
                    operator=SemanticPredicateOperator.OLDER_THAN_DAYS,
                    value=30,
                ),
            ),
        )
        if concept.id == active_account.id
        else concept
        for concept in catalog.concepts
    )
    invalid_pack = replace(pack, semantic_catalog=replace(catalog, concepts=concepts))

    with pytest.raises(DomainPackValidationError, match="unsupported predicate"):
        active_human_users_predicates(invalid_pack)
