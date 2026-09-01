from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
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
    EvaluationEnvironmentIdentity,
    reference_time_is_eligible,
    validate_persisted_environment_identity,
)
from app.evaluation.readiness_policy import (
    V1_CLARIFICATION_THRESHOLD,
    V1_EXECUTION_SUCCESS_THRESHOLD,
    V1_RESULT_ACCURACY_THRESHOLD,
    V1_SECURITY_THRESHOLD,
    V1_UNSAFE_BLOCK_THRESHOLD,
)
from app.evaluation.scoring import (
    SAFE_FAILURE_REASONS,
    SAFE_SEMANTIC_FAILURE_REASONS,
)
from app.evaluation.selection import (
    EvaluationSuite,
    evaluation_dataset_digest,
    select_evaluation_suite,
)
from app.query_engine.llm_provider import sanitize_provider_measurement
from app.query_engine.provider_config import valid_model_label


STABILITY_REQUIRED_RUN_COUNT = 3
_PLANNER_STATUSES = frozenset({"passed", "failed", "not_evaluated", "not_reached"})
_FAILURE_STAGES = frozenset(
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
_SAFE_REASON = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_RESULT_METRIC_FIELDS = frozenset(
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
        "failure_stage",
        "stage_reason_code",
        "provider_measurement",
        "planner",
        "result_provenance",
    }
)
_PLANNER_METRIC_FIELDS = frozenset(
    {
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
)
_SEMANTIC_CONTRACT_FIELDS = frozenset(
    {
        "evaluated",
        "passed",
        "concepts_correct",
        "metric_correct",
        "rules_correct",
        "grain_correct",
        "outputs_correct",
        "aggregations_correct",
        "group_by_correct",
        "having_correct",
        "ordering_correct",
        "failure_reasons",
    }
)


class StabilityStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class StabilityResultEvidence:
    case_id: str
    status: str
    score: Any
    expected_output: Any
    actual_output: Any
    metrics: Any
    error_message: str | None


@dataclass(frozen=True)
class StabilityRunEvidence:
    run_id: UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    summary: Any
    results: tuple[StabilityResultEvidence, ...]


@dataclass(frozen=True)
class StabilityCanaryAssessment:
    status: StabilityStatus
    reason_code: str | None
    run_ids: tuple[UUID, ...]
    source_git_sha: str | None
    provider: str | None
    model_label: str | None
    dataset_id: str | None
    dataset_version: str | None
    dataset_digest: str | None
    semantic_catalog: dict[str, str]
    evaluation_environment: dict[str, str | int]
    suite_id: str | None
    suite_version: str | None
    suite_digest: str | None


@dataclass(frozen=True)
class _EvidenceIdentity:
    source_git_sha: str
    provider: str
    model_label: str
    dataset_id: str
    dataset_version: str
    dataset_digest: str
    catalog_id: str
    catalog_version: str
    catalog_hash: str
    environment: tuple[tuple[str, str | int], ...]
    suite_id: str
    suite_version: str
    suite_digest: str
    case_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Envelope:
    evidence: StabilityRunEvidence
    identity: _EvidenceIdentity


@dataclass(frozen=True)
class _CaseObservation:
    case_id: str
    actual_outcome: str
    passed: bool
    score: float
    result_correct: bool | None
    query_execution_attempted: bool
    execution_succeeded: bool
    failure_stage: str | None
    semantic_contract_passed: bool | None
    renderer_status: str | None
    conformance_status: str | None


@dataclass(frozen=True)
class _ParsedRun:
    envelope: _Envelope
    observations: tuple[_CaseObservation, ...]
    renderer_defect_count: int
    conformance_defect_count: int


def evaluate_stability_canary(
    evaluation_set: EvaluationSet,
    evidences: Sequence[StabilityRunEvidence],
    *,
    semantic_catalog_identity: Mapping[str, Any],
) -> StabilityCanaryAssessment:
    expected_suite = select_evaluation_suite(
        evaluation_set,
        EvaluationSuite.CANARY,
    ).as_safe_dict()
    if not evidences:
        return _assessment(
            StabilityStatus.INCOMPLETE,
            "stability_runs_missing",
        )

    envelopes: list[_Envelope] = []
    malformed = False
    for evidence in evidences:
        envelope = _parse_envelope(
            evidence,
            evaluation_set,
            expected_suite,
            semantic_catalog_identity,
        )
        if envelope is None:
            malformed = True
        else:
            envelopes.append(envelope)

    groups: dict[_EvidenceIdentity, list[_Envelope]] = defaultdict(list)
    for envelope in envelopes:
        groups[envelope.identity].append(envelope)
    qualifying_groups = [items for items in groups.values() if len(items) >= 3]
    if not qualifying_groups:
        if malformed:
            reason = "stability_evidence_malformed"
        elif len(envelopes) < STABILITY_REQUIRED_RUN_COUNT:
            reason = "stability_runs_missing"
        else:
            reason = "stability_identity_mismatch"
        return _assessment(StabilityStatus.INCOMPLETE, reason)

    selected_group = max(
        qualifying_groups,
        key=lambda items: max(_run_sort_key(item.evidence) for item in items),
    )
    selected = tuple(
        sorted(
            selected_group,
            key=lambda item: _run_sort_key(item.evidence),
            reverse=True,
        )[:STABILITY_REQUIRED_RUN_COUNT]
    )
    parsed_runs: list[_ParsedRun] = []
    for envelope in selected:
        parsed = _parse_run(evaluation_set, envelope)
        if parsed is None:
            return _assessment(
                StabilityStatus.INCOMPLETE,
                "stability_evidence_malformed",
                selected,
            )
        parsed_runs.append(parsed)

    for parsed in parsed_runs:
        if parsed.renderer_defect_count:
            return _assessment(
                StabilityStatus.FAILED,
                "stability_renderer_defect",
                selected,
            )
        if parsed.conformance_defect_count:
            return _assessment(
                StabilityStatus.FAILED,
                "stability_conformance_defect",
                selected,
            )
        if any(
            evaluation_set.cases_by_id[item.case_id].difficulty
            is EvaluationDifficulty.SECURITY
            and not item.passed
            for item in parsed.observations
        ):
            return _assessment(
                StabilityStatus.FAILED,
                "stability_security_case_failed",
                selected,
            )
        threshold_failure = _threshold_failure(evaluation_set, parsed.observations)
        if threshold_failure is not None:
            return _assessment(
                StabilityStatus.FAILED,
                threshold_failure,
                selected,
            )

    by_case: dict[str, list[_CaseObservation]] = defaultdict(list)
    for parsed in parsed_runs:
        for observation in parsed.observations:
            by_case[observation.case_id].append(observation)
    for observations in by_case.values():
        if len({item.actual_outcome for item in observations}) != 1:
            return _assessment(
                StabilityStatus.FAILED,
                "stability_outcome_oscillation",
                selected,
            )
        if len({item.passed for item in observations}) != 1 or len(
            {item.score for item in observations}
        ) != 1:
            return _assessment(
                StabilityStatus.FAILED,
                "stability_result_oscillation",
                selected,
            )
        if len({item.semantic_contract_passed for item in observations}) != 1:
            return _assessment(
                StabilityStatus.FAILED,
                "stability_semantic_contract_oscillation",
                selected,
            )
        if len({item.failure_stage for item in observations}) != 1:
            return _assessment(
                StabilityStatus.FAILED,
                "stability_failure_stage_oscillation",
                selected,
            )

    return _assessment(StabilityStatus.PASSED, None, selected)


def _parse_envelope(
    evidence: StabilityRunEvidence,
    evaluation_set: EvaluationSet,
    expected_suite: dict[str, Any],
    semantic_catalog_identity: Mapping[str, Any],
) -> _Envelope | None:
    if (
        evidence.status != "succeeded"
        or evidence.started_at is None
        or evidence.completed_at is None
        or not isinstance(evidence.summary, dict)
    ):
        return None
    summary = evidence.summary
    provider = summary.get("provider")
    model_label = summary.get("model_label")
    if provider != "openai" or not valid_model_label(model_label):
        return None
    if (
        summary.get("dataset_id") != evaluation_set.dataset_id
        or summary.get("dataset_version") != evaluation_set.version
        or summary.get("dataset_digest") != evaluation_dataset_digest(evaluation_set)
        or summary.get("evaluation_suite") != expected_suite
        or summary.get("filters") != _empty_filters()
        or not _exact_int(summary.get("selected_count"), len(expected_suite["selected_case_ids"]))
        or not _exact_int(summary.get("completed_count"), len(expected_suite["selected_case_ids"]))
        or summary.get("failure_code") is not None
    ):
        return None
    catalog = summary.get("semantic_catalog")
    if not isinstance(catalog, dict) or catalog != dict(semantic_catalog_identity):
        return None
    environment = validate_persisted_environment_identity(
        summary.get("evaluation_environment")
    )
    if (
        environment is None
        or not reference_time_is_eligible(environment, evidence.started_at)
    ):
        return None
    return _Envelope(
        evidence=evidence,
        identity=_identity(
            environment,
            provider,
            str(model_label),
            evaluation_set,
            catalog,
            expected_suite,
        ),
    )


def _parse_run(
    evaluation_set: EvaluationSet,
    envelope: _Envelope,
) -> _ParsedRun | None:
    evidence = envelope.evidence
    expected_ids = envelope.identity.case_ids
    if (
        len(evidence.results) != len(expected_ids)
        or tuple(sorted(result.case_id for result in evidence.results))
        != tuple(sorted(expected_ids))
    ):
        return None
    observations: list[_CaseObservation] = []
    provider_measurements = 0
    renderer_defects = 0
    conformance_defects = 0
    for result in sorted(evidence.results, key=lambda item: item.case_id):
        observation = _parse_result(
            evaluation_set,
            result,
            envelope.identity.provider,
            envelope.identity.model_label,
        )
        if observation is None:
            return None
        observations.append(observation)
        renderer_defects += observation.renderer_status == "failed"
        conformance_defects += observation.conformance_status == "failed"
        if isinstance(result.metrics, dict) and result.metrics.get("provider_measurement") is not None:
            provider_measurements += 1
    if provider_measurements == 0:
        return None
    planner = evidence.summary.get("planner_metrics")
    if (
        not isinstance(planner, dict)
        or set(planner) != _PLANNER_METRIC_FIELDS
        or not all(
            _bounded_count(planner.get(key), maximum=len(expected_ids))
            for key in (
                "eligible_case_count",
                "generated_plan_count",
                "validated_plan_count",
                "required_intent_evaluated_count",
                "required_intent_passed_count",
                "renderer_defect_count",
                "conformance_defect_count",
                "semantic_contract_evaluated_count",
                "semantic_contract_passed_count",
            )
        )
        or not all(
            planner.get(key) is None or _bounded_rate(planner.get(key)) is not None
            for key in (
                "semantic_plan_validation_pass_rate",
                "required_intent_adherence_rate",
                "semantic_contract_pass_rate",
            )
        )
        or not _exact_int(planner.get("renderer_defect_count"), renderer_defects)
        or not _exact_int(
            planner.get("conformance_defect_count"), conformance_defects
        )
    ):
        return None
    return _ParsedRun(
        envelope=envelope,
        observations=tuple(observations),
        renderer_defect_count=renderer_defects,
        conformance_defect_count=conformance_defects,
    )


def _parse_result(
    evaluation_set: EvaluationSet,
    evidence: StabilityResultEvidence,
    provider: str,
    model_label: str,
) -> _CaseObservation | None:
    case = evaluation_set.cases_by_id.get(evidence.case_id)
    if (
        case is None
        or evidence.status not in {"succeeded", "failed"}
        or evidence.error_message is not None
        or not isinstance(evidence.expected_output, dict)
        or set(evidence.expected_output) != {"outcome", "referenced_tables"}
        or evidence.expected_output.get("outcome") != case.expected_outcome.value
        or evidence.expected_output.get("referenced_tables")
        != list(case.expected_tables)
        or not isinstance(evidence.actual_output, dict)
        or set(evidence.actual_output)
        != {"outcome", "referenced_tables", "execution_succeeded", "error_code"}
        or not isinstance(evidence.metrics, dict)
        or not set(evidence.metrics) <= _RESULT_METRIC_FIELDS
    ):
        return None
    actual_outcome = evidence.actual_output.get("outcome")
    execution_succeeded = evidence.actual_output.get("execution_succeeded")
    passed = evidence.metrics.get("passed")
    score = _bounded_rate(evidence.score)
    metric_score = _bounded_rate(evidence.metrics.get("score"))
    attempted = evidence.metrics.get("query_execution_attempted")
    result_correct = evidence.metrics.get("result_correct")
    required_metrics = _RESULT_METRIC_FIELDS - {
        "failure_stage",
        "stage_reason_code",
        "provider_measurement",
        "planner",
        "result_provenance",
    }
    if (
        not required_metrics <= set(evidence.metrics)
        or actual_outcome not in {item.value for item in ActualOutcome}
        or not isinstance(execution_succeeded, bool)
        or not isinstance(passed, bool)
        or not isinstance(attempted, bool)
        or score is None
        or score != metric_score
        or (evidence.status == "succeeded") is not passed
        or (
            case.expected_outcome is ExpectedOutcome.SUCCESS
            and not isinstance(result_correct, bool)
        )
        or (
            case.expected_outcome is not ExpectedOutcome.SUCCESS
            and result_correct is not None
        )
    ):
        return None
    actual_tables = evidence.actual_output.get("referenced_tables")
    if not isinstance(actual_tables, list) or any(
        not isinstance(item, str) for item in actual_tables
    ):
        return None
    for key in (
        "outcome_correct",
        "execution_correct",
        "tables_correct",
        "security_sensitive",
        "query_invoked",
    ):
        if not isinstance(evidence.metrics.get(key), bool):
            return None
    if (
        evidence.metrics["outcome_correct"]
        is not (actual_outcome == case.expected_outcome.value)
        or evidence.metrics["execution_correct"]
        is not (
            execution_succeeded
            == (case.expected_outcome is ExpectedOutcome.SUCCESS)
        )
        or evidence.metrics["tables_correct"]
        is not (set(actual_tables) == set(case.expected_tables))
        or evidence.metrics["security_sensitive"] is not case.security_sensitive
        or evidence.metrics.get("difficulty") != case.difficulty.value
        or evidence.metrics.get("category") != case.category
        or evidence.metrics.get("case_type") != case.case_type.value
    ):
        return None
    components = [
        evidence.metrics["outcome_correct"],
        evidence.metrics["execution_correct"],
        evidence.metrics["tables_correct"],
    ]
    if result_correct is not None:
        components.append(result_correct)
    if passed is not all(components) or score != sum(components) / len(components):
        return None
    for key in (
        "expected_row_count",
        "actual_row_count",
        "missing_row_count",
        "extra_row_count",
    ):
        if not _bounded_count(evidence.metrics.get(key)):
            return None
    duration = evidence.metrics.get("duration_ms")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, int | float)
        or not math.isfinite(float(duration))
        or not 0 <= float(duration) <= 86_400_000
    ):
        return None
    failure_reasons = evidence.metrics.get("failure_reasons")
    if (
        not isinstance(failure_reasons, list)
        or any(reason not in SAFE_FAILURE_REASONS for reason in failure_reasons)
    ):
        return None
    measurement = evidence.metrics.get("provider_measurement")
    if measurement is not None:
        if not isinstance(measurement, dict):
            return None
        sanitized = sanitize_provider_measurement(measurement)
        if (
            sanitized is None
            or sanitized != measurement
            or sanitized.get("provider") != provider
            or sanitized.get("model_label") != model_label
        ):
            return None
    failure_stage = evidence.metrics.get("failure_stage")
    if failure_stage is not None and failure_stage not in _FAILURE_STAGES:
        return None
    stage_reason = evidence.metrics.get("stage_reason_code")
    if stage_reason is not None and (
        not isinstance(stage_reason, str) or _SAFE_REASON.fullmatch(stage_reason) is None
    ):
        return None
    provenance = evidence.metrics.get("result_provenance")
    if provenance is not None and not isinstance(provenance, dict):
        return None
    planner = evidence.metrics.get("planner")
    semantic_passed = None
    renderer_status = None
    conformance_status = None
    planner_required = (
        case.template_id is None
        and case.expected_outcome is ExpectedOutcome.SUCCESS
    )
    if planner_required:
        parsed_planner = _parse_planner(planner)
        if parsed_planner is None:
            return None
        semantic_passed, renderer_status, conformance_status = parsed_planner
    elif planner is not None:
        return None
    return _CaseObservation(
        case_id=case.id,
        actual_outcome=str(actual_outcome),
        passed=passed,
        score=score,
        result_correct=result_correct,
        query_execution_attempted=attempted,
        execution_succeeded=execution_succeeded,
        failure_stage=failure_stage,
        semantic_contract_passed=semantic_passed,
        renderer_status=renderer_status,
        conformance_status=conformance_status,
    )


def _parse_planner(value: Any) -> tuple[bool | None, str, str] | None:
    if not isinstance(value, dict) or set(value) != {
        "plan_generated",
        "plan_validation_status",
        "required_intent_status",
        "renderer_status",
        "conformance_status",
        "semantic_contract",
    }:
        return None
    for key in (
        "plan_validation_status",
        "required_intent_status",
        "renderer_status",
        "conformance_status",
    ):
        if value.get(key) not in _PLANNER_STATUSES:
            return None
    if not isinstance(value.get("plan_generated"), bool):
        return None
    contract = value.get("semantic_contract")
    if (
        not isinstance(contract, dict)
        or set(contract) != _SEMANTIC_CONTRACT_FIELDS
        or not isinstance(contract.get("evaluated"), bool)
    ):
        return None
    passed = contract.get("passed")
    if passed is not None and not isinstance(passed, bool):
        return None
    if contract["evaluated"] is not (passed is not None):
        return None
    for key in _SEMANTIC_CONTRACT_FIELDS - {"evaluated", "passed", "failure_reasons"}:
        component_value = contract.get(key)
        if component_value is not None and not isinstance(component_value, bool):
            return None
        if contract["evaluated"] is not (component_value is not None):
            return None
    reasons = contract.get("failure_reasons")
    if (
        not isinstance(reasons, list)
        or any(reason not in SAFE_SEMANTIC_FAILURE_REASONS for reason in reasons)
    ):
        return None
    return passed, str(value["renderer_status"]), str(value["conformance_status"])


def _threshold_failure(
    evaluation_set: EvaluationSet,
    observations: Sequence[_CaseObservation],
) -> str | None:
    success = [
        item
        for item in observations
        if evaluation_set.cases_by_id[item.case_id].expected_outcome
        is ExpectedOutcome.SUCCESS
    ]
    unsafe = [
        item
        for item in observations
        if evaluation_set.cases_by_id[item.case_id].case_type is CaseType.UNSAFE_SQL
    ]
    clarification = [
        item
        for item in observations
        if evaluation_set.cases_by_id[item.case_id].case_type
        is CaseType.CLARIFICATION
    ]
    security = [
        item
        for item in observations
        if evaluation_set.cases_by_id[item.case_id].difficulty
        is EvaluationDifficulty.SECURITY
    ]
    checks = (
        (
            success,
            lambda item: item.actual_outcome == ActualOutcome.SUCCESS.value
            and item.query_execution_attempted
            and item.execution_succeeded,
            V1_EXECUTION_SUCCESS_THRESHOLD,
            "stability_execution_below_threshold",
        ),
        (
            success,
            lambda item: item.result_correct is True,
            V1_RESULT_ACCURACY_THRESHOLD,
            "stability_result_accuracy_below_threshold",
        ),
        (
            unsafe,
            lambda item: item.actual_outcome == ActualOutcome.UNSAFE_BLOCKED.value
            and not item.query_execution_attempted,
            V1_UNSAFE_BLOCK_THRESHOLD,
            "stability_unsafe_gate_failed",
        ),
        (
            clarification,
            lambda item: item.actual_outcome == ActualOutcome.CLARIFICATION.value
            and not item.query_execution_attempted,
            V1_CLARIFICATION_THRESHOLD,
            "stability_clarification_gate_failed",
        ),
        (
            security,
            lambda item: item.passed,
            V1_SECURITY_THRESHOLD,
            "stability_security_case_failed",
        ),
    )
    for denominator, predicate, threshold, reason in checks:
        if not denominator:
            return "stability_evidence_malformed"
        actual = sum(predicate(item) for item in denominator) / len(denominator)
        if actual < threshold:
            return reason
    return None


def _identity(
    environment: EvaluationEnvironmentIdentity,
    provider: str,
    model_label: str,
    evaluation_set: EvaluationSet,
    catalog: Mapping[str, Any],
    suite: Mapping[str, Any],
) -> _EvidenceIdentity:
    return _EvidenceIdentity(
        source_git_sha=environment.source_git_sha,
        provider=provider,
        model_label=model_label,
        dataset_id=evaluation_set.dataset_id,
        dataset_version=evaluation_set.version,
        dataset_digest=evaluation_dataset_digest(evaluation_set),
        catalog_id=str(catalog["catalog_id"]),
        catalog_version=str(catalog["catalog_version"]),
        catalog_hash=str(catalog["catalog_hash"]),
        environment=tuple(sorted(environment.as_dict().items())),
        suite_id=str(suite["id"]),
        suite_version=str(suite["version"]),
        suite_digest=str(suite["digest"]),
        case_ids=tuple(str(item) for item in suite["selected_case_ids"]),
    )


def _assessment(
    status: StabilityStatus,
    reason_code: str | None,
    selected: Sequence[_Envelope] = (),
) -> StabilityCanaryAssessment:
    identity = selected[0].identity if selected else None
    return StabilityCanaryAssessment(
        status=status,
        reason_code=reason_code,
        run_ids=tuple(item.evidence.run_id for item in selected),
        source_git_sha=identity.source_git_sha if identity else None,
        provider=identity.provider if identity else None,
        model_label=identity.model_label if identity else None,
        dataset_id=identity.dataset_id if identity else None,
        dataset_version=identity.dataset_version if identity else None,
        dataset_digest=identity.dataset_digest if identity else None,
        semantic_catalog=(
            {
                "catalog_id": identity.catalog_id,
                "catalog_version": identity.catalog_version,
                "catalog_hash": identity.catalog_hash,
            }
            if identity
            else {}
        ),
        evaluation_environment=dict(identity.environment) if identity else {},
        suite_id=identity.suite_id if identity else None,
        suite_version=identity.suite_version if identity else None,
        suite_digest=identity.suite_digest if identity else None,
    )


def _run_sort_key(evidence: StabilityRunEvidence) -> tuple[datetime, str]:
    assert evidence.completed_at is not None
    return evidence.completed_at, str(evidence.run_id)


def _empty_filters() -> dict[str, Any]:
    return {
        "case_id": None,
        "difficulty": None,
        "category": None,
        "case_type": None,
        "security_only": False,
    }


def _bounded_rate(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0 <= number <= 1 else None


def _exact_int(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _bounded_count(value: Any, *, maximum: int = 10_000_000) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= maximum
    )
