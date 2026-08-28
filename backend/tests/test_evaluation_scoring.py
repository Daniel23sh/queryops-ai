from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.evaluation.contracts import (
    ComparisonMode,
    ExpectedOutcome,
    ProvenanceAuthorizationEvidence,
)
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.provenance import build_evaluation_comparison_provenance
from app.evaluation.scoring import score_evaluation_case


def _successful_case():
    return load_it_operations_evaluation_set().cases_by_id["itops-easy-005"]


def _score(case, expected_rows, actual_rows, *, tables=None, provenance=None):
    return score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables if tables is None else tables,
        expected_rows=expected_rows,
        actual_rows=actual_rows,
        provenance=provenance,
    )


def _provenance(expected_sql: str, actual_sql: str, *, validated: bool = True):
    return build_evaluation_comparison_provenance(
        baseline_sql=expected_sql,
        final_sql=actual_sql,
        actual_authorization_evidence=(
            ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED
            if validated
            else ProvenanceAuthorizationEvidence.UNVERIFIED
        ),
    )


def test_equal_unordered_results_pass_in_different_order() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    score = _score(case, [{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 1}])
    assert score.passed is True
    assert score.score == 1.0


def test_ordered_comparison_detects_order_mismatch() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.ORDERED_ROWS)
    score = _score(case, [{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 1}])
    assert score.result_correct is False
    assert score.failure_reasons == ("result_semantics_mismatch",)


def test_aggregation_group_comparison_is_semantic() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.GROUPED_ROWS)
    score = _score(
        case,
        [{"priority": "high", "count": Decimal("2")}, {"priority": "low", "count": 3}],
        [{"count": 3.0, "priority": "low"}, {"count": 2, "priority": "high"}],
    )
    assert score.passed is True


def test_single_grouped_aggregate_ignores_only_a_harmless_alias() -> None:
    case = _successful_case()

    score = _score(
        case,
        [{"active_user_count": 7}],
        [{"active_human_user_count": Decimal("7.0")}],
    )

    assert score.passed is True
    assert score.result_correct is True


def test_single_grouped_aggregate_still_rejects_a_different_value() -> None:
    case = _successful_case()

    different_alias = _score(
        case,
        [{"active_user_count": 7}],
        [{"active_human_user_count": 8}],
    )
    same_alias = _score(
        case,
        [{"active_user_count": 7}],
        [{"active_user_count": 8}],
    )

    assert different_alias.result_correct is False
    assert different_alias.failure_reasons == ("result_semantics_mismatch",)
    assert same_alias.result_correct is False


def test_grouped_alias_relaxation_does_not_apply_to_multi_column_rows() -> None:
    case = _successful_case()
    score = _score(
        case,
        [{"status": "active", "user_count": 7}],
        [{"state": "active", "human_count": 7}],
    )

    assert score.result_correct is False
    assert score.failure_reasons == ("result_semantics_mismatch",)


def test_grouped_alias_relaxation_preserves_row_shape_and_null_semantics() -> None:
    case = _successful_case()

    assert _score(case, [{"expected": None}], [{"actual": None}]).passed is True
    assert _score(case, [{"expected": None}], [{"actual": 0}]).passed is False
    missing = _score(case, [], [{"actual": 0}])
    extra = _score(case, [{"expected": 0}], [])
    assert missing.failure_reasons == ("row_count_mismatch",)
    assert extra.failure_reasons == ("row_count_mismatch",)


def test_alias_relaxation_is_not_global_for_ordinary_tabular_modes() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)

    score = _score(case, [{"active_user_count": 7}], [{"renamed_count": 7}])

    assert score.result_correct is False


def test_duplicate_row_multiplicity_is_not_discarded() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    score = _score(case, [{"id": 1}, {"id": 1}], [{"id": 1}, {"id": 2}])
    assert score.result_correct is False


def test_uuid_datetime_decimal_integer_and_float_normalization() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    identifier = uuid.uuid4()
    instant = datetime(2026, 1, 2, 12, 30, tzinfo=timezone.utc)
    score = _score(
        case,
        [{"id": identifier, "at": instant, "value": Decimal("4.0")}],
        [{"id": str(identifier), "at": instant.astimezone(timezone(timedelta(hours=2))), "value": 4}],
    )
    assert score.passed is True


def test_numeric_tolerance_is_explicit_and_case_controlled() -> None:
    exact_case = replace(
        _successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS, numeric_tolerance=None
    )
    tolerant_case = replace(exact_case, numeric_tolerance=Decimal("0.01"))
    expected = [{"amount": Decimal("10.00")}]
    actual = [{"amount": 10.009}]

    assert _score(exact_case, expected, actual).passed is False
    assert _score(tolerant_case, expected, actual).passed is True


def test_nulls_compare_only_to_nulls() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    assert _score(case, [{"value": None}], [{"value": None}]).passed is True
    assert _score(case, [{"value": None}], [{"value": ""}]).passed is False


def test_expected_denial_unsafe_block_and_clarification_score_without_execution() -> None:
    cases = load_it_operations_evaluation_set().cases_by_id
    denial = cases["itops-security-001"]
    unsafe = cases["itops-security-003"]
    clarification = cases["itops-security-005"]

    denied_score = score_evaluation_case(
        denial,
        actual_outcome=ExpectedOutcome.DENIED,
        execution_succeeded=False,
    )
    clarification_score = score_evaluation_case(
        clarification,
        actual_outcome=ExpectedOutcome.CLARIFICATION,
        execution_succeeded=False,
    )
    unsafe_score = score_evaluation_case(
        unsafe,
        actual_outcome=ExpectedOutcome.UNSAFE_BLOCKED,
        execution_succeeded=False,
        actual_referenced_tables=unsafe.expected_tables,
    )
    assert denied_score.passed is True
    assert denied_score.result_correct is None
    assert unsafe_score.passed is True
    assert clarification_score.passed is True


def test_wrong_referenced_tables_fail_even_when_rows_match() -> None:
    case = _successful_case()
    score = _score(case, [{"count": 1}], [{"count": 1}], tables=["devices"])
    assert score.tables_correct is False
    assert "referenced_tables_mismatch" in score.failure_reasons


def test_stable_key_comparison_and_missing_key_are_safe() -> None:
    case = replace(
        _successful_case(),
        comparison_mode=ComparisonMode.STABLE_KEYS,
        stable_key_columns=("id",),
    )
    assert _score(case, [{"id": 1, "name": "old"}], [{"id": 1, "name": "new"}]).passed
    missing = _score(case, [{"id": 1}], [{"name": "not-returned"}])
    assert missing.passed is False
    assert missing.failure_reasons == ("missing_stable_key",)


def test_provenance_resolves_stable_identity_across_aliases() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-hard-005"]
    provenance = _provenance(
        "SELECT devices.id AS device_id FROM devices",
        "SELECT devices.id AS id FROM devices",
    )

    score = _score(
        case,
        [{"device_id": "device-1"}],
        [{"id": "device-1"}],
        provenance=provenance,
    )

    assert score.passed is True


def test_provenance_rejects_unrelated_id_as_stable_identity() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-hard-005"]
    provenance = _provenance(
        "SELECT devices.id AS device_id FROM devices",
        "SELECT directory_users.id AS id FROM directory_users",
    )

    score = _score(
        case,
        [{"device_id": "same-value"}],
        [{"id": "same-value"}],
        provenance=provenance,
    )

    assert score.result_correct is False
    assert score.failure_reasons == ("missing_stable_key",)


def test_stable_alias_without_provenance_remains_fail_closed() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-hard-005"]

    score = _score(case, [{"device_id": "device-1"}], [{"id": "device-1"}])

    assert score.result_correct is False
    assert score.failure_reasons == ("missing_stable_key",)


def test_provenance_matches_equivalent_grouped_aggregate_aliases() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-hard-009"]
    provenance = _provenance(
        "SELECT groups.id, COUNT(*) AS addition_count FROM groups "
        "GROUP BY groups.id ORDER BY addition_count DESC",
        "SELECT groups.id, COUNT(*) AS membership_addition_count FROM groups "
        "GROUP BY groups.id ORDER BY membership_addition_count DESC",
    )

    score = _score(
        case,
        [
            {"id": "group-1", "addition_count": 5},
            {"id": "group-2", "addition_count": 3},
        ],
        [
            {"id": "group-1", "membership_addition_count": 5},
            {"id": "group-2", "membership_addition_count": 3},
        ],
        provenance=provenance,
    )

    assert score.passed is True


def test_provenance_does_not_equate_count_and_count_distinct() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-hard-009"]
    provenance = _provenance(
        "SELECT groups.id, COUNT(user_group_memberships.user_id) AS addition_count "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id GROUP BY groups.id",
        "SELECT groups.id, COUNT(DISTINCT user_group_memberships.user_id) "
        "AS addition_count FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id GROUP BY groups.id",
    )

    score = _score(
        case,
        [{"id": "group-1", "addition_count": 2}],
        [{"id": "group-1", "addition_count": 2}],
        provenance=provenance,
    )

    assert score.result_correct is False


def test_provenance_does_not_equate_different_aggregation_targets() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-hard-009"]
    provenance = _provenance(
        "SELECT groups.id, COUNT(user_group_memberships.user_id) AS item_count "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id GROUP BY groups.id",
        "SELECT groups.id, COUNT(user_group_memberships.group_id) AS item_count "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id GROUP BY groups.id",
    )

    score = _score(
        case,
        [{"id": "group-1", "item_count": 2}],
        [{"id": "group-1", "item_count": 2}],
        provenance=provenance,
    )

    assert score.result_correct is False


def test_authorized_extra_output_passes_at_same_grain_and_multiplicity() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-medium-015"]
    expected_sql = (
        "SELECT user_group_memberships.user_id, groups.name AS group_name "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id"
    )
    actual_sql = (
        "SELECT user_group_memberships.user_id, groups.name AS group_name, "
        "user_group_memberships.group_id FROM groups "
        "JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id"
    )

    score = _score(
        case,
        [
            {"user_id": "user-1", "group_name": "Admins"},
            {"user_id": "user-2", "group_name": "Security"},
        ],
        [
            {"user_id": "user-1", "group_name": "Admins", "group_id": "g-1"},
            {"user_id": "user-2", "group_name": "Security", "group_id": "g-2"},
        ],
        provenance=_provenance(expected_sql, actual_sql),
    )

    assert score.passed is True


def test_unverified_extra_output_remains_fail_closed() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-medium-015"]
    expected_sql = "SELECT user_id FROM user_group_memberships"
    actual_sql = "SELECT user_id, group_id FROM user_group_memberships"

    score = _score(
        case,
        [{"user_id": "user-1"}],
        [{"user_id": "user-1", "group_id": "group-1"}],
        provenance=_provenance(expected_sql, actual_sql, validated=False),
    )

    assert score.result_correct is False


def test_extra_output_with_different_row_grain_fails() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-medium-015"]
    provenance = _provenance(
        "SELECT user_group_memberships.user_id FROM user_group_memberships",
        "SELECT user_group_memberships.user_id, user_group_memberships.group_id "
        "FROM user_group_memberships GROUP BY user_group_memberships.user_id, "
        "user_group_memberships.group_id",
    )

    score = _score(
        case,
        [{"user_id": "user-1"}],
        [{"user_id": "user-1", "group_id": "group-1"}],
        provenance=provenance,
    )

    assert score.result_correct is False


def test_extra_output_projection_cannot_collapse_distinct_rows() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-medium-015"]
    provenance = _provenance(
        "SELECT user_group_memberships.user_id FROM user_group_memberships",
        "SELECT user_group_memberships.user_id, user_group_memberships.group_id "
        "FROM user_group_memberships",
    )

    score = _score(
        case,
        [{"user_id": "user-1"}, {"user_id": "user-1"}],
        [
            {"user_id": "user-1", "group_id": "group-1"},
            {"user_id": "user-1", "group_id": "group-2"},
        ],
        provenance=provenance,
    )

    assert score.result_correct is False


def test_missing_expected_canonical_output_fails() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-medium-015"]
    provenance = _provenance(
        "SELECT user_group_memberships.user_id, groups.name AS group_name "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id",
        "SELECT groups.name AS group_name, user_group_memberships.group_id "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id",
    )

    score = _score(
        case,
        [{"user_id": "user-1", "group_name": "Admins"}],
        [{"group_name": "Admins", "group_id": "group-1"}],
        provenance=provenance,
    )

    assert score.result_correct is False


def test_bounded_different_stable_key_subset_still_fails_with_provenance() -> None:
    case = replace(
        load_it_operations_evaluation_set().cases_by_id["itops-easy-006"],
        expected_tables=("license_assignments",),
    )
    provenance = _provenance(
        "SELECT license_assignments.id FROM license_assignments",
        "SELECT license_assignments.id FROM license_assignments",
    )
    expected = [{"id": f"assignment-{index}"} for index in range(100)]
    actual = [{"id": f"assignment-{index}"} for index in range(1, 101)]

    score = _score(case, expected, actual, provenance=provenance)

    assert score.result_correct is False


def test_extra_output_without_provenance_preserves_exact_key_behavior() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)

    score = _score(case, [{"id": 1}], [{"id": 1, "name": "extra"}])

    assert score.result_correct is False


def test_provenance_does_not_relax_order_within_primary_ties() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-hard-009"]
    provenance = _provenance(
        "SELECT groups.name, COUNT(*) AS addition_count FROM groups "
        "GROUP BY groups.name ORDER BY addition_count DESC, groups.name ASC",
        "SELECT groups.name, COUNT(*) AS membership_addition_count FROM groups "
        "GROUP BY groups.name ORDER BY membership_addition_count DESC",
    )

    score = _score(
        case,
        [
            {"name": "Alpha", "addition_count": 5},
            {"name": "Beta", "addition_count": 5},
        ],
        [
            {"name": "Beta", "membership_addition_count": 5},
            {"name": "Alpha", "membership_addition_count": 5},
        ],
        provenance=provenance,
    )

    assert score.result_correct is False


def test_score_diagnostics_never_include_raw_rows() -> None:
    case = replace(_successful_case(), comparison_mode=ComparisonMode.UNORDERED_ROWS)
    secret = "raw-row-secret@example.invalid"
    score = _score(case, [{"value": secret}], [{"value": "different"}])
    serialized = json.dumps(score.as_safe_metrics(), sort_keys=True)

    assert secret not in serialized
    assert "different" not in serialized
    assert set(score.as_safe_metrics()) == {
        "score",
        "passed",
        "outcome_correct",
        "execution_correct",
        "tables_correct",
        "result_correct",
        "expected_row_count",
        "actual_row_count",
        "failure_reasons",
    }
