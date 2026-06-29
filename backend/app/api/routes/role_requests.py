from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.responses import error_response, success_response
from app.auth.permissions import require_authenticated_user, require_permission
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.models.product import AppAuditLog, AppUser, RequestStatus, Role, RoleUpgradeRequest


router = APIRouter(prefix="/api/v1")

ROLE_UPGRADE_TARGETS = frozenset({"manager", "analyst", "admin"})


class RoleRequestCreate(BaseModel):
    requested_role: str = ""
    reason: str = ""


class RoleRequestDecision(BaseModel):
    decision_reason: str = ""


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


@router.get("/admin/role-requests")
def list_admin_role_requests(
    _admin_user: AppUser = Depends(require_permission("can_approve_role_requests")),
    db: Session = Depends(get_db),
):
    role_requests = db.scalars(
        select(RoleUpgradeRequest).order_by(
            RoleUpgradeRequest.created_at.desc(),
            RoleUpgradeRequest.id.desc(),
        )
    ).all()

    return success_response(
        [_serialize_role_request(role_request) for role_request in role_requests]
    )


@router.post("/admin/role-requests/{role_request_id}/approve")
def approve_role_request(
    role_request_id: UUID,
    payload: RoleRequestDecision,
    request: Request,
    admin_user: AppUser = Depends(require_permission("can_approve_role_requests")),
    db: Session = Depends(get_db),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    role_request = _get_role_request_or_error(db, role_request_id)
    if not isinstance(role_request, RoleUpgradeRequest):
        return role_request

    processing_error = _role_request_processing_error(role_request, admin_user)
    if processing_error is not None:
        return processing_error

    decision_reason = payload.decision_reason.strip()
    requester = role_request.requester
    old_role = requester.role.name if requester.role else None
    new_role = role_request.requested_role.name
    decided_at = datetime.now(UTC)

    requester.role_id = role_request.requested_role_id
    role_request.status = RequestStatus.APPROVED.value
    role_request.decision_reason = decision_reason
    role_request.decided_by_user_id = admin_user.id
    role_request.decided_at = decided_at
    db.add(
        _build_audit_log(
            role_request=role_request,
            admin_user=admin_user,
            event_type="role_request.approved",
            action="approve",
            summary=(
                f"Approved role upgrade for {requester.email} "
                f"from {old_role or 'unassigned'} to {new_role}."
            ),
            metadata={
                "requester_user_id": str(requester.id),
                "requested_role_id": str(role_request.requested_role_id),
                "old_role": old_role,
                "new_role": new_role,
                "requested_role": new_role,
                "decision_reason": decision_reason,
            },
        )
    )
    db.commit()
    db.refresh(role_request)

    return success_response(_serialize_role_request(role_request))


@router.post("/admin/role-requests/{role_request_id}/reject")
def reject_role_request(
    role_request_id: UUID,
    payload: RoleRequestDecision,
    request: Request,
    admin_user: AppUser = Depends(require_permission("can_approve_role_requests")),
    db: Session = Depends(get_db),
):
    csrf_error = _csrf_error_response(request)
    if csrf_error is not None:
        return csrf_error

    role_request = _get_role_request_or_error(db, role_request_id)
    if not isinstance(role_request, RoleUpgradeRequest):
        return role_request

    processing_error = _role_request_processing_error(role_request, admin_user)
    if processing_error is not None:
        return processing_error

    decision_reason = payload.decision_reason.strip()
    requester = role_request.requester
    old_role = requester.role.name if requester.role else None
    requested_role = role_request.requested_role.name
    decided_at = datetime.now(UTC)

    role_request.status = RequestStatus.REJECTED.value
    role_request.decision_reason = decision_reason
    role_request.decided_by_user_id = admin_user.id
    role_request.decided_at = decided_at
    db.add(
        _build_audit_log(
            role_request=role_request,
            admin_user=admin_user,
            event_type="role_request.rejected",
            action="reject",
            summary=f"Rejected role upgrade for {requester.email} to {requested_role}.",
            metadata={
                "requester_user_id": str(requester.id),
                "requested_role_id": str(role_request.requested_role_id),
                "old_role": old_role,
                "requested_role": requested_role,
                "decision_reason": decision_reason,
            },
        )
    )
    db.commit()
    db.refresh(role_request)

    return success_response(_serialize_role_request(role_request))


def _serialize_role_request(role_request: RoleUpgradeRequest) -> dict:
    return {
        "id": str(role_request.id),
        "requester": {
            "id": str(role_request.requester.id),
            "email": role_request.requester.email,
            "full_name": role_request.requester.full_name,
        },
        "requested_role": role_request.requested_role.name,
        "status": role_request.status,
        "reason": role_request.reason,
        "decision_reason": role_request.decision_reason,
        "decided_by": (
            {
                "id": str(role_request.decided_by_user.id),
                "email": role_request.decided_by_user.email,
                "full_name": role_request.decided_by_user.full_name,
            }
            if role_request.decided_by_user
            else None
        ),
        "decided_at": _serialize_datetime(role_request.decided_at),
        "created_at": _serialize_datetime(role_request.created_at),
        "updated_at": _serialize_datetime(role_request.updated_at),
    }


def _csrf_error_response(request: Request):
    session_data = session_from_request(request)
    if session_data is not None and csrf_is_valid(request, session_data):
        return None

    return error_response(
        code="CSRF_TOKEN_MISSING",
        message="A valid CSRF token is required for this request.",
        status_code=403,
    )


def _get_role_request_or_error(db: Session, role_request_id: UUID):
    role_request = db.get(RoleUpgradeRequest, role_request_id)
    if role_request is None:
        return error_response(
            code="ROLE_REQUEST_NOT_FOUND",
            message="Role upgrade request was not found.",
            status_code=404,
        )

    return role_request


def _role_request_processing_error(
    role_request: RoleUpgradeRequest,
    admin_user: AppUser,
):
    if role_request.requester_user_id == admin_user.id:
        return error_response(
            code="ROLE_REQUEST_SELF_APPROVAL",
            message="You cannot approve or reject your own role upgrade request.",
            status_code=403,
        )

    if role_request.status != RequestStatus.PENDING.value:
        return error_response(
            code="ROLE_REQUEST_ALREADY_PROCESSED",
            message="This role upgrade request has already been processed.",
            status_code=409,
        )

    return None


def _build_audit_log(
    *,
    role_request: RoleUpgradeRequest,
    admin_user: AppUser,
    event_type: str,
    action: str,
    summary: str,
    metadata: dict,
) -> AppAuditLog:
    return AppAuditLog(
        actor_user_id=admin_user.id,
        event_type=event_type,
        action=action,
        status="success",
        entity_type="role_upgrade_request",
        entity_id=role_request.id,
        summary=summary,
        audit_metadata=metadata,
    )


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
