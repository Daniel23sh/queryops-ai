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


def dashboard_is_manageable(
    dashboard: Dashboard,
    current_user: AppUser,
    access_context: UserAccessContext,
) -> bool:
    if dashboard.is_archived:
        return False

    if dashboard.visibility_scope == VisibilityScope.PERSONAL.value:
        return (
            dashboard.owner_user_id == current_user.id
            and access_context.has_permission("can_create_personal_dashboard")
        )

    if dashboard.visibility_scope == VisibilityScope.DEPARTMENT.value:
        return dashboard_is_visible(
            dashboard,
            current_user,
            access_context,
        ) and any(
            access_context.has_permission(permission)
            for permission in (
                "can_manage_department_dashboard",
                "can_manage_scope_dashboard",
            )
        )

    if dashboard.visibility_scope == VisibilityScope.GLOBAL.value:
        return access_context.has_global_scope and access_context.has_permission(
            "can_manage_global_dashboard"
        )

    return False
