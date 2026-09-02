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


class EvaluationSuite(str, Enum):
    FULL = "full"
    CANARY = "canary"


class CanaryCoverage(str, Enum):
    CANONICAL_METRIC = "canonical_metric"
    DETAIL_QUERY = "detail_query"
    GROUPED_COUNT = "grouped_count"
    EXPLICIT_HAVING = "explicit_having"
    OR_COMPOSITION = "or_composition"
    LITERAL_FILTER = "literal_filter"
    MULTI_TABLE_CHAIN = "multi_table_relationship_chain"
    SCOPED_AUTHORIZATION = "scoped_authorization"
    CLARIFICATION = "clarification"
    UNSAFE_REQUEST = "unsafe_request"


V2_DATASET_ID = "it_operations_v2"
V2_DATASET_VERSION = "2"
V2_DATASET_DIGEST = (
    "26233d82e82633fe890b1f3e52f7cfd26eb4ce59db66a3c35a8ed1de97fa806b"
)
CANARY_SUITE_ID = "it_operations_v2_stability_canary"
CANARY_SUITE_VERSION = "1"
CANARY_CASE_IDS = (
    "itops-easy-005",
    "itops-easy-006",
    "itops-easy-008",
    "itops-medium-006",
    "itops-hard-004",
    "itops-hard-006",
    "itops-hard-007",
    "itops-security-002",
    "itops-security-003",
    "itops-security-005",
)
CANARY_COVERAGE = {
    CanaryCoverage.CANONICAL_METRIC: ("itops-easy-005",),
    CanaryCoverage.DETAIL_QUERY: ("itops-easy-006",),
    CanaryCoverage.GROUPED_COUNT: ("itops-medium-006",),
    CanaryCoverage.EXPLICIT_HAVING: ("itops-hard-004",),
    CanaryCoverage.OR_COMPOSITION: ("itops-hard-007",),
    # disabled_directory_account expands through the deterministic compiler to
    # the exact account_status literal predicate without weakening grounding.
    CanaryCoverage.LITERAL_FILTER: ("itops-easy-008",),
    CanaryCoverage.MULTI_TABLE_CHAIN: ("itops-medium-006", "itops-hard-006"),
    CanaryCoverage.SCOPED_AUTHORIZATION: ("itops-security-002",),
    CanaryCoverage.CLARIFICATION: ("itops-security-005",),
    CanaryCoverage.UNSAFE_REQUEST: ("itops-security-003",),
}


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


@dataclass(frozen=True)
class EvaluationSuiteSelection:
    suite_id: str
    suite_version: str
    suite_digest: str
    cases: tuple[EvaluationCase, ...]

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "id": self.suite_id,
            "version": self.suite_version,
            "digest": self.suite_digest,
            "selected_case_ids": [case.id for case in self.cases],
            "selected_count": len(self.cases),
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


def select_evaluation_suite(
    evaluation_set: EvaluationSet,
    suite: EvaluationSuite,
    filters: EvaluationFilters | None = None,
) -> EvaluationSuiteSelection:
    selected_filters = filters or EvaluationFilters()
    if suite is EvaluationSuite.CANARY:
        if selected_filters != EvaluationFilters():
            raise EvaluationSelectionError(
                "Canary suite cannot be combined with evaluation filters"
            )
        dataset_digest = evaluation_dataset_digest(evaluation_set)
        if (
            evaluation_set.dataset_id != V2_DATASET_ID
            or evaluation_set.version != V2_DATASET_VERSION
            or dataset_digest != V2_DATASET_DIGEST
        ):
            raise EvaluationSelectionError(
                "Canary suite requires the frozen Evaluation V2 dataset"
            )
        missing_ids = sorted(set(CANARY_CASE_IDS) - set(evaluation_set.cases_by_id))
        if missing_ids:
            raise EvaluationSelectionError(
                "Canary suite references unavailable Evaluation V2 cases"
            )
        cases = tuple(evaluation_set.cases_by_id[case_id] for case_id in CANARY_CASE_IDS)
        suite_digest = _suite_digest(
            CANARY_SUITE_ID,
            CANARY_SUITE_VERSION,
            evaluation_set,
            CANARY_CASE_IDS,
            CANARY_COVERAGE,
        )
        return EvaluationSuiteSelection(
            suite_id=CANARY_SUITE_ID,
            suite_version=CANARY_SUITE_VERSION,
            suite_digest=suite_digest,
            cases=cases,
        )

    cases = select_evaluation_cases(evaluation_set, selected_filters)
    all_case_ids = tuple(case.id for case in evaluation_set.cases)
    return EvaluationSuiteSelection(
        suite_id=f"{evaluation_set.dataset_id}_full",
        suite_version=evaluation_set.version,
        suite_digest=_suite_digest(
            f"{evaluation_set.dataset_id}_full",
            evaluation_set.version,
            evaluation_set,
            all_case_ids,
        ),
        cases=cases,
    )


def evaluation_dataset_digest(evaluation_set: EvaluationSet) -> str:
    document = asdict(evaluation_set)
    for case in document["cases"]:
        if case.get("semantic_contract") is None:
            case.pop("semantic_contract", None)
    canonical = json.dumps(
        document,
        default=_json_default,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _suite_digest(
    suite_id: str,
    suite_version: str,
    evaluation_set: EvaluationSet,
    case_ids: tuple[str, ...],
    coverage: dict[CanaryCoverage, tuple[str, ...]] | None = None,
) -> str:
    document = {
        "suite_id": suite_id,
        "suite_version": suite_version,
        "dataset_id": evaluation_set.dataset_id,
        "dataset_version": evaluation_set.version,
        "dataset_digest": evaluation_dataset_digest(evaluation_set),
        "case_ids": list(case_ids),
        "coverage": {
            category.value: list(ids)
            for category, ids in sorted(
                (coverage or {}).items(), key=lambda item: item[0].value
            )
        },
    }
    canonical = json.dumps(
        document,
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
