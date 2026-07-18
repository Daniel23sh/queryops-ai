from __future__ import annotations

from app.action_engine.base import ActionHandler
from app.models.product import SupportedActionType


class UnknownActionTypeError(LookupError):
    pass


class DuplicateActionHandlerError(ValueError):
    pass


class InvalidActionHandlerError(TypeError):
    pass


class ActionRegistry:
    """An explicit in-process allowlist with no dynamic module loading."""

    def __init__(self) -> None:
        self._handlers: dict[SupportedActionType, ActionHandler] = {}

    def register(self, handler: ActionHandler) -> None:
        if not isinstance(handler, ActionHandler):
            raise InvalidActionHandlerError(
                "Action handlers must implement the typed ActionHandler contract."
            )

        try:
            action_type = SupportedActionType(handler.action_type)
        except (TypeError, ValueError) as exc:
            raise InvalidActionHandlerError(
                "Action handlers must declare a supported action type."
            ) from exc

        if action_type in self._handlers:
            raise DuplicateActionHandlerError(
                f"A handler is already registered for {action_type.value}."
            )

        self._handlers[action_type] = handler

    def get(self, action_type: SupportedActionType | str) -> ActionHandler:
        try:
            supported_type = SupportedActionType(action_type)
        except (TypeError, ValueError) as exc:
            raise UnknownActionTypeError("Unknown action type.") from exc

        try:
            return self._handlers[supported_type]
        except KeyError as exc:
            raise UnknownActionTypeError("No handler is registered for this action type.") from exc

    @property
    def registered_action_types(self) -> tuple[SupportedActionType, ...]:
        return tuple(sorted(self._handlers, key=lambda action_type: action_type.value))


def build_default_action_registry() -> ActionRegistry:
    """Build the explicit V1 registry without reflection or plugin discovery."""

    from app.domains.it_operations.actions.reclaim_unused_license import (
        ReclaimUnusedLicenseHandler,
    )
    from app.domains.it_operations.actions.disable_inactive_user import (
        DisableInactiveUserHandler,
    )

    registry = ActionRegistry()
    registry.register(ReclaimUnusedLicenseHandler())
    registry.register(DisableInactiveUserHandler())
    return registry
