"""Synthetic counterexamples only: no provider or persisted evaluation evidence."""

import json
from dataclasses import asdict, replace

import pytest

from app.evaluation.contracts import ActualOutcome, ProvenanceAuthorizationEvidence
from app.evaluation.contracts import EvaluationSemanticField
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.identity import IdentityProof
from app.evaluation.provenance import build_evaluation_comparison_provenance
from app.evaluation.scoring import (
    score_evaluation_case,
    score_evaluation_semantic_contract,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_grounding import build_semantic_grounding_projection
from app.query_engine.semantic_plan import SemanticPlan, validate_semantic_plan
from app.query_engine.sql_renderer import render_validated_semantic_plan
from app.query_engine.sql_validator import validate_sql


def example(case_id, *, grouping=None):
    pack = load_it_operations_domain_pack()
    case = load_it_operations_evaluation_v2_set().cases_by_id[case_id]
    contract = asdict(case.semantic_contract)
    relationships = {
        "itops-medium-006": [
            "directory_user_department",
            "user_group_membership_user",
            "user_group_membership_group",
        ],
        "itops-hard-004": [
            "login_event_user",
            "user_group_membership_user",
            "user_group_membership_group",
        ],
        "itops-hard-006": ["license_assignment_license"],
    }[case_id]
    fields = (
        [dict(entity_id=table, column=column) for table, column in grouping]
        if grouping is not None
        else contract["group_by"]
    )
    schema = {
        "allowed_tables": [t.name for t in pack.tables if t.queryable],
        "allowed_columns": {
            t.name: [c.name for c in t.columns] for t in pack.tables if t.queryable
        },
        "tables": [
            {
                "name": t.name,
                "resource": {"is_queryable": True},
                "scope_type": t.scope_type,
                "scope_column": t.scope_column,
            }
            for t in pack.tables
            if t.queryable
        ],
    }
    projection = build_semantic_grounding_projection(
        pack.semantic_catalog,
        case.question,
        schema,
        {
            "scope_type": case.required_scope_type,
            "has_global_scope": case.scope_mode.value == "global",
            "scope_reference_resolved": True,
        },
    )
    plan = SemanticPlan.model_validate_json(
        json.dumps(
            dict(
                entity_ids=list(case.expected_tables),
                concept_ids=contract["required_concept_ids"],
                composition_rule_ids=contract["required_composition_rule_ids"],
                metric_id=None,
                distinct=False,
                literal_filters=[],
                relationships=[
                    dict(relationship_id=r, join_type="inner") for r in relationships
                ],
                output_fields=fields,
                aggregations=contract["aggregations"],
                group_by=fields,
                having=[dict(h, value=int(h["value"])) for h in contract["having"]],
                order_by=contract["ordering"],
                limit=None,
            )
        )
    )
    validated = validate_semantic_plan(
        plan,
        domain_pack=pack,
        projection=projection,
        schema_context=schema,
        scope_reference_resolved=True,
    )
    sql = render_validated_semantic_plan(validated, pack)
    assert validate_sql(sql, schema).valid
    assert validate_sql(case.baseline_sql, schema).valid
    return case, validated, sql


def compare(case, sql, expected, actual, *, verified=True):
    provenance = build_evaluation_comparison_provenance(
        baseline_sql=case.baseline_sql,
        final_sql=sql,
        actual_authorization_evidence=(
            ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED
            if verified
            else ProvenanceAuthorizationEvidence.UNVERIFIED
        ),
    )
    return score_evaluation_case(
        case,
        actual_outcome=ActualOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=expected,
        actual_rows=actual,
        provenance=provenance,
    )


@pytest.mark.parametrize(
    "grouping",
    [
        [("departments", "name")],
        [("departments", "id")],
        [("departments", "id"), ("departments", "name")],
    ],
)
def test_department_representations(grouping):
    case, plan, sql = example("itops-medium-006", grouping=grouping)
    assert score_evaluation_semantic_contract(case, plan.as_observation()).passed
    expected = [
        {"id": "department-1", "department_name": "Engineering", "user_count": 2}
    ]
    actual = [{"name": "Engineering", "user_count": 2}]
    if ("departments", "name") not in grouping:
        actual[0].pop("name")
    if ("departments", "id") in grouping:
        actual[0]["id"] = "department-1"
    assert compare(case, sql, expected, actual).passed


def test_different_department_grain_fails():
    case, plan, sql = example(
        "itops-medium-006",
        grouping=[
            ("departments", "name"),
            ("directory_users", "account_status"),
        ],
    )
    score = score_evaluation_semantic_contract(case, plan.as_observation())
    assert not score.group_by_correct and not score.grain_correct
    assert not compare(
        case,
        sql,
        [{"id": "department-1", "department_name": "Engineering", "user_count": 2}],
        [{"name": "Engineering", "account_status": "active", "user_count": 2}],
    ).passed


@pytest.mark.parametrize(
    "table,column", [("login_events", "user_id"), ("directory_users", "id")]
)
def test_equivalent_user_keys_and_supported_bridge(table, column):
    case, plan, sql = example("itops-hard-004", grouping=[(table, column)])
    assert "JOIN directory_users du ON du.id = le.user_id" in case.baseline_sql
    assert set(plan.plan.entity_ids) == set(case.expected_tables)
    assert score_evaluation_semantic_contract(case, plan.as_observation()).passed
    assert compare(
        case,
        sql,
        [{"user_id": "u1", "failed_login_count": 6}],
        [{column: "u1", "failed_login_count": 6}],
    ).passed


@pytest.mark.parametrize("mutation", ["missing", "left", "unrelated"])
def test_user_key_equivalence_requires_selected_inner_relationship(mutation):
    case, plan, _ = example("itops-hard-004", grouping=[("directory_users", "id")])
    observation = plan.as_observation()
    if mutation == "missing":
        observation.pop("relationship_join_types")
    else:
        for selected in observation["relationship_join_types"]:
            if selected["relationship_id"] == "login_event_user":
                selected.update(
                    join_type="left" if mutation == "left" else "inner",
                    relationship_id="login_event_user"
                    if mutation == "left"
                    else "device_assignee",
                )
    assert not score_evaluation_semantic_contract(case, observation).passed


@pytest.mark.parametrize("mutation", ["count", "threshold", "having"])
def test_failed_login_measure_and_having_remain_binding(mutation):
    case, plan, _ = example("itops-hard-004")
    observation = plan.as_observation()
    if mutation == "count":
        observation["aggregations"][0]["distinct"] = False
    elif mutation == "threshold":
        observation["having"][0]["value"] = 4
    else:
        observation["having"] = []
    assert not score_evaluation_semantic_contract(case, observation).passed


def test_savings_requires_only_requested_measure_and_ranking():
    case, plan, sql = example("itops-hard-006")
    assert "reclaim_count" not in case.baseline_sql and "reclaim_count" not in sql
    assert [a.id for a in case.semantic_contract.aggregations] == ["monthly_savings"]
    assert score_evaluation_semantic_contract(case, plan.as_observation()).passed
    for field, value in [("aggregations", []), ("order_by", [])]:
        observation = plan.as_observation()
        observation[field] = value
        assert not score_evaluation_semantic_contract(case, observation).passed
    observation = plan.as_observation()
    observation["order_by"][0]["direction"] = "asc"
    assert not score_evaluation_semantic_contract(case, observation).passed


def test_exact_ties_pass_but_wrong_rank_and_values_fail():
    case, _, sql = example("itops-hard-006")
    expected = [
        dict(product_name=p, monthly_savings=s)
        for p, s in [("A", 20), ("B", 10), ("C", 10)]
    ]
    assert compare(case, sql, expected, [expected[i] for i in [0, 2, 1]]).passed
    assert not compare(case, sql, expected, expected[::-1]).passed
    assert not compare(
        case, sql, expected, [expected[0], expected[1], expected[1]]
    ).passed
    nearby = [expected[0], expected[1], dict(product_name="C", monthly_savings=9.999)]
    assert not compare(case, sql, nearby, [nearby[i] for i in [0, 2, 1]]).passed


@pytest.mark.parametrize("join", ["LEFT JOIN", "JOIN"])
def test_sql_identity_does_not_trust_outer_or_disjunctive_join(join):
    case, _, sql = example("itops-hard-004", grouping=[("directory_users", "id")])
    if join == "LEFT JOIN":
        sql = sql.replace("INNER JOIN login_events", "LEFT JOIN login_events")
    else:
        sql = sql.replace(
            "login_events.user_id = directory_users.id",
            "(login_events.user_id = directory_users.id OR login_events.department_id = directory_users.department_id)",
        )
    provenance = build_evaluation_comparison_provenance(
        baseline_sql=case.baseline_sql, final_sql=sql
    )
    # Independently authored malformed/outer SQL must not supply an equality proof.
    assert not any(
        {f.table for f in pair} == {"login_events", "directory_users"}
        for pair in provenance.actual.inner_key_equalities
    )


def test_unverified_provenance_does_not_gain_identity_equivalence():
    case, _, sql = example("itops-hard-004", grouping=[("directory_users", "id")])
    assert not compare(
        case,
        sql,
        [{"user_id": "u1", "failed_login_count": 6}],
        [{"id": "u1", "failed_login_count": 6}],
        verified=False,
    ).passed


def test_ranking_retains_numeric_tolerance():
    case, _, sql = example("itops-hard-006")
    expected = [dict(product_name="A", monthly_savings=20)]
    assert compare(
        case, sql, expected, [dict(product_name="A", monthly_savings=20.001)]
    ).passed
    assert not compare(
        case, sql, expected, [dict(product_name="A", monthly_savings=20.02)]
    ).passed


def test_unique_grain_proof_is_not_value_equality_or_composite_uniqueness():
    proof = IdentityProof()
    assert proof.grain([("departments", "id")]) == proof.grain(
        [("departments", "name")]
    )
    assert proof.field(("departments", "id")) != proof.field(("departments", "name"))
    assert proof.grain([("licenses", "id")]) != proof.grain(
        [("licenses", "product_name")]
    )


def test_shared_group_key_is_required_and_compared_by_value():
    case, _, sql = example("itops-medium-006", grouping=[("departments", "id")])
    expected = [dict(id="department-1", department_name="Engineering", user_count=2)]
    assert not compare(
        case, sql, expected, [dict(id="Engineering", user_count=2)]
    ).passed


def test_explicit_output_requirement_is_not_replaced_by_another_unique_key():
    case, plan, sql = example("itops-medium-006", grouping=[("departments", "id")])
    explicit = replace(
        case,
        semantic_contract=replace(
            case.semantic_contract,
            output_fields=(EvaluationSemanticField("departments", "name"),),
        ),
    )
    assert not score_evaluation_semantic_contract(
        explicit, plan.as_observation()
    ).outputs_correct
    expected = [dict(id="department-1", department_name="Engineering", user_count=2)]
    assert not compare(
        explicit, sql, expected, [dict(id="department-1", user_count=2)]
    ).passed
    assert not compare(
        case, sql, expected, [dict(id="department-2", user_count=2)]
    ).passed
    assert not compare(
        case, sql.replace("departments.id, ", "", 1), expected, [dict(user_count=2)]
    ).passed
