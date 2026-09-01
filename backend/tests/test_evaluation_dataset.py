from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from app.evaluation.contracts import (
    EvaluationAnswerability,
    EvaluationDifficulty,
    EvaluationSemanticSource,
    ExpectedOutcome,
)
from app.evaluation.loader import (
    EVALUATION_DATASET_PATH,
    EVALUATION_V2_DATASET_PATH,
    EvaluationDatasetValidationError,
    load_it_operations_evaluation_set,
    load_it_operations_evaluation_v2_set,
)
from app.evaluation.selection import (
    CANARY_CASE_IDS,
    CANARY_COVERAGE,
    CanaryCoverage,
    EvaluationFilters,
    EvaluationSelectionError,
    EvaluationSuite,
    evaluation_dataset_digest,
    select_evaluation_suite,
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
V1_DATASET_DIGEST = "1e7b12fbf35de4d2c52937a762f3960df444eb3303ee7061a0e4506819c22bc4"
V2_DATASET_DIGEST = "913f8232a795ff59dd2a4ffc5b657bf69239c16182f257fd2850b68d9003de9b"


def _semantic_contract_for_outcome(outcome: str) -> dict[str, object]:
    answerability = {
        "success": "answerable",
        "clarification": "clarification",
        "denied": "denied",
        "unsafe_blocked": "unsafe",
    }[outcome]
    return {
        "answerability": answerability,
        "semantic_source": (
            "explicit_question" if outcome == "success" else "not_applicable"
        ),
        "required_concept_ids": [],
        "required_metric_id": None,
        "required_composition_rule_ids": [],
        "grain_fields": [],
        "output_fields": [],
        "aggregations": [],
        "group_by": [],
        "having": [],
        "ordering": [],
    }


def _v2_document() -> dict[str, object]:
    data = json.loads(EVALUATION_DATASET_PATH.read_text(encoding="utf-8"))
    data["dataset_id"] = "it_operations_v2"
    data["version"] = "2"
    for case in data["cases"]:
        case["semantic_contract"] = _semantic_contract_for_outcome(
            case["expected_outcome"]
        )
    return data


def _write_v2(tmp_path: Path, data: dict[str, object] | None = None) -> Path:
    path = tmp_path / "evaluation_v2.yaml"
    path.write_text(json.dumps(data or _v2_document()), encoding="utf-8")
    return path


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


def test_v1_remains_loadable_with_frozen_digest_and_no_semantic_contract() -> None:
    evaluation_set = load_it_operations_evaluation_set()

    assert evaluation_set.dataset_id == "it_operations_v1"
    assert evaluation_set.version == "1"
    assert all(case.semantic_contract is None for case in evaluation_set.cases)
    assert evaluation_dataset_digest(evaluation_set) == V1_DATASET_DIGEST


def test_reviewed_v2_dataset_is_complete_answerable_and_digest_frozen() -> None:
    evaluation_set = load_it_operations_evaluation_v2_set()

    assert EVALUATION_V2_DATASET_PATH.name == "evaluation_questions_v2.yaml"
    assert evaluation_set.dataset_id == "it_operations_v2"
    assert evaluation_set.version == "2"
    assert len(evaluation_set.cases) == 40
    assert Counter(case.difficulty for case in evaluation_set.cases) == {
        EvaluationDifficulty.EASY: 10,
        EvaluationDifficulty.MEDIUM: 15,
        EvaluationDifficulty.HARD: 10,
        EvaluationDifficulty.SECURITY: 5,
    }
    assert len(evaluation_set.cases_by_id) == 40
    assert evaluation_dataset_digest(evaluation_set) == V2_DATASET_DIGEST

    for case in evaluation_set.cases:
        contract = case.semantic_contract
        assert contract is not None
        if case.expected_outcome is ExpectedOutcome.SUCCESS:
            assert contract.answerability is EvaluationAnswerability.ANSWERABLE
            assert contract.semantic_source is not EvaluationSemanticSource.NOT_APPLICABLE


def test_v2_canary_is_bounded_complete_and_deterministic() -> None:
    evaluation_set = load_it_operations_evaluation_v2_set()

    first = select_evaluation_suite(evaluation_set, EvaluationSuite.CANARY)
    second = select_evaluation_suite(evaluation_set, EvaluationSuite.CANARY)

    assert 8 <= len(CANARY_CASE_IDS) <= 12
    assert len(CANARY_CASE_IDS) == len(set(CANARY_CASE_IDS)) == 10
    assert tuple(case.id for case in first.cases) == CANARY_CASE_IDS
    assert first == second
    assert len(first.suite_digest) == 64
    assert set(CANARY_CASE_IDS) <= set(evaluation_set.cases_by_id)
    assert set(CANARY_COVERAGE) == set(CanaryCoverage)
    assert all(
        set(case_ids) <= set(CANARY_CASE_IDS)
        for case_ids in CANARY_COVERAGE.values()
    )


def test_v2_full_suite_selects_40_and_filtered_run_remains_distinct() -> None:
    evaluation_set = load_it_operations_evaluation_v2_set()

    full = select_evaluation_suite(evaluation_set, EvaluationSuite.FULL)
    filtered = select_evaluation_suite(
        evaluation_set,
        EvaluationSuite.FULL,
        EvaluationFilters(case_id="itops-hard-004"),
    )

    assert len(full.cases) == 40
    assert len(filtered.cases) == 1
    assert filtered.cases[0].id == "itops-hard-004"
    assert filtered.suite_digest == full.suite_digest
    assert filtered.as_safe_dict()["selected_case_ids"] == ["itops-hard-004"]


def test_canary_rejects_filters_and_non_v2_dataset() -> None:
    v2 = load_it_operations_evaluation_v2_set()

    with pytest.raises(EvaluationSelectionError, match="cannot be combined"):
        select_evaluation_suite(
            v2,
            EvaluationSuite.CANARY,
            EvaluationFilters(security_only=True),
        )
    with pytest.raises(EvaluationSelectionError, match="frozen Evaluation V2"):
        select_evaluation_suite(
            load_it_operations_evaluation_set(),
            EvaluationSuite.CANARY,
        )


def test_reviewed_v2_non_execution_cases_are_explicitly_classified() -> None:
    cases = load_it_operations_evaluation_v2_set().cases_by_id

    assert cases["itops-security-001"].semantic_contract.answerability is EvaluationAnswerability.DENIED
    assert cases["itops-security-002"].semantic_contract.answerability is EvaluationAnswerability.DENIED
    assert cases["itops-security-003"].semantic_contract.answerability is EvaluationAnswerability.UNSAFE
    assert cases["itops-security-004"].semantic_contract.answerability is EvaluationAnswerability.DENIED
    assert cases["itops-security-005"].semantic_contract.answerability is EvaluationAnswerability.CLARIFICATION
    assert all(
        cases[f"itops-security-{number:03d}"].security_sensitive
        for number in range(1, 6)
    )


def test_reviewed_v2_ambiguous_historical_terms_have_authoritative_meaning() -> None:
    cases = load_it_operations_evaluation_v2_set().cases_by_id

    assert "last 90 days" in cases["itops-easy-001"].question
    assert "grouped by priority and status" in cases["itops-easy-003"].question
    assert "more than 5 failed logins" in cases["itops-hard-004"].question
    assert "last 30 days" in cases["itops-hard-004"].question
    assert "assigned devices" in cases["itops-hard-002"].question
    assert "monthly savings" in cases["itops-hard-006"].question
    assert "more than 60 days" in cases["itops-hard-006"].question
    assert "number of membership additions" in cases["itops-hard-009"].question
    assert "non-compliant device count" in cases["itops-hard-010"].question
    assert "then by users" in cases["itops-hard-010"].question

    questions = " ".join(case.question.lower() for case in cases.values())
    assert "failed login spike" not in questions
    assert "highest concentration" not in questions
    assert "active devices" not in questions


def test_reviewed_v2_baselines_match_the_reviewed_result_grain() -> None:
    cases = load_it_operations_evaluation_v2_set().cases_by_id

    assert "GROUP BY priority, status" in cases["itops-easy-003"].baseline_sql
    assert cases["itops-medium-003"].expected_tables == (
        "directory_users",
        "license_assignments",
    )
    assert "JOIN licenses" not in cases["itops-medium-003"].baseline_sql
    assert "si.software_name" not in cases["itops-medium-009"].baseline_sql
    assert "SELECT DISTINCT d.id FROM devices" in cases["itops-medium-009"].baseline_sql
    assert "JOIN licenses" not in cases["itops-hard-001"].baseline_sql


def test_reviewed_v2_only_requires_question_requested_ordering() -> None:
    cases = load_it_operations_evaluation_v2_set().cases_by_id
    ordered = {
        case.id: case.semantic_contract.ordering
        for case in cases.values()
        if case.semantic_contract.ordering
    }

    assert set(ordered) == {
        "itops-hard-006",
        "itops-hard-009",
        "itops-hard-010",
    }
    assert len(ordered["itops-hard-006"]) == 1
    assert len(ordered["itops-hard-009"]) == 1
    assert len(ordered["itops-hard-010"]) == 2


def test_v2_contract_loads_and_is_digest_bound(tmp_path: Path) -> None:
    first = load_it_operations_evaluation_set(_write_v2(tmp_path))
    data = _v2_document()
    concept_id = load_it_operations_domain_pack().semantic_catalog.concepts[0].id
    data["cases"][0]["semantic_contract"]["required_concept_ids"] = [concept_id]
    second = load_it_operations_evaluation_set(_write_v2(tmp_path, data))

    assert first.dataset_id == "it_operations_v2"
    assert first.version == "2"
    assert all(case.semantic_contract is not None for case in first.cases)
    assert evaluation_dataset_digest(first) != evaluation_dataset_digest(second)


def test_v2_semantic_identifier_order_is_canonical_for_digest(tmp_path: Path) -> None:
    concepts = load_it_operations_domain_pack().semantic_catalog.concepts
    assert len(concepts) >= 2
    first_data = _v2_document()
    first_data["cases"][0]["semantic_contract"]["required_concept_ids"] = [
        concepts[0].id,
        concepts[1].id,
    ]
    second_data = _v2_document()
    second_data["cases"][0]["semantic_contract"]["required_concept_ids"] = [
        concepts[1].id,
        concepts[0].id,
    ]

    first = load_it_operations_evaluation_set(_write_v2(tmp_path, first_data))
    second = load_it_operations_evaluation_set(_write_v2(tmp_path, second_data))

    assert evaluation_dataset_digest(first) == evaluation_dataset_digest(second)


def test_v2_non_result_cases_omit_irrelevant_semantic_fields(tmp_path: Path) -> None:
    evaluation_set = load_it_operations_evaluation_set(_write_v2(tmp_path))

    for case in evaluation_set.cases:
        if case.expected_outcome is ExpectedOutcome.SUCCESS:
            continue
        assert case.semantic_contract is not None
        safe = case.semantic_contract.as_safe_dict()
        assert safe["required_concept_ids"] == []
        assert safe["required_metric_id"] is None
        assert safe["aggregations"] == []
        assert safe["output_fields"] == []


@pytest.mark.parametrize(
    ("mutate_contract", "message"),
    [
        (
            lambda contract: contract.update(
                {"required_concept_ids": ["unknown_concept"]}
            ),
            "unknown concept",
        ),
        (
            lambda contract: contract.update({"required_metric_id": "unknown_metric"}),
            "unknown metric",
        ),
        (
            lambda contract: contract.update(
                {"required_composition_rule_ids": ["unknown_rule"]}
            ),
            "unknown rule",
        ),
        (
            lambda contract: contract.update(
                {"output_fields": [{"entity_id": "unknown_entity", "column": "id"}]}
            ),
            "unknown entity",
        ),
        (
            lambda contract: contract.update(
                {
                    "output_fields": [
                        {"entity_id": "directory_users", "column": "unknown_column"}
                    ]
                }
            ),
            "unknown entity field",
        ),
        (
            lambda contract: contract.update({"surprise": True}),
            "unknown fields",
        ),
    ],
)
def test_v2_loader_rejects_malformed_semantic_contracts(
    tmp_path: Path,
    mutate_contract,
    message: str,
) -> None:
    data = _v2_document()
    mutate_contract(data["cases"][0]["semantic_contract"])

    with pytest.raises(EvaluationDatasetValidationError, match=message):
        load_it_operations_evaluation_set(_write_v2(tmp_path, data))


def test_v2_loader_rejects_result_semantics_on_denied_case(tmp_path: Path) -> None:
    data = _v2_document()
    denied = next(
        case for case in data["cases"] if case["expected_outcome"] == "denied"
    )
    denied["semantic_contract"]["output_fields"] = [
        {"entity_id": "directory_users", "column": "id"}
    ]

    with pytest.raises(EvaluationDatasetValidationError, match="non-answerable"):
        load_it_operations_evaluation_set(_write_v2(tmp_path, data))


def test_v2_loader_rejects_contract_field_outside_expected_metadata(
    tmp_path: Path,
) -> None:
    data = _v2_document()
    data["cases"][0]["semantic_contract"]["output_fields"] = [
        {"entity_id": "devices", "column": "id"}
    ]

    with pytest.raises(EvaluationDatasetValidationError, match="expected_columns"):
        load_it_operations_evaluation_set(_write_v2(tmp_path, data))


def test_v2_loader_rejects_contract_concept_outside_expected_tables(
    tmp_path: Path,
) -> None:
    data = _v2_document()
    data["cases"][0]["semantic_contract"]["required_concept_ids"] = [
        "privileged_group"
    ]

    with pytest.raises(EvaluationDatasetValidationError, match="expected_tables"):
        load_it_operations_evaluation_set(_write_v2(tmp_path, data))


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


def test_medium_009_baseline_uses_tracked_non_compliant_device_posture() -> None:
    evaluation_set = load_it_operations_evaluation_set()
    pack = load_it_operations_domain_pack()
    case = evaluation_set.cases_by_id["itops-medium-009"]

    assert pack.business_terms_by_name["non-compliant device"].description == (
        "A managed device with non-compliant posture, outdated antivirus, "
        "missing antivirus, or disabled encryption."
    )
    assert (
        "compliance_status = 'non_compliant' OR antivirus_status IN "
        "('outdated', 'missing') OR encryption_enabled = false"
        in pack.template("non_compliant_devices_by_department").sql
    )
    assert (
        "d.compliance_status = 'non_compliant' OR d.antivirus_status IN "
        "('outdated', 'missing') OR d.encryption_enabled = false"
        in case.baseline_sql
    )
    expected_columns = {entry.table: set(entry.columns) for entry in case.expected_columns}
    assert {"compliance_status", "antivirus_status", "encryption_enabled"} <= (
        expected_columns["devices"]
    )


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
