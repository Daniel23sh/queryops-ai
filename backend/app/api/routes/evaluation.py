from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.responses import ApiError, success_response
from app.auth.permissions import require_authenticated_user
from app.db.session import get_db
from app.evaluation.contracts import ActualOutcome, CaseType, EvaluationDifficulty
from app.evaluation.loader import EvaluationDatasetValidationError
from app.evaluation.read_service import (
    EvaluationQueryFilters,
    EvaluationReadError,
    EvaluationReadService,
)
from app.models.product import AppUser
from app.schemas.evaluation import (
    EvaluationCapabilityMetricsResponse,
    EvaluationOverviewResponse,
    EvaluationQueryMetricsResponse,
    EvaluationSecurityMetricsResponse,
)


router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])
ERROR_RESPONSES = {
    401: {"description": "Authentication is required."},
    403: {"description": "The current role, permission, or scope is not authorized."},
    404: {"description": "The requested run is unknown or inaccessible."},
    422: {"description": "A query parameter failed strict validation."},
    503: {"description": "Safe evaluation metrics cannot currently be resolved."},
}


@router.get(
    "/overview",
    response_model=EvaluationOverviewResponse,
    responses=ERROR_RESPONSES,
)
def evaluation_overview(
    run_id: UUID | None = None,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    return _respond(lambda: _service(db, current_user).overview(run_id))


@router.get(
    "/queries",
    response_model=EvaluationQueryMetricsResponse,
    responses=ERROR_RESPONSES,
)
def evaluation_queries(
    run_id: UUID | None = None,
    difficulty: EvaluationDifficulty | None = None,
    category: str | None = Query(default=None, min_length=1, max_length=64),
    case_type: CaseType | None = None,
    outcome: ActualOutcome | None = None,
    passed: bool | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    return _respond(
        lambda: _service(db, current_user).queries(
            run_id,
            EvaluationQueryFilters(
                difficulty=difficulty,
                category=category,
                case_type=case_type,
                actual_outcome=outcome,
                passed=passed,
            ),
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/security",
    response_model=EvaluationSecurityMetricsResponse,
    responses=ERROR_RESPONSES,
)
def evaluation_security(
    run_id: UUID | None = None,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    return _respond(lambda: _service(db, current_user).security(run_id))


@router.get(
    "/actions",
    response_model=EvaluationCapabilityMetricsResponse,
    responses=ERROR_RESPONSES,
)
def evaluation_actions(
    run_id: UUID | None = None,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    return _respond(lambda: _service(db, current_user).capability(run_id, "actions"))


@router.get(
    "/dashboards",
    response_model=EvaluationCapabilityMetricsResponse,
    responses=ERROR_RESPONSES,
)
def evaluation_dashboards(
    run_id: UUID | None = None,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    return _respond(
        lambda: _service(db, current_user).capability(run_id, "dashboards")
    )


def _service(db: Session, current_user: AppUser) -> EvaluationReadService:
    return EvaluationReadService(db, current_user)


def _respond(read: Callable[[], Any]):
    try:
        data = read()
        return success_response(data.model_dump(mode="json"))
    except EvaluationReadError as exc:
        raise _api_error(exc) from exc
    except (EvaluationDatasetValidationError, SQLAlchemyError) as exc:
        raise ApiError(
            code="EVALUATION_METRICS_UNAVAILABLE",
            message="Evaluation metrics are unavailable.",
            status_code=503,
        ) from exc


def _api_error(exc: EvaluationReadError) -> ApiError:
    if exc.code == "FORBIDDEN":
        return ApiError(code=exc.code, message=exc.safe_message, status_code=403)
    if exc.code == "EVALUATION_RUN_NOT_FOUND":
        return ApiError(code=exc.code, message=exc.safe_message, status_code=404)
    if exc.code == "EVALUATION_SCOPE_ATTRIBUTION_UNAVAILABLE":
        return ApiError(code=exc.code, message=exc.safe_message, status_code=503)
    return ApiError(code=exc.code, message=exc.safe_message, status_code=400)
