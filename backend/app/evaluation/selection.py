from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from app.evaluation.contracts import (
    CaseType,
    EvaluationCase,
    EvaluationDifficulty,
    EvaluationSet,
)


class EvaluationSelectionError(ValueError):
    """Raised before persistence when deterministic filters are invalid."""

    code = "invalid_evaluation_selection"

    @property
    def safe_message(self) -> str:
        return str(self)


@dataclass(frozen=True)
class EvaluationFilters:
    case_id: str | None = None
    difficulty: EvaluationDifficulty | None = None
    category: str | None = None
    case_type: CaseType | None = None
    security_only: bool = False

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "difficulty": self.difficulty.value if self.difficulty else None,
            "category": self.category,
            "case_type": self.case_type.value if self.case_type else None,
            "security_only": self.security_only,
        }


def select_evaluation_cases(
    evaluation_set: EvaluationSet,
    filters: EvaluationFilters | None = None,
) -> tuple[EvaluationCase, ...]:
    selected_filters = filters or EvaluationFilters()
    if (
        selected_filters.case_id is not None
        and selected_filters.case_id not in evaluation_set.cases_by_id
    ):
        raise EvaluationSelectionError(
            f"Unknown evaluation case id: {selected_filters.case_id}"
        )

    cases = tuple(
        case
        for case in evaluation_set.cases
        if _matches(case, selected_filters)
    )
    if not cases:
        raise EvaluationSelectionError("Evaluation filters selected no cases")
    return cases


def evaluation_dataset_digest(evaluation_set: EvaluationSet) -> str:
    canonical = json.dumps(
        asdict(evaluation_set),
        default=_json_default,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _matches(case: EvaluationCase, filters: EvaluationFilters) -> bool:
    return all(
        (
            filters.case_id is None or case.id == filters.case_id,
            filters.difficulty is None or case.difficulty is filters.difficulty,
            filters.category is None or case.category == filters.category,
            filters.case_type is None or case.case_type is filters.case_type,
            not filters.security_only or case.security_sensitive,
        )
    )


def _json_default(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported evaluation digest value: {type(value).__name__}")
