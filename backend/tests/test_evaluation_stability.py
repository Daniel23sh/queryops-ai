from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.evaluation.contracts import CaseType, ExpectedOutcome
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.selection import (
    EvaluationSuite,
    evaluation_dataset_digest,
    select_evaluation_suite,
)
from app.evaluation.stability import (
    StabilityResultEvidence,
    StabilityRunEvidence,
    StabilityStatus,
    evaluate_stability_canary,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import semantic_catalog_identity


def test_zero_one_and_two_matching_runs_preserve_valid_progress() -> None:
    dataset = load_it_operations_evaluation_v2_set()

    for run_count in range(3):
        assessment = _evaluate(
            dataset,
            tuple(_run(index=index) for index in range(run_count)),
        )
        assert assessment.status is StabilityStatus.INCOMPLETE
        assert assessment.reason_code == "stability_runs_missing"
        assert len(assessment.run_ids) == run_count
        assert set(assessment.run_ids) == {
            _run(index=index).run_id for index in range(run_count)
        }


def test_three_matching_passing_runs_form_one_stable_set() -> None:
    assessment = _evaluate(
        load_it_operations_evaluation_v2_set(),
        tuple(_run(index=index) for index in range(3)),
    )

    assert assessment.status is StabilityStatus.PASSED
    assert assessment.reason_code is None
    assert len(assessment.run_ids) == 3
    assert assessment.source_git_sha == "a" * 40
    assert assessment.model_label == "gpt-5.6-terra"


def test_mismatched_sha_or_model_does_not_form_a_stability_set() -> None:
    for mutation in ("sha", "model"):
        runs = [_run(index=0), _run(index=1), _run(index=2)]
        summary = dict(runs[-1].summary)
        if mutation == "sha":
            summary["evaluation_environment"] = {
                **summary["evaluation_environment"],
                "source_git_sha": "b" * 40,
            }
        else:
            summary["model_label"] = "gpt-5.6-luna"
            rows = tuple(
                _with_measurement_model(row, "gpt-5.6-luna")
                for row in runs[-1].results
            )
            runs[-1] = replace(runs[-1], results=rows)
        runs[-1] = replace(runs[-1], summary=summary)

        assessment = _evaluate(
            load_it_operations_evaluation_v2_set(),
            tuple(runs),
        )

        assert assessment.status is StabilityStatus.INCOMPLETE
        assert assessment.reason_code == "stability_identity_mismatch"
        assert len(assessment.run_ids) == 2
        assert assessment.source_git_sha == "a" * 40


def test_mismatched_dataset_and_malformed_results_fail_closed() -> None:
    for mutation in ("dataset", "results"):
        runs = [_run(index=index) for index in range(3)]
        if mutation == "dataset":
            runs[-1] = _with_summary(runs[-1], dataset_digest="0" * 64)
        else:
            runs[-1] = replace(runs[-1], results=runs[-1].results[:-1])

        assessment = _evaluate(
            load_it_operations_evaluation_v2_set(),
            tuple(runs),
        )

        assert assessment.status is StabilityStatus.INCOMPLETE
        assert assessment.reason_code == "stability_evidence_malformed"
        assert len(assessment.run_ids) == 2


def test_mixed_partial_identities_report_only_the_best_matching_group() -> None:
    runs = [
        _run(index=0),
        _run(index=1),
        _with_source_sha(_run(index=2), "b" * 40),
        _with_source_sha(_run(index=3), "c" * 40),
    ]

    assessment = _evaluate(
        load_it_operations_evaluation_v2_set(),
        tuple(runs),
    )

    assert assessment.status is StabilityStatus.INCOMPLETE
    assert assessment.reason_code == "stability_identity_mismatch"
    assert set(assessment.run_ids) == {runs[0].run_id, runs[1].run_id}
    assert assessment.source_git_sha == "a" * 40


def test_security_renderer_and_conformance_defects_fail_the_set() -> None:
    mutations = (
        (_failed_security_run, "stability_security_case_failed"),
        (
            lambda run: _planner_defect(run, "renderer_status"),
            "stability_renderer_defect",
        ),
        (
            lambda run: _planner_defect(run, "conformance_status"),
            "stability_conformance_defect",
        ),
    )
    for mutate, expected_reason in mutations:
        runs = [_run(index=index) for index in range(3)]
        runs[-1] = mutate(runs[-1])

        assessment = _evaluate(
            load_it_operations_evaluation_v2_set(),
            tuple(runs),
        )

        assert assessment.status is StabilityStatus.FAILED
        assert assessment.reason_code == expected_reason


def test_outcome_oscillation_fails_even_when_each_run_clears_aggregate_rates() -> None:
    runs = [_run(index=index) for index in range(3)]
    rows = list(runs[-1].results)
    index = next(
        index
        for index, row in enumerate(rows)
        if row.case_id == "itops-easy-006"
    )
    row = rows[index]
    rows[index] = replace(
        row,
        status="failed",
        score=0.25,
        actual_output={
            **row.actual_output,
            "outcome": "clarification",
            "execution_succeeded": False,
        },
        metrics={
            **row.metrics,
            "score": 0.25,
            "passed": False,
            "outcome_correct": False,
            "execution_correct": False,
            "result_correct": False,
            "query_execution_attempted": False,
            "failure_reasons": [
                "unexpected_outcome",
                "execution_state_mismatch",
                "result_semantics_mismatch",
            ],
            "failure_stage": "plan_generation",
        },
    )
    runs[-1] = replace(runs[-1], results=tuple(rows))

    assessment = _evaluate(
        load_it_operations_evaluation_v2_set(),
        tuple(runs),
    )

    assert assessment.status is StabilityStatus.FAILED
    assert assessment.reason_code == "stability_outcome_oscillation"


def test_latest_complete_identity_set_is_selected_deterministically() -> None:
    older = [_run(index=index) for index in range(3)]
    newer = [
        _with_source_sha(_run(index=index + 3), "b" * 40)
        for index in range(3)
    ]
    newer[-1] = _planner_defect(newer[-1], "renderer_status")

    assessment = _evaluate(
        load_it_operations_evaluation_v2_set(),
        tuple(reversed([*older, *newer])),
    )

    assert assessment.status is StabilityStatus.FAILED
    assert assessment.reason_code == "stability_renderer_defect"
    assert set(assessment.run_ids) == {run.run_id for run in newer}
    assert assessment.source_git_sha == "b" * 40


def _evaluate(dataset, runs):
    return evaluate_stability_canary(
        dataset,
        runs,
        semantic_catalog_identity=semantic_catalog_identity(
            load_it_operations_domain_pack().semantic_catalog
        ),
    )


def _run(*, index: int) -> StabilityRunEvidence:
    dataset = load_it_operations_evaluation_v2_set()
    suite = select_evaluation_suite(dataset, EvaluationSuite.CANARY)
    started_at = datetime(2026, 8, 24, 12, 0, tzinfo=UTC) + timedelta(
        minutes=index
    )
    rows = tuple(_result(dataset.cases_by_id[case_id]) for case_id in suite.as_safe_dict()["selected_case_ids"])
    planner = [
        row.metrics["planner"]
        for row in rows
        if isinstance(row.metrics, dict) and "planner" in row.metrics
    ]
    return StabilityRunEvidence(
        run_id=UUID(f"00000000-0000-4000-8000-{index + 1:012d}"),
        status="succeeded",
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=30),
        summary={
            "provider": "openai",
            "model_label": "gpt-5.6-terra",
            "dataset_id": dataset.dataset_id,
            "dataset_version": dataset.version,
            "dataset_digest": evaluation_dataset_digest(dataset),
            "semantic_catalog": semantic_catalog_identity(
                load_it_operations_domain_pack().semantic_catalog
            ),
            "evaluation_environment": {
                "manifest_version": "queryops-evaluation-environment-v1",
                "seed_version": "it-operations-seed-v1",
                "seed_profile": "medium",
                "seed": 42,
                "reference_time": "2026-08-24T12:00:00Z",
                "source_git_sha": "a" * 40,
                "alembic_revision": "0010_disable_inactive_user",
                "postgres_version": "16.9",
                "database_fingerprint": "b" * 64,
                "dependency_manifest_hash": "c" * 64,
            },
            "evaluation_suite": suite.as_safe_dict(),
            "filters": {
                "case_id": None,
                "difficulty": None,
                "category": None,
                "case_type": None,
                "security_only": False,
            },
            "selected_count": 10,
            "completed_count": 10,
            "failure_code": None,
            "planner_metrics": {
                "eligible_case_count": len(planner),
                "generated_plan_count": len(planner),
                "validated_plan_count": len(planner),
                "semantic_plan_validation_pass_rate": 1.0,
                "required_intent_evaluated_count": len(planner),
                "required_intent_passed_count": len(planner),
                "required_intent_adherence_rate": 1.0,
                "renderer_defect_count": sum(
                    item["renderer_status"] == "failed" for item in planner
                ),
                "conformance_defect_count": sum(
                    item["conformance_status"] == "failed" for item in planner
                ),
                "semantic_contract_evaluated_count": len(planner),
                "semantic_contract_passed_count": len(planner),
                "semantic_contract_pass_rate": 1.0,
            },
        },
        results=rows,
    )


def _result(case) -> StabilityResultEvidence:
    success = case.expected_outcome is ExpectedOutcome.SUCCESS
    metrics: dict[str, Any] = {
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
    }
    if case.template_id is None and success:
        metrics["provider_measurement"] = {
            "provider": "openai",
            "model_label": "gpt-5.6-terra",
            "duration_ms": 1.0,
            "attempt_count": 1,
            "input_tokens": 1,
            "cached_input_tokens": 0,
            "output_tokens": 1,
            "total_tokens": 2,
        }
        metrics["planner"] = {
            "plan_generated": True,
            "plan_validation_status": "passed",
            "required_intent_status": "passed",
            "renderer_status": "passed",
            "conformance_status": "passed",
            "semantic_contract": {
                "evaluated": True,
                "passed": True,
                "concepts_correct": True,
                "metric_correct": True,
                "rules_correct": True,
                "grain_correct": True,
                "outputs_correct": True,
                "aggregations_correct": True,
                "group_by_correct": True,
                "having_correct": True,
                "ordering_correct": True,
                "failure_reasons": [],
            },
        }
    return StabilityResultEvidence(
        case_id=case.id,
        status="succeeded",
        score=1.0,
        expected_output={
            "outcome": case.expected_outcome.value,
            "referenced_tables": list(case.expected_tables),
        },
        actual_output={
            "outcome": case.expected_outcome.value,
            "referenced_tables": list(case.expected_tables),
            "execution_succeeded": success,
            "error_code": None,
        },
        metrics=metrics,
        error_message=None,
    )


def _with_summary(run: StabilityRunEvidence, **updates: Any) -> StabilityRunEvidence:
    return replace(run, summary={**run.summary, **updates})


def _with_source_sha(run: StabilityRunEvidence, source_sha: str) -> StabilityRunEvidence:
    return _with_summary(
        run,
        evaluation_environment={
            **run.summary["evaluation_environment"],
            "source_git_sha": source_sha,
        },
    )


def _with_measurement_model(
    row: StabilityResultEvidence,
    model_label: str,
) -> StabilityResultEvidence:
    if "provider_measurement" not in row.metrics:
        return row
    return replace(
        row,
        metrics={
            **row.metrics,
            "provider_measurement": {
                **row.metrics["provider_measurement"],
                "model_label": model_label,
            },
        },
    )


def _failed_security_run(run: StabilityRunEvidence) -> StabilityRunEvidence:
    dataset = load_it_operations_evaluation_v2_set()
    rows = list(run.results)
    index = next(
        index
        for index, row in enumerate(rows)
        if dataset.cases_by_id[row.case_id].case_type is CaseType.AUTHORIZATION
    )
    row = rows[index]
    rows[index] = replace(
        row,
        status="failed",
        score=2 / 3,
        actual_output={
            **row.actual_output,
            "outcome": "internal_error",
            "error_code": "internal_error",
        },
        metrics={
            **row.metrics,
            "score": 2 / 3,
            "passed": False,
            "outcome_correct": False,
            "failure_reasons": ["unexpected_outcome"],
        },
    )
    return replace(run, results=tuple(rows))


def _planner_defect(
    run: StabilityRunEvidence,
    status_key: str,
) -> StabilityRunEvidence:
    rows = list(run.results)
    index = next(index for index, row in enumerate(rows) if "planner" in row.metrics)
    row = rows[index]
    rows[index] = replace(
        row,
        metrics={
            **row.metrics,
            "planner": {**row.metrics["planner"], status_key: "failed"},
        },
    )
    summary = dict(run.summary)
    planner_metrics = dict(summary["planner_metrics"])
    aggregate_key = (
        "renderer_defect_count"
        if status_key == "renderer_status"
        else "conformance_defect_count"
    )
    planner_metrics[aggregate_key] = 1
    summary["planner_metrics"] = planner_metrics
    return replace(run, summary=summary, results=tuple(rows))
