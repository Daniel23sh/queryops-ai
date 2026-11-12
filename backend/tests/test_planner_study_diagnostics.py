"""Independent supplied-plan controls, never model outputs or database evidence."""
import pytest

from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_plan import SemanticHavingIntent, SemanticOrderIntent, validate_semantic_plan
from scripts import planner_study as study
from scripts.planner_study_diagnostics import bounded_diagnostics, compare_plans, result_indices
from scripts.planner_study_fixtures import CASES, HOST, STATUS
from scripts.semantic_ownership_fixtures import count, field, offline_schema, plan


def checked(value, case=CASES[0]):
    pack = load_it_operations_domain_pack()
    schema = offline_schema(pack)
    projection = build_semantic_catalog_projection(pack.semantic_catalog, case.question, schema, {})
    return validate_semantic_plan(value, domain_pack=pack, projection=projection,
                                  schema_context=schema, scope_reference_resolved=True)


def compare(actual, expected, case=CASES[0]):
    return compare_plans(checked(actual, case), checked(expected, case), load_it_operations_domain_pack())


@pytest.mark.parametrize("case", [CASES[0], CASES[1], CASES[3]])
def test_canonical_controls_are_equivalent(case):
    assert compare(case.plans[0], case.plans[0], case) == {
        "plan_comparison": "equivalent", "mismatch_axes": [],
    }


def test_singleton_in_and_redundant_identical_predicate_are_equivalent_spellings():
    posture, status = CASES[:2]
    singleton = posture.plans[0].model_copy(update={"literal_filters": (
        posture.plans[0].literal_filters[0].model_copy(update={"operator": "in", "value": ("laptop",)}),)})
    redundant = status.plans[0].model_copy(update={"literal_filters": (*status.plans[0].literal_filters, STATUS)})
    for actual, case in ((singleton, posture), (redundant, status)):
        assert not study.matching_plan(checked(actual, case), checked(case.plans[0], case))
        assert compare(actual, case.plans[0], case)["plan_comparison"] == "equivalent"


def test_selected_inner_membership_key_has_equal_group_count_identity():
    case = CASES[3]
    expected = case.plans[0]
    bridge = expected.model_copy(update={"aggregations": (
        count(field("user_group_memberships", "group_id"), distinct=True),)})
    assert compare(bridge, expected, case)["plan_comparison"] == "equivalent"
    assert not study.matching_plan(checked(bridge, case), checked(expected, case))
    assert result_indices(checked(bridge, case).plan, expected, load_it_operations_domain_pack()) == [0]


@pytest.mark.parametrize("actual,expected,case,axis", [
    (CASES[1].plans[0], CASES[0].plans[0], CASES[0], "rules"),
    (CASES[0].plans[0].model_copy(update={"concept_ids": ("non_compliant_device",)}),
     CASES[0].plans[0], CASES[0], "extra_predicates"),
    (CASES[0].plans[0], CASES[1].plans[0], CASES[1], "rules"),
    (CASES[3].plans[0].model_copy(update={"aggregations": (count(),)}),
     CASES[3].plans[0], CASES[3], "aggregations"),
])
def test_wrong_definition_narrowing_and_count_controls_are_not_proven_equivalent(actual, expected, case, axis):
    result = compare(actual, expected, case)
    assert result["plan_comparison"] == "unestablished"
    assert axis in result["mismatch_axes"]


@pytest.mark.parametrize("filters,axis", [
    ((), "missing_predicates"),
    ((CASES[0].plans[0].literal_filters[0].model_copy(update={"value": "desktop"}),), "changed_predicates"),
])
def test_missing_and_changed_subtype_are_distinguishable_without_retaining_values(filters, axis):
    expected = CASES[0].plans[0]
    result = compare(expected.model_copy(update={"literal_filters": filters}), expected)
    assert result == {"plan_comparison": "unestablished", "mismatch_axes": [axis]}


@pytest.mark.parametrize("join_type", ["left", "left_reverse"])
def test_outer_joins_do_not_prove_membership_fk_and_group_pk_equal(join_type):
    case = CASES[3]
    relationships = tuple(r.model_copy(update={"join_type": join_type})
                          if r.relationship_id == "user_group_membership_group" else r
                          for r in case.plans[0].relationships)
    expected = case.plans[0].model_copy(update={"relationships": relationships})
    actual = expected.model_copy(update={"aggregations": (
        count(field("user_group_memberships", "group_id"), distinct=True),)})
    assert compare(actual, expected, case)["plan_comparison"] == "unestablished"
    assert result_indices(checked(actual, case).plan, expected, load_it_operations_domain_pack()) is None


def test_different_selected_graphs_do_not_supply_identity_proof():
    case = CASES[3]
    actual = case.plans[0].model_copy(update={"aggregations": (
        count(field("user_group_memberships", "group_id"), distinct=True),)})
    expected = case.plans[0].model_copy(update={"relationships": tuple(
        r.model_copy(update={"join_type": "left"}) if r.relationship_id == "user_group_membership_group" else r
        for r in case.plans[0].relationships)})
    assert compare(actual, expected, case)["plan_comparison"] == "unestablished"
    assert result_indices(checked(actual, case).plan, expected, load_it_operations_domain_pack()) is None


def test_nullable_count_target_is_not_joined_row_count():
    # Devices without an assignee contribute to COUNT(*) and not COUNT(assigned_user_id).
    expected = plan(entity_ids=("devices",), aggregations=(count(),))
    actual = expected.model_copy(update={"aggregations": (count(field("devices", "assigned_user_id")),)})
    assert compare(actual, expected)["plan_comparison"] == "unestablished"
    assert result_indices(checked(actual).plan, expected, load_it_operations_domain_pack()) is None


def test_count_and_count_distinct_identities_do_not_become_comparable_from_scalar_shape():
    case = CASES[3]
    actual = case.plans[0].model_copy(update={"aggregations": (count(),)})
    assert result_indices(checked(actual, case).plan, case.plans[0], load_it_operations_domain_pack()) is None


def test_requested_output_identity_is_required_for_comparison():
    case = CASES[6]
    missing = case.plans[0].model_copy(update={"output_fields": (HOST,)})
    assert compare(missing, case.plans[0], case)["plan_comparison"] == "unestablished"
    assert result_indices(checked(missing, case).plan, case.plans[0], load_it_operations_domain_pack()) is None
    # The canonical renderer sorts fields; fixture order is restored by identities, not row values.
    assert result_indices(checked(case.plans[0], case).plan, case.plans[0], load_it_operations_domain_pack()) == [1, 0]


def test_extra_grouping_dimension_remains_unresolved():
    case = CASES[2]
    extra = (*case.plans[0].group_by, field("devices", "os"))
    actual = case.plans[0].model_copy(update={"output_fields": extra, "group_by": extra})
    result = compare(actual, case.plans[0], case)
    assert result["plan_comparison"] == "unestablished"
    assert "grouping" in result["mismatch_axes"]


def test_having_keeps_the_referenced_aggregate_expression():
    # An unassigned-only group passes COUNT(*) > 0, not COUNT(assigned_user_id) > 0.
    case = CASES[2]
    aggregates = (count().model_copy(update={"id": "a"}),
                  count(field("devices", "assigned_user_id")).model_copy(update={"id": "b"}))
    expected = case.plans[0].model_copy(update={
        "aggregations": aggregates,
        "having": (SemanticHavingIntent(aggregation_id="a", operator="greater_than", value=0),),
    })
    actual = expected.model_copy(update={"aggregations": (
        aggregates[0].model_copy(update={"id": "b"}), aggregates[1].model_copy(update={"id": "a"}))})
    assert compare(actual, expected, case)["plan_comparison"] == "unestablished"


def test_aggregate_ordering_and_limit_keep_the_referenced_expression():
    # Three unassigned laptops outrank one assigned desktop by rows, but not by assignees.
    case = CASES[2]
    aggregates = (count().model_copy(update={"id": "a"}),
                  count(field("devices", "assigned_user_id")).model_copy(update={"id": "b"}))
    expected = case.plans[0].model_copy(update={
        "aggregations": aggregates,
        "order_by": (SemanticOrderIntent(target_kind="aggregation", field=None,
                                         aggregation_id="a", direction="desc"),),
        "limit": 1,
    })
    actual = expected.model_copy(update={"aggregations": (
        aggregates[0].model_copy(update={"id": "b"}), aggregates[1].model_copy(update={"id": "a"}))})
    assert compare(actual, expected, case)["plan_comparison"] == "unestablished"


@pytest.mark.parametrize("changes,axis", [
    ({"distinct": True}, "distinct"),
    ({"limit": 1}, "limit"),
    ({"order_by": (SemanticOrderIntent(target_kind="field", field=HOST, aggregation_id=None, direction="desc"),)}, "ordering"),
])
def test_strict_matcher_omissions_are_not_equivalence_proofs(changes, axis):
    expected = CASES[0].plans[0]
    result = compare(expected.model_copy(update=changes), expected)
    assert result["plan_comparison"] == "unestablished"
    assert axis in result["mismatch_axes"]


def record(**changes):
    value = {"version": 1, "outcome": "plan", "clarification_reason": None,
             "plan_comparison": "unestablished", "mismatch_axes": ["changed_predicates"],
             "result_multiset_match": "not_evaluated"}
    value.update(changes)
    return value


def test_bounded_record_supports_legacy_and_finite_diagnostic_states():
    assert bounded_diagnostics(None)
    assert bounded_diagnostics(record())
    assert bounded_diagnostics(record(outcome="clarification", clarification_reason="unresolved_scope"))
    assert bounded_diagnostics(record(plan_comparison="equivalent", mismatch_axes=[], result_multiset_match=True))


@pytest.mark.parametrize("changes", [
    {"raw_plan": "secret"}, {"version": True}, {"version": 2},
    {"outcome": "secret"}, {"clarification_reason": "secret"},
    {"plan_comparison": "not_equivalent"}, {"mismatch_axes": ["secret"]},
    {"mismatch_axes": "predicates"}, {"mismatch_axes": [{}]},
    {"result_multiset_match": 1}, {"result_multiset_match": "secret"},
])
def test_bounded_record_rejects_arbitrary_content_and_types(changes):
    assert not bounded_diagnostics(record(**changes))
