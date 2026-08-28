from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.evaluation.contracts import (
    ActualOutcome,
    ExpectedOutcome,
    ProvenanceAuthorizationEvidence,
)
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.provenance import extract_evaluation_query_provenance
from app.evaluation.runner import _CaseExecution, _build_case_provenance
from app.evaluation.scoring import score_evaluation_case
from app.db.base import Base
from app.models.product import QueryRun


def _extract(sql: str, *, validated: bool = False):
    return extract_evaluation_query_provenance(
        sql,
        authorization_evidence=(
            ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED
            if validated
            else ProvenanceAuthorizationEvidence.UNVERIFIED
        ),
    )


def test_field_aliases_share_canonical_source_identity() -> None:
    short = _extract("SELECT devices.id AS id FROM devices")
    descriptive = _extract("SELECT devices.id AS device_id FROM devices")

    assert short.outputs[0].presentation_name == "id"
    assert descriptive.outputs[0].presentation_name == "device_id"
    assert short.outputs[0].identity == descriptive.outputs[0].identity


def test_same_alias_does_not_merge_different_source_fields() -> None:
    device = _extract("SELECT devices.id AS id FROM devices")
    user = _extract("SELECT directory_users.id AS id FROM directory_users")

    assert device.outputs[0].identity != user.outputs[0].identity


def test_aggregate_aliases_share_canonical_aggregation_identity() -> None:
    first = _extract(
        "SELECT groups.id, COUNT(*) AS addition_count "
        "FROM groups GROUP BY groups.id"
    )
    second = _extract(
        "SELECT groups.id, COUNT(*) AS membership_addition_count "
        "FROM groups GROUP BY groups.id"
    )

    assert first.outputs[1].identity == second.outputs[1].identity
    assert first.outputs[1].presentation_name != second.outputs[1].presentation_name


def test_count_and_count_distinct_have_different_identities() -> None:
    counted = _extract(
        "SELECT groups.id, COUNT(user_group_memberships.user_id) AS member_count "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id GROUP BY groups.id"
    )
    distinct = _extract(
        "SELECT groups.id, COUNT(DISTINCT user_group_memberships.user_id) "
        "AS member_count FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id GROUP BY groups.id"
    )

    assert counted.outputs[1].identity != distinct.outputs[1].identity


def test_different_aggregation_targets_have_different_identities() -> None:
    users = _extract(
        "SELECT groups.id, COUNT(user_group_memberships.user_id) AS item_count "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id GROUP BY groups.id"
    )
    memberships = _extract(
        "SELECT groups.id, COUNT(user_group_memberships.group_id) AS item_count "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id GROUP BY groups.id"
    )

    assert users.outputs[1].identity != memberships.outputs[1].identity


def test_grouping_identities_are_canonical_and_define_grouped_grain() -> None:
    provenance = _extract(
        "SELECT departments.name, COUNT(directory_users.id) AS user_count "
        "FROM departments JOIN directory_users "
        "ON directory_users.department_id = departments.id "
        "GROUP BY departments.name"
    )

    assert [field.as_safe_dict() for field in provenance.grouping_fields] == [
        {"table": "departments", "column": "name"}
    ]
    assert provenance.row_grain.mode == "grouped"
    assert provenance.row_grain.identities[0].field == provenance.grouping_fields[0]


def test_ordering_captures_canonical_expression_direction_and_position() -> None:
    provenance = _extract(
        "SELECT groups.id, groups.name, COUNT(*) AS addition_count "
        "FROM groups GROUP BY groups.id, groups.name "
        "ORDER BY addition_count DESC, groups.name ASC"
    )

    assert [item.position for item in provenance.ordering] == [1, 2]
    assert [item.direction for item in provenance.ordering] == ["desc", "asc"]
    assert provenance.ordering[0].identity == provenance.outputs[2].identity
    assert provenance.ordering[1].identity == provenance.outputs[1].identity
    assert provenance.ordering_significance_explicit is False


def test_extra_validated_output_is_explicit_and_authorized() -> None:
    expected = _extract(
        "SELECT user_group_memberships.user_id, groups.name AS group_name "
        "FROM groups JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id",
        validated=True,
    )
    actual = _extract(
        "SELECT user_group_memberships.user_id, groups.name AS group_name, "
        "user_group_memberships.group_id FROM groups "
        "JOIN user_group_memberships "
        "ON user_group_memberships.group_id = groups.id",
        validated=True,
    )

    assert len(expected.outputs) == 2
    assert len(actual.outputs) == 3
    assert actual.outputs[2].identity.field is not None
    assert actual.outputs[2].identity.field.as_safe_dict() == {
        "table": "user_group_memberships",
        "column": "group_id",
    }
    assert actual.outputs[2].authorized is True
    unverified = _extract(
        "SELECT user_group_memberships.group_id "
        "FROM user_group_memberships"
    )
    assert unverified.outputs[0].authorized is None


def test_grouping_changes_structural_row_grain() -> None:
    detail = _extract(
        "SELECT directory_users.id FROM directory_users"
    )
    grouped = _extract(
        "SELECT directory_users.department_id, COUNT(*) AS user_count "
        "FROM directory_users GROUP BY directory_users.department_id"
    )

    assert detail.row_grain.mode == "detail"
    assert grouped.row_grain.mode == "grouped"
    assert detail.row_grain != grouped.row_grain


def test_safe_provenance_serialization_excludes_sql_literals_and_rows() -> None:
    secret = "raw-secret-hostname"
    sql = (
        "SELECT devices.id AS device_id FROM devices "
        f"WHERE devices.hostname = '{secret}'"
    )
    serialized = json.dumps(_extract(sql, validated=True).as_safe_dict(), sort_keys=True)

    assert secret not in serialized
    assert sql not in serialized
    assert "where" not in serialized.lower()
    assert "rows" not in serialized.lower()


def test_runner_builds_independent_safe_baseline_and_final_sql_provenance() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    query_run_id = uuid4()
    final_sql = (
        "SELECT groups.id, COUNT(*) AS membership_addition_count "
        "FROM groups GROUP BY groups.id"
    )
    with Session(engine) as db:
        db.add(
            QueryRun(
                id=query_run_id,
                status="succeeded",
                executed_sql=final_sql,
                query_metadata={"validation": {"valid": True}},
            )
        )
        db.commit()
        case = load_it_operations_evaluation_set().cases_by_id["itops-hard-009"]
        execution = _CaseExecution(
            actual_outcome=ActualOutcome.SUCCESS,
            execution_succeeded=True,
            query_invoked=True,
            query_execution_attempted=True,
            query_run_id=query_run_id,
            actual_rows=(),
            actual_referenced_tables=("groups", "user_group_memberships"),
            error_code=None,
        )

        provenance = _build_case_provenance(db, case, execution)

    assert provenance is not None
    assert provenance.expected is not None
    assert provenance.actual is not None
    assert provenance.expected.authorization_evidence is (
        ProvenanceAuthorizationEvidence.FROZEN_BASELINE_VALIDATED
    )
    assert provenance.actual.authorization_evidence is (
        ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED
    )
    serialized = json.dumps(provenance.as_safe_dict(), sort_keys=True)
    assert final_sql not in serialized


def test_existing_stable_key_scoring_behavior_is_unchanged() -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-hard-005"]
    score = score_evaluation_case(
        case,
        actual_outcome=ExpectedOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=[{"device_id": "device-1"}],
        actual_rows=[{"id": "device-1"}],
    )

    assert score.result_correct is False
    assert score.failure_reasons == ("missing_stable_key",)
