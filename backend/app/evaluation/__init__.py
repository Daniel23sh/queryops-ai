"""Deterministic evaluation dataset and semantic scoring foundations."""

from app.evaluation.contracts import (
    CaseType,
    ComparisonMode,
    EvaluationCase,
    EvaluationDifficulty,
    EvaluationSet,
    ExpectedOutcome,
    RequestingRole,
    ScopeMode,
)
from app.evaluation.loader import (
    EvaluationDatasetValidationError,
    load_it_operations_evaluation_set,
)
from app.evaluation.scoring import EvaluationScore, score_evaluation_case

__all__ = [
    "CaseType",
    "ComparisonMode",
    "EvaluationCase",
    "EvaluationDatasetValidationError",
    "EvaluationDifficulty",
    "EvaluationScore",
    "EvaluationSet",
    "ExpectedOutcome",
    "RequestingRole",
    "ScopeMode",
    "load_it_operations_evaluation_set",
    "score_evaluation_case",
]
