from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.responses import error_response, success_response
from app.auth.access_context import build_user_access_context
from app.auth.permissions import require_authenticated_user, require_permission
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.models.product import (
    AccessScope,
    AppAuditLog,
    AppUser,
    RequestStatus,
    Role,
    RoleUpgradeRequest,
    UserAccessScope,
)


router = APIRouter(prefix="/api/v1")

ROLE_UPGRADE_TARGETS = frozenset({"manager", "analyst", "admin"})
ROLE_HIERARCHY = {
    "user": 0,
    "manager": 1,
    "analyst": 2,
    "admin": 3,
}


class RoleRequestCreate(BaseModel):
    requested_role: str = ""
    requested_scope_id: UUID | None = None
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
    if current_role is not None and not _is_upward_role_request(
        current_role.name,
        requested_role.name,
    ):
        return error_response(
            code="ROLE_REQUEST_NOT_UPWARD",
            message="Role upgrade requests must target a higher role.",
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

    requested_scope = _requested_scope_for_create(
        db,
        current_user,
        payload.requested_scope_id,
        requested_role.name,
    )
    if requested_scope is not None and not isinstance(requested_scope, AccessScope):
        return requested_scope

    role_request = RoleUpgradeRequest(
        requester_user_id=current_user.id,
        requested_role_id=requested_role.id,
        requested_scope_id=requested_scope.id if requested_scope else None,
        requested_scope_type=requested_scope.scope_type if requested_scope else None,
        requested_scope_key=requested_scope.scope_key if requested_scope else None,
        department_id=(
            requested_scope.department_id if requested_scope else current_user.department_id
        ),
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
    if not decision_reason:
        return _decision_reason_required_response()

    requester = role_request.requester
    old_role = requester.role.name if requester.role else None
    new_role = role_request.requested_role.name
    decided_at = datetime.now(UTC)
    requested_scope = role_request.requested_scope or _default_scope_for_user(
        requester,
        db,
    )
    assigned_scope = _scope_for_approval(
        role_request=role_request,
        requester=requester,
        requested_role_name=new_role,
        db=db,
    )
    assigned_access_level = _access_level_for_role(new_role)
    if assigned_scope is not None:
        _assign_user_scope(
            db,
            user=requester,
            scope=assigned_scope,
            access_level=assigned_access_level,
            make_default=True,
        )
    if requested_scope is not None and role_request.requested_scope_id is None:
        role_request.requested_scope_id = requested_scope.id
        role_request.requested_scope_type = requested_scope.scope_type
        role_request.requested_scope_key = requested_scope.scope_key

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
                "requested_scope": _scope_audit_metadata(requested_scope),
                "assigned_scope": _assigned_scope_audit_metadata(
                    assigned_scope,
                    assigned_access_level,
                ),
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
    if not decision_reason:
        return _decision_reason_required_response()

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
        "requested_scope": _serialize_requested_scope(role_request),
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


def _decision_reason_required_response():
    return error_response(
        code="ROLE_REQUEST_DECISION_REASON_REQUIRED",
        message="A decision reason is required.",
        status_code=400,
    )


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


def _requested_scope_for_create(
    db: Session,
    user: AppUser,
    requested_scope_id: UUID | None,
    requested_role_name: str,
):
    if requested_scope_id is not None:
        requested_scope = db.get(AccessScope, requested_scope_id)
        if requested_scope is None:
            return error_response(
                code="REQUESTED_SCOPE_NOT_FOUND",
                message="Requested access scope was not found.",
                status_code=400,
            )
        scope_error = _requested_scope_validation_error(
            requested_scope,
            requested_role_name,
        )
        if scope_error is not None:
            return scope_error
        return requested_scope

    if requested_role_name == "admin":
        return None

    requested_scope = _default_scope_for_user(user, db)
    scope_error = _requested_scope_validation_error(
        requested_scope,
        requested_role_name,
    )
    if scope_error is not None:
        return scope_error
    return requested_scope


def _requested_scope_validation_error(
    scope: AccessScope | None,
    requested_role_name: str,
):
    if requested_role_name == "admin":
        if scope is None:
            return None
        if scope.scope_type == "global" and scope.scope_key == "global":
            return None
        return error_response(
            code="INVALID_REQUESTED_SCOPE",
            message="Admin role requests must use global scope.",
            status_code=400,
        )

    if scope is not None and scope.scope_type == "department":
        return None

    return error_response(
        code="INVALID_REQUESTED_SCOPE",
        message="Non-admin role requests must use a department scope.",
        status_code=400,
    )


def _default_scope_for_user(user: AppUser, db: Session) -> AccessScope | None:
    access_context = build_user_access_context(user, db)
    if access_context.default_scope is not None:
        return db.get(AccessScope, access_context.default_scope.id)

    if user.department_id is None:
        return None
    return db.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == "department",
            AccessScope.department_id == user.department_id,
        )
    )


def _scope_for_approval(
    *,
    role_request: RoleUpgradeRequest,
    requester: AppUser,
    requested_role_name: str,
    db: Session,
) -> AccessScope | None:
    if requested_role_name == "admin":
        return db.scalar(
            select(AccessScope).where(
                AccessScope.scope_type == "global",
                AccessScope.scope_key == "global",
            )
        )

    return role_request.requested_scope or _default_scope_for_user(requester, db)


def _assign_user_scope(
    db: Session,
    *,
    user: AppUser,
    scope: AccessScope,
    access_level: str,
    make_default: bool,
) -> None:
    existing_scope = db.get(
        UserAccessScope,
        {"user_id": user.id, "scope_id": scope.id},
    )
    if make_default:
        for user_scope in list(user.user_access_scopes):
            user_scope.is_default = user_scope.scope_id == scope.id

    if existing_scope is None:
        existing_scope = UserAccessScope(
            user_id=user.id,
            scope_id=scope.id,
            access_level=access_level,
            is_default=make_default,
        )
        db.add(existing_scope)
    else:
        existing_scope.access_level = access_level
        if make_default:
            existing_scope.is_default = True


def _access_level_for_role(role_name: str) -> str:
    if role_name in {"admin", "analyst"}:
        return "manage"
    return "read"


def _is_upward_role_request(current_role_name: str, requested_role_name: str) -> bool:
    current_rank = ROLE_HIERARCHY.get(current_role_name)
    requested_rank = ROLE_HIERARCHY.get(requested_role_name)
    if current_rank is None or requested_rank is None:
        return False
    return requested_rank > current_rank


def _serialize_requested_scope(role_request: RoleUpgradeRequest) -> dict | None:
    scope = role_request.requested_scope
    if scope is None:
        return None
    user_scope = next(
        (
            assignment
            for assignment in role_request.requester.user_access_scopes
            if assignment.scope_id == scope.id
        ),
        None,
    )
    return {
        "id": str(scope.id),
        "type": scope.scope_type,
        "key": scope.scope_key,
        "display_name": scope.display_name,
        "access_level": user_scope.access_level if user_scope else None,
        "is_default": user_scope.is_default if user_scope else False,
        "department_id": str(scope.department_id) if scope.department_id else None,
    }


def _scope_audit_metadata(scope: AccessScope | None) -> dict | None:
    if scope is None:
        return None
    return {
        "id": str(scope.id),
        "type": scope.scope_type,
        "key": scope.scope_key,
    }


def _assigned_scope_audit_metadata(
    scope: AccessScope | None,
    access_level: str,
) -> dict | None:
    if scope is None:
        return None
    return {
        "id": str(scope.id),
        "type": scope.scope_type,
        "key": scope.scope_key,
        "access_level": access_level,
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
