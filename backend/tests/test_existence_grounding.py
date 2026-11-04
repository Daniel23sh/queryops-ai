"""Existence is a population condition, not a request for aggregate output."""

import pytest

from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_plan import SemanticPlanValidationError, validate_semantic_plan
from tests.test_semantic_grounding import (
    _assert_no_dangling_concept_dependencies,
    _projection,
    _schema_context,
    _size,
    _user_context,
)
from tests.test_sql_renderer import _field, _plan


@pytest.mark.parametrize("parent,child,qualifier", [
    ("devices", "software_installs", "high-risk unsupported software installations"),
    ("users", "login_events", "failed logins in the last 30 days"),
])
@pytest.mark.parametrize("threshold", ["at least one", "at least 1", "more than zero", "more than 0"])
def test_existence_lists_do_not_suggest_aggregate_or_fact_grain(parent, child, qualifier, threshold):
    projection = _projection(f"Give a list of {parent} IDs with {threshold} {qualifier}.")
    intent = projection.suggested_result_intent
    assert projection.grounded_result_intent is None
    assert intent is None or (
        intent.row_grain is None and not intent.aggregations
        and not intent.group_by and not intent.having and intent.distinct is None
    )
    assert child in {entity["id"] for entity in projection.entities}
    assert not any(projection.mandatory_evidence().values())
    _assert_no_dangling_concept_dependencies(projection)
    assert _size(projection) <= 16_000


@pytest.mark.parametrize("question", [
    "Show stale devices with at least one unsupported software installation.",
    "List inactive human users with more than 0 active mandatory license assignments.",
])
def test_existence_abstention_does_not_fall_through_to_related_detail_grain(question):
    projection = _projection(question)
    assert projection.grounded_result_intent is None
    assert projection.suggested_result_intent is None


@pytest.mark.parametrize("threshold,operator,value", [
    ("more than five", "greater_than", 5),
    ("exactly one", "equals", 1),
    ("at least two", "greater_than_or_equal", 2),
    ("at most 1", "less_than_or_equal", 1),
])
@pytest.mark.parametrize("subject,qualifier", [
    ("devices", "unsupported software installations"),
    ("users", "failed logins in the last 30 days"),
])
def test_nonexistential_thresholds_keep_count_and_having(subject, qualifier, threshold, operator, value):
    projection = _projection(f"List {subject} with {threshold} {qualifier}.")
    intent = projection.suggested_result_intent
    assert projection.grounded_result_intent is None
    assert intent is not None and intent.row_grain.mode == "grouped"
    assert len(intent.aggregations) == len(intent.group_by) == len(intent.having) == 1
    assert (intent.having[0].operator, intent.having[0].value) == (operator, value)


@pytest.mark.parametrize("verb", ["Count", "Show"])
@pytest.mark.parametrize("facts,subject", [
    ("unsupported software installations", "device"),
    ("failed logins", "user"),
])
@pytest.mark.parametrize("threshold", ["at least one", "more than 0"])
def test_explicit_grouping_and_counts_keep_existence_threshold(verb, facts, subject, threshold):
    projection = _projection(f"{verb} {facts} per {subject} with {threshold}.")
    intent = projection.suggested_result_intent
    assert intent is not None and intent.aggregations and intent.group_by and intent.having
    assert projection.grounded_result_intent is None


def test_existence_keeps_requested_authorized_fields_without_binding_them():
    projection = _projection("Show device hostname with at least one unsupported software installation.")
    intent = projection.suggested_result_intent
    assert intent is not None and not intent.aggregations and not intent.group_by and not intent.having
    assert {(field.table, field.column) for field in intent.required_output_fields} == {("devices", "hostname")}
    assert projection.grounded_result_intent is None

    schema = _schema_context()
    schema["allowed_columns"]["devices"].remove("hostname")
    pack = load_it_operations_domain_pack()
    restricted = build_semantic_catalog_projection(
        pack.semantic_catalog,
        "Show device hostname with at least one unsupported software installation.",
        schema, _user_context("department"),
    )
    assert restricted.suggested_result_intent is None
    with pytest.raises(SemanticPlanValidationError) as failure:
        validate_semantic_plan(
            _plan(entity_ids=("devices",), output_fields=(_field("devices", "hostname"),)),
            domain_pack=pack, projection=restricted, schema_context=schema,
            scope_reference_resolved=True,
        )
    assert failure.value.reason == "field_not_authorized"


@pytest.mark.parametrize("concept", [
    "active_license_assignment", "unused_license_assignment",
    "high_confidence_unused_license_assignment", "active_mandatory_license_assignment",
    "active_exception_license_assignment",
])
def test_optional_license_definitions_bind_only_when_selected(concept):
    pack = load_it_operations_domain_pack()
    projection = _projection(
        "Show IDs for every active paid license assignment, including mandatory assignments, exceptions and recently used assignments."
    )
    assert projection.grounded_result_intent is projection.suggested_result_intent is None
    assert concept in {c["id"] for c in projection.concepts}
    checked = validate_semantic_plan(
        _plan(entity_ids=("license_assignments",), concept_ids=(concept,),
              output_fields=(_field("license_assignments", "id"),)),
        domain_pack=pack, projection=projection, schema_context=_schema_context(),
        scope_reference_resolved=True,
    )
    columns = {predicate.column for predicate in checked.effective_predicates}
    if concept == "active_license_assignment":
        assert columns == {"status"}
    elif "unused" in concept:
        assert {"is_mandatory", "last_used_at"} <= columns
        assert ("is_exception" in columns) == (concept == "high_confidence_unused_license_assignment")
    else:
        assert ("is_mandatory" if "mandatory" in concept else "is_exception") in columns
