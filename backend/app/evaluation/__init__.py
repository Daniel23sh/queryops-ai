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
    load_it_operations_evaluation_v2_set,
)
from app.evaluation.scoring import (
    EvaluationScore,
    EvaluationSemanticScore,
    score_evaluation_case,
    score_evaluation_semantic_contract,
)

__all__ = [
    "CaseType",
    "ComparisonMode",
    "EvaluationCase",
    "EvaluationDatasetValidationError",
    "EvaluationDifficulty",
    "EvaluationScore",
    "EvaluationSemanticScore",
    "EvaluationSet",
    "ExpectedOutcome",
    "RequestingRole",
    "ScopeMode",
    "load_it_operations_evaluation_set",
    "load_it_operations_evaluation_v2_set",
    "score_evaluation_case",
    "score_evaluation_semantic_contract",
]
