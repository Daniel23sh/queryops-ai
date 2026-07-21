from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext, build_user_access_context
from app.evaluation.contracts import EvaluationCase, RequestingRole, ScopeMode
from app.models.product import AccessScope, AppUser, Role


EVALUATION_ACTOR_EMAILS = {
    RequestingRole.USER: "demo.user@queryops.local",
    RequestingRole.MANAGER: "demo.manager@queryops.local",
    RequestingRole.ANALYST: "demo.analyst@queryops.local",
    RequestingRole.ADMIN: "demo.admin@queryops.local",
}


class EvaluationSetupError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class EvaluationTargetScope:
    scope_type: str
    scope_key: str


@dataclass(frozen=True)
class EvaluationIdentity:
    user: AppUser
    access_context: UserAccessContext
    target_scope: EvaluationTargetScope | None


def resolve_evaluation_identity(
    db: Session,
    case: EvaluationCase,
) -> EvaluationIdentity:
    email = EVALUATION_ACTOR_EMAILS[case.requesting_role]
    row = db.execute(
        select(AppUser, Role)
        .join(Role, Role.id == AppUser.role_id)
        .where(AppUser.email == email)
    ).one_or_none()
    if row is None:
        raise EvaluationSetupError(
            "evaluation_actor_missing",
            f"Required seeded {case.requesting_role.value} evaluation actor is missing.",
        )
    user, role = row
    if user.status != "active" or role.name != case.requesting_role.value:
        raise EvaluationSetupError(
            "evaluation_actor_invalid",
            f"Required seeded {case.requesting_role.value} evaluation actor is invalid.",
        )

    access_context = build_user_access_context(user, db)
    target_scope = _resolve_target_scope(db, case, access_context)
    return EvaluationIdentity(
        user=user,
        access_context=access_context,
        target_scope=target_scope,
    )


def _resolve_target_scope(
    db: Session,
    case: EvaluationCase,
    access_context: UserAccessContext,
) -> EvaluationTargetScope | None:
    if case.scope_mode is ScopeMode.NONE:
        return None

    scope_type = case.required_scope_type
    if scope_type is None:
        raise EvaluationSetupError(
            "evaluation_scope_invalid",
            "Evaluation case is missing its required scope type.",
        )
    if case.scope_mode is ScopeMode.GLOBAL:
        if not access_context.has_global_scope:
            raise EvaluationSetupError(
                "evaluation_scope_missing",
                "Required seeded global evaluation scope is missing.",
            )
        return EvaluationTargetScope(scope_type="global", scope_key="global")

    if case.scope_mode is ScopeMode.ASSIGNED:
        matching = next(
            (scope for scope in access_context.scopes if scope.type == scope_type),
            None,
        )
        if matching is None:
            raise EvaluationSetupError(
                "evaluation_scope_missing",
                f"Required seeded {scope_type} evaluation scope is missing.",
            )
        return EvaluationTargetScope(
            scope_type=matching.type,
            scope_key=matching.key,
        )

    if access_context.has_global_scope:
        raise EvaluationSetupError(
            "evaluation_scope_invalid",
            "Cross-scope evaluation requires a restricted seeded actor.",
        )
    assigned_keys = {
        scope.key for scope in access_context.scopes if scope.type == scope_type
    }
    target = db.scalar(
        select(AccessScope)
        .where(
            AccessScope.scope_type == scope_type,
            AccessScope.scope_key.not_in(assigned_keys),
        )
        .order_by(AccessScope.scope_key)
        .limit(1)
    )
    if target is None:
        raise EvaluationSetupError(
            "evaluation_cross_scope_missing",
            f"No deterministic out-of-scope {scope_type} fixture is available.",
        )
    return EvaluationTargetScope(
        scope_type=target.scope_type,
        scope_key=target.scope_key,
    )
