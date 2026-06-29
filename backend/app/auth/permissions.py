from __future__ import annotations

from collections.abc import Callable, Sequence

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.responses import ApiError
from app.auth.session import SessionData, session_from_request
from app.db.session import get_db
from app.models.product import (
    AppUser,
    Permission,
    PermissionEffect,
    RolePermission,
    UserPermission,
    UserStatus,
)


def resolve_effective_permission_keys(user: AppUser, db: Session) -> list[str]:
    role_permission_keys: set[str] = set()
    if user.role_id is not None:
        role_permission_keys.update(
            db.scalars(
                select(Permission.key)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == user.role_id)
            )
        )

    user_permission_rows = db.execute(
        select(Permission.key, UserPermission.effect)
        .join(UserPermission, UserPermission.permission_id == Permission.id)
        .where(UserPermission.user_id == user.id)
    ).all()
    allow_keys = {
        permission_key
        for permission_key, effect in user_permission_rows
        if effect == PermissionEffect.ALLOW.value
    }
    deny_keys = {
        permission_key
        for permission_key, effect in user_permission_rows
        if effect == PermissionEffect.DENY.value
    }

    return sorted((role_permission_keys | allow_keys) - deny_keys)


def get_current_app_user(
    request: Request,
    db: Session = Depends(get_db),
) -> AppUser | None:
    session_data = session_from_request(request)
    if session_data is None:
        return None
    return get_current_app_user_for_session(session_data, db)


def get_current_app_user_for_session(
    session_data: SessionData,
    db: Session,
) -> AppUser | None:
    user = db.get(AppUser, session_data.user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        return None
    return user


def require_authenticated_user(
    current_user: AppUser | None = Depends(get_current_app_user),
) -> AppUser:
    if current_user is None:
        raise ApiError(
            code="UNAUTHORIZED",
            message="Authentication is required.",
            status_code=401,
        )
    return current_user


def require_permission(permission_key: str) -> Callable[..., AppUser]:
    def dependency(
        current_user: AppUser = Depends(require_authenticated_user),
        db: Session = Depends(get_db),
    ) -> AppUser:
        permission_keys = set(resolve_effective_permission_keys(current_user, db))
        if permission_key not in permission_keys:
            raise _forbidden()
        return current_user

    return dependency


def require_any_permission(permission_keys: Sequence[str]) -> Callable[..., AppUser]:
    required_keys = frozenset(permission_keys)

    def dependency(
        current_user: AppUser = Depends(require_authenticated_user),
        db: Session = Depends(get_db),
    ) -> AppUser:
        effective_keys = set(resolve_effective_permission_keys(current_user, db))
        if not required_keys.intersection(effective_keys):
            raise _forbidden()
        return current_user

    return dependency


def _forbidden() -> ApiError:
    return ApiError(
        code="FORBIDDEN",
        message="You are not authorized to perform this action.",
        status_code=403,
    )
