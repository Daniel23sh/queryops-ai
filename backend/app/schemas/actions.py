from __future__ import annotations

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.product import SupportedActionType


MAX_ACTION_REASON_LENGTH = 1_000
MAX_EXPLICIT_TARGET_IDS = 100


class StrictActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionPreviewRequest(StrictActionRequest):
    action_type: SupportedActionType
    source_query_run_id: UUID | None = None
    scope_id: UUID
    department_id: UUID | None = None
    target_user_ids: list[UUID] | None = Field(default=None, max_length=100)
    license_assignment_ids: list[UUID] | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=MAX_ACTION_REASON_LENGTH)

    @field_validator("target_user_ids", "license_assignment_ids")
    @classmethod
    def deduplicate_ids(cls, values: list[UUID] | None) -> list[UUID] | None:
        if values is None:
            return None
        return list(dict.fromkeys(values))

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A reason is required.")
        return normalized

    @model_validator(mode="after")
    def enforce_combined_selector_limit(self) -> Self:
        selector_count = len(self.target_user_ids or []) + len(
            self.license_assignment_ids or []
        )
        if selector_count > MAX_EXPLICIT_TARGET_IDS:
            raise ValueError(
                "Explicit action selectors exceed the supported record limit."
            )
        if self.action_type == SupportedActionType.DISABLE_INACTIVE_USER:
            if not self.target_user_ids:
                raise ValueError(
                    "Disable inactive user requires explicit Directory User targets."
                )
            if self.license_assignment_ids:
                raise ValueError(
                    "Disable inactive user accepts only Directory User targets."
                )
        return self


class ActionSubmitRequest(StrictActionRequest):
    action_request_id: UUID
    reason: str = Field(min_length=1, max_length=MAX_ACTION_REASON_LENGTH)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A reason is required.")
        return normalized


class ActionCancelRequest(StrictActionRequest):
    reason: str = Field(min_length=1, max_length=MAX_ACTION_REASON_LENGTH)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A reason is required.")
        return normalized
