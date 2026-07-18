from __future__ import annotations

from typing import TypeAlias

from sqlalchemy.orm import Session

from app.action_engine.disable_execution import (
    DisableRevalidation,
    lock_disable_dependencies,
    safe_disable_revalidation_flags,
)
from app.action_engine.revalidation import (
    ReclaimRevalidation,
    lock_reclaim_dependencies,
    safe_revalidation_flags,
)
from app.models.product import SupportedActionType


ActionRevalidation: TypeAlias = ReclaimRevalidation | DisableRevalidation


def require_action_revalidation(
    action_type: SupportedActionType | str,
    result: object,
) -> ActionRevalidation:
    supported_type = SupportedActionType(action_type)
    if (
        supported_type == SupportedActionType.RECLAIM_UNUSED_LICENSE
        and isinstance(result, ReclaimRevalidation)
    ):
        return result
    if (
        supported_type == SupportedActionType.DISABLE_INACTIVE_USER
        and isinstance(result, DisableRevalidation)
    ):
        return result
    raise TypeError("The action handler returned an invalid revalidation result.")


def lock_action_dependencies(
    db: Session,
    action_type: SupportedActionType | str,
    result: ActionRevalidation,
) -> None:
    supported_type = SupportedActionType(action_type)
    if (
        supported_type == SupportedActionType.RECLAIM_UNUSED_LICENSE
        and isinstance(result, ReclaimRevalidation)
    ):
        lock_reclaim_dependencies(db, result)
        return
    if (
        supported_type == SupportedActionType.DISABLE_INACTIVE_USER
        and isinstance(result, DisableRevalidation)
    ):
        lock_disable_dependencies(db, result)
        return
    raise TypeError("The action revalidation does not match its action type.")


def require_stable_execution_set(
    initial: ActionRevalidation,
    final: ActionRevalidation,
) -> None:
    initial_ids = [record.record_id for record in initial.executable_records]
    final_ids = [record.record_id for record in final.executable_records]
    if (
        len(initial_ids) != len(set(initial_ids))
        or len(final_ids) != len(set(final_ids))
        or not set(final_ids).issubset(initial_ids)
    ):
        raise RuntimeError("The action execution set changed before dependency locking.")


def safe_action_revalidation_flags(
    action_type: SupportedActionType | str,
    result: ActionRevalidation,
) -> list[dict[str, object]]:
    supported_type = SupportedActionType(action_type)
    if (
        supported_type == SupportedActionType.RECLAIM_UNUSED_LICENSE
        and isinstance(result, ReclaimRevalidation)
    ):
        return safe_revalidation_flags(result)
    if (
        supported_type == SupportedActionType.DISABLE_INACTIVE_USER
        and isinstance(result, DisableRevalidation)
    ):
        return safe_disable_revalidation_flags(result)
    raise TypeError("The action revalidation does not match its action type.")
