from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


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


@dataclass(frozen=True)
class ExpectedTableColumns:
    table: str
    columns: tuple[str, ...]


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


@dataclass(frozen=True)
class EvaluationSet:
    dataset_id: str
    domain_id: str
    version: str
    cases: tuple[EvaluationCase, ...]

    @property
    def cases_by_id(self) -> dict[str, EvaluationCase]:
        return {case.id: case for case in self.cases}
