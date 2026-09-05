from __future__ import annotations

import ast
import json
import socket
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.evaluation.contracts import CaseType, EvaluationAnswerability
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.selection import V2_DATASET_DIGEST, evaluation_dataset_digest
from app.evaluation.structural_conformance import (
    CURRENT_GROUNDING_UNAVAILABLE_COMPONENTS,
    Compatibility,
    ComponentRelation,
    Coverage,
    StructuralCapability,
    _axis_report,
    build_v2_structural_conformance_report,
)
from app.query_engine.semantic_plan import SemanticAggregationIntent, SemanticFieldRef
from app.query_engine.structural_intent import (
    StructuralRowGrain,
    empty_structural_intent,
    known,
)
from app.query_engine.structural_intent_adapters import StructuralMappingError
from app.query_engine.structural_intent_comparison import (
    StructuralComparisonPolicy,
    StructuralRequirement,
)
from scripts.audit_structural_conformance import run_cli


@pytest.fixture(scope="module")
def report():
    return build_v2_structural_conformance_report()


def by_id(report):
    return {case.case_id: case for case in report.cases}


def components(axis):
    return dict(axis.components)


def test_report_is_deterministic_and_json_safe(report):
    first = json.dumps(report.as_safe_dict(), sort_keys=True, separators=(",", ":"))
    second = json.dumps(
        build_v2_structural_conformance_report().as_safe_dict(),
        sort_keys=True,
        separators=(",", ":"),
    )
    assert first == second
    assert "SELECT " not in first
    assert "baseline_sql" not in first
    assert "question" not in first
    assert "prompt" not in first


def test_all_frozen_cases_accounted_for_once_and_digest_unchanged(report):
    evaluation_set = load_it_operations_evaluation_v2_set()
    ids = [case.case_id for case in report.cases]
    assert len(ids) == len(set(ids)) == len(evaluation_set.cases) == 40
    assert set(ids) == set(evaluation_set.cases_by_id)
    assert report.dataset_digest == evaluation_dataset_digest(evaluation_set)
    assert report.dataset_digest == V2_DATASET_DIGEST


def test_answerability_and_query_type_scopes_are_separate(report):
    evaluation_set = load_it_operations_evaluation_v2_set()
    expected_answerable = {
        case.id
        for case in evaluation_set.cases
        if case.semantic_contract.answerability is EvaluationAnswerability.ANSWERABLE
    }
    actual_answerable = {case.case_id for case in report.cases if case.answerable}
    assert actual_answerable == expected_answerable
    assert report.all_cases.case_count == 40
    assert report.answerable_cases.case_count == 35
    assert report.free_query_answerable_cases.case_count == 29
    assert Counter(case.case_type for case in report.cases) == {
        CaseType.TEMPLATE_QUERY.value: 6,
        CaseType.FREE_QUERY.value: 29,
        CaseType.AUTHORIZATION.value: 3,
        CaseType.UNSAFE_SQL.value: 1,
        CaseType.CLARIFICATION.value: 1,
    }
    for case in report.cases:
        if not case.answerable:
            assert case.compatibility is Compatibility.NOT_APPLICABLE
            assert case.expected is None
            assert case.required.coverage is Coverage.NOT_APPLICABLE
            assert case.suggested.coverage is Coverage.NOT_APPLICABLE


def test_required_and_suggested_axes_are_independent(report):
    cases = by_id(report)
    assert cases["itops-medium-013"].required.coverage is Coverage.NONE
    assert cases["itops-medium-013"].suggested.coverage is Coverage.PARTIAL
    assert (
        cases["itops-medium-013"].required.structural_intent
        != cases["itops-medium-013"].suggested.structural_intent
    )
    assert cases["itops-medium-014"].required.coverage is Coverage.NONE
    assert cases["itops-medium-014"].suggested.coverage is Coverage.PARTIAL


def test_missing_output_semantics_are_not_conflicts(report):
    case = by_id(report)["itops-easy-006"]
    diagnostic = components(case.required)["output_fields"]
    assert diagnostic.relation is ComponentRelation.UNSPECIFIED
    assert diagnostic.provable_conflict is False
    assert case.compatibility is Compatibility.COMPATIBLE


def test_incompatible_exact_aggregation_is_a_conservative_conflict(report):
    case = by_id(report)["itops-medium-006"]
    diagnostic = components(case.required)["aggregations"]
    assert diagnostic.relation is ComponentRelation.CONFLICT
    assert diagnostic.provable_conflict is True
    assert case.compatibility is Compatibility.CONFLICT
    expected = case.expected["aggregations"]["value"][0]
    grounded = case.required.structural_intent["aggregations"]["value"][0]
    assert expected["field"] == {"entity_id": "directory_users", "column": "id"}
    assert grounded["field"] == {"entity_id": "groups", "column": "id"}
    assert report.normalization_rules_reused == ()


def test_partial_aggregate_coverage_is_independent_from_exact_conflict():
    field = SemanticFieldRef(entity_id="records", column="id")

    def aggregation(identifier, distinct):
        return SemanticAggregationIntent(
            id=identifier,
            function="count",
            field=field,
            distinct=distinct,
        )

    common = aggregation("common", False)
    expected_intent = empty_structural_intent().model_copy(
        update={"aggregations": known((common, aggregation("expected", True)))}
    )
    grounded_intent = empty_structural_intent().model_copy(
        update={"aggregations": known((common, aggregation("grounded", False)))}
    )
    expected = StructuralRequirement(
        intent=expected_intent,
        policy=StructuralComparisonPolicy(aggregations="required_subset"),
        binding="required",
    )
    grounding = StructuralRequirement(
        intent=grounded_intent,
        policy=StructuralComparisonPolicy(aggregations="exact"),
        binding="required",
    )
    axis = _axis_report(expected, grounding)
    diagnostic = components(axis)["aggregations"]
    assert diagnostic.relation is ComponentRelation.CONFLICT
    assert diagnostic.coverage_relation is ComponentRelation.PARTIALLY_COVERED
    assert diagnostic.provable_conflict is True
    assert axis.coverage is Coverage.PARTIAL


@pytest.mark.parametrize("forcing_component", ["aggregations", "group_by"])
def test_detail_grain_conflicts_with_forced_aggregate_or_grouping(forcing_component):
    field = SemanticFieldRef(entity_id="records", column="id")
    expected_intent = empty_structural_intent().model_copy(
        update={
            "row_grain": known(
                StructuralRowGrain(
                    mode="detail",
                    identity_fields=known((field,)),
                )
            )
        }
    )
    grounding_update = (
        {
            "aggregations": known(
                (
                    SemanticAggregationIntent(
                        id="count",
                        function="count",
                        field=None,
                        distinct=False,
                    ),
                )
            )
        }
        if forcing_component == "aggregations"
        else {"group_by": known((field,))}
    )
    expected = StructuralRequirement(
        intent=expected_intent,
        policy=StructuralComparisonPolicy(row_grain="required_subset"),
        binding="required",
    )
    grounding = StructuralRequirement(
        intent=empty_structural_intent().model_copy(update=grounding_update),
        policy=StructuralComparisonPolicy(**{forcing_component: "exact"}),
        binding="required",
    )
    axis = _axis_report(expected, grounding)
    diagnostic = components(axis)[forcing_component]
    assert diagnostic.relation is ComponentRelation.CONFLICT
    assert diagnostic.coverage_relation is ComponentRelation.NOT_APPLICABLE
    assert diagnostic.provable_conflict is True
    assert axis.coverage is Coverage.NONE


def test_ordering_is_unrepresented_not_a_conflict(report):
    case = by_id(report)["itops-hard-007"]
    diagnostic = components(case.required)["ordering"]
    assert CURRENT_GROUNDING_UNAVAILABLE_COMPONENTS == {"ordering"}
    assert diagnostic.relation is ComponentRelation.UNSUPPORTED
    assert diagnostic.provable_conflict is False
    assert case.compatibility is Compatibility.COMPATIBLE


def test_multiple_structural_items_and_order_priority_are_preserved(report):
    case = by_id(report)["itops-hard-010"]
    expected = case.expected
    assert len(expected["aggregations"]["value"]) == 2
    assert len(expected["group_by"]["value"]) == 2
    assert [item["aggregation_id"] for item in expected["ordering"]["value"]] == [
        "risky_device_count",
        "inactive_user_count",
    ]
    matrix = {item.capability: item for item in report.capability_matrix}
    assert matrix[StructuralCapability.MULTI_AGGREGATE].total_applicable_cases > 0
    assert matrix[StructuralCapability.MULTI_ORDERING].total_applicable_cases > 0


def test_capabilities_come_from_structure_not_difficulty(report):
    cases = by_id(report)
    assert StructuralCapability.CANONICAL_METRIC in cases["itops-easy-005"].capabilities
    assert (
        StructuralCapability.DISTINCT_DETAIL in cases["itops-medium-009"].capabilities
    )
    assert StructuralCapability.HAVING in cases["itops-medium-008"].capabilities
    assert StructuralCapability.JOINED_AGGREGATE in cases["itops-hard-003"].capabilities
    assert StructuralCapability.COMPOSITION_RULE in cases["itops-hard-007"].capabilities
    assert all(
        item.total_applicable_cases
        == sum(
            item.capability in case.capabilities
            for case in report.cases
            if case.answerable and case.case_type == CaseType.FREE_QUERY.value
        )
        for item in report.capability_matrix
    )


def test_no_network_provider_or_database_path_is_available(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("external side effect attempted")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(Session, "execute", forbidden)
    report = build_v2_structural_conformance_report()
    assert len(report.cases) == 40

    tree = ast.parse(Path("app/evaluation/structural_conformance.py").read_text())
    imports = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    forbidden_roots = {
        "app.db",
        "app.evaluation.baseline",
        "app.evaluation.runner",
        "app.evaluation.scoring",
        "app.evaluation.readiness",
        "app.models",
        "app.query_engine.openai_provider",
        "app.query_engine.plan_generator",
        "app.query_engine.sql_renderer",
        "app.query_engine.semantic_conformance",
    }
    assert not {
        imported
        for imported in imports
        if any(imported.startswith(root) for root in forbidden_roots)
    }


def test_required_and_suggested_mapping_failures_are_isolated(monkeypatch):
    import app.evaluation.structural_conformance as harness

    original = harness.grounded_to_structural_requirement

    def fail_suggested(*args, **kwargs):
        if kwargs["binding"] == "suggested":
            raise StructuralMappingError("safe mapping failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(harness, "grounded_to_structural_requirement", fail_suggested)
    suggested_failure = by_id(build_v2_structural_conformance_report())[
        "itops-medium-013"
    ]
    assert suggested_failure.compatibility is Compatibility.COMPATIBLE
    assert suggested_failure.required.coverage is Coverage.NONE
    assert suggested_failure.suggested.coverage is Coverage.NONE
    assert all(
        item.relation is ComponentRelation.UNAVAILABLE
        for _, item in suggested_failure.suggested.components
    )

    def fail_required(*args, **kwargs):
        if kwargs["binding"] == "required":
            raise StructuralMappingError("safe mapping failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(harness, "grounded_to_structural_requirement", fail_required)
    required_failure = by_id(build_v2_structural_conformance_report())[
        "itops-medium-013"
    ]
    assert required_failure.compatibility is Compatibility.UNAVAILABLE
    assert required_failure.required.coverage is Coverage.NONE
    assert required_failure.suggested.coverage is Coverage.PARTIAL


def test_scoring_readiness_and_runtime_do_not_import_harness():
    for path in (
        Path("app/evaluation/scoring.py"),
        Path("app/evaluation/readiness.py"),
        Path("app/evaluation/runner.py"),
        Path("app/query_engine/semantic_grounding.py"),
        Path("app/query_engine/semantic_plan.py"),
        Path("app/query_engine/sql_renderer.py"),
        Path("app/query_engine/semantic_conformance.py"),
    ):
        assert "structural_conformance" not in path.read_text(), path


def test_cli_text_and_json_are_deterministic(capsys):
    assert run_cli([]) == 0
    text = capsys.readouterr().out
    assert "all_cases: cases=40" in text
    assert "free_query_answerable_cases: cases=29" in text
    assert "Capability matrix" in text
    assert run_cli(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summaries"]["all_cases"]["case_count"] == 40
    assert len(payload["cases"]) == 40
