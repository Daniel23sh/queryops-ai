from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.responses import error_response, success_response
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.models.product import AppUser, RequestStatus, Role, RoleUpgradeRequest


router = APIRouter(prefix="/api/v1")

ROLE_UPGRADE_TARGETS = frozenset({"manager", "analyst", "admin"})


class RoleRequestCreate(BaseModel):
    requested_role: str = ""
    reason: str = ""


@router.post("/role-requests")
def create_role_request(
    payload: RoleRequestCreate,
    request: Request,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    session_data = session_from_request(request)
    if session_data is None or not csrf_is_valid(request, session_data):
        return error_response(
            code="CSRF_TOKEN_MISSING",
            message="A valid CSRF token is required for this request.",
            status_code=403,
        )

    requested_role_name = payload.requested_role.strip().lower()
    if requested_role_name not in ROLE_UPGRADE_TARGETS:
        return error_response(
            code="INVALID_REQUESTED_ROLE",
            message="Requested role must be manager, analyst, or admin.",
            status_code=400,
            details={"allowed_roles": sorted(ROLE_UPGRADE_TARGETS)},
        )

    reason = payload.reason.strip()
    if not reason:
        return error_response(
            code="ROLE_REQUEST_REASON_REQUIRED",
            message="A role upgrade request reason is required.",
            status_code=400,
        )

    requested_role = db.scalar(select(Role).where(Role.name == requested_role_name))
    if requested_role is None:
        return error_response(
            code="INVALID_REQUESTED_ROLE",
            message="Requested role is not available.",
            status_code=400,
        )

    current_role = db.get(Role, current_user.role_id) if current_user.role_id else None
    if current_role is not None and current_role.name == requested_role.name:
        return error_response(
            code="ROLE_REQUEST_CURRENT_ROLE",
            message="You already have the requested role.",
            status_code=400,
        )

    pending_request = db.scalar(
        select(RoleUpgradeRequest).where(
            RoleUpgradeRequest.requester_user_id == current_user.id,
            RoleUpgradeRequest.status == RequestStatus.PENDING.value,
        )
    )
    if pending_request is not None:
        return error_response(
            code="PENDING_ROLE_REQUEST_EXISTS",
            message="You already have a pending role upgrade request.",
            status_code=409,
        )

    role_request = RoleUpgradeRequest(
        requester_user_id=current_user.id,
        requested_role_id=requested_role.id,
        department_id=current_user.department_id,
        status=RequestStatus.PENDING.value,
        reason=reason,
    )
    db.add(role_request)
    db.commit()
    db.refresh(role_request)

    return success_response(_serialize_role_request(role_request), status_code=201)


@router.get("/role-requests/my")
def list_my_role_requests(
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    role_requests = db.scalars(
        select(RoleUpgradeRequest)
        .where(RoleUpgradeRequest.requester_user_id == current_user.id)
        .order_by(RoleUpgradeRequest.created_at.desc(), RoleUpgradeRequest.id.desc())
    ).all()

    return success_response(
        [_serialize_role_request(role_request) for role_request in role_requests]
    )


def _serialize_role_request(role_request: RoleUpgradeRequest) -> dict:
    return {
        "id": str(role_request.id),
        "requested_role": role_request.requested_role.name,
        "status": role_request.status,
        "reason": role_request.reason,
        "decision_reason": role_request.decision_reason,
        "decided_at": _serialize_datetime(role_request.decided_at),
        "created_at": _serialize_datetime(role_request.created_at),
        "updated_at": _serialize_datetime(role_request.updated_at),
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
