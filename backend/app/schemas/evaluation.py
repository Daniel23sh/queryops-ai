from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.contracts import (
    ActualOutcome,
    CaseType,
    EvaluationDifficulty,
    ExpectedOutcome,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoverageAvailability(str, Enum):
    MEASURED = "measured"
    PARTIALLY_MEASURED = "partially_measured"
    NOT_MEASURED = "not_measured"
    UNAVAILABLE = "unavailable"


class RunLifecycleStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SafeFailureReason(str, Enum):
    UNEXPECTED_OUTCOME = "unexpected_outcome"
    EXECUTION_STATE_MISMATCH = "execution_state_mismatch"
    REFERENCED_TABLES_MISMATCH = "referenced_tables_mismatch"
    ROW_COUNT_MISMATCH = "row_count_mismatch"
    RESULT_SEMANTICS_MISMATCH = "result_semantics_mismatch"
    MISSING_STABLE_KEY = "missing_stable_key"
    INVALID_NUMERIC_VALUE = "invalid_numeric_value"


class SafeEvaluationErrorCode(str, Enum):
    ACCESS_DENIED = "access_denied"
    CLARIFICATION_REQUIRED = "clarification_required"
    EXECUTION_FAILED = "execution_failed"
    INTERNAL_ERROR = "internal_error"
    UNSAFE_SQL_BLOCKED = "unsafe_sql_blocked"
    BASELINE_FAILED = "evaluation_baseline_failed"
    CASE_INTERNAL_ERROR = "evaluation_case_internal_error"
    SETUP_FAILED = "evaluation_setup_failed"


class SecurityBehavior(str, Enum):
    AUTHORIZATION_DENIAL = "authorization_denial"
    SCOPE_DENIAL = "scope_denial"
    UNSAFE_QUERY_BLOCK = "unsafe_query_block"
    PROTECTED_RESOURCE_DENIAL = "protected_resource_denial"
    CLARIFICATION = "clarification"


class EvaluationRunView(StrictModel):
    id: UUID
    provider: Literal["mock"]
    model_label: Literal["mock-queryops-v1"]
    dataset_id: str = Field(min_length=1, max_length=128)
    dataset_version: str = Field(min_length=1, max_length=64)
    dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: RunLifecycleStatus
    started_at: datetime | None
    completed_at: datetime | None


class MetricSummary(StrictModel):
    availability: CoverageAvailability
    eligible_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    overall_score: float | None = Field(default=None, ge=0, le=1)
    expected_behavior_match_rate: float | None = Field(default=None, ge=0, le=1)
    security_pass_rate: float | None = Field(default=None, ge=0, le=1)
    query_execution_succeeded_count: int = Field(ge=0)
    query_execution_failed_count: int = Field(ge=0)


class MetricBreakdown(StrictModel):
    key: str = Field(min_length=1, max_length=128)
    eligible_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0, le=1)


class CoverageItem(StrictModel):
    capability: Literal["queries", "actions", "security", "dashboards"]
    availability: CoverageAvailability
    measured_case_count: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0, le=1)


class EvaluationOverview(StrictModel):
    run: EvaluationRunView | None
    metrics: MetricSummary
    by_difficulty: list[MetricBreakdown]
    by_category: list[MetricBreakdown]
    by_case_type: list[MetricBreakdown]
    coverage: list[CoverageItem]


class EvaluationTechnicalDetails(StrictModel):
    expected_outcome: ExpectedOutcome
    actual_outcome: ActualOutcome
    execution_succeeded: bool
    query_execution_attempted: bool
    expected_row_count: int = Field(ge=0)
    actual_row_count: int = Field(ge=0)
    missing_row_count: int = Field(ge=0)
    extra_row_count: int = Field(ge=0)
    failure_reasons: list[SafeFailureReason] = Field(max_length=7)
    error_code: SafeEvaluationErrorCode | None
    duration_ms: float = Field(ge=0)
    referenced_tables: list[str] | None


class EvaluationCaseMetric(StrictModel):
    case_id: str = Field(pattern=r"^itops-(easy|medium|hard|security)-[0-9]{3}$")
    category: str = Field(min_length=1, max_length=64)
    difficulty: EvaluationDifficulty
    case_type: CaseType
    passed: bool
    score: float = Field(ge=0, le=1)
    technical: EvaluationTechnicalDetails | None


class Pagination(StrictModel):
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    returned: int = Field(ge=0)
    total: int = Field(ge=0)


class EvaluationQueryMetrics(StrictModel):
    run: EvaluationRunView | None
    metrics: MetricSummary
    by_difficulty: list[MetricBreakdown]
    by_category: list[MetricBreakdown]
    by_case_type: list[MetricBreakdown]
    items: list[EvaluationCaseMetric]
    pagination: Pagination


class EvaluationSecurityMetrics(StrictModel):
    run: EvaluationRunView | None
    metrics: MetricSummary
    by_expected_behavior: list[MetricBreakdown]
    items: list[EvaluationCaseMetric]


class EvaluationCapabilityMetrics(StrictModel):
    run: EvaluationRunView | None
    capability: Literal["actions", "dashboards"]
    availability: CoverageAvailability
    measured_cases: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0, le=1)
    reason_code: Literal[
        "action_evaluation_not_available",
        "dashboard_evaluation_not_available",
    ]


class ResponseMeta(StrictModel):
    request_id: UUID
    timestamp: datetime


class EvaluationOverviewResponse(StrictModel):
    data: EvaluationOverview
    meta: ResponseMeta


class EvaluationQueryMetricsResponse(StrictModel):
    data: EvaluationQueryMetrics
    meta: ResponseMeta


class EvaluationSecurityMetricsResponse(StrictModel):
    data: EvaluationSecurityMetrics
    meta: ResponseMeta


class EvaluationCapabilityMetricsResponse(StrictModel):
    data: EvaluationCapabilityMetrics
    meta: ResponseMeta
