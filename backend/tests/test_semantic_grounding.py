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
from app.query_engine.semantic_grounding import (
    _connector_path_rank,
    _select_minimal_relationship_graph,
)
from app.query_engine.semantic_catalog import (
    MAX_SEMANTIC_PROJECTION_BYTES,
    SemanticCatalogProjection,
    SemanticRelationship,
    SemanticRelationshipCardinality,
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
    assert exact.grounded_result_intent is None
    assert exact.suggested_result_intent is None

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


def test_grouping_without_quantity_or_bridge_does_not_invent_result_shape() -> None:
    projection = _projection("Show users by department.")

    assert projection.grounded_result_intent is None
    assert projection.suggested_result_intent is None


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


def test_inferred_detail_identity_is_suggested_not_required() -> None:
    projection = _projection(
        "Show inactive users with active mandatory licenses."
    )
    required = projection.grounded_result_intent
    suggested = projection.suggested_result_intent

    assert required is None
    assert suggested is not None
    assert suggested.row_grain is not None
    assert suggested.row_grain.mode == "detail"
    assert _field_keys(suggested.row_grain.identity_fields) == {
        ("license_assignments", "id")
    }
    assert _field_keys(suggested.required_output_fields) == {
        ("directory_users", "id"),
        ("license_assignments", "id"),
    }
    assert suggested.distinct is False


def test_implicit_quantity_bridge_is_suggested_not_required() -> None:
    projection = _projection(
        "Show users with active license assignments by product."
    )
    required = projection.grounded_result_intent
    suggested = projection.suggested_result_intent

    assert required is None
    assert suggested is not None
    assert suggested.row_grain is not None
    assert suggested.row_grain.mode == "grouped"
    assert _field_keys(suggested.row_grain.identity_fields) == {
        ("licenses", "product_name")
    }
    assert _field_keys(suggested.required_output_fields) == {
        ("licenses", "product_name")
    }
    assert _field_keys(suggested.group_by) == {
        ("licenses", "product_name")
    }
    assert [
        (
            item.function,
            item.target_field.table if item.target_field else None,
            item.target_field.column if item.target_field else None,
            item.distinct,
        )
        for item in suggested.aggregations
    ] == [("count", "directory_users", "id", True)]


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


def test_explicit_output_remains_required_with_ambiguous_grouping() -> None:
    projection = _projection(
        "Show users in privileged groups by department name."
    )
    required = projection.grounded_result_intent
    suggested = projection.suggested_result_intent

    assert required is not None
    assert _field_keys(required.required_output_fields) == {
        ("departments", "name")
    }
    assert required.row_grain is None
    assert required.group_by == ()
    assert required.aggregations == ()
    assert suggested is not None
    assert _field_keys(suggested.group_by) == {("departments", "name")}


def test_structural_result_intent_cases_keep_required_suggested_boundary() -> None:
    cases = load_it_operations_evaluation_set().cases_by_id
    ambiguous_case = cases["itops-medium-006"]
    ambiguous = _projection(
        ambiguous_case.question,
        scope_type=ambiguous_case.required_scope_type or "none",
    )
    assert ambiguous.mandatory_evidence() == {
        "entity_ids": ["groups", "user_group_memberships"],
        "concept_ids": ["privileged_group"],
        "metric_ids": [],
        "rule_ids": [],
    }
    assert ambiguous.grounded_result_intent is None
    assert ambiguous.suggested_result_intent is not None
    assert ambiguous.suggested_result_intent.row_grain is not None
    assert ambiguous.suggested_result_intent.row_grain.mode == "grouped"
    assert _field_keys(ambiguous.suggested_result_intent.group_by) == {
        ("departments", "name")
    }
    suggested_aggregation = ambiguous.suggested_result_intent.aggregations[0]
    assert suggested_aggregation.target_field is not None
    assert (
        suggested_aggregation.function,
        suggested_aggregation.target_field.table,
        suggested_aggregation.target_field.column,
        suggested_aggregation.distinct,
    ) == ("count", "directory_users", "id", True)
    assert set(ambiguous.as_observation()["selected_relationship_ids"]) == {
        "directory_user_department",
        "group_department",
        "user_group_membership_department",
        "user_group_membership_group",
        "user_group_membership_user",
    }

    threshold_case = cases["itops-medium-008"]
    threshold = _projection(
        threshold_case.question,
        scope_type=threshold_case.required_scope_type or "none",
    )
    assert threshold.grounded_result_intent is not None
    assert _field_keys(threshold.grounded_result_intent.group_by) == {
        ("login_events", "user_id")
    }
    threshold_aggregation = threshold.grounded_result_intent.aggregations[0]
    assert threshold_aggregation.target_field is not None
    assert (
        threshold_aggregation.function,
        threshold_aggregation.target_field.table,
        threshold_aggregation.target_field.column,
        threshold_aggregation.distinct,
    ) == ("count", "login_events", "id", False)
    assert tuple(
        (item.operator, item.value)
        for item in threshold.grounded_result_intent.having
    ) == (("greater_than", 5),)
    assert threshold.suggested_result_intent is None

    detail_case = cases["itops-medium-014"]
    detail = _projection(
        detail_case.question,
        scope_type=detail_case.required_scope_type or "none",
    )
    assert detail.grounded_result_intent is None
    assert detail.suggested_result_intent is not None
    assert detail.suggested_result_intent.row_grain is not None
    assert _field_keys(detail.suggested_result_intent.row_grain.identity_fields) == {
        ("license_assignments", "id")
    }


def test_required_and_suggested_intent_serialization_is_deterministic_and_bounded(
) -> None:
    projection = _projection(
        "Show users with active license assignments by product."
    )

    first = projection.as_prompt_dict()
    second = projection.as_prompt_dict()

    assert first == second
    assert first["result_intent"]["required"] is None
    assert first["result_intent"]["suggested"] is not None
    assert first["result_intent"]["suggested"]["group_by"] == [
        {"table": "licenses", "column": "product_name"}
    ]
    assert "grounded_result_intent" not in first
    assert _size(projection) <= MAX_SEMANTIC_PROJECTION_BYTES


def test_ambiguous_baseline_only_result_semantics_are_not_grounded() -> None:
    cases = load_it_operations_evaluation_set().cases_by_id

    hard_003 = _projection(cases["itops-hard-003"].question)
    assert hard_003.grounded_result_intent is None

    hard_004 = _projection(cases["itops-hard-004"].question)
    assert hard_004.grounded_result_intent is None

    medium_004 = _projection(cases["itops-medium-004"].question)
    assert medium_004.grounded_result_intent is None
    assert medium_004.suggested_result_intent is None


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


def test_relationship_graph_preserves_direct_anchor_relationship() -> None:
    relationships = (
        _graph_relationship(
            "license_assignment_license",
            "license_assignments",
            "licenses",
        ),
        _graph_relationship(
            "assignment_department",
            "license_assignments",
            "departments",
        ),
        _graph_relationship(
            "department_license",
            "departments",
            "licenses",
        ),
    )

    relationship_ids, entity_ids = _select_minimal_relationship_graph(
        {"license_assignments", "licenses"},
        relationships,
    )

    assert relationship_ids == {"license_assignment_license"}
    assert entity_ids == {"license_assignments", "licenses"}


def test_connected_direct_anchor_graph_does_not_expand_alternate_paths() -> None:
    relationships = (
        _graph_relationship("anchor_a_b", "anchor_a", "anchor_b"),
        _graph_relationship("anchor_b_c", "anchor_b", "anchor_c"),
        _graph_relationship("alternate_a_x", "anchor_a", "path_x"),
        _graph_relationship("alternate_x_c", "path_x", "anchor_c"),
    )

    relationship_ids, entity_ids = _select_minimal_relationship_graph(
        {"anchor_a", "anchor_b", "anchor_c"},
        relationships,
    )

    assert relationship_ids == {"anchor_a_b", "anchor_b_c"}
    assert entity_ids == {"anchor_a", "anchor_b", "anchor_c"}


def test_relationship_graph_adds_only_one_required_connector() -> None:
    relationships = (
        _graph_relationship("anchor_a_b", "anchor_a", "anchor_b"),
        _graph_relationship("connector_b_x", "anchor_b", "path_x"),
        _graph_relationship("connector_x_c", "path_x", "anchor_c"),
        _graph_relationship("alternate_b_y", "anchor_b", "path_y"),
        _graph_relationship("alternate_y_c", "path_y", "anchor_c"),
    )

    relationship_ids, entity_ids = _select_minimal_relationship_graph(
        {"anchor_a", "anchor_b", "anchor_c"},
        relationships,
    )

    assert relationship_ids == {
        "anchor_a_b",
        "alternate_b_y",
        "alternate_y_c",
    }
    assert entity_ids == {"anchor_a", "anchor_b", "anchor_c", "path_y"}


def test_equal_hop_connector_prefers_fewer_optional_relationships() -> None:
    relationships = (
        _graph_relationship(
            "a_optional_a_y",
            "anchor_a",
            "path_y",
            optional=True,
        ),
        _graph_relationship("a_optional_y_b", "path_y", "anchor_b"),
        _graph_relationship("z_required_a_x", "anchor_a", "path_x"),
        _graph_relationship("z_required_x_b", "path_x", "anchor_b"),
    )

    relationship_ids, entity_ids = _select_minimal_relationship_graph(
        {"anchor_a", "anchor_b"},
        relationships,
    )

    assert relationship_ids == {"z_required_a_x", "z_required_x_b"}
    assert entity_ids == {"anchor_a", "anchor_b", "path_x"}


def test_equal_connector_rank_prefers_fewer_new_path_entities() -> None:
    relationships = (
        _graph_relationship("a_new_a_y", "anchor_a", "path_y"),
        _graph_relationship("a_new_y_b", "path_y", "anchor_b"),
        _graph_relationship("z_existing_a_x", "anchor_a", "path_x"),
        _graph_relationship("z_existing_x_b", "path_x", "anchor_b"),
    )
    relationships_by_id = {
        relationship.id: relationship for relationship in relationships
    }
    selected_entity_ids = {"anchor_a", "anchor_b", "path_x"}

    existing_path_rank = _connector_path_rank(
        (
            ("anchor_a", "path_x", "anchor_b"),
            ("z_existing_a_x", "z_existing_x_b"),
        ),
        relationships_by_id=relationships_by_id,
        selected_entity_ids=selected_entity_ids,
    )
    new_path_rank = _connector_path_rank(
        (
            ("anchor_a", "path_y", "anchor_b"),
            ("a_new_a_y", "a_new_y_b"),
        ),
        relationships_by_id=relationships_by_id,
        selected_entity_ids=selected_entity_ids,
    )

    assert existing_path_rank < new_path_rank


def test_relationship_graph_tie_break_is_stable_when_input_is_reordered() -> None:
    relationships = (
        _graph_relationship("a_a_x", "anchor_a", "path_x"),
        _graph_relationship("b_x_b", "path_x", "anchor_b"),
        _graph_relationship("c_a_y", "anchor_a", "path_y"),
        _graph_relationship("d_y_b", "path_y", "anchor_b"),
    )

    selected = _select_minimal_relationship_graph(
        {"anchor_a", "anchor_b"},
        relationships,
    )
    reordered = _select_minimal_relationship_graph(
        {"anchor_a", "anchor_b"},
        tuple(reversed(relationships)),
    )

    assert selected == reordered
    assert selected == (
        {"a_a_x", "b_x_b"},
        {"anchor_a", "anchor_b", "path_x"},
    )


def test_disconnected_relationship_graph_remains_safely_disconnected() -> None:
    relationships = (
        _graph_relationship("a_b", "anchor_a", "path_b"),
        _graph_relationship("c_d", "anchor_c", "path_d"),
    )

    relationship_ids, entity_ids = _select_minimal_relationship_graph(
        {"anchor_a", "anchor_c"},
        relationships,
    )

    assert relationship_ids == set()
    assert entity_ids == {"anchor_a", "anchor_c"}


def test_real_multi_anchor_graph_uses_membership_chain_without_department() -> None:
    projection = _projection(
        "Show failed logins for users in privileged groups."
    )
    observation = projection.as_observation()

    assert set(observation["selected_entity_ids"]) == {
        "directory_users",
        "groups",
        "login_events",
        "user_group_memberships",
    }
    assert set(observation["selected_relationship_ids"]) == {
        "login_event_user",
        "user_group_membership_group",
        "user_group_membership_user",
    }
    assert "departments" not in observation["selected_entity_ids"]


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
    metric_entities = {
        metric["entity_id"] for metric in projection.as_prompt_dict()["metrics"]
    }
    assert not (path_only_entities & concept_entities)
    assert not (path_only_entities & metric_entities)
    assert not (
        path_only_entities
        & set(projection.mandatory_evidence()["entity_ids"])
    )


def test_examples_do_not_expand_the_selected_relationship_graph() -> None:
    pack = load_it_operations_domain_pack()
    relevant = next(
        example
        for example in pack.semantic_catalog.examples
        if example.id == "active_employees_with_non_compliant_devices"
    )
    unrelated = next(
        example
        for example in pack.semantic_catalog.examples
        if example.id == "unused_assignments_by_department"
    )
    catalog = replace(
        pack.semantic_catalog,
        examples=(
            relevant,
            replace(
                unrelated,
                id="matching_request_with_unselected_relationship",
                request=relevant.request,
            ),
        ),
    )

    projection = build_semantic_catalog_projection(
        catalog,
        relevant.request,
        _schema_context(),
        _user_context("global"),
    )
    observation = projection.as_observation()

    assert observation["selected_relationship_ids"] == ["device_assignee"]
    assert observation["selected_example_ids"] == [
        "active_employees_with_non_compliant_devices"
    ]


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


def _graph_relationship(
    relationship_id: str,
    from_entity: str,
    to_entity: str,
    *,
    optional: bool = False,
) -> SemanticRelationship:
    return SemanticRelationship(
        id=relationship_id,
        from_entity=from_entity,
        from_column="id",
        to_entity=to_entity,
        to_column="id",
        cardinality=SemanticRelationshipCardinality.MANY_TO_ONE,
        optional=optional,
        description=relationship_id,
    )
