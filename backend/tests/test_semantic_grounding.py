from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.errors import DomainPackValidationError
from app.query_engine.semantic_catalog import (
    MAX_SEMANTIC_PROJECTION_BYTES,
    SemanticCatalogProjection,
    build_semantic_catalog_projection,
)


@pytest.mark.parametrize(
    "question",
    [
        "Show users that are enabled.",
        "Show accounts that haven't been disabled.",
        "List employees whose directory access is still active.",
        "Show users with active accounts.",
        "List current employees with working accounts.",
    ],
)
def test_directory_paraphrases_receive_bounded_identity_candidates(
    question: str,
) -> None:
    projection = _projection(question)
    observation = projection.as_observation()

    assert observation["selected_entity_ids"] == ["directory_users"]
    assert {
        "active_directory_account",
        "active_employee",
        "active_human_directory_user",
        "human_directory_user",
    } <= set(observation["selected_concept_ids"])
    assert observation["selected_metric_ids"] == ["active_human_users"]
    assert _size(projection) <= MAX_SEMANTIC_PROJECTION_BYTES


def test_exact_metric_is_mandatory_but_negated_literal_is_not() -> None:
    exact = _projection("How many active users are there?")
    assert exact.mandatory_evidence() == {
        "entity_ids": ["directory_users"],
        "concept_ids": [],
        "metric_ids": ["active_human_users"],
        "rule_ids": [],
    }

    literal = _projection("How many users are not disabled?")
    assert literal.mandatory_evidence() == {
        "entity_ids": ["directory_users"],
        "concept_ids": [],
        "metric_ids": [],
        "rule_ids": [],
    }
    assert "active_human_users" in literal.as_observation()["selected_metric_ids"]


@pytest.mark.parametrize("scope_type", ["department", "global"])
def test_exact_rule_is_mandatory_and_scope_language_is_not_business_entity(
    scope_type: str,
) -> None:
    projection = _projection(
        "Show non-compliant devices in my department.",
        scope_type=scope_type,
    )

    assert projection.mandatory_evidence() == {
        "entity_ids": ["devices"],
        "concept_ids": [],
        "metric_ids": [],
        "rule_ids": ["non_compliant_device_posture"],
    }
    assert "departments" not in projection.as_observation()["selected_entity_ids"]
    serialized = json.dumps(projection.as_prompt_dict(), sort_keys=True)
    assert "department-id" not in serialized


def test_resolved_possessive_scope_does_not_force_department_into_mock_plan() -> None:
    projection = _projection(
        "Show unused paid licenses in my department.",
        scope_type="global",
    )

    assert projection.mandatory_evidence() == {
        "entity_ids": ["license_assignments", "licenses"],
        "concept_ids": ["unused_license_assignment"],
        "metric_ids": [],
        "rule_ids": [],
    }
    assert "departments" not in projection.as_observation()["selected_entity_ids"]


def test_non_compliant_status_is_narrower_than_device_posture() -> None:
    status_only = _projection(
        "Show devices with non-compliant status and outdated software."
    )
    posture = _projection("Show non-compliant devices with outdated software.")

    assert status_only.mandatory_evidence()["concept_ids"] == [
        "non_compliant_device",
        "outdated_software_install",
    ]
    assert status_only.mandatory_evidence()["rule_ids"] == []
    assert posture.mandatory_evidence()["rule_ids"] == [
        "non_compliant_device_posture"
    ]


def test_known_value_alone_cannot_anchor_an_entity() -> None:
    projection = _projection("Show active records.")
    assert projection.entities == ()
    assert projection.concepts == ()
    assert projection.metrics == ()


def test_unique_description_fallback_is_narrow_and_ambiguous_fallback_is_empty() -> None:
    devices = _projection("Summarize managed server inventory.")
    assert devices.as_observation()["selected_entity_ids"] == ["devices"]
    assert any(
        signal["tier"] == "description_context"
        for signal in devices.candidate_signals
    )

    ambiguous = _projection("Summarize the relevant records.")
    assert ambiguous.entities == ()
    assert ambiguous.candidate_signals == ()


def test_intermediate_path_entities_do_not_import_unrelated_semantics() -> None:
    projection = _projection("Show devices and access groups.")
    observation = projection.as_observation()

    assert {"devices", "groups"} <= set(observation["selected_entity_ids"])
    path_only_entities = set(observation["selected_entity_ids"]) - {
        "devices",
        "groups",
    }
    assert path_only_entities
    concept_entities = {
        concept["entity_id"] for concept in projection.as_prompt_dict()["concepts"]
    }
    assert not (path_only_entities & concept_entities)


def test_examples_require_direct_evidence_not_broad_entity_context() -> None:
    active = _projection("How many active users are there?")
    assert "active_user_metric" in active.as_observation()["selected_example_ids"]

    broad = _projection("Show directory users.")
    assert broad.as_observation()["selected_example_ids"] == []


def test_projection_trimming_preserves_mandatory_metric_semantics() -> None:
    pack = load_it_operations_domain_pack()
    concepts = tuple(
        replace(concept, description="x" * 20_000)
        if concept.id == "disabled_directory_account"
        else concept
        for concept in pack.semantic_catalog.concepts
    )
    catalog = replace(pack.semantic_catalog, concepts=concepts)

    projection = build_semantic_catalog_projection(
        catalog,
        "How many active users are there?",
        _schema_context(),
        _user_context("global"),
    )

    assert projection.mandatory_evidence()["metric_ids"] == ["active_human_users"]
    assert "disabled_directory_account" not in {
        concept["id"] for concept in projection.concepts
    }
    assert _size(projection) <= MAX_SEMANTIC_PROJECTION_BYTES


def test_mandatory_projection_overflow_fails_closed() -> None:
    pack = load_it_operations_domain_pack()
    metrics = tuple(
        replace(metric, description="x" * 20_000)
        if metric.id == "active_human_users"
        else metric
        for metric in pack.semantic_catalog.metrics
    )
    catalog = replace(pack.semantic_catalog, metrics=metrics)

    with pytest.raises(DomainPackValidationError, match="safe prompt size"):
        build_semantic_catalog_projection(
            catalog,
            "How many active users are there?",
            _schema_context(),
            _user_context("global"),
        )


def _projection(question: str, *, scope_type: str = "global"):
    pack = load_it_operations_domain_pack()
    return build_semantic_catalog_projection(
        pack.semantic_catalog,
        question,
        _schema_context(),
        _user_context(scope_type),
    )


def _schema_context() -> dict[str, object]:
    pack = load_it_operations_domain_pack()
    return {
        "allowed_tables": list(pack.allowed_resource_table_names),
        "allowed_columns": {
            table.name: [column.name for column in table.columns]
            for table in pack.tables
        },
        "tables": [
            {"name": table.name, "scope_column": table.scope_column}
            for table in pack.tables
        ],
    }


def _user_context(scope_type: str) -> dict[str, object]:
    return {
        "scope_type": scope_type,
        "has_global_scope": scope_type == "global",
        "scope_reference_resolved": scope_type != "none",
        "department_id": "department-id-must-not-appear",
    }


def _size(projection: SemanticCatalogProjection) -> int:
    return len(
        json.dumps(
            projection.as_prompt_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
