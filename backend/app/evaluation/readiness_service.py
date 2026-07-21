from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.read_service import VisibilityMode, resolve_evaluation_visibility
from app.evaluation.readiness import (
    ReadinessAssessment,
    ReadinessResultEvidence,
    ReadinessRunEvidence,
    evaluate_v1_readiness,
)
from app.models.product import AppUser, EvaluationResult, EvaluationRun, RunStatus
from app.schemas.evaluation import (
    EvaluationReadiness,
    ReadinessGateView,
    ReadinessTechnicalView,
    ReadinessUsageView,
)


def assessment_for_run(db: Session, run_id: UUID) -> ReadinessAssessment:
    evaluation_set = load_it_operations_evaluation_set()
    run = db.get(EvaluationRun, run_id)
    if run is None:
        return evaluate_v1_readiness(evaluation_set, None)
    return evaluate_v1_readiness(evaluation_set, _evidence(db, run))


def latest_readiness_assessment(db: Session) -> ReadinessAssessment:
    evaluation_set = load_it_operations_evaluation_set()
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
    ).all()
    for run in candidates:
        assessment = evaluate_v1_readiness(evaluation_set, _evidence(db, run))
        if assessment.gates[0].status.value == "passed":
            return assessment
    return evaluate_v1_readiness(evaluation_set, None)


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
        include_policy_values
        and assessment.run_id is not None
        and assessment.selected_count is not None
        and assessment.average_latency_ms is not None
        and assessment.usage is not None
    ):
        technical = ReadinessTechnicalView(
            run_id=assessment.run_id,
            dataset_id=assessment.dataset_id,
            dataset_digest=assessment.dataset_digest,
            selected_count=assessment.selected_count,
            average_latency_ms=assessment.average_latency_ms,
            usage=ReadinessUsageView(**assessment.usage.__dict__),
        )
    return EvaluationReadiness.model_validate(
        {
            "policy_id": assessment.policy_id,
            "verdict": assessment.verdict.value,
            "provider": assessment.provider,
            "model_label": assessment.model_label,
            "dataset_version": assessment.dataset_version,
            "completed_count": assessment.completed_count,
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
