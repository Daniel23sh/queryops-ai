from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.responses import error_response, success_response
from app.auth.permissions import require_authenticated_user
from app.auth.session import csrf_is_valid, session_from_request
from app.db.session import get_db
from app.models.product import AppUser, Notification, NotificationStatus


router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    is_read: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    filters = [Notification.recipient_user_id == current_user.id]
    if is_read is True:
        filters.append(Notification.status == NotificationStatus.READ.value)
    elif is_read is False:
        filters.append(Notification.status == NotificationStatus.UNREAD.value)
    statement = select(Notification).where(*filters)
    total = db.scalar(select(func.count(Notification.id)).where(*filters)) or 0
    unread_count = (
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.recipient_user_id == current_user.id,
                Notification.status == NotificationStatus.UNREAD.value,
            )
        )
        or 0
    )
    rows = db.scalars(
        statement.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return success_response(
        {
            "items": [_serialize_notification(row) for row in rows],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned": len(rows),
                "total": total,
            },
            "unread_count": unread_count,
        }
    )


@router.post("/read-all")
def mark_all_notifications_read(
    request: Request,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    csrf_error = _csrf_error(request)
    if csrf_error is not None:
        return csrf_error
    now = datetime.now(UTC)
    try:
        result = db.execute(
            update(Notification)
            .where(
                Notification.recipient_user_id == current_user.id,
                Notification.status == NotificationStatus.UNREAD.value,
            )
            .values(status=NotificationStatus.READ.value, read_at=now)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return _database_error()
    return success_response({"affected_count": result.rowcount})


@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: UUID,
    request: Request,
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    csrf_error = _csrf_error(request)
    if csrf_error is not None:
        return csrf_error
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == current_user.id,
        )
    )
    if notification is None:
        return error_response(
            code="NOTIFICATION_NOT_FOUND",
            message="Notification was not found.",
            status_code=404,
        )
    if notification.status != NotificationStatus.READ.value:
        notification.status = NotificationStatus.READ.value
        notification.read_at = datetime.now(UTC)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            return _database_error()
    return success_response(_serialize_notification(notification))


def _serialize_notification(notification: Notification) -> dict[str, object]:
    return {
        "id": str(notification.id),
        "type": notification.notification_type,
        "title": notification.title,
        "body": notification.body,
        "is_read": notification.status == NotificationStatus.READ.value,
        "related_entity": (
            {
                "type": notification.related_resource_type,
                "id": str(notification.related_resource_id),
            }
            if notification.related_resource_type and notification.related_resource_id
            else None
        ),
        "created_at": _timestamp(notification.created_at),
        "read_at": _timestamp(notification.read_at),
    }


def _csrf_error(request: Request):
    session_data = session_from_request(request)
    if session_data is not None and csrf_is_valid(request, session_data):
        return None
    return error_response(
        code="CSRF_TOKEN_MISSING",
        message="A valid CSRF token is required for this request.",
        status_code=403,
    )


def _database_error():
    return error_response(
        code="INTERNAL_ERROR",
        message="Notifications could not be updated safely.",
        status_code=500,
    )


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
