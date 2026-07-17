from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.action_engine.approval import ApprovalLifecycleService, ApprovalServiceError
from app.api.responses import error_response, success_response
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.models.product import AppUser
from app.schemas.approvals import ApprovalDecisionRequest


router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


def get_approval_clock() -> Callable[[], datetime]:
    return lambda: datetime.now(UTC)


@router.get("/pending")
def list_pending_approvals(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    clock: Callable[[], datetime] = Depends(get_approval_clock),
):
    try:
        data = ApprovalLifecycleService(clock=clock).list_pending(
            db,
            current_user=current_user,
            limit=limit,
            offset=offset,
        )
    except ApprovalServiceError as exc:
        return _service_error(exc)
    except SQLAlchemyError:
        return _database_error(db)
    return success_response(data)


@router.get("/{approval_id}")
def get_approval_detail(
    approval_id: UUID,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    clock: Callable[[], datetime] = Depends(get_approval_clock),
):
    try:
        data = ApprovalLifecycleService(clock=clock).get_detail(
            db,
            current_user=current_user,
            approval_id=approval_id,
        )
    except ApprovalServiceError as exc:
        return _service_error(exc)
    except SQLAlchemyError:
        return _database_error(db)
    return success_response(data)


@router.post("/{approval_id}/approve")
def approve_action(
    approval_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    clock: Callable[[], datetime] = Depends(get_approval_clock),
):
    csrf_error = _csrf_error(request)
    if csrf_error is not None:
        return csrf_error
    parsed = _parse_decision(payload)
    if not isinstance(parsed, ApprovalDecisionRequest):
        return parsed
    try:
        data = ApprovalLifecycleService(clock=clock).approve(
            db,
            current_user=current_user,
            approval_id=approval_id,
            decision_reason=parsed.decision_reason,
        )
    except ApprovalServiceError as exc:
        return _service_error(exc)
    except SQLAlchemyError:
        return _database_error(db)
    return success_response(data)


@router.post("/{approval_id}/reject")
def reject_action(
    approval_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    clock: Callable[[], datetime] = Depends(get_approval_clock),
):
    csrf_error = _csrf_error(request)
    if csrf_error is not None:
        return csrf_error
    parsed = _parse_decision(payload)
    if not isinstance(parsed, ApprovalDecisionRequest):
        return parsed
    try:
        data = ApprovalLifecycleService(clock=clock).reject(
            db,
            current_user=current_user,
            approval_id=approval_id,
            decision_reason=parsed.decision_reason,
        )
    except ApprovalServiceError as exc:
        return _service_error(exc)
    except SQLAlchemyError:
        return _database_error(db)
    return success_response(data)


def _parse_decision(payload: Any):
    try:
        return ApprovalDecisionRequest.model_validate(payload)
    except ValidationError as exc:
        fields = sorted(
            {
                str(error["loc"][0])
                for error in exc.errors(include_url=False, include_input=False)
                if error.get("loc")
            }
        )
        return error_response(
            code="INVALID_APPROVAL_DECISION",
            message="Approval decision payload is invalid.",
            status_code=422,
            details={"fields": fields},
        )


def _csrf_error(request: Request):
    session_data = session_from_request(request)
    if session_data is not None and csrf_is_valid(request, session_data):
        return None
    return error_response(
        code="CSRF_TOKEN_MISSING",
        message="A valid CSRF token is required for this request.",
        status_code=403,
    )


def _service_error(error: ApprovalServiceError):
    return error_response(
        code=error.code,
        message=error.message,
        status_code=error.status_code,
    )


def _database_error(db: Session):
    try:
        db.rollback()
    except SQLAlchemyError:
        pass
    return error_response(
        code="INTERNAL_ERROR",
        message="The approval request could not be processed safely.",
        status_code=500,
    )
