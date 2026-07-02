from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


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

