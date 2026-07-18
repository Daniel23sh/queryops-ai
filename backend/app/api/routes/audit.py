from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.responses import error_response, success_response
from app.auth.access_context import build_user_access_context
from app.auth.permissions import require_authenticated_user
from app.db.session import get_db
from app.models.product import AppAuditLog, AppUser


router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/logs")
def list_audit_logs(
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    actor_app_user_id: UUID | None = None,
    scope_id: UUID | None = None,
    scope_type: str | None = Query(default=None, min_length=1, max_length=64),
    scope_key: str | None = Query(default=None, min_length=1, max_length=128),
    department_id: UUID | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    context = build_user_access_context(current_user, db)
    can_view_global = context.has_permission("can_view_global_audit")
    can_view_scope = context.has_permission("can_view_scope_audit")
    if not can_view_global and not can_view_scope:
        return error_response(
            code="FORBIDDEN",
            message="You are not authorized to view audit logs.",
            status_code=403,
        )

    statement = select(AppAuditLog)
    if not can_view_global:
        assigned_scope_ids = [scope.id for scope in context.scopes]
        if not assigned_scope_ids:
            return success_response(
                {
                    "items": [],
                    "pagination": {"limit": limit, "offset": offset, "returned": 0},
                }
            )
        statement = statement.where(AppAuditLog.scope_id.in_(assigned_scope_ids))
    if event_type is not None:
        statement = statement.where(AppAuditLog.event_type == event_type)
    if actor_app_user_id is not None:
        statement = statement.where(AppAuditLog.actor_user_id == actor_app_user_id)
    if scope_id is not None:
        statement = statement.where(AppAuditLog.scope_id == scope_id)
    if scope_type is not None:
        statement = statement.where(AppAuditLog.scope_type == scope_type)
    if scope_key is not None:
        statement = statement.where(AppAuditLog.scope_key == scope_key)
    if department_id is not None:
        statement = statement.where(AppAuditLog.department_id == department_id)
    if from_date is not None:
        statement = statement.where(AppAuditLog.created_at >= from_date)
    if to_date is not None:
        statement = statement.where(AppAuditLog.created_at <= to_date)

    rows = db.scalars(
        statement.order_by(AppAuditLog.created_at.desc(), AppAuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return success_response(
        {
            "items": [_serialize_audit(row, include_global=can_view_global) for row in rows],
            "pagination": {"limit": limit, "offset": offset, "returned": len(rows)},
        }
    )


def _serialize_audit(log: AppAuditLog, *, include_global: bool) -> dict[str, object]:
    data: dict[str, object] = {
        "id": str(log.id),
        "event_type": log.event_type,
        "actor": (
            {"id": str(log.actor_user_id), "display_name": log.actor.full_name}
            if log.actor is not None
            else None
        ),
        "action_request_id": str(log.action_request_id) if log.action_request_id else None,
        "approval_request_id": (
            str(log.approval_request_id) if log.approval_request_id else None
        ),
        "scope": {
            "id": str(log.scope_id) if log.scope_id else None,
            "type": log.scope_type,
            "key": log.scope_key,
            "department_id": str(log.department_id) if log.department_id else None,
        },
        "severity": log.severity,
        "status": log.status,
        "summary": log.summary,
        "created_at": log.created_at.isoformat(),
    }
    if include_global:
        data["before_state"] = log.before_state_json
        data["after_state"] = log.after_state_json
        data["self_approved"] = log.self_approved is True
        metadata = log.audit_metadata if isinstance(log.audit_metadata, dict) else {}
        failure_category = metadata.get("failure_category")
        if isinstance(failure_category, str):
            data["failure_category"] = failure_category
    return data
