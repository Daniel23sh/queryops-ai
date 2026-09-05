from dataclasses import replace
from decimal import Decimal

import pytest

from app.evaluation.contracts import EvaluationAnswerability
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.structural_intent_adapter import (
    evaluation_contract_to_structural_requirement,
)


CASES = load_it_operations_evaluation_v2_set().cases_by_id


def contract(case_id):
    return CASES[case_id].semantic_contract


def test_detail_v2_policy_and_no_distinct_inference():
    source = contract("itops-medium-009")  # Question says distinct; contract does not.
    before = source.as_safe_dict()
    result = evaluation_contract_to_structural_requirement(source)
    assert result.intent.row_grain.value.mode == "detail"
    assert result.policy.row_grain == result.policy.output_fields == "required_subset"
    assert result.intent.aggregations.state == "known"
    assert result.intent.aggregations.value == ()
    assert result.policy.aggregations == result.policy.group_by == "ignored"
    assert result.intent.distinct.state == "unspecified"
    assert result.policy.distinct == "ignored"
    assert source.as_safe_dict() == before


def test_v2_grouped_having_and_ordering_policies():
    grouped = evaluation_contract_to_structural_requirement(contract("itops-hard-004"))
    assert grouped.policy.row_grain == grouped.policy.group_by == "exact"
    assert grouped.policy.aggregations == grouped.policy.having == "required_subset"
    assert grouped.intent.having.value[0].value == Decimal(5)
    ranked = evaluation_contract_to_structural_requirement(contract("itops-hard-010"))
    assert ranked.policy.ordering == "ordered_prefix"
    assert tuple(item.aggregation_id for item in ranked.intent.ordering.value) == (
        "risky_device_count",
        "inactive_user_count",
    )
    assert len(ranked.intent.aggregations.value) == 2


def test_v2_threshold_never_roundtrips_through_float():
    source = contract("itops-hard-004")
    threshold = Decimal("9007199254740993.1234567890123456789")
    source = replace(source, having=(replace(source.having[0], value=threshold),))
    mapped = evaluation_contract_to_structural_requirement(source)
    assert mapped.intent.having.value[0].value == threshold


@pytest.mark.parametrize(
    "answerability",
    [
        EvaluationAnswerability.DENIED,
        EvaluationAnswerability.UNSAFE,
        EvaluationAnswerability.CLARIFICATION,
    ],
)
def test_non_answerable_contracts_are_not_empty_successes(answerability):
    assert (
        evaluation_contract_to_structural_requirement(
            replace(
                contract("itops-security-001"),
                answerability=answerability,
            )
        )
        is None
    )


def test_metric_business_requirements_are_not_synthesized():
    result = evaluation_contract_to_structural_requirement(contract("itops-easy-005"))
    assert result.intent.row_grain.state == "unspecified"
    assert result.intent.aggregations.value == ()
    assert set(result.policy.model_dump().values()) == {"ignored"}
    assert "active_human_users" not in result.model_dump_json()


def test_distinct_grain_and_output_fields_preserved():
    mapped = evaluation_contract_to_structural_requirement(contract("itops-medium-015"))
    grain = {
        (item.entity_id, item.column)
        for item in mapped.intent.row_grain.value.identity_fields.value
    }
    outputs = {
        (item.entity_id, item.column) for item in mapped.intent.output_fields.value
    }
    assert ("groups", "id") in grain and ("groups", "id") not in outputs
    assert ("groups", "name") in outputs


def test_grouped_contract_with_empty_grain_is_preserved_not_repaired():
    source = replace(contract("itops-hard-004"), grain_fields=())
    mapped = evaluation_contract_to_structural_requirement(source)
    assert mapped.intent.row_grain.value.mode == "grouped"
    assert mapped.intent.row_grain.value.identity_fields.value == ()
    assert mapped.policy.row_grain == "exact"
