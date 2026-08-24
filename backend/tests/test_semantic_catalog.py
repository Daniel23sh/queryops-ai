from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.domains.it_operations.models import Base
from app.domains.it_operations.seed import seed_database
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.evaluation.loader import load_it_operations_evaluation_set
from app.query_engine.errors import DomainPackValidationError
from app.query_engine.semantic_catalog import (
    MAX_SEMANTIC_PROJECTION_BYTES,
    build_semantic_catalog_projection,
    safe_semantic_catalog_observation,
)
from app.query_engine.semantic_catalog_loader import parse_semantic_catalog


CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "domains"
    / "it_operations"
    / "domain_pack"
    / "semantic_catalog.yaml"
)


def test_it_operations_catalog_loads_with_versioned_identity_and_cache() -> None:
    first = load_it_operations_domain_pack()
    second = load_it_operations_domain_pack()
    catalog = first.semantic_catalog

    assert first is second
    assert catalog.id == "it_operations_semantic_catalog"
    assert catalog.version == "1"
    assert catalog.domain_id == "it_operations"
    assert catalog.dataset_id == "it_operations_v1"
    assert len(catalog.digest) == 64
    assert set(catalog.entities_by_id) == set(first.allowed_resource_table_names)
    assert catalog.restricted_tables == ("it_audit_events",)


def test_active_human_directory_user_has_verified_business_predicates() -> None:
    concept = load_it_operations_domain_pack().semantic_catalog.concepts_by_id[
        "active_human_directory_user"
    ]

    assert {
        (predicate.column, predicate.operator.value, predicate.value)
        for predicate in concept.required_predicates
    } == {
        ("account_type", "equals", "human"),
        ("employee_status", "equals", "active"),
        ("account_status", "equals", "active"),
    }
    assert concept.aggregation is not None
    assert concept.aggregation.function == "count"


def test_projection_selects_relevant_semantics_and_resolved_rls_guidance() -> None:
    pack = load_it_operations_domain_pack()
    schema_context = _schema_context(pack)
    user_context = {
        "scope_type": "department",
        "has_global_scope": False,
        "scope_reference_resolved": True,
        "department_id": "must-not-be-projected",
        "user_id": "must-not-be-projected",
    }

    first = build_semantic_catalog_projection(
        pack.semantic_catalog,
        "How many active human directory users are in my department?",
        schema_context,
        user_context,
    )
    second = build_semantic_catalog_projection(
        pack.semantic_catalog,
        "How many active human directory users are in my department?",
        schema_context,
        user_context,
    )
    projected = first.as_prompt_dict()
    serialized = json.dumps(projected, sort_keys=True)

    assert projected == second.as_prompt_dict()
    assert [item["id"] for item in projected["entities"]] == ["directory_users"]
    assert [item["id"] for item in projected["concepts"]] == [
        "active_human_directory_user"
    ]
    predicates = projected["concepts"][0]["required_predicates"]
    assert {
        (item["column"], item["operator"], item["value"])
        for item in predicates
    } == {
        ("account_type", "equals", "human"),
        ("employee_status", "equals", "active"),
        ("account_status", "equals", "active"),
    }
    assert projected["authorization_guidance"][0]["enforcement"] == (
        "postgresql_rls"
    )
    assert projected["authorization_guidance"][0][
        "scope_reference_resolved"
    ] is True
    assert "must-not-be-projected" not in serialized
    assert "it_audit_events" not in serialized
    assert len(serialized.encode("utf-8")) <= MAX_SEMANTIC_PROJECTION_BYTES


def test_projection_falls_back_to_schema_without_inventing_a_concept() -> None:
    pack = load_it_operations_domain_pack()
    projection = build_semantic_catalog_projection(
        pack.semantic_catalog,
        "Summarize the relevant records.",
        _schema_context(pack),
        {"scope_type": "none", "scope_reference_resolved": False},
    )

    assert projection.entities == ()
    assert projection.concepts == ()
    assert projection.authorization_guidance == ()
    assert projection.catalog_hash == pack.semantic_catalog.digest


@pytest.mark.parametrize(
    ("question", "expected_concept"),
    [
        ("Show inactive users.", "inactive_directory_user"),
        ("Show high-confidence unused licenses.", "high_confidence_unused_license_assignment"),
        ("Show failed login spikes.", "failed_login_within_30_days"),
        ("Show devices that have not reported in 30 days.", "stale_device"),
        ("Show unresolved critical security events.", "unresolved_critical_security_event"),
        ("Show active license assignments marked as exceptions.", "active_exception_license_assignment"),
    ],
)
def test_projection_covers_repeated_evaluation_business_concepts(
    question: str,
    expected_concept: str,
) -> None:
    pack = load_it_operations_domain_pack()
    projection = build_semantic_catalog_projection(
        pack.semantic_catalog,
        question,
        _schema_context(pack),
        {"scope_type": "department", "scope_reference_resolved": True},
    )

    assert expected_concept in {
        item["id"] for item in projection.as_prompt_dict()["concepts"]
    }


def test_every_frozen_case_produces_a_bounded_deterministic_safe_projection() -> None:
    pack = load_it_operations_domain_pack()
    schema_context = _schema_context(pack)

    for case in load_it_operations_evaluation_set().cases:
        scope_type = case.required_scope_type or "none"
        user_context = {
            "scope_type": scope_type,
            "scope_reference_resolved": scope_type != "none",
        }
        first = build_semantic_catalog_projection(
            pack.semantic_catalog,
            case.question,
            schema_context,
            user_context,
        )
        second = build_semantic_catalog_projection(
            pack.semantic_catalog,
            case.question,
            schema_context,
            user_context,
        )
        serialized = json.dumps(first.as_prompt_dict(), sort_keys=True)

        assert first.as_prompt_dict() == second.as_prompt_dict()
        assert len(serialized.encode("utf-8")) <= MAX_SEMANTIC_PROJECTION_BYTES
        assert "it_audit_events" not in serialized


def test_successful_free_queries_receive_all_expected_join_entities() -> None:
    pack = load_it_operations_domain_pack()
    schema_context = _schema_context(pack)

    for case in load_it_operations_evaluation_set().cases:
        if (
            case.expected_outcome.value != "success"
            or case.case_type.value != "free_query"
        ):
            continue
        scope_type = case.required_scope_type or "none"
        projection = build_semantic_catalog_projection(
            pack.semantic_catalog,
            case.question,
            schema_context,
            {
                "scope_type": scope_type,
                "scope_reference_resolved": scope_type != "none",
            },
        )

        assert set(case.expected_tables) <= {
            item["table"] for item in projection.entities
        }, case.id


@pytest.mark.parametrize(
    ("table_name", "excluded_column"),
    [("devices", "assigned_user_id"), ("directory_users", "id")],
)
def test_projection_excludes_relationship_with_unauthorized_endpoint_column(
    table_name: str,
    excluded_column: str,
) -> None:
    pack = load_it_operations_domain_pack()
    schema_context = _schema_context(pack)
    schema_context["allowed_columns"][table_name].remove(excluded_column)

    projection = build_semantic_catalog_projection(
        pack.semantic_catalog,
        "Show devices assigned to inactive users.",
        schema_context,
        {"scope_type": "department", "scope_reference_resolved": True},
    )

    assert "device_assignee" not in {
        item["id"] for item in projection.relationships
    }


def test_catalog_relationships_match_declared_foreign_keys() -> None:
    pack = load_it_operations_domain_pack()

    for relationship in pack.semantic_catalog.relationships:
        from_table = pack.semantic_catalog.entities_by_id[
            relationship.from_entity
        ].table
        to_table = pack.semantic_catalog.entities_by_id[relationship.to_entity].table
        column = Base.metadata.tables[from_table].c[relationship.from_column]
        foreign_keys = {
            (foreign_key.column.table.name, foreign_key.column.name)
            for foreign_key in column.foreign_keys
        }

        assert (to_table, relationship.to_column) in foreign_keys
        assert relationship.cardinality.value == "many_to_one"
        assert relationship.optional is column.nullable


def test_catalog_known_values_cover_deterministically_seeded_values() -> None:
    pack = load_it_operations_domain_pack()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db, profile_name="small", reset=True)
        for entity in pack.semantic_catalog.entities:
            table = Base.metadata.tables[entity.table]
            for known_values in entity.known_values:
                actual = set(
                    db.scalars(select(table.c[known_values.column]).distinct())
                )
                assert actual <= set(known_values.values), (
                    entity.id,
                    known_values.column,
                    actual - set(known_values.values),
                )
    engine.dispose()


def test_catalog_digest_is_canonical_and_changes_with_semantics() -> None:
    pack = load_it_operations_domain_pack()
    reordered = _catalog_document()
    reordered["entities"] = list(reversed(reordered["entities"]))
    reordered["relationships"] = list(reversed(reordered["relationships"]))
    reordered["concepts"] = list(reversed(reordered["concepts"]))
    changed = _catalog_document()
    changed["concepts"][0]["description"] += " Verified change."

    assert _parse(reordered).digest == pack.semantic_catalog.digest
    assert _parse(changed).digest != pack.semantic_catalog.digest
    assert "catalog_hash" not in build_semantic_catalog_projection(
        pack.semantic_catalog,
        "active human directory users",
        _schema_context(pack),
        {"scope_type": "department", "scope_reference_resolved": True},
    ).as_prompt_dict()


def test_catalog_observation_accepts_only_fixed_safe_identity_shape() -> None:
    pack = load_it_operations_domain_pack()
    projection = build_semantic_catalog_projection(
        pack.semantic_catalog,
        "active human directory users",
        _schema_context(pack),
        {"scope_type": "department", "scope_reference_resolved": True},
    )
    observation = safe_semantic_catalog_observation(projection.as_observation())

    assert observation == projection.as_observation()
    assert safe_semantic_catalog_observation(
        {**projection.as_observation(), "catalog_hash": "not-a-digest"}
    ) is None


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    [
        (lambda value: value["entities"][0].update(table="missing_table"), "unknown table"),
        (
            lambda value: value["concepts"][0]["required_predicates"][0].update(
                column="missing_column"
            ),
            "unknown column",
        ),
        (
            lambda value: value["concepts"][0]["required_predicates"][0].update(
                operator="contains"
            ),
            "Unsupported semantic predicate operator",
        ),
        (
            lambda value: value["concepts"][0]["required_predicates"][0].update(
                value=["human"]
            ),
            "must be scalar",
        ),
        (
            lambda value: value["concepts"].append(copy.deepcopy(value["concepts"][0])),
            "Duplicate semantic catalog concept id",
        ),
        (
            lambda value: value["restricted_tables"].append("directory_users"),
            "exposed as queryable",
        ),
        (
            lambda value: value["relationships"][0].update(from_column="missing_column"),
            "unknown from column",
        ),
        (
            lambda value: value["relationships"][0].update(cardinality="many_to_many"),
            "Unsupported semantic relationship cardinality",
        ),
        (
            lambda value: value["relationships"][0].update(optional="yes"),
            "must be a boolean",
        ),
        (
            lambda value: value["catalog"].update(dataset_id="other_dataset"),
            "dataset does not match",
        ),
        (
            lambda value: value["authorization_guidance"][0].update(
                scope_entity_id="missing_entity"
            ),
            "unknown scope entity",
        ),
        (
            lambda value: value["concepts"][0]["required_predicates"][0].update(
                operator="within_last_days",
                value=30,
            ),
            "temporal operator requires",
        ),
    ],
)
def test_catalog_validation_rejects_invalid_references_and_shapes(
    mutation: Any,
    error_match: str,
) -> None:
    document = _catalog_document()
    mutation(document)
    with pytest.raises(DomainPackValidationError, match=error_match):
        _parse(document)


def _catalog_document() -> dict[str, Any]:
    loaded = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _parse(document: dict[str, Any]) -> Any:
    pack = load_it_operations_domain_pack()
    return parse_semantic_catalog(
        document,
        domain_id=pack.domain_id,
        expected_catalog_id=pack.semantic_catalog.id,
        expected_catalog_version=pack.semantic_catalog.version,
        expected_dataset_id=pack.semantic_catalog.dataset_id,
        tables_by_name=pack.tables_by_name,
        allowed_resource_table_names=pack.allowed_resource_table_names,
    )


def _schema_context(pack: Any) -> dict[str, Any]:
    return {
        "allowed_tables": list(pack.allowed_resource_table_names),
        "allowed_columns": {
            table_name: sorted(pack.table(table_name).columns_by_name)
            for table_name in pack.allowed_resource_table_names
        },
    }
