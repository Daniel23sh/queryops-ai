from __future__ import annotations

from app.auth.access_context import UserAccessContext
from app.models.product import AppUser, Dashboard, VisibilityScope


def dashboard_is_visible(
    dashboard: Dashboard,
    current_user: AppUser,
    access_context: UserAccessContext,
) -> bool:
    if dashboard.visibility_scope == VisibilityScope.PERSONAL.value:
        return dashboard.owner_user_id == current_user.id

    if dashboard.visibility_scope == VisibilityScope.GLOBAL.value:
        return access_context.has_global_scope

    if dashboard.visibility_scope == VisibilityScope.DEPARTMENT.value:
        if access_context.has_global_scope:
            return True
        if dashboard.department_id is None:
            return False
        if current_user.department_id == dashboard.department_id:
            return True
        return any(
            scope.type == "department"
            and scope.department_id == dashboard.department_id
            for scope in access_context.scopes
        )

    return False
