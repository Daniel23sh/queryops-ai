from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.evaluation.contracts import (
    ActualOutcome,
    CaseType,
    EvaluationDifficulty,
    ExpectedOutcome,
)
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.readiness import (
    GateStatus,
    ReadinessResultEvidence,
    ReadinessRunEvidence,
    ReadinessVerdict,
    V1_READINESS_POLICY_ID,
    evaluate_v1_readiness,
)
from app.evaluation.selection import evaluation_dataset_digest


def test_complete_openai_evidence_passes_exact_policy() -> None:
    dataset = load_it_operations_evaluation_set()
    assessment = evaluate_v1_readiness(dataset, _evidence())

    assert assessment.policy_id == V1_READINESS_POLICY_ID
    assert assessment.verdict is ReadinessVerdict.READY
    assert [gate.code for gate in assessment.gates] == [
        "qualifying_evidence",
        "deterministic_release_gates",
        "execution_success_rate",
        "result_accuracy",
        "unsafe_query_block_rate",
        "clarification_accuracy",
        "security_case_pass_rate",
    ]
    assert all(gate.status is GateStatus.PASSED for gate in assessment.gates)
    assert assessment.gates[2].actual == 1.0
    assert assessment.gates[2].threshold == 0.85
    assert assessment.average_latency_ms == 1.0


@pytest.mark.parametrize(
    ("metric", "mutator", "reason"),
    [
        (
            "execution_success_rate",
            lambda rows: _fail_success_rows(rows, 6, execution=True),
            "execution_success_below_threshold",
        ),
        (
            "result_accuracy",
            lambda rows: _fail_success_rows(rows, 9, result=True),
            "result_accuracy_below_threshold",
        ),
        (
            "unsafe_query_block_rate",
            lambda rows: _mutate_type(rows, CaseType.UNSAFE_SQL, attempted=True),
            "unsafe_block_gate_failed",
        ),
        (
            "clarification_accuracy",
            lambda rows: _mutate_type(rows, CaseType.CLARIFICATION, attempted=True),
            "clarification_gate_failed",
        ),
        (
            "security_case_pass_rate",
            lambda rows: _fail_security(rows),
            "security_gate_failed",
        ),
    ],
)
def test_just_below_each_threshold_is_not_ready(metric, mutator, reason) -> None:
    evidence = _evidence()
    mutated = replace(evidence, results=mutator(list(evidence.results)))
    assessment = evaluate_v1_readiness(load_it_operations_evaluation_set(), mutated)

    gate = next(item for item in assessment.gates if item.code == metric)
    assert assessment.verdict is ReadinessVerdict.NOT_READY
    assert gate.status is GateStatus.FAILED
    assert gate.reason_code == reason


def test_missing_mock_filtered_partial_and_nonterminal_evidence_are_incomplete() -> None:
    dataset = load_it_operations_evaluation_set()
    assert evaluate_v1_readiness(dataset, None).verdict is ReadinessVerdict.INCOMPLETE

    evidence = _evidence()
    mock = _with_summary(evidence, provider="mock", model_label="mock-queryops-v1")
    assert evaluate_v1_readiness(dataset, mock).gates[0].reason_code == "provider_not_eligible"

    filtered = _with_summary(
        evidence,
        filters={
            "case_id": "itops-easy-001",
            "difficulty": None,
            "category": None,
            "case_type": None,
            "security_only": False,
        },
    )
    assert evaluate_v1_readiness(dataset, filtered).gates[0].reason_code == "filtered_run_not_eligible"

    partial = replace(evidence, results=evidence.results[:-1])
    assert evaluate_v1_readiness(dataset, partial).verdict is ReadinessVerdict.INCOMPLETE
    for status in ("running", "failed"):
        nonterminal = replace(evidence, status=status, completed_at=None)
        assert evaluate_v1_readiness(dataset, nonterminal).gates[0].reason_code == "run_incomplete"


@pytest.mark.parametrize("identity_key", ["dataset_id", "dataset_version", "dataset_digest"])
def test_stale_dataset_identity_is_incomplete(identity_key: str) -> None:
    evidence = _with_summary(_evidence(), **{identity_key: "stale"})
    assessment = evaluate_v1_readiness(load_it_operations_evaluation_set(), evidence)
    assert assessment.gates[0].reason_code == "dataset_identity_mismatch"


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "malformed"])
def test_missing_duplicate_extra_or_malformed_results_are_incomplete(mutation: str) -> None:
    evidence = _evidence()
    rows = list(evidence.results)
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = rows[0]
    elif mutation == "extra":
        rows.append(replace(rows[0], case_id="itops-extra-999"))
    else:
        rows[0] = replace(rows[0], metrics={**rows[0].metrics, "passed": "yes"})
    assessment = evaluate_v1_readiness(
        load_it_operations_evaluation_set(), replace(evidence, results=tuple(rows))
    )
    assert assessment.verdict is ReadinessVerdict.INCOMPLETE
    assert assessment.gates[0].reason_code == "result_set_malformed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("score", float("nan")),
        ("passed", 1),
        ("duration_ms", -1),
        ("attempt_count", True),
        ("total_tokens", -1),
    ],
)
def test_invalid_rates_booleans_durations_and_usage_fail_closed(field: str, value: Any) -> None:
    evidence = _evidence()
    row = evidence.results[0]
    metrics = dict(row.metrics)
    score = row.score
    if field == "score":
        score = value
        metrics["score"] = value
    elif field in {"passed", "duration_ms"}:
        metrics[field] = value
    else:
        measurement = dict(metrics["provider_measurement"])
        measurement[field] = value
        metrics["provider_measurement"] = measurement
    rows = (replace(row, score=score, metrics=metrics), *evidence.results[1:])
    assessment = evaluate_v1_readiness(
        load_it_operations_evaluation_set(), replace(evidence, results=tuple(rows))
    )
    assert assessment.verdict is ReadinessVerdict.INCOMPLETE


def test_stored_aggregate_disagreement_cannot_override_recomputed_results() -> None:
    evidence = _with_summary(
        _evidence(),
        overall_score=0.0,
        expected_behavior_match_rate=0.0,
        security_pass_rate=0.0,
    )
    assert evaluate_v1_readiness(
        load_it_operations_evaluation_set(), evidence
    ).verdict is ReadinessVerdict.READY


def test_provider_model_measurement_mismatch_is_incomplete() -> None:
    evidence = _evidence()
    row = evidence.results[0]
    metrics = dict(row.metrics)
    metrics["provider_measurement"] = {
        **metrics["provider_measurement"],
        "model_label": "gpt-5.6-luna",
    }
    assessment = evaluate_v1_readiness(
        load_it_operations_evaluation_set(),
        replace(evidence, results=(replace(row, metrics=metrics), *evidence.results[1:])),
    )
    assert assessment.gates[0].reason_code == "result_set_malformed"


def test_unsafe_and_clarification_execution_attempts_fail_even_with_expected_label() -> None:
    evidence = _evidence()
    rows = _mutate_type(list(evidence.results), CaseType.UNSAFE_SQL, attempted=True)
    rows = list(_mutate_type(list(rows), CaseType.CLARIFICATION, attempted=True))
    assessment = evaluate_v1_readiness(
        load_it_operations_evaluation_set(), replace(evidence, results=tuple(rows))
    )
    assert assessment.verdict is ReadinessVerdict.NOT_READY
    assert next(g for g in assessment.gates if g.code == "unsafe_query_block_rate").actual == 0
    assert next(g for g in assessment.gates if g.code == "clarification_accuracy").actual == 0


def test_deterministic_evidence_is_mandatory_and_no_sensitive_fields_are_projected() -> None:
    assessment = evaluate_v1_readiness(
        load_it_operations_evaluation_set(),
        _evidence(),
        deterministic_evidence_passed=False,
    )
    serialized = repr(assessment)
    assert assessment.verdict is ReadinessVerdict.INCOMPLETE
    assert "deterministic_evidence_missing" in serialized
    for sentinel in ("SELECT secret", "row-secret", "provider-payload", "api-key"):
        assert sentinel not in serialized


def _evidence() -> ReadinessRunEvidence:
    dataset = load_it_operations_evaluation_set()
    rows = tuple(_result(case) for case in dataset.cases)
    usage = {
        "call_count": 40,
        "attempt_count": 40,
        "duration_ms": 40.0,
        "input_tokens": 40,
        "cached_input_tokens": 0,
        "output_tokens": 40,
        "total_tokens": 80,
    }
    return ReadinessRunEvidence(
        run_id=uuid4(),
        status="succeeded",
        completed_at=datetime.now(UTC),
        summary={
            "provider": "openai",
            "model_label": "gpt-5.6-terra",
            "dataset_id": dataset.dataset_id,
            "dataset_version": dataset.version,
            "dataset_digest": evaluation_dataset_digest(dataset),
            "selected_count": 40,
            "completed_count": 40,
            "filters": {
                "case_id": None,
                "difficulty": None,
                "category": None,
                "case_type": None,
                "security_only": False,
            },
            "provider_usage": usage,
            "failure_code": None,
        },
        results=rows,
    )


def _result(case) -> ReadinessResultEvidence:
    success = case.expected_outcome is ExpectedOutcome.SUCCESS
    actual_outcome = case.expected_outcome.value
    return ReadinessResultEvidence(
        case_id=case.id,
        status="succeeded",
        score=1.0,
        expected_output={
            "outcome": case.expected_outcome.value,
            "referenced_tables": list(case.expected_tables),
        },
        actual_output={
            "outcome": actual_outcome,
            "referenced_tables": list(case.expected_tables),
            "execution_succeeded": success,
            "error_code": None,
        },
        metrics={
            "score": 1.0,
            "passed": True,
            "outcome_correct": True,
            "execution_correct": True,
            "tables_correct": True,
            "result_correct": True if success else None,
            "expected_row_count": 1 if success else 0,
            "actual_row_count": 1 if success else 0,
            "failure_reasons": [],
            "difficulty": case.difficulty.value,
            "category": case.category,
            "case_type": case.case_type.value,
            "security_sensitive": case.security_sensitive,
            "duration_ms": 1.0,
            "missing_row_count": 0,
            "extra_row_count": 0,
            "query_invoked": case.case_type is not CaseType.AUTHORIZATION,
            "query_execution_attempted": success,
            "provider_measurement": {
                "provider": "openai",
                "model_label": "gpt-5.6-terra",
                "duration_ms": 1.0,
                "attempt_count": 1,
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 1,
                "total_tokens": 2,
            },
        },
        error_message=None,
    )


def _with_summary(evidence: ReadinessRunEvidence, **updates: Any) -> ReadinessRunEvidence:
    return replace(evidence, summary={**evidence.summary, **updates})


def _fail_success_rows(rows, count: int, *, execution=False, result=False):
    dataset = load_it_operations_evaluation_set()
    output = list(rows)
    indexes = [
        index
        for index, row in enumerate(output)
        if dataset.cases_by_id[row.case_id].expected_outcome is ExpectedOutcome.SUCCESS
    ][:count]
    for index in indexes:
        row = output[index]
        metrics = dict(row.metrics)
        actual = dict(row.actual_output)
        if execution:
            actual["outcome"] = ActualOutcome.EXECUTION_FAILED.value
            actual["execution_succeeded"] = False
            metrics.update(
                {
                    "outcome_correct": False,
                    "execution_correct": False,
                    "passed": False,
                    "score": 0.5,
                    "failure_reasons": [
                        "unexpected_outcome",
                        "execution_state_mismatch",
                    ],
                }
            )
        if result:
            metrics["result_correct"] = False
            metrics.update(
                {
                    "passed": False,
                    "score": 0.75,
                    "failure_reasons": ["result_semantics_mismatch"],
                }
            )
        output[index] = replace(
            row,
            status="failed",
            score=metrics["score"],
            actual_output=actual,
            metrics=metrics,
        )
    return tuple(output)


def _mutate_type(rows, case_type: CaseType, *, attempted: bool):
    dataset = load_it_operations_evaluation_set()
    for index, row in enumerate(rows):
        if dataset.cases_by_id[row.case_id].case_type is case_type:
            rows[index] = replace(
                row,
                metrics={**row.metrics, "query_execution_attempted": attempted},
            )
    return tuple(rows)


def _fail_security(rows):
    dataset = load_it_operations_evaluation_set()
    for index, row in enumerate(rows):
        if dataset.cases_by_id[row.case_id].difficulty is EvaluationDifficulty.SECURITY:
            rows[index] = replace(
                row,
                status="failed",
                score=2 / 3,
                actual_output={**row.actual_output, "outcome": "internal_error"},
                metrics={
                    **row.metrics,
                    "score": 2 / 3,
                    "passed": False,
                    "outcome_correct": False,
                    "failure_reasons": ["unexpected_outcome"],
                },
            )
            break
    return tuple(rows)
