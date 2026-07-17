from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.action_engine.registry import ActionRegistry, build_default_action_registry
from app.action_engine.service import ActionLifecycleService, ActionServiceError
from app.api.responses import error_response, success_response
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.models.product import AppUser
from app.schemas.actions import (
    ActionCancelRequest,
    ActionPreviewRequest,
    ActionSubmitRequest,
)


router = APIRouter(prefix="/api/v1/actions", tags=["actions"])


@lru_cache(maxsize=1)
def get_action_registry() -> ActionRegistry:
    return build_default_action_registry()


def get_action_clock() -> Callable[[], datetime]:
    return lambda: datetime.now(UTC)


@router.post("/preview")
def create_action_preview(
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    registry: ActionRegistry = Depends(get_action_registry),
    clock: Callable[[], datetime] = Depends(get_action_clock),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error
    parsed = _parse_payload(ActionPreviewRequest, payload)
    if not isinstance(parsed, ActionPreviewRequest):
        return parsed
    try:
        data = ActionLifecycleService(registry=registry, clock=clock).create_preview(
            db,
            current_user=current_user,
            payload=parsed,
        )
    except ActionServiceError as exc:
        return _service_error_response(exc)
    except SQLAlchemyError:
        return _database_error_response(db)
    return success_response(data, status_code=201)


@router.post("/request")
def submit_action_request(
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    registry: ActionRegistry = Depends(get_action_registry),
    clock: Callable[[], datetime] = Depends(get_action_clock),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error
    parsed = _parse_payload(ActionSubmitRequest, payload)
    if not isinstance(parsed, ActionSubmitRequest):
        return parsed
    try:
        data = ActionLifecycleService(registry=registry, clock=clock).submit_request(
            db,
            current_user=current_user,
            payload=parsed,
        )
    except ActionServiceError as exc:
        return _service_error_response(exc)
    except SQLAlchemyError:
        return _database_error_response(db)
    return success_response(data)


@router.get("/{action_request_id}")
def get_action_request_detail(
    action_request_id: UUID,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    registry: ActionRegistry = Depends(get_action_registry),
    clock: Callable[[], datetime] = Depends(get_action_clock),
):
    try:
        data = ActionLifecycleService(registry=registry, clock=clock).get_detail(
            db,
            current_user=current_user,
            action_request_id=action_request_id,
        )
    except ActionServiceError as exc:
        return _service_error_response(exc)
    except SQLAlchemyError:
        return _database_error_response(db)
    return success_response(data)


@router.post("/{action_request_id}/cancel")
def cancel_action_request(
    action_request_id: UUID,
    request: Request,
    payload: Any = Body(default=None),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    registry: ActionRegistry = Depends(get_action_registry),
    clock: Callable[[], datetime] = Depends(get_action_clock),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error
    parsed = _parse_payload(ActionCancelRequest, payload)
    if not isinstance(parsed, ActionCancelRequest):
        return parsed
    try:
        data = ActionLifecycleService(registry=registry, clock=clock).cancel_request(
            db,
            current_user=current_user,
            action_request_id=action_request_id,
            payload=parsed,
        )
    except ActionServiceError as exc:
        return _service_error_response(exc)
    except SQLAlchemyError:
        return _database_error_response(db)
    return success_response(data)


def _parse_payload(model: type[BaseModel], payload: Any):
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        fields = sorted(
            {
                str(error["loc"][0])
                for error in exc.errors(include_url=False, include_input=False)
                if error.get("loc")
            }
        )
        return error_response(
            code="INVALID_ACTION_REQUEST",
            message="Action request payload is invalid.",
            status_code=422,
            details={"fields": fields},
        )


def _csrf_error_response(request: Request):
    session_data = session_from_request(request)
    if session_data is not None and csrf_is_valid(request, session_data):
        return None
    return error_response(
        code="CSRF_TOKEN_MISSING",
        message="A valid CSRF token is required for this request.",
        status_code=403,
    )


def _service_error_response(error: ActionServiceError):
    return error_response(
        code=error.code,
        message=error.message,
        status_code=error.status_code,
    )


def _database_error_response(db: Session):
    try:
        db.rollback()
    except SQLAlchemyError:
        pass
    return error_response(
        code="INTERNAL_ERROR",
        message="The action request could not be processed safely.",
        status_code=500,
    )
