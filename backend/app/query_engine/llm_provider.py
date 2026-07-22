from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


MAX_PROVIDER_MODEL_LABEL_LENGTH = 128
MAX_PROVIDER_DURATION_MS = 86_400_000.0
MAX_PROVIDER_USAGE_COUNT = 1_000_000_000


@dataclass(frozen=True)
class SQLGenerationResult:
    generated_sql: str | None
    provider_name: str
    model_name: str
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    clarification_required: bool = False
    unsupported_reason: str | None = None
    safe_error: str | None = None


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_sql(
        self,
        question: str,
        schema_context: Mapping[str, Any],
        user_context: Mapping[str, Any],
        options: Mapping[str, Any],
    ) -> SQLGenerationResult:
        """Return structured SQL generation output without executing SQL."""
        ...


class LLMProviderFailure(RuntimeError):
    def __init__(self, code: str, *, fatal: bool = False) -> None:
        super().__init__("SQL generation is unavailable.")
        self.code = code
        self.fatal = fatal
        self.safe_message = "SQL generation is unavailable."


def sanitize_provider_measurement(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    provider = value.get("provider")
    model_label = value.get("model_label")
    duration_ms = value.get("duration_ms")
    attempt_count = value.get("attempt_count")
    if (
        provider != "openai"
        or not isinstance(model_label, str)
        or not 1 <= len(model_label) <= MAX_PROVIDER_MODEL_LABEL_LENGTH
        or not isinstance(duration_ms, int | float)
        or isinstance(duration_ms, bool)
        or not 0 <= float(duration_ms) <= MAX_PROVIDER_DURATION_MS
        or not isinstance(attempt_count, int)
        or isinstance(attempt_count, bool)
        or not 1 <= attempt_count <= 3
    ):
        return None
    safe: dict[str, Any] = {
        "provider": provider,
        "model_label": model_label,
        "duration_ms": round(float(duration_ms), 3),
        "attempt_count": attempt_count,
    }
    for key in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
    ):
        count = value.get(key)
        if (
            isinstance(count, int)
            and not isinstance(count, bool)
            and 0 <= count <= MAX_PROVIDER_USAGE_COUNT
        ):
            safe[key] = count
    return safe
