"""Candidate availability is an authorized option set, not an intent oracle."""

from dataclasses import replace

import pytest

from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_plan import validate_semantic_plan
from app.query_engine.sql_renderer import render_validated_semantic_plan
from tests.test_semantic_grounding import (
    _assert_no_dangling_concept_dependencies,
    _projection,
    _schema_context,
    _size,
    _user_context,
)
from tests.test_sql_renderer import _field, _plan


@pytest.mark.parametrize("question,entity", [
    ("How many computers do we manage?", "devices"),
    ("List company personnel.", "directory_users"),
    ("Show authentication attempts.", "login_events"),
    ("Summarize helpdesk cases.", "support_tickets"),
])
def test_authorized_entity_availability_does_not_require_a_lexical_match(question, entity):
    projection = _projection(question)
    assert entity in {item["id"] for item in projection.entities}
    assert projection.grounded_result_intent is None
    assert not any(projection.mandatory_evidence().values())
    assert _size(projection) <= 16_000


def test_extra_candidates_do_not_invent_meaning_for_ambiguous_or_negated_requests():
    pack = load_it_operations_domain_pack()
    for question in ("Show the relevant records.", "Show active records.",
                     "List devices, not non-compliant devices."):
        projection = _projection(question)
        assert "devices" in {item["id"] for item in projection.entities}
        assert projection.grounded_result_intent is None
        assert not any(projection.mandatory_evidence().values())
        checked = validate_semantic_plan(
            _plan(entity_ids=("devices",), output_fields=(_field("devices", "id"),)),
            domain_pack=pack, projection=projection, schema_context=_schema_context(),
            scope_reference_resolved=True,
        )
        assert checked.effective_predicates == ()
        assert checked.rule_or_predicate_groups == ()
        assert "WHERE" not in render_validated_semantic_plan(checked, pack)


def test_optional_definition_bundles_keep_dependency_closure_and_budget():
    projection = _projection(
        "Find directory users whose account is enabled after employment ended."
    )
    assert "terminated_employee_with_active_account" in {
        item["id"] for item in projection.concepts
    }
    _assert_no_dangling_concept_dependencies(projection)
    concept_ids = {item["id"] for item in projection.concepts}
    for rule in projection.composition_rules:
        assert set(rule["all_of_concept_ids"] + rule["or_concept_ids"]) <= concept_ids
    for metric in projection.metrics:
        assert set(metric["required_concept_ids"]) <= concept_ids
    assert _size(projection) <= 16_000


def test_oversized_optional_graph_or_definition_does_not_break_existing_core():
    pack = load_it_operations_domain_pack()
    catalog = replace(
        pack.semantic_catalog,
        entities=tuple(replace(item, description="x" * 20_000)
                       if item.id == "devices" else item
                       for item in pack.semantic_catalog.entities),
        concepts=tuple(replace(item, description="x" * 20_000)
                       if item.id == "stale_device" else item
                       for item in pack.semantic_catalog.concepts),
    )
    projection = build_semantic_catalog_projection(
        catalog, "How many active users are there?", _schema_context(), _user_context("global")
    )
    assert "active_human_users" in {item["id"] for item in projection.metrics}
    assert "devices" not in {item["id"] for item in projection.entities}
    assert "stale_device" not in {item["id"] for item in projection.concepts}
    assert _size(projection) <= 16_000
    _assert_no_dangling_concept_dependencies(projection)


def test_known_w6a_regression_corpus_is_available_without_history(monkeypatch):
    from scripts.probe_candidate_availability import measure_current

    def no_history(*args, **kwargs):
        raise AssertionError("CI measurement must work in a shallow checkout")

    monkeypatch.setattr("subprocess.check_output", no_history)
    report = measure_current()
    assert report["summary"]["positive_cases_fully_projected"] == 69
    assert report["summary"]["over_cap_ids"] == []
    assert report["summary"]["legacy_control_failures"] == [
        "counterevidence-ambiguous", "counterevidence-value-only",
        "counterevidence-no-assigned-scope", "counterevidence-non-queryable",
        "counterevidence-restricted",
    ]
    assert all(report["authorization_and_closure_checks"].values())


def test_optional_availability_is_stable_under_catalog_reordering():
    pack = load_it_operations_domain_pack()
    catalog = pack.semantic_catalog
    reordered = replace(catalog, **{
        name: tuple(reversed(getattr(catalog, name)))
        for name in ("entities", "relationships", "concepts", "metrics", "composition_rules")
    })
    for question in ("Show the relevant records.", "How many computers do we manage?"):
        original = build_semantic_catalog_projection(
            catalog, question, _schema_context(), _user_context("global")
        )
        shuffled = build_semantic_catalog_projection(
            reordered, question, _schema_context(), _user_context("global")
        )
        assert original.as_prompt_dict() == shuffled.as_prompt_dict()


def test_oversized_optional_definition_is_not_partially_installed():
    catalog = load_it_operations_domain_pack().semantic_catalog
    catalog = replace(catalog, concepts=tuple(
        replace(item, description="x" * 20_000)
        if item.id == "active_directory_account" else item
        for item in catalog.concepts
    ))
    projection = build_semantic_catalog_projection(
        catalog, "Show the relevant records.", _schema_context(), _user_context("global")
    )
    assert "directory_users" in {item["id"] for item in projection.entities}
    ids = {item["id"] for item in projection.concepts}
    assert not {"active_directory_account", "active_human_directory_user",
                "terminated_employee_with_active_account"} & ids
    assert "active_human_users" not in {item["id"] for item in projection.metrics}
    assert _size(projection) <= 16_000
    _assert_no_dangling_concept_dependencies(projection)


def test_mock_unsafe_metadata_does_not_treat_available_tables_as_referenced():
    from app.query_engine.llm_provider import PlanGenerationOutcome
    from app.query_engine.mock_llm_provider import MockLLMProvider

    question = "Update every directory user account to disabled."
    projection = _projection(question)
    assert len(projection.entities) > 1
    result = MockLLMProvider().generate_plan(
        question, _schema_context(), _user_context("global"),
        {"semantic_catalog": projection},
    )
    assert result.outcome is PlanGenerationOutcome.UNSAFE_REQUEST
    assert result.semantic_plan is None
    assert result.generation_metadata["referenced_tables"] == ["directory_users"]
