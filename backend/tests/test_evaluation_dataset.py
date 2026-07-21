from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from app.evaluation.contracts import EvaluationDifficulty, ExpectedOutcome
from app.evaluation.loader import (
    EVALUATION_DATASET_PATH,
    EvaluationDatasetValidationError,
    load_it_operations_evaluation_set,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack


EXPECTED_TEMPLATE_IDS = {
    "high_severity_security_events_by_department",
    "inactive_users_by_department",
    "non_compliant_devices_by_department",
    "open_support_tickets_by_department",
    "privileged_group_memberships_by_department",
    "unused_licenses_by_department",
}


def test_dataset_has_exact_distribution_unique_ids_and_deterministic_order() -> None:
    first = load_it_operations_evaluation_set()
    second = load_it_operations_evaluation_set()

    assert len(first.cases) == 40
    assert Counter(case.difficulty for case in first.cases) == {
        EvaluationDifficulty.EASY: 10,
        EvaluationDifficulty.MEDIUM: 15,
        EvaluationDifficulty.HARD: 10,
        EvaluationDifficulty.SECURITY: 5,
    }
    assert [case.id for case in first.cases] == sorted(case.id for case in first.cases)
    assert len(first.cases_by_id) == 40
    assert first == second


def test_dataset_references_only_known_tables_and_columns() -> None:
    evaluation_set = load_it_operations_evaluation_set()
    pack = load_it_operations_domain_pack()

    for case in evaluation_set.cases:
        assert set(case.expected_tables) == {entry.table for entry in case.expected_columns}
        for entry in case.expected_columns:
            assert entry.table in pack.tables_by_name
            assert set(entry.columns) <= set(pack.table(entry.table).columns_by_name)


def test_executable_baselines_are_safe_and_protected_tables_are_never_executable() -> None:
    evaluation_set = load_it_operations_evaluation_set()
    pack = load_it_operations_domain_pack()

    for case in evaluation_set.cases:
        if case.expected_outcome is ExpectedOutcome.SUCCESS:
            assert case.baseline_sql is not None
            assert case.baseline_sql.lstrip().lower().startswith(("select ", "with "))
            assert ";" not in case.baseline_sql
            assert all(pack.table(table).queryable for table in case.expected_tables)
            assert set(case.expected_tables) <= set(pack.allowed_resource_table_names)
        else:
            assert case.baseline_sql is None


def test_existing_six_template_evaluation_cases_are_represented() -> None:
    evaluation_set = load_it_operations_evaluation_set()
    template_cases = {case.template_id: case for case in evaluation_set.cases if case.template_id}

    assert set(template_cases) == EXPECTED_TEMPLATE_IDS
    pack = load_it_operations_domain_pack()
    for template_id in EXPECTED_TEMPLATE_IDS:
        assert template_cases[template_id].question == pack.template(template_id).natural_language_question


def test_roles_scope_modes_and_security_non_execution_expectations_are_valid() -> None:
    evaluation_set = load_it_operations_evaluation_set()
    security_cases = [
        case for case in evaluation_set.cases if case.difficulty is EvaluationDifficulty.SECURITY
    ]

    assert len(security_cases) == 5
    assert {case.requesting_role.value for case in evaluation_set.cases} <= {
        "user", "manager", "analyst", "admin"
    }
    assert {case.scope_mode.value for case in evaluation_set.cases} <= {
        "none", "assigned", "global", "cross_scope"
    }
    assert all(case.security_sensitive for case in security_cases)
    assert all(case.expected_outcome is not ExpectedOutcome.SUCCESS for case in security_cases)


def test_loader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(EvaluationDatasetValidationError, match="not found"):
        load_it_operations_evaluation_set(tmp_path / "missing.yaml")


def test_loader_rejects_malformed_content(tmp_path: Path) -> None:
    path = tmp_path / "evaluation.yaml"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(EvaluationDatasetValidationError, match="Invalid JSON-compatible"):
        load_it_operations_evaluation_set(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["cases"][0].update({"surprise": True}), "unknown fields"),
        (lambda data: data["cases"][1].update({"id": data["cases"][0]["id"]}), "duplicate"),
        (lambda data: data["cases"][0].update({"difficulty": "impossible"}), "unknown value"),
        (lambda data: data["cases"][0].update({"expected_tables": ["invented"]}), "unknown table"),
        (
            lambda data: data["cases"][0]["expected_columns"]["directory_users"].append(
                "invented_column"
            ),
            "unknown column",
        ),
        (
            lambda data: data["cases"][0].update(
                {"baseline_sql": "UPDATE directory_users SET account_status = 'disabled'"}
            ),
            "not safe read-only SQL",
        ),
        (lambda data: data["cases"][0].update({"expected_outcome": "denied"}), "contradictory"),
        (lambda data: data["cases"][0].update({"difficulty": "medium"}), "distribution"),
    ],
)
def test_loader_rejects_invalid_dataset_variants(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    data = json.loads(EVALUATION_DATASET_PATH.read_text(encoding="utf-8"))
    mutation(data)
    path = tmp_path / "evaluation.yaml"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(EvaluationDatasetValidationError, match=message):
        load_it_operations_evaluation_set(path)


def test_loader_rejects_missing_required_field(tmp_path: Path) -> None:
    data = json.loads(EVALUATION_DATASET_PATH.read_text(encoding="utf-8"))
    del data["cases"][0]["question"]
    path = tmp_path / "evaluation.yaml"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(EvaluationDatasetValidationError, match="missing fields"):
        load_it_operations_evaluation_set(path)
