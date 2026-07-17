"""Deterministic contracts for governed operational actions."""

from app.action_engine.base import (
    AccessContextSnapshot,
    AccessDecisionSnapshot,
    ActionHandler,
    ActionPreview,
    ActionTargetInput,
    ActionTargetReference,
    AdminOverrideRecordDescriptor,
    EligibleRecordDescriptor,
    ExecutionResult,
    PolicyFlag,
    PreviewTimestamps,
    ResourceAccessDecisionSnapshot,
    RevalidationResult,
    SafeResourceDescriptor,
    SafeEstimatedImpact,
    SkippedRecordDescriptor,
)
from app.action_engine.policy import (
    ActionPolicyDecision,
    evaluate_action_approval,
    evaluate_action_request,
)
from app.action_engine.registry import (
    ActionRegistry,
    DuplicateActionHandlerError,
    InvalidActionHandlerError,
    UnknownActionTypeError,
)

__all__ = [
    "AccessContextSnapshot",
    "AccessDecisionSnapshot",
    "ActionHandler",
    "ActionPolicyDecision",
    "ActionPreview",
    "ActionRegistry",
    "ActionTargetInput",
    "ActionTargetReference",
    "AdminOverrideRecordDescriptor",
    "DuplicateActionHandlerError",
    "EligibleRecordDescriptor",
    "ExecutionResult",
    "InvalidActionHandlerError",
    "PolicyFlag",
    "PreviewTimestamps",
    "ResourceAccessDecisionSnapshot",
    "RevalidationResult",
    "SafeResourceDescriptor",
    "SafeEstimatedImpact",
    "SkippedRecordDescriptor",
    "UnknownActionTypeError",
    "evaluate_action_approval",
    "evaluate_action_request",
]
