from __future__ import annotations

import ast
import json
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

import pytest

from app.evaluation.loader import load_it_operations_evaluation_set
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.errors import DomainPackValidationError
from app.query_engine.result_intent import GroundedFieldIdentity
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
        "entity_ids": ["license_assignments"],
        "concept_ids": ["unused_license_assignment"],
        "metric_ids": [],
        "rule_ids": [],
    }
    assert "departments" not in projection.as_observation()["selected_entity_ids"]
    assert "licenses" in projection.as_observation()["selected_entity_ids"]


def test_specific_license_assignment_phrase_keeps_license_lookup_optional() -> None:
    projection = _projection("Show active license assignments.")

    assert projection.mandatory_evidence()["entity_ids"] == [
        "license_assignments"
    ]
    assert {"license_assignments", "licenses"} <= set(
        projection.as_observation()["selected_entity_ids"]
    )
    assert {
        signal["tier"]
        for signal in projection.candidate_signals
        if signal["kind"] == "entity" and signal["id"] == "licenses"
    } == {"lexical_context"}


@pytest.mark.parametrize(
    "question",
    [
        "Show license assignments with license product name.",
        "Show license assignments with vendor and monthly cost.",
    ],
)
def test_explicit_license_product_attributes_keep_lookup_mandatory(
    question: str,
) -> None:
    projection = _projection(question)

    assert {"license_assignments", "licenses"} <= set(
        projection.mandatory_evidence()["entity_ids"]
    )


def test_fact_identity_keeps_generic_user_lookup_optional() -> None:
    projection = _projection(
        "Show users with more than five failed logins in the last 30 days."
    )

    assert projection.mandatory_evidence()["entity_ids"] == ["login_events"]
    assert "directory_users" in projection.as_observation()["selected_entity_ids"]


@pytest.mark.parametrize("attribute", ["full name", "email"])
def test_user_display_attribute_keeps_directory_lookup_mandatory(
    attribute: str,
) -> None:
    projection = _projection(
        f"Show user {attribute} with more than five failed logins in the last 30 days."
    )

    assert {"directory_users", "login_events"} <= set(
        projection.mandatory_evidence()["entity_ids"]
    )


def test_non_overlapping_specific_entity_mentions_remain_mandatory() -> None:
    projection = _projection("Show license assignments and license products.")

    assert {"license_assignments", "licenses"} <= set(
        projection.mandatory_evidence()["entity_ids"]
    )


def test_exact_concept_base_entity_remains_mandatory() -> None:
    projection = _projection("Show high-confidence unused licenses.")

    assert "high_confidence_unused_license_assignment" in (
        projection.mandatory_evidence()["concept_ids"]
    )
    assert projection.mandatory_evidence()["entity_ids"] == [
        "license_assignments"
    ]


def test_medium_011_retains_complete_composed_concept_definition() -> None:
    case = load_it_operations_evaluation_set().cases_by_id[
        "itops-medium-011"
    ]
    projection = _projection(
        case.question,
        scope_type=case.required_scope_type or "none",
    )
    concept_ids = set(projection.as_observation()["selected_concept_ids"])

    assert {
        "active_directory_account",
        "terminated_employee",
        "terminated_employee_with_active_account",
    } <= concept_ids
    assert projection.mandatory_evidence()["concept_ids"] == [
        "terminated_employee_with_active_account"
    ]
    _assert_no_dangling_concept_dependencies(projection)
    assert _size(projection) <= MAX_SEMANTIC_PROJECTION_BYTES


def test_composed_concept_dependency_closure_is_recursive() -> None:
    pack = load_it_operations_domain_pack()
    concepts = tuple(
        replace(concept, all_of_concept_ids=("terminated_employee",))
        if concept.id == "active_directory_account"
        else replace(
            concept,
            all_of_concept_ids=("active_directory_account",),
        )
        if concept.id == "terminated_employee_with_active_account"
        else concept
        for concept in pack.semantic_catalog.concepts
    )
    catalog = replace(pack.semantic_catalog, concepts=concepts)

    projection = build_semantic_catalog_projection(
        catalog,
        "Show terminated employees with active directory accounts.",
        _schema_context(),
        _user_context("department"),
    )
    concept_ids = projection.as_observation()["selected_concept_ids"]
    expected_closure = {
        "active_directory_account",
        "terminated_employee",
        "terminated_employee_with_active_account",
    }

    assert expected_closure <= set(concept_ids)
    assert [item for item in concept_ids if item in expected_closure] == [
        concept.id
        for concept in catalog.concepts
        if concept.id in expected_closure
    ]
    assert projection.mandatory_evidence()["concept_ids"] == [
        "terminated_employee_with_active_account"
    ]
    _assert_no_dangling_concept_dependencies(projection)


def test_shared_composed_concept_dependency_is_deduplicated() -> None:
    projection = _projection(
        "Show active human users and terminated employees with active directory accounts."
    )
    concept_ids = projection.as_observation()["selected_concept_ids"]

    assert {
        "active_human_directory_user",
        "terminated_employee_with_active_account",
    } <= set(concept_ids)
    assert concept_ids.count("active_directory_account") == 1
    _assert_no_dangling_concept_dependencies(projection)


def test_supersedence_still_removes_unneeded_independent_concept() -> None:
    projection = _projection(
        "Show active license assignments marked as exceptions."
    )
    concept_ids = set(projection.as_observation()["selected_concept_ids"])

    assert "active_exception_license_assignment" in concept_ids
    assert "active_license_assignment" not in concept_ids
    _assert_no_dangling_concept_dependencies(projection)


def test_explicit_quantity_by_department_builds_grouped_count_intent() -> None:
    projection = _projection("How many privileged users by department?")
    intent = projection.grounded_result_intent

    assert intent is not None
    assert intent.row_grain is not None
    assert intent.row_grain.mode == "grouped"
    assert _field_keys(intent.row_grain.identity_fields) == {
        ("departments", "name")
    }
    assert _field_keys(intent.required_output_fields) == {
        ("departments", "name")
    }
    assert [
        (
            item.function,
            item.target_field.table if item.target_field else None,
            item.target_field.column if item.target_field else None,
            item.distinct,
        )
        for item in intent.aggregations
    ] == [("count", "directory_users", "id", True)]


def test_resolved_scope_reference_is_not_the_grouped_count_subject() -> None:
    projection = _projection(
        "How many open support tickets exist in my department by priority?",
        scope_type="department",
    )
    intent = projection.grounded_result_intent

    assert intent is not None
    assert _field_keys(intent.group_by) == {("support_tickets", "priority")}
    assert _field_keys(intent.required_output_fields) == {
        ("support_tickets", "priority")
    }
    assert [
        (
            item.function,
            item.target_field,
            item.distinct,
        )
        for item in intent.aggregations
    ] == [("count", None, False)]
    assert projection.mandatory_evidence()["entity_ids"] == ["support_tickets"]


def test_grouping_without_quantity_does_not_invent_count() -> None:
    projection = _projection("Show users by department.")
    intent = projection.grounded_result_intent

    assert intent is not None
    assert intent.row_grain is not None
    assert intent.row_grain.mode == "grouped"
    assert _field_keys(intent.group_by) == {("departments", "name")}
    assert intent.aggregations == ()
    assert intent.having == ()


def test_explicit_failed_login_threshold_builds_grouped_having_intent() -> None:
    projection = _projection(
        "Show failed logins per user with more than 5."
    )
    intent = projection.grounded_result_intent

    assert intent is not None
    assert _field_keys(intent.group_by) == {("login_events", "user_id")}
    assert _field_keys(intent.required_output_fields) == {
        ("login_events", "user_id")
    }
    assert [
        (
            item.function,
            item.target_field.table if item.target_field else None,
            item.target_field.column if item.target_field else None,
            item.distinct,
        )
        for item in intent.aggregations
    ] == [("count", "login_events", "id", False)]
    assert [
        (item.operator, item.value) for item in intent.having
    ] == [("greater_than", 5)]


def test_vague_login_spike_does_not_invent_numeric_having() -> None:
    projection = _projection("Which users have a failed login spike?")
    intent = projection.grounded_result_intent

    assert intent is None or intent.having == ()


def test_assignment_request_preserves_detail_identity_and_multiplicity() -> None:
    projection = _projection(
        "Show inactive users with active mandatory licenses."
    )
    intent = projection.grounded_result_intent

    assert intent is not None
    assert intent.row_grain is not None
    assert intent.row_grain.mode == "detail"
    assert _field_keys(intent.row_grain.identity_fields) == {
        ("license_assignments", "id")
    }
    assert _field_keys(intent.required_output_fields) == {
        ("directory_users", "id"),
        ("license_assignments", "id"),
    }
    assert intent.distinct is False


def test_explicit_output_attributes_resolve_to_canonical_fields() -> None:
    projection = _projection(
        "Show user id and assignment id for active mandatory licenses."
    )
    intent = projection.grounded_result_intent

    assert intent is not None
    assert _field_keys(intent.required_output_fields) == {
        ("directory_users", "id"),
        ("license_assignments", "id"),
    }


def test_structural_result_intent_cases_remain_fail_closed() -> None:
    cases = load_it_operations_evaluation_set().cases_by_id
    expected = {
        "itops-medium-006": {
            "group_by": {("departments", "name")},
            "aggregation": ("count", "directory_users", "id", True),
            "having": (),
            "detail": None,
        },
        "itops-medium-008": {
            "group_by": {("login_events", "user_id")},
            "aggregation": ("count", "login_events", "id", False),
            "having": (("greater_than", 5),),
            "detail": None,
        },
        "itops-medium-014": {
            "group_by": set(),
            "aggregation": None,
            "having": (),
            "detail": {("license_assignments", "id")},
        },
    }

    for case_id, requirements in expected.items():
        case = cases[case_id]
        intent = _projection(
            case.question,
            scope_type=case.required_scope_type or "none",
        ).grounded_result_intent
        assert intent is not None
        assert _field_keys(intent.group_by) == requirements["group_by"]
        aggregation = requirements["aggregation"]
        if aggregation is None:
            assert intent.aggregations == ()
        else:
            item = intent.aggregations[0]
            assert (
                item.function,
                item.target_field.table if item.target_field else None,
                item.target_field.column if item.target_field else None,
                item.distinct,
            ) == aggregation
        assert tuple(
            (item.operator, item.value) for item in intent.having
        ) == requirements["having"]
        detail = requirements["detail"]
        if detail is not None:
            assert intent.row_grain is not None
            assert _field_keys(intent.row_grain.identity_fields) == detail


def test_ambiguous_baseline_only_result_semantics_are_not_grounded() -> None:
    cases = load_it_operations_evaluation_set().cases_by_id

    hard_003 = _projection(cases["itops-hard-003"].question)
    assert hard_003.grounded_result_intent is None

    hard_004 = _projection(cases["itops-hard-004"].question)
    assert hard_004.grounded_result_intent is None

    medium_004 = _projection(cases["itops-medium-004"].question)
    assert medium_004.grounded_result_intent is not None
    assert medium_004.grounded_result_intent.aggregations == ()
    assert medium_004.grounded_result_intent.having == ()
    assert _field_keys(medium_004.grounded_result_intent.group_by) == {
        ("licenses", "product_name")
    }


def test_result_intent_query_engine_modules_do_not_import_evaluation() -> None:
    for path in (
        Path("app/query_engine/result_intent.py"),
        Path("app/query_engine/semantic_catalog.py"),
        Path("app/query_engine/semantic_grounding.py"),
        Path("app/query_engine/semantic_plan.py"),
    ):
        tree = ast.parse(path.read_text())
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert not any(name.startswith("app.evaluation") for name in imports)


def test_specific_overlap_does_not_suppress_unrelated_entity() -> None:
    projection = _projection("Show license assignments and open support tickets.")

    mandatory = projection.mandatory_evidence()
    assert {"license_assignments", "support_tickets"} <= set(
        mandatory["entity_ids"]
    )
    assert "licenses" not in mandatory["entity_ids"]


@pytest.mark.parametrize(
    ("case_id", "mandatory_entity_ids", "optional_entity_ids"),
    [
        ("itops-medium-010", {"license_assignments"}, {"licenses"}),
        ("itops-easy-006", {"license_assignments"}, {"licenses"}),
        (
            "itops-hard-003",
            {"license_assignments", "support_tickets"},
            {"departments", "licenses"},
        ),
        (
            "itops-hard-004",
            {"groups", "login_events", "user_group_memberships"},
            {"directory_users"},
        ),
        ("itops-medium-008", {"login_events"}, {"directory_users"}),
        (
            "itops-medium-014",
            {"directory_users", "license_assignments"},
            {"licenses"},
        ),
    ],
)
def test_frozen_over_grounding_cases_keep_lookup_entities_optional(
    case_id: str,
    mandatory_entity_ids: set[str],
    optional_entity_ids: set[str],
) -> None:
    case = load_it_operations_evaluation_set().cases_by_id[case_id]
    projection = _projection(
        case.question,
        scope_type=case.required_scope_type or "none",
    )

    assert set(projection.mandatory_evidence()["entity_ids"]) == (
        mandatory_entity_ids
    )
    assert optional_entity_ids <= set(
        projection.as_observation()["selected_entity_ids"]
    )
    assert not (
        optional_entity_ids & set(projection.mandatory_evidence()["entity_ids"])
    )


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


def _assert_no_dangling_concept_dependencies(
    projection: SemanticCatalogProjection,
) -> None:
    concept_ids = {concept["id"] for concept in projection.concepts}
    assert all(
        set(concept["all_of_concept_ids"]) <= concept_ids
        for concept in projection.concepts
    )


def _field_keys(
    fields: Iterable[GroundedFieldIdentity],
) -> set[tuple[str, str]]:
    return {(field.table, field.column) for field in fields}
