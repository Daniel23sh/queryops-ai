from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoverageAvailability(str, Enum):
    MEASURED = "measured"
    PARTIALLY_MEASURED = "partially_measured"
    NOT_MEASURED = "not_measured"
    UNAVAILABLE = "unavailable"


class EvaluationRunView(StrictModel):
    id: UUID
    provider: str
    model_label: str
    dataset_id: str
    dataset_version: str
    dataset_digest: str
    status: str
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
    query_execution_succeeded_count: int = Field(ge=0)
    query_execution_failed_count: int = Field(ge=0)


class MetricBreakdown(StrictModel):
    key: str
    eligible_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0, le=1)


class CoverageItem(StrictModel):
    capability: str
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
    expected_outcome: str
    actual_outcome: str
    execution_succeeded: bool
    query_execution_attempted: bool
    expected_row_count: int = Field(ge=0)
    actual_row_count: int = Field(ge=0)
    missing_row_count: int = Field(ge=0)
    extra_row_count: int = Field(ge=0)
    failure_reasons: list[str]
    error_code: str | None
    duration_ms: float = Field(ge=0)
    referenced_tables: list[str] | None


class EvaluationCaseMetric(StrictModel):
    case_id: str
    category: str
    difficulty: str
    case_type: str
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
    items: list[EvaluationCaseMetric]
    pagination: Pagination


class EvaluationSecurityMetrics(StrictModel):
    run: EvaluationRunView | None
    metrics: MetricSummary
    items: list[EvaluationCaseMetric]


class EvaluationCapabilityMetrics(StrictModel):
    run: EvaluationRunView | None
    capability: str
    availability: CoverageAvailability
    measured_case_count: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0, le=1)
    reason_code: str


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
