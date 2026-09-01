from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from app.evaluation.contracts import (
    ActualOutcome,
    CaseType,
    EvaluationDifficulty,
    EvaluationSet,
    ExpectedOutcome,
)
from app.evaluation.environment import (
    reference_time_is_eligible,
    validate_persisted_environment_identity,
)
from app.evaluation.readiness_policy import (
    V1_CLARIFICATION_THRESHOLD,
    V1_EXECUTION_SUCCESS_THRESHOLD,
    V1_READINESS_POLICY_ID,
    V1_REQUIRED_CASE_COUNT,
    V1_RESULT_ACCURACY_THRESHOLD,
    V1_SECURITY_THRESHOLD,
    V1_UNSAFE_BLOCK_THRESHOLD,
)
from app.evaluation.selection import (
    EvaluationSuite,
    evaluation_dataset_digest,
    select_evaluation_suite,
)
from app.evaluation.scoring import SAFE_FAILURE_REASONS
from app.evaluation.stability import StabilityCanaryAssessment, StabilityStatus
from app.query_engine.llm_provider import sanitize_provider_measurement
from app.query_engine.provider_config import valid_model_label


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ReadinessVerdict(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    INCOMPLETE = "incomplete"


class GateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class ReadinessResultEvidence:
    case_id: str
    status: str
    score: Any
    expected_output: Any
    actual_output: Any
    metrics: Any
    error_message: str | None


@dataclass(frozen=True)
class ReadinessRunEvidence:
    run_id: UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    summary: Any
    results: tuple[ReadinessResultEvidence, ...]


@dataclass(frozen=True)
class ReadinessUsage:
    call_count: int
    attempt_count: int
    duration_ms: float
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ReadinessGate:
    code: str
    label: str
    status: GateStatus
    threshold: float | None = None
    actual: float | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class ReadinessAssessment:
    policy_id: str
    verdict: ReadinessVerdict
    run_id: UUID | None
    provider: str | None
    model_label: str | None
    dataset_id: str
    dataset_version: str
    dataset_digest: str
    semantic_catalog: dict[str, str]
    evaluation_environment: dict[str, str | int]
    selected_count: int | None
    completed_count: int | None
    average_latency_ms: float | None
    usage: ReadinessUsage | None
    gates: tuple[ReadinessGate, ...]
    stability_canary: StabilityCanaryAssessment


@dataclass(frozen=True)
class _ParsedResult:
    case_id: str
    actual_outcome: str
    query_execution_attempted: bool
    execution_succeeded: bool
    result_correct: bool | None
    passed: bool
    duration_ms: float
    provider_measurement: dict[str, Any] | None


_GATE_DEFINITIONS = (
    ("qualifying_evidence", "Qualifying full V2 OpenAI evidence", None),
    ("deterministic_release_gates", "Deterministic release gates", None),
    ("stability_canary", "Three-run V2 stability canary", None),
    ("planner_implementation_integrity", "Planner implementation integrity", None),
    ("execution_success_rate", "Execution success rate", V1_EXECUTION_SUCCESS_THRESHOLD),
    ("result_accuracy", "Result accuracy", V1_RESULT_ACCURACY_THRESHOLD),
    ("unsafe_query_block_rate", "Unsafe query block rate", V1_UNSAFE_BLOCK_THRESHOLD),
    ("clarification_accuracy", "Clarification accuracy", V1_CLARIFICATION_THRESHOLD),
    ("security_case_pass_rate", "Security-case pass rate", V1_SECURITY_THRESHOLD),
)
_METRICS_FIELDS = frozenset(
    {
        "score",
        "passed",
        "outcome_correct",
        "execution_correct",
        "tables_correct",
        "result_correct",
        "expected_row_count",
        "actual_row_count",
        "failure_reasons",
        "difficulty",
        "category",
        "case_type",
        "security_sensitive",
        "duration_ms",
        "missing_row_count",
        "extra_row_count",
        "query_invoked",
        "query_execution_attempted",
        "provider_measurement",
        "failure_stage",
        "stage_reason_code",
        "planner",
        "result_provenance",
    }
)
_MEASUREMENT_FIELDS = frozenset(
    {
        "provider",
        "model_label",
        "duration_ms",
        "attempt_count",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
    }
)
_USAGE_FIELDS = frozenset(
    {
        "call_count",
        "attempt_count",
        "duration_ms",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
    }
)
_SAFE_ERROR_CODES = frozenset(
    {
        "access_denied",
        "clarification_required",
        "execution_failed",
        "internal_error",
        "unsafe_sql_blocked",
        "provider_authentication_failed",
        "provider_timeout",
        "provider_unavailable",
        "provider_response_invalid",
        "semantic_conformance_failed",
        "semantic_sql_render_failed",
        "validation_failed",
    }
)
_SAFE_PIPELINE_STAGES = frozenset(
    {
        "grounding",
        "plan_generation",
        "plan_validation",
        "sql_rendering",
        "sql_safety",
        "semantic_conformance",
        "execution",
        "result_comparison",
        "setup",
    }
)


def evaluate_v1_readiness(
    evaluation_set: EvaluationSet,
    evidence: ReadinessRunEvidence | None,
    *,
    deterministic_evidence_passed: bool,
    semantic_catalog_identity: Mapping[str, Any],
    stability_canary: StabilityCanaryAssessment,
) -> ReadinessAssessment:
    digest = evaluation_dataset_digest(evaluation_set)
    current_catalog = _validated_catalog_identity(semantic_catalog_identity)
    if current_catalog is None:
        return _incomplete(
            evaluation_set,
            digest,
            "semantic_catalog_identity_mismatch",
            stability_canary=stability_canary,
        )
    if stability_canary.status is not StabilityStatus.PASSED:
        return _stability_blocked(
            evaluation_set,
            digest,
            current_catalog,
            stability_canary,
        )
    if evidence is None:
        return _incomplete(
            evaluation_set,
            digest,
            "qualifying_run_missing",
            semantic_catalog=current_catalog,
            stability_canary=stability_canary,
        )
    validated = _validate_evidence(
        evaluation_set,
        digest,
        current_catalog,
        evidence,
        stability_canary,
    )
    if isinstance(validated, str):
        return _incomplete(
            evaluation_set,
            digest,
            validated,
            evidence=evidence,
            semantic_catalog=current_catalog,
            stability_canary=stability_canary,
        )
    summary, results, usage, environment, planner_defects = validated

    gates: list[ReadinessGate] = [
        ReadinessGate(
            code="qualifying_evidence",
            label="Qualifying full V2 OpenAI evidence",
            status=GateStatus.PASSED,
        ),
        ReadinessGate(
            code="deterministic_release_gates",
            label="Deterministic release gates",
            status=(
                GateStatus.PASSED
                if deterministic_evidence_passed
                else GateStatus.INCOMPLETE
            ),
            reason_code=(
                None if deterministic_evidence_passed else "deterministic_evidence_missing"
            ),
        ),
        ReadinessGate(
            code="stability_canary",
            label="Three-run V2 stability canary",
            status=GateStatus.PASSED,
        ),
        ReadinessGate(
            code="planner_implementation_integrity",
            label="Planner implementation integrity",
            status=(
                GateStatus.PASSED
                if planner_defects == (0, 0)
                else GateStatus.FAILED
            ),
            reason_code=(
                None
                if planner_defects == (0, 0)
                else "planner_implementation_defect"
            ),
        ),
    ]
    success_cases = tuple(
        result
        for result in results
        if evaluation_set.cases_by_id[result.case_id].expected_outcome
        is ExpectedOutcome.SUCCESS
    )
    unsafe_cases = tuple(
        result
        for result in results
        if evaluation_set.cases_by_id[result.case_id].case_type is CaseType.UNSAFE_SQL
    )
    clarification_cases = tuple(
        result
        for result in results
        if evaluation_set.cases_by_id[result.case_id].case_type
        is CaseType.CLARIFICATION
    )
    security_cases = tuple(
        result
        for result in results
        if evaluation_set.cases_by_id[result.case_id].difficulty
        is EvaluationDifficulty.SECURITY
    )
    if len(security_cases) != 5:
        return _incomplete(
            evaluation_set,
            digest,
            "result_set_malformed",
            evidence=evidence,
            semantic_catalog=current_catalog,
            stability_canary=stability_canary,
        )
    metric_inputs = (
        (
            "execution_success_rate",
            "Execution success rate",
            V1_EXECUTION_SUCCESS_THRESHOLD,
            success_cases,
            lambda result: (
                result.actual_outcome == ActualOutcome.SUCCESS.value
                and result.query_execution_attempted
                and result.execution_succeeded
            ),
            "execution_success_below_threshold",
        ),
        (
            "result_accuracy",
            "Result accuracy",
            V1_RESULT_ACCURACY_THRESHOLD,
            success_cases,
            lambda result: result.result_correct is True,
            "result_accuracy_below_threshold",
        ),
        (
            "unsafe_query_block_rate",
            "Unsafe query block rate",
            V1_UNSAFE_BLOCK_THRESHOLD,
            unsafe_cases,
            lambda result: (
                result.actual_outcome == ActualOutcome.UNSAFE_BLOCKED.value
                and not result.query_execution_attempted
            ),
            "unsafe_block_gate_failed",
        ),
        (
            "clarification_accuracy",
            "Clarification accuracy",
            V1_CLARIFICATION_THRESHOLD,
            clarification_cases,
            lambda result: (
                result.actual_outcome == ActualOutcome.CLARIFICATION.value
                and not result.query_execution_attempted
            ),
            "clarification_gate_failed",
        ),
        (
            "security_case_pass_rate",
            "Security-case pass rate",
            V1_SECURITY_THRESHOLD,
            security_cases,
            lambda result: result.passed,
            "security_gate_failed",
        ),
    )
    for code, label, threshold, denominator, predicate, failure_code in metric_inputs:
        if not denominator:
            gates.append(
                ReadinessGate(
                    code=code,
                    label=label,
                    status=GateStatus.INCOMPLETE,
                    threshold=threshold,
                    reason_code="result_set_malformed",
                )
            )
            continue
        actual = round(sum(predicate(result) for result in denominator) / len(denominator), 6)
        passed = actual >= threshold
        gates.append(
            ReadinessGate(
                code=code,
                label=label,
                status=GateStatus.PASSED if passed else GateStatus.FAILED,
                threshold=threshold,
                actual=actual,
                reason_code=None if passed else failure_code,
            )
        )

    if any(gate.status is GateStatus.INCOMPLETE for gate in gates):
        verdict = ReadinessVerdict.INCOMPLETE
    elif any(gate.status is GateStatus.FAILED for gate in gates):
        verdict = ReadinessVerdict.NOT_READY
    else:
        verdict = ReadinessVerdict.READY
    return ReadinessAssessment(
        policy_id=V1_READINESS_POLICY_ID,
        verdict=verdict,
        run_id=evidence.run_id,
        provider="openai",
        model_label=str(summary["model_label"]),
        dataset_id=evaluation_set.dataset_id,
        dataset_version=evaluation_set.version,
        dataset_digest=digest,
        semantic_catalog=current_catalog,
        evaluation_environment=environment.as_dict(),
        selected_count=V1_REQUIRED_CASE_COUNT,
        completed_count=V1_REQUIRED_CASE_COUNT,
        average_latency_ms=round(
            sum(result.duration_ms for result in results) / len(results), 3
        ),
        usage=usage,
        gates=tuple(gates),
        stability_canary=stability_canary,
    )


def _validate_evidence(
    evaluation_set: EvaluationSet,
    digest: str,
    semantic_catalog_identity: dict[str, str],
    evidence: ReadinessRunEvidence,
    stability_canary: StabilityCanaryAssessment,
) -> tuple[
    dict[str, Any],
    tuple[_ParsedResult, ...],
    ReadinessUsage,
    Any,
    tuple[int, int],
] | str:
    if evidence.status != "succeeded" or evidence.completed_at is None:
        return "run_incomplete"
    if not isinstance(evidence.summary, dict):
        return "result_set_malformed"
    summary = evidence.summary
    if summary.get("provider") != "openai":
        return "provider_not_eligible"
    if not valid_model_label(summary.get("model_label")):
        return "provider_not_eligible"
    if (
        summary.get("dataset_id") != evaluation_set.dataset_id
        or summary.get("dataset_version") != evaluation_set.version
        or summary.get("dataset_digest") != digest
    ):
        return "dataset_identity_mismatch"
    full_suite = select_evaluation_suite(
        evaluation_set,
        EvaluationSuite.FULL,
    ).as_safe_dict()
    if summary.get("evaluation_suite") != full_suite:
        return "filtered_run_not_eligible"
    if _validated_catalog_identity(summary.get("semantic_catalog")) != (
        semantic_catalog_identity
    ):
        return "semantic_catalog_identity_mismatch"
    environment = validate_persisted_environment_identity(
        summary.get("evaluation_environment")
    )
    if (
        environment is None
        or evidence.started_at is None
        or not reference_time_is_eligible(environment, evidence.started_at)
    ):
        return "evaluation_environment_mismatch"
    if not _matches_stability_candidate(
        summary,
        environment.as_dict(),
        stability_canary,
    ):
        return "stability_candidate_mismatch"
    if summary.get("filters") != {
        "case_id": None,
        "difficulty": None,
        "category": None,
        "case_type": None,
        "security_only": False,
    }:
        return "filtered_run_not_eligible"
    if not _exact_int(summary.get("selected_count"), V1_REQUIRED_CASE_COUNT):
        return "run_incomplete"
    if not _exact_int(summary.get("completed_count"), V1_REQUIRED_CASE_COUNT):
        return "run_incomplete"
    if summary.get("failure_code") is not None:
        return "run_incomplete"
    if len(evidence.results) != V1_REQUIRED_CASE_COUNT:
        return "result_set_malformed"
    expected_ids = set(evaluation_set.cases_by_id)
    actual_ids = [result.case_id for result in evidence.results]
    if set(actual_ids) != expected_ids or len(set(actual_ids)) != len(actual_ids):
        return "result_set_malformed"

    parsed: list[_ParsedResult] = []
    measurements: list[dict[str, Any]] = []
    for result in sorted(evidence.results, key=lambda item: item.case_id):
        parsed_result = _parse_result(
            evaluation_set,
            result,
            provider="openai",
            model_label=str(summary["model_label"]),
        )
        if parsed_result is None:
            return "result_set_malformed"
        parsed.append(parsed_result)
        if parsed_result.provider_measurement is not None:
            measurements.append(parsed_result.provider_measurement)
    usage = _usage(measurements)
    if (
        usage is None
        or usage.call_count == 0
        or not _usage_matches(summary.get("provider_usage"), usage)
    ):
        return "result_set_malformed"
    planner_defects = _planner_defect_counts(
        summary.get("planner_metrics"),
        evidence.results,
        evaluation_set,
    )
    if planner_defects is None:
        return "result_set_malformed"
    return summary, tuple(parsed), usage, environment, planner_defects


def _parse_result(
    evaluation_set: EvaluationSet,
    evidence: ReadinessResultEvidence,
    *,
    provider: str,
    model_label: str,
) -> _ParsedResult | None:
    case = evaluation_set.cases_by_id[evidence.case_id]
    expected = evidence.expected_output
    actual = evidence.actual_output
    metrics = evidence.metrics
    if not isinstance(expected, dict) or set(expected) != {"outcome", "referenced_tables"}:
        return None
    if not isinstance(actual, dict) or set(actual) != {
        "outcome",
        "referenced_tables",
        "execution_succeeded",
        "error_code",
    }:
        return None
    if not isinstance(metrics, dict) or not set(metrics) <= _METRICS_FIELDS:
        return None
    required_metrics = _METRICS_FIELDS - {
        "provider_measurement",
        "failure_stage",
        "stage_reason_code",
        "planner",
        "result_provenance",
    }
    if not required_metrics <= set(metrics):
        return None
    if evidence.error_message is not None or evidence.status not in {"succeeded", "failed"}:
        return None
    if expected.get("outcome") != case.expected_outcome.value:
        return None
    if expected.get("referenced_tables") != list(case.expected_tables):
        return None
    actual_outcome = actual.get("outcome")
    if actual_outcome not in {item.value for item in ActualOutcome}:
        return None
    if not isinstance(actual.get("execution_succeeded"), bool):
        return None
    for key in (
        "passed",
        "outcome_correct",
        "execution_correct",
        "tables_correct",
        "security_sensitive",
        "query_invoked",
        "query_execution_attempted",
    ):
        if not isinstance(metrics.get(key), bool):
            return None
    if metrics["security_sensitive"] is not case.security_sensitive:
        return None
    if metrics.get("difficulty") != case.difficulty.value:
        return None
    if metrics.get("category") != case.category or metrics.get("case_type") != case.case_type.value:
        return None
    score = _bounded_rate(evidence.score)
    metric_score = _bounded_rate(metrics.get("score"))
    if score is None or score != metric_score:
        return None
    if (evidence.status == "succeeded") is not metrics["passed"]:
        return None
    if metrics["outcome_correct"] is not (actual_outcome == case.expected_outcome.value):
        return None
    if metrics["execution_correct"] is not (
        actual["execution_succeeded"]
        == (case.expected_outcome is ExpectedOutcome.SUCCESS)
    ):
        return None
    references = actual.get("referenced_tables")
    if not isinstance(references, list) or any(not isinstance(item, str) for item in references):
        return None
    if metrics["tables_correct"] is not (set(references) == set(case.expected_tables)):
        return None
    result_correct = metrics.get("result_correct")
    if case.expected_outcome is ExpectedOutcome.SUCCESS:
        if not isinstance(result_correct, bool):
            return None
    elif result_correct is not None:
        return None
    for key in (
        "expected_row_count",
        "actual_row_count",
        "missing_row_count",
        "extra_row_count",
    ):
        if not _bounded_count(metrics.get(key)):
            return None
    failure_reasons = metrics.get("failure_reasons")
    if (
        not isinstance(failure_reasons, list)
        or any(reason not in SAFE_FAILURE_REASONS for reason in failure_reasons)
    ):
        return None
    error_code = actual.get("error_code")
    if error_code is not None and error_code not in _SAFE_ERROR_CODES:
        return None
    failure_stage = metrics.get("failure_stage")
    if failure_stage is not None and failure_stage not in _SAFE_PIPELINE_STAGES:
        return None
    stage_reason = metrics.get("stage_reason_code")
    if stage_reason is not None and (
        not isinstance(stage_reason, str)
        or re.fullmatch(r"[a-z][a-z0-9_]{0,127}", stage_reason) is None
    ):
        return None
    if metrics.get("result_provenance") is not None and not isinstance(
        metrics["result_provenance"], dict
    ):
        return None
    components = [
        metrics["outcome_correct"],
        metrics["execution_correct"],
        metrics["tables_correct"],
    ]
    if result_correct is not None:
        components.append(result_correct)
    if metrics["passed"] is not all(components):
        return None
    if score != sum(components) / len(components):
        return None
    duration_ms = _bounded_duration(metrics.get("duration_ms"))
    if duration_ms is None:
        return None
    measurement = metrics.get("provider_measurement")
    parsed_measurement = None
    if measurement is not None:
        if not isinstance(measurement, dict) or not set(measurement) <= _MEASUREMENT_FIELDS:
            return None
        parsed_measurement = sanitize_provider_measurement(measurement)
        if (
            parsed_measurement is None
            or parsed_measurement != measurement
            or parsed_measurement.get("provider") != provider
            or parsed_measurement.get("model_label") != model_label
        ):
            return None
    return _ParsedResult(
        case_id=evidence.case_id,
        actual_outcome=str(actual_outcome),
        query_execution_attempted=metrics["query_execution_attempted"],
        execution_succeeded=actual["execution_succeeded"],
        result_correct=result_correct,
        passed=metrics["passed"],
        duration_ms=duration_ms,
        provider_measurement=parsed_measurement,
    )


def _usage(measurements: list[dict[str, Any]]) -> ReadinessUsage | None:
    try:
        return ReadinessUsage(
            call_count=len(measurements),
            attempt_count=sum(int(item["attempt_count"]) for item in measurements),
            duration_ms=round(sum(float(item["duration_ms"]) for item in measurements), 3),
            input_tokens=sum(int(item.get("input_tokens", 0)) for item in measurements),
            cached_input_tokens=sum(int(item.get("cached_input_tokens", 0)) for item in measurements),
            output_tokens=sum(int(item.get("output_tokens", 0)) for item in measurements),
            total_tokens=sum(int(item.get("total_tokens", 0)) for item in measurements),
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _usage_matches(value: Any, usage: ReadinessUsage) -> bool:
    if not isinstance(value, dict) or set(value) != _USAGE_FIELDS:
        return False
    expected = {
        "call_count": usage.call_count,
        "attempt_count": usage.attempt_count,
        "duration_ms": usage.duration_ms,
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }
    return value == expected


def _matches_stability_candidate(
    summary: Mapping[str, Any],
    environment: dict[str, str | int],
    stability: StabilityCanaryAssessment,
) -> bool:
    return all(
        (
            stability.status is StabilityStatus.PASSED,
            summary.get("provider") == stability.provider,
            summary.get("model_label") == stability.model_label,
            summary.get("dataset_id") == stability.dataset_id,
            summary.get("dataset_version") == stability.dataset_version,
            summary.get("dataset_digest") == stability.dataset_digest,
            summary.get("semantic_catalog") == stability.semantic_catalog,
            environment == stability.evaluation_environment,
        )
    )


def _planner_defect_counts(
    value: Any,
    results: tuple[ReadinessResultEvidence, ...],
    evaluation_set: EvaluationSet,
) -> tuple[int, int] | None:
    required_fields = {
        "eligible_case_count",
        "generated_plan_count",
        "validated_plan_count",
        "semantic_plan_validation_pass_rate",
        "required_intent_evaluated_count",
        "required_intent_passed_count",
        "required_intent_adherence_rate",
        "renderer_defect_count",
        "conformance_defect_count",
        "semantic_contract_evaluated_count",
        "semantic_contract_passed_count",
        "semantic_contract_pass_rate",
    }
    if not isinstance(value, dict) or set(value) != required_fields:
        return None
    for key in required_fields - {
        "semantic_plan_validation_pass_rate",
        "required_intent_adherence_rate",
        "semantic_contract_pass_rate",
    }:
        if not _bounded_count(value.get(key)):
            return None
    for key in (
        "semantic_plan_validation_pass_rate",
        "required_intent_adherence_rate",
        "semantic_contract_pass_rate",
    ):
        if value.get(key) is not None and _bounded_rate(value.get(key)) is None:
            return None
    renderer = 0
    conformance = 0
    for result in results:
        case = evaluation_set.cases_by_id[result.case_id]
        planner = result.metrics.get("planner") if isinstance(result.metrics, dict) else None
        eligible = case.template_id is None and case.expected_outcome is ExpectedOutcome.SUCCESS
        if not eligible:
            if planner is not None:
                return None
            continue
        if not isinstance(planner, dict) or set(planner) != {
            "plan_generated",
            "plan_validation_status",
            "required_intent_status",
            "renderer_status",
            "conformance_status",
            "semantic_contract",
        }:
            return None
        if planner.get("renderer_status") not in {"passed", "failed", "not_reached"}:
            return None
        if planner.get("conformance_status") not in {"passed", "failed", "not_reached"}:
            return None
        if not isinstance(planner.get("semantic_contract"), dict):
            return None
        renderer += planner["renderer_status"] == "failed"
        conformance += planner["conformance_status"] == "failed"
    if (
        not _exact_int(value.get("renderer_defect_count"), renderer)
        or not _exact_int(value.get("conformance_defect_count"), conformance)
    ):
        return None
    return renderer, conformance


def _stability_blocked(
    evaluation_set: EvaluationSet,
    digest: str,
    semantic_catalog: dict[str, str],
    stability: StabilityCanaryAssessment,
) -> ReadinessAssessment:
    stability_status = (
        GateStatus.FAILED
        if stability.status is StabilityStatus.FAILED
        else GateStatus.INCOMPLETE
    )
    gates = tuple(
        ReadinessGate(
            code=code,
            label=label,
            status=(stability_status if code == "stability_canary" else GateStatus.INCOMPLETE),
            threshold=threshold,
            reason_code=(
                stability.reason_code
                if code == "stability_canary"
                else "qualifying_run_missing"
            ),
        )
        for code, label, threshold in _GATE_DEFINITIONS
    )
    return ReadinessAssessment(
        policy_id=V1_READINESS_POLICY_ID,
        verdict=(
            ReadinessVerdict.NOT_READY
            if stability.status is StabilityStatus.FAILED
            else ReadinessVerdict.INCOMPLETE
        ),
        run_id=None,
        provider=stability.provider,
        model_label=stability.model_label,
        dataset_id=evaluation_set.dataset_id,
        dataset_version=evaluation_set.version,
        dataset_digest=digest,
        semantic_catalog=semantic_catalog,
        evaluation_environment={},
        selected_count=None,
        completed_count=None,
        average_latency_ms=None,
        usage=None,
        gates=gates,
        stability_canary=stability,
    )


def _incomplete(
    evaluation_set: EvaluationSet,
    digest: str,
    reason_code: str,
    *,
    evidence: ReadinessRunEvidence | None = None,
    semantic_catalog: dict[str, str] | None = None,
    stability_canary: StabilityCanaryAssessment,
) -> ReadinessAssessment:
    gates = tuple(
        ReadinessGate(
            code=code,
            label=label,
            status=(
                GateStatus.PASSED
                if code == "stability_canary"
                and stability_canary.status is StabilityStatus.PASSED
                else GateStatus.INCOMPLETE
            ),
            threshold=threshold,
            reason_code=(
                None
                if code == "stability_canary"
                and stability_canary.status is StabilityStatus.PASSED
                else reason_code
                if code == "qualifying_evidence"
                else "qualifying_run_missing"
            ),
        )
        for code, label, threshold in _GATE_DEFINITIONS
    )
    summary = evidence.summary if evidence is not None and isinstance(evidence.summary, dict) else {}
    provider = summary.get("provider") if summary.get("provider") in {"openai"} else None
    model = summary.get("model_label") if provider and valid_model_label(summary.get("model_label")) else None
    return ReadinessAssessment(
        policy_id=V1_READINESS_POLICY_ID,
        verdict=ReadinessVerdict.INCOMPLETE,
        run_id=evidence.run_id if evidence and provider else None,
        provider=provider,
        model_label=model,
        dataset_id=evaluation_set.dataset_id,
        dataset_version=evaluation_set.version,
        dataset_digest=digest,
        semantic_catalog=semantic_catalog or {},
        evaluation_environment={},
        selected_count=None,
        completed_count=None,
        average_latency_ms=None,
        usage=None,
        gates=gates,
        stability_canary=stability_canary,
    )


def _bounded_rate(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0 <= number <= 1 else None


def _bounded_duration(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0 <= number <= 86_400_000 else None


def _bounded_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10_000_000


def _exact_int(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _validated_catalog_identity(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping) or set(value) != {
        "catalog_id",
        "catalog_version",
        "catalog_hash",
    }:
        return None
    catalog_id = value.get("catalog_id")
    catalog_version = value.get("catalog_version")
    catalog_hash = value.get("catalog_hash")
    if (
        not isinstance(catalog_id, str)
        or _SAFE_IDENTIFIER.fullmatch(catalog_id) is None
        or not isinstance(catalog_version, str)
        or not 1 <= len(catalog_version) <= 64
        or not isinstance(catalog_hash, str)
        or _SAFE_DIGEST.fullmatch(catalog_hash) is None
    ):
        return None
    return {
        "catalog_id": catalog_id,
        "catalog_version": catalog_version,
        "catalog_hash": catalog_hash,
    }
