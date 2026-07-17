from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_DECISION_REASON_LENGTH = 1_000


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_reason: str = Field(min_length=1, max_length=MAX_DECISION_REASON_LENGTH)

    @field_validator("decision_reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A decision reason is required.")
        return normalized
