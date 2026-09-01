from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Literal


class EvaluationDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    SECURITY = "security"


class CaseType(str, Enum):
    TEMPLATE_QUERY = "template_query"
    FREE_QUERY = "free_query"
    AUTHORIZATION = "authorization"
    UNSAFE_SQL = "unsafe_sql"
    CLARIFICATION = "clarification"


class ExpectedOutcome(str, Enum):
    SUCCESS = "success"
    DENIED = "denied"
    UNSAFE_BLOCKED = "unsafe_blocked"
    CLARIFICATION = "clarification"


class EvaluationAnswerability(str, Enum):
    ANSWERABLE = "answerable"
    CLARIFICATION = "clarification"
    DENIED = "denied"
    UNSAFE = "unsafe"


class EvaluationSemanticSource(str, Enum):
    EXPLICIT_QUESTION = "explicit_question"
    CATALOG = "catalog"
    BOTH = "both"
    NOT_APPLICABLE = "not_applicable"


class ActualOutcome(str, Enum):
    SUCCESS = "success"
    DENIED = "denied"
    UNSAFE_BLOCKED = "unsafe_blocked"
    CLARIFICATION = "clarification"
    EXECUTION_FAILED = "execution_failed"
    INTERNAL_ERROR = "internal_error"


class ComparisonMode(str, Enum):
    UNORDERED_ROWS = "unordered_rows"
    ORDERED_ROWS = "ordered_rows"
    GROUPED_ROWS = "grouped_rows"
    STABLE_KEYS = "stable_keys"
    NONE = "none"


class RequestingRole(str, Enum):
    USER = "user"
    MANAGER = "manager"
    ANALYST = "analyst"
    ADMIN = "admin"


class ScopeMode(str, Enum):
    NONE = "none"
    ASSIGNED = "assigned"
    GLOBAL = "global"
    CROSS_SCOPE = "cross_scope"


class ProvenanceAuthorizationEvidence(str, Enum):
    FROZEN_BASELINE_VALIDATED = "frozen_baseline_validated"
    FINAL_SQL_VALIDATED = "final_sql_validated"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, order=True)
class CanonicalFieldIdentity:
    table: str
    column: str

    def as_safe_dict(self) -> dict[str, str]:
        return {"table": self.table, "column": self.column}


@dataclass(frozen=True)
class CanonicalAggregationIdentity:
    function: str
    target_field: CanonicalFieldIdentity | None
    distinct: bool
    grouping_fields: tuple[CanonicalFieldIdentity, ...]

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "target_field": (
                self.target_field.as_safe_dict()
                if self.target_field is not None
                else None
            ),
            "distinct": self.distinct,
            "grouping_fields": [
                field.as_safe_dict() for field in self.grouping_fields
            ],
        }


@dataclass(frozen=True)
class CanonicalExpressionIdentity:
    kind: Literal["field", "aggregation"]
    field: CanonicalFieldIdentity | None = None
    aggregation: CanonicalAggregationIdentity | None = None

    def __post_init__(self) -> None:
        if self.kind == "field" and (
            self.field is None or self.aggregation is not None
        ):
            raise ValueError("Field identity is inconsistent")
        if self.kind == "aggregation" and (
            self.aggregation is None or self.field is not None
        ):
            raise ValueError("Aggregation identity is inconsistent")

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "field": self.field.as_safe_dict() if self.field is not None else None,
            "aggregation": (
                self.aggregation.as_safe_dict()
                if self.aggregation is not None
                else None
            ),
        }


@dataclass(frozen=True)
class EvaluationOutputProvenance:
    presentation_name: str
    identity: CanonicalExpressionIdentity
    authorized: bool | None

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "presentation_name": self.presentation_name,
            "identity": self.identity.as_safe_dict(),
            "authorized": self.authorized,
        }


@dataclass(frozen=True)
class EvaluationOrderingProvenance:
    position: int
    direction: Literal["asc", "desc"]
    identity: CanonicalExpressionIdentity

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "direction": self.direction,
            "identity": self.identity.as_safe_dict(),
        }


@dataclass(frozen=True)
class EvaluationRowGrainProvenance:
    mode: Literal["detail", "distinct_output", "grouped"]
    identities: tuple[CanonicalExpressionIdentity, ...]
    source_tables: tuple[str, ...]

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "identities": [identity.as_safe_dict() for identity in self.identities],
            "source_tables": list(self.source_tables),
        }


@dataclass(frozen=True)
class EvaluationQueryProvenance:
    outputs: tuple[EvaluationOutputProvenance, ...]
    grouping_fields: tuple[CanonicalFieldIdentity, ...]
    ordering: tuple[EvaluationOrderingProvenance, ...]
    row_grain: EvaluationRowGrainProvenance
    authorization_evidence: ProvenanceAuthorizationEvidence
    ordering_significance_explicit: bool = False

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "outputs": [output.as_safe_dict() for output in self.outputs],
            "grouping_fields": [
                field.as_safe_dict() for field in self.grouping_fields
            ],
            "ordering": [item.as_safe_dict() for item in self.ordering],
            "row_grain": self.row_grain.as_safe_dict(),
            "authorization_evidence": self.authorization_evidence.value,
            "ordering_significance_explicit": self.ordering_significance_explicit,
        }


@dataclass(frozen=True)
class EvaluationComparisonProvenance:
    expected: EvaluationQueryProvenance | None
    actual: EvaluationQueryProvenance | None

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "expected": (
                self.expected.as_safe_dict() if self.expected is not None else None
            ),
            "actual": self.actual.as_safe_dict() if self.actual is not None else None,
        }


@dataclass(frozen=True)
class ExpectedTableColumns:
    table: str
    columns: tuple[str, ...]


@dataclass(frozen=True, order=True)
class EvaluationSemanticField:
    entity_id: str
    column: str

    def as_safe_dict(self) -> dict[str, str]:
        return {"entity_id": self.entity_id, "column": self.column}


@dataclass(frozen=True)
class EvaluationSemanticAggregation:
    id: str
    function: Literal["count", "sum"]
    field: EvaluationSemanticField | None
    distinct: bool

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "function": self.function,
            "field": self.field.as_safe_dict() if self.field is not None else None,
            "distinct": self.distinct,
        }


@dataclass(frozen=True)
class EvaluationSemanticHaving:
    aggregation_id: str
    operator: Literal[
        "equals",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
    ]
    value: Decimal

    def as_safe_dict(self) -> dict[str, str]:
        return {
            "aggregation_id": self.aggregation_id,
            "operator": self.operator,
            "value": str(self.value),
        }


@dataclass(frozen=True)
class EvaluationSemanticOrdering:
    target_kind: Literal["field", "aggregation"]
    field: EvaluationSemanticField | None
    aggregation_id: str | None
    direction: Literal["asc", "desc"]

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "target_kind": self.target_kind,
            "field": self.field.as_safe_dict() if self.field is not None else None,
            "aggregation_id": self.aggregation_id,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class EvaluationSemanticContract:
    answerability: EvaluationAnswerability
    semantic_source: EvaluationSemanticSource
    required_concept_ids: tuple[str, ...]
    required_metric_id: str | None
    required_composition_rule_ids: tuple[str, ...]
    grain_fields: tuple[EvaluationSemanticField, ...]
    output_fields: tuple[EvaluationSemanticField, ...]
    aggregations: tuple[EvaluationSemanticAggregation, ...]
    group_by: tuple[EvaluationSemanticField, ...]
    having: tuple[EvaluationSemanticHaving, ...]
    ordering: tuple[EvaluationSemanticOrdering, ...]

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "answerability": self.answerability.value,
            "semantic_source": self.semantic_source.value,
            "required_concept_ids": list(self.required_concept_ids),
            "required_metric_id": self.required_metric_id,
            "required_composition_rule_ids": list(
                self.required_composition_rule_ids
            ),
            "grain_fields": [field.as_safe_dict() for field in self.grain_fields],
            "output_fields": [field.as_safe_dict() for field in self.output_fields],
            "aggregations": [item.as_safe_dict() for item in self.aggregations],
            "group_by": [field.as_safe_dict() for field in self.group_by],
            "having": [item.as_safe_dict() for item in self.having],
            "ordering": [item.as_safe_dict() for item in self.ordering],
        }


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    question: str
    category: str
    difficulty: EvaluationDifficulty
    case_type: CaseType
    requesting_role: RequestingRole
    required_scope_type: str | None
    scope_mode: ScopeMode
    expected_outcome: ExpectedOutcome
    expected_tables: tuple[str, ...]
    expected_columns: tuple[ExpectedTableColumns, ...]
    baseline_sql: str | None
    requires_join: bool
    clarification_expected: bool
    security_sensitive: bool
    comparison_mode: ComparisonMode
    numeric_tolerance: Decimal | None
    stable_key_columns: tuple[str, ...]
    template_id: str | None
    semantic_contract: EvaluationSemanticContract | None = None


@dataclass(frozen=True)
class EvaluationSet:
    dataset_id: str
    domain_id: str
    version: str
    cases: tuple[EvaluationCase, ...]

    @property
    def cases_by_id(self) -> dict[str, EvaluationCase]:
        return {case.id: case for case in self.cases}
