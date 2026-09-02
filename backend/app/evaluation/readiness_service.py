from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.read_service import VisibilityMode, resolve_evaluation_visibility
from app.evaluation.readiness import (
    ReadinessAssessment,
    ReadinessResultEvidence,
    ReadinessRunEvidence,
    evaluate_v1_readiness,
)
from app.evaluation.stability import (
    StabilityCanaryAssessment,
    StabilityResultEvidence,
    StabilityRunEvidence,
    evaluate_stability_canary,
)
from app.models.product import AppUser, EvaluationResult, EvaluationRun, RunStatus
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import semantic_catalog_identity
from app.schemas.evaluation import (
    EvaluationReadiness,
    ReadinessGateView,
    ReadinessTechnicalView,
    ReadinessUsageView,
    StabilityCanaryView,
)


# This evidence is backed by the required network-free release suites and the
# fail-closed aggregate CI job for this policy version. It is passed explicitly
# so the pure evaluator never treats omitted deterministic evidence as success.
_V1_DETERMINISTIC_RELEASE_EVIDENCE_PASSED = True


def assessment_for_run(db: Session, run_id: UUID) -> ReadinessAssessment:
    evaluation_set = load_it_operations_evaluation_v2_set()
    catalog_identity = semantic_catalog_identity(
        load_it_operations_domain_pack().semantic_catalog
    )
    run = db.get(EvaluationRun, run_id)
    stability = latest_stability_assessment(db)
    if run is None:
        return evaluate_v1_readiness(
            evaluation_set,
            None,
            deterministic_evidence_passed=_V1_DETERMINISTIC_RELEASE_EVIDENCE_PASSED,
            semantic_catalog_identity=catalog_identity,
            stability_canary=stability,
        )
    return evaluate_v1_readiness(
        evaluation_set,
        _evidence(db, run),
        deterministic_evidence_passed=_V1_DETERMINISTIC_RELEASE_EVIDENCE_PASSED,
        semantic_catalog_identity=catalog_identity,
        stability_canary=stability,
    )


def latest_readiness_assessment(db: Session) -> ReadinessAssessment:
    evaluation_set = load_it_operations_evaluation_v2_set()
    catalog_identity = semantic_catalog_identity(
        load_it_operations_domain_pack().semantic_catalog
    )
    stability = latest_stability_assessment(db)
    candidates = db.scalars(
        select(EvaluationRun)
        .where(
            EvaluationRun.status == RunStatus.SUCCEEDED.value,
            EvaluationRun.completed_at.is_not(None),
            EvaluationRun.summary["provider"].as_string() == "openai",
            EvaluationRun.summary["dataset_id"].as_string()
            == evaluation_set.dataset_id,
            EvaluationRun.summary["dataset_version"].as_string()
            == evaluation_set.version,
            EvaluationRun.summary["semantic_catalog"]["catalog_id"].as_string()
            == catalog_identity["catalog_id"],
            EvaluationRun.summary["semantic_catalog"]["catalog_version"].as_string()
            == catalog_identity["catalog_version"],
            EvaluationRun.summary["semantic_catalog"]["catalog_hash"].as_string()
            == catalog_identity["catalog_hash"],
        )
        .order_by(EvaluationRun.completed_at.desc(), EvaluationRun.id.desc())
    ).all()
    for run in candidates:
        assessment = evaluate_v1_readiness(
            evaluation_set,
            _evidence(db, run),
            deterministic_evidence_passed=_V1_DETERMINISTIC_RELEASE_EVIDENCE_PASSED,
            semantic_catalog_identity=catalog_identity,
            stability_canary=stability,
        )
        if assessment.gates[0].status.value == "passed":
            return assessment
    return evaluate_v1_readiness(
        evaluation_set,
        None,
        deterministic_evidence_passed=_V1_DETERMINISTIC_RELEASE_EVIDENCE_PASSED,
        semantic_catalog_identity=catalog_identity,
        stability_canary=stability,
    )


def latest_stability_assessment(db: Session) -> StabilityCanaryAssessment:
    evaluation_set = load_it_operations_evaluation_v2_set()
    catalog_identity = semantic_catalog_identity(
        load_it_operations_domain_pack().semantic_catalog
    )
    candidates = db.scalars(
        select(EvaluationRun)
        .where(
            EvaluationRun.status == RunStatus.SUCCEEDED.value,
            EvaluationRun.completed_at.is_not(None),
            EvaluationRun.summary["provider"].as_string() == "openai",
            EvaluationRun.summary["dataset_id"].as_string()
            == evaluation_set.dataset_id,
            EvaluationRun.summary["dataset_version"].as_string()
            == evaluation_set.version,
        )
        .order_by(EvaluationRun.completed_at.desc(), EvaluationRun.id.desc())
        .limit(100)
    ).all()
    return evaluate_stability_canary(
        evaluation_set,
        tuple(_stability_evidence(db, run) for run in candidates),
        semantic_catalog_identity=catalog_identity,
    )


def readiness_for_viewer(
    db: Session,
    current_user: AppUser,
) -> EvaluationReadiness:
    visibility = resolve_evaluation_visibility(db, current_user)
    assessment = latest_readiness_assessment(db)
    include_policy_values = visibility.mode is VisibilityMode.GLOBAL
    gates = [
        ReadinessGateView.model_validate(
            {
                "code": gate.code,
                "label": gate.label,
                "status": gate.status.value,
                "threshold": gate.threshold if include_policy_values else None,
                "actual": gate.actual if include_policy_values else None,
                "reason_code": gate.reason_code,
            }
        )
        for gate in assessment.gates
    ]
    technical = None
    if (
        (visibility.technical or include_policy_values)
        and assessment.run_id is not None
    ):
        technical = ReadinessTechnicalView(
            run_id=assessment.run_id,
            dataset_id=assessment.dataset_id,
            dataset_digest=assessment.dataset_digest,
            selected_count=(assessment.selected_count if include_policy_values else None),
            average_latency_ms=(
                assessment.average_latency_ms if include_policy_values else None
            ),
            usage=(
                ReadinessUsageView(**assessment.usage.__dict__)
                if include_policy_values and assessment.usage is not None
                else None
            ),
        )
    return EvaluationReadiness.model_validate(
        {
            "policy_id": assessment.policy_id,
            "verdict": assessment.verdict.value,
            "provider": assessment.provider,
            "model_label": assessment.model_label,
            "dataset_version": assessment.dataset_version,
            "completed_count": assessment.completed_count,
            "stability_canary": StabilityCanaryView(
                status=assessment.stability_canary.status.value,
                reason_code=assessment.stability_canary.reason_code,
                run_count=len(assessment.stability_canary.run_ids),
            ),
            "gates": gates,
            "technical": technical,
        }
    )


def _evidence(db: Session, run: EvaluationRun) -> ReadinessRunEvidence:
    rows = db.scalars(
        select(EvaluationResult)
        .where(EvaluationResult.evaluation_run_id == run.id)
        .order_by(EvaluationResult.case_name, EvaluationResult.id)
    ).all()
    return ReadinessRunEvidence(
        run_id=run.id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        summary=run.summary,
        results=tuple(
            ReadinessResultEvidence(
                case_id=row.case_name,
                status=row.status,
                score=row.score,
                expected_output=row.expected_output,
                actual_output=row.actual_output,
                metrics=row.metrics,
                error_message=row.error_message,
            )
            for row in rows
        ),
    )


def _stability_evidence(db: Session, run: EvaluationRun) -> StabilityRunEvidence:
    evidence = _evidence(db, run)
    return StabilityRunEvidence(
        run_id=evidence.run_id,
        status=evidence.status,
        started_at=evidence.started_at,
        completed_at=evidence.completed_at,
        summary=evidence.summary,
        results=tuple(
            StabilityResultEvidence(
                case_id=result.case_id,
                status=result.status,
                score=result.score,
                expected_output=result.expected_output,
                actual_output=result.actual_output,
                metrics=result.metrics,
                error_message=result.error_message,
            )
            for result in evidence.results
        ),
    )
