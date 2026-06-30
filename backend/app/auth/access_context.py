from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import resolve_effective_permission_keys
from app.models.product import AccessScope, AppUser, Role, UserAccessScope


@dataclass(frozen=True)
class AccessScopeContext:
    id: uuid.UUID
    type: str
    key: str
    display_name: str
    access_level: str
    is_default: bool
    department_id: uuid.UUID | None


@dataclass(frozen=True)
class UserAccessContext:
    user_id: uuid.UUID
    role: str | None
    permissions: frozenset[str]
    scopes: tuple[AccessScopeContext, ...]
    default_scope: AccessScopeContext | None
    has_global_scope: bool
    subject_attributes: dict[str, Any]

    def has_permission(self, permission_key: str) -> bool:
        return permission_key in self.permissions

    def has_scope(self, scope_type: str, scope_key: str) -> bool:
        return any(
            scope.type == scope_type and scope.key == scope_key for scope in self.scopes
        )

    def has_scope_id(self, scope_id: uuid.UUID | str) -> bool:
        scope_uuid = uuid.UUID(str(scope_id))
        return any(scope.id == scope_uuid for scope in self.scopes)


def build_user_access_context(user: AppUser, db: Session) -> UserAccessContext:
    role = db.get(Role, user.role_id) if user.role_id else None
    permissions = frozenset(resolve_effective_permission_keys(user, db))
    scopes = tuple(_load_scope_contexts(user, db))
    default_scope = next((scope for scope in scopes if scope.is_default), None)
    if default_scope is None and scopes:
        default_scope = scopes[0]
    has_global_scope = any(
        scope.type == "global" and scope.key == "global" for scope in scopes
    )

    subject_attributes = {
        "role": role.name if role else None,
        "permissions": sorted(permissions),
        "scope_types": sorted({scope.type for scope in scopes}),
        "has_global_scope": has_global_scope,
        "auth_provider": user.auth_provider,
    }

    return UserAccessContext(
        user_id=user.id,
        role=role.name if role else None,
        permissions=permissions,
        scopes=scopes,
        default_scope=default_scope,
        has_global_scope=has_global_scope,
        subject_attributes=subject_attributes,
    )


def _load_scope_contexts(user: AppUser, db: Session) -> list[AccessScopeContext]:
    rows = db.execute(
        select(UserAccessScope, AccessScope)
        .join(AccessScope, AccessScope.id == UserAccessScope.scope_id)
        .where(UserAccessScope.user_id == user.id)
        .order_by(
            UserAccessScope.is_default.desc(),
            AccessScope.scope_type,
            AccessScope.scope_key,
        )
    ).all()

    return [
        AccessScopeContext(
            id=scope.id,
            type=scope.scope_type,
            key=scope.scope_key,
            display_name=scope.display_name,
            access_level=user_scope.access_level,
            is_default=user_scope.is_default,
            department_id=scope.department_id,
        )
        for user_scope, scope in rows
    ]
