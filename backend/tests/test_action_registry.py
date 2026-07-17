from __future__ import annotations

from typing import Any

import pytest

from app.action_engine.registry import (
    ActionRegistry,
    DuplicateActionHandlerError,
    InvalidActionHandlerError,
    UnknownActionTypeError,
)
from app.models.product import SupportedActionType


class StubActionHandler:
    action_type = SupportedActionType.RECLAIM_UNUSED_LICENSE

    def __init__(self) -> None:
        self.domain_call_count = 0

    def build_preview(self, **_kwargs: Any) -> None:
        self.domain_call_count += 1

    def revalidate(self, **_kwargs: Any) -> None:
        self.domain_call_count += 1

    def execute(self, **_kwargs: Any) -> None:
        self.domain_call_count += 1


def test_supported_typed_handler_can_be_registered() -> None:
    registry = ActionRegistry()
    handler = StubActionHandler()

    registry.register(handler)

    assert registry.get(SupportedActionType.RECLAIM_UNUSED_LICENSE) is handler
    assert registry.registered_action_types == (
        SupportedActionType.RECLAIM_UNUSED_LICENSE,
    )


def test_unknown_action_type_fails_closed() -> None:
    registry = ActionRegistry()

    with pytest.raises(UnknownActionTypeError, match="Unknown action type"):
        registry.get("user_controlled_action")


def test_unregistered_supported_action_type_fails_closed() -> None:
    registry = ActionRegistry()

    with pytest.raises(UnknownActionTypeError, match="No handler is registered"):
        registry.get(SupportedActionType.DISABLE_INACTIVE_USER)


def test_duplicate_registration_is_rejected() -> None:
    registry = ActionRegistry()
    registry.register(StubActionHandler())

    with pytest.raises(DuplicateActionHandlerError):
        registry.register(StubActionHandler())


def test_invalid_handler_is_rejected() -> None:
    registry = ActionRegistry()

    with pytest.raises(InvalidActionHandlerError):
        registry.register(object())  # type: ignore[arg-type]


def test_registry_lookup_does_not_perform_domain_work() -> None:
    registry = ActionRegistry()
    handler = StubActionHandler()
    registry.register(handler)

    assert registry.get(handler.action_type) is handler
    assert handler.domain_call_count == 0
