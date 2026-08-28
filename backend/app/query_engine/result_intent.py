from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)


Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128),
]
MAX_RESULT_INTENT_ITEMS = 64


class GroundedFieldIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    table: Identifier
    column: Identifier


class GroundedRowGrain(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mode: Literal["detail", "grouped"]
    identity_fields: tuple[GroundedFieldIdentity, ...] = Field(
        min_length=1,
        max_length=MAX_RESULT_INTENT_ITEMS,
    )


class GroundedAggregationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: Identifier
    function: Literal["count", "sum"]
    target_field: GroundedFieldIdentity | None
    distinct: bool

    @model_validator(mode="after")
    def validate_function(self) -> GroundedAggregationIntent:
        if self.function == "sum" and self.target_field is None:
            raise ValueError("Sum aggregation requires a target field")
        return self


class GroundedHavingIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    aggregation_id: Identifier
    operator: Literal[
        "equals",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
    ]
    value: int | float


class GroundedResultIntent(BaseModel):
    """Deterministic required result semantics, independent of SQL syntax."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    row_grain: GroundedRowGrain | None = None
    required_output_fields: tuple[GroundedFieldIdentity, ...] = Field(
        default=(),
        max_length=MAX_RESULT_INTENT_ITEMS,
    )
    aggregations: tuple[GroundedAggregationIntent, ...] = Field(
        default=(),
        max_length=MAX_RESULT_INTENT_ITEMS,
    )
    group_by: tuple[GroundedFieldIdentity, ...] = Field(
        default=(),
        max_length=MAX_RESULT_INTENT_ITEMS,
    )
    having: tuple[GroundedHavingIntent, ...] = Field(
        default=(),
        max_length=MAX_RESULT_INTENT_ITEMS,
    )
    distinct: bool | None = None

    @model_validator(mode="after")
    def validate_references(self) -> GroundedResultIntent:
        aggregation_ids = [item.id for item in self.aggregations]
        if len(set(aggregation_ids)) != len(aggregation_ids):
            raise ValueError("Grounded aggregation IDs must be unique")
        if any(item.aggregation_id not in aggregation_ids for item in self.having):
            raise ValueError("Grounded HAVING references an unknown aggregation")
        return self

    def as_safe_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def referenced_fields(self) -> tuple[GroundedFieldIdentity, ...]:
        fields = list(self.required_output_fields)
        fields.extend(self.group_by)
        if self.row_grain is not None:
            fields.extend(self.row_grain.identity_fields)
        fields.extend(
            item.target_field
            for item in self.aggregations
            if item.target_field is not None
        )
        return tuple(sorted(set(fields), key=lambda item: (item.table, item.column)))


def safe_grounded_result_intent(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        intent = GroundedResultIntent.model_validate(value, strict=False)
    except ValidationError:
        return None
    return intent.as_safe_dict()
