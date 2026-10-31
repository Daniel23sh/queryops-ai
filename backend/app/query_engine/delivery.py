"""Safe delivery provenance for re-executing server-persisted query SQL."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.query_engine.sql_executor import SQLExecutionResult
from app.query_engine.sql_validator import (
    DEFAULT_QUERY_LIMIT,
    MAX_QUERY_LIMIT,
    SQLValidationResult,
)

DELIVERY_WARNINGS = {
    "safety_limited": "Partial result: a safety limit may have omitted rows. The full total is unknown.",
    "unknown": "Result completeness is unknown. The returned rows may not be the full result.",
}


def restore_saved_bound(
    validation: SQLValidationResult,
    metadata: Any,
) -> SQLValidationResult:
    """Revalidation proves SQL safety, but cannot establish its original bound."""
    unknown = replace(validation, input_limit=None, limit_source=None)
    if not validation.valid or not isinstance(metadata, dict):
        return unknown
    prior = metadata.get("validation")
    if not isinstance(prior, dict) or prior.get("valid") is not True:
        return unknown
    effective = prior.get("effective_limit")
    original = prior.get("input_limit")
    source = prior.get("limit_source")
    if (
        type(effective) is not int
        or effective < 0
        or effective != validation.effective_limit
        or validation.limit_source != "input"
    ):
        return unknown
    if source == "input" and type(original) is int and original == effective:
        return replace(validation, input_limit=original, limit_source="input")
    if source == "safety_added" and original is None and effective == DEFAULT_QUERY_LIMIT:
        return replace(validation, input_limit=None, limit_source="safety_added")
    if (
        source == "safety_clamped"
        and type(original) is int
        and original > effective
        and effective == MAX_QUERY_LIMIT
    ):
        return replace(validation, input_limit=original, limit_source="safety_clamped")
    return unknown


def bound_metadata(validation: SQLValidationResult) -> dict[str, Any]:
    return {
        "valid": validation.valid,
        "error_code": validation.error_code,
        "input_limit": validation.input_limit,
        "effective_limit": validation.effective_limit,
        "limit_source": validation.limit_source,
    }


def delivery_completeness(result: SQLExecutionResult) -> str:
    value = result.execution_metadata.get("delivery_completeness")
    return value if isinstance(value, str) and value in {"complete", "safety_limited", "unknown"} else "unknown"
