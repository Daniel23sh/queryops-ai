from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext, build_user_access_context
from app.evaluation.context import EVALUATION_ACTOR_EMAILS
from app.evaluation.contracts import (
    ActualOutcome,
    CaseType,
    EvaluationCase,
    EvaluationDifficulty,
    EvaluationSet,
    ExpectedOutcome,
    RequestingRole,
    ScopeMode,
)
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.scoring import SAFE_FAILURE_REASONS
from app.evaluation.selection import evaluation_dataset_digest
from app.models.product import (
    AppUser,
    DataResource,
    EvaluationResult,
    EvaluationRun,
    Role,
    RunStatus,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.schemas.evaluation import (
    CoverageAvailability,
    CoverageItem,
    EvaluationCapabilityMetrics,
    EvaluationCaseMetric,
    EvaluationOverview,
    EvaluationQueryMetrics,
    EvaluationRunView,
    EvaluationSecurityMetrics,
    EvaluationTechnicalDetails,
    MetricBreakdown,
    MetricSummary,
    Pagination,
)


MODEL_LABEL = "mock-queryops-v1"
SAFE_RUN_STATUSES = frozenset(
    {"queued", "running", "succeeded", "failed", "cancelled"}
)
SAFE_RESULT_STATUSES = frozenset({"succeeded", "failed", "skipped"})
SAFE_ERROR_CODES = frozenset(
    {
        "access_denied",
        "clarification_required",
        "execution_failed",
        "internal_error",
        "unsafe_sql_blocked",
        "evaluation_baseline_failed",
        "evaluation_case_internal_error",
        "evaluation_setup_failed",
    }
)


class EvaluationReadError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class VisibilityMode(str, Enum):
    SCOPED = "scoped"
    GLOBAL = "global"


@dataclass(frozen=True)
class EvaluationVisibility:
    mode: VisibilityMode
    scope_keys: frozenset[str]
    technical: bool
    include_resource_metadata: bool


@dataclass(frozen=True)
class EvaluationQueryFilters:
    difficulty: EvaluationDifficulty | None = None
    category: str | None = None
    case_type: CaseType | None = None
    actual_outcome: ActualOutcome | None = None
    passed: bool | None = None


@dataclass(frozen=True)
class _ParsedResult:
    case: EvaluationCase
    passed: bool
    score: float
    expected_outcome: str
    actual_outcome: str
    execution_succeeded: bool
    query_execution_attempted: bool
    expected_row_count: int
    actual_row_count: int
    missing_row_count: int
    extra_row_count: int
    failure_reasons: tuple[str, ...]
    error_code: str | None
    duration_ms: float
    referenced_tables: tuple[str, ...]


@dataclass(frozen=True)
class _ReadSnapshot:
    run: EvaluationRun | None
    run_view: EvaluationRunView | None
    eligible_cases: tuple[EvaluationCase, ...]
    selected_case_ids: frozenset[str]
    results: tuple[_ParsedResult, ...]

    @property
    def selected_count(self) -> int:
        return len(self.selected_case_ids)


def resolve_evaluation_visibility(
    db: Session,
    current_user: AppUser,
) -> EvaluationVisibility:
    context = build_user_access_context(current_user, db)
    role = context.role
    if role == RequestingRole.MANAGER.value:
        _require_permission(context, "can_view_department_evaluation")
        scope_keys = _department_scope_keys(context)
        if not scope_keys:
            raise _forbidden()
        return EvaluationVisibility(
            mode=VisibilityMode.SCOPED,
            scope_keys=scope_keys,
            technical=False,
            include_resource_metadata=False,
        )
    if role == RequestingRole.ANALYST.value:
        _require_permission(context, "can_view_scope_evaluation")
        scope_keys = _department_scope_keys(context)
        if not scope_keys:
            raise _forbidden()
        return EvaluationVisibility(
            mode=VisibilityMode.SCOPED,
            scope_keys=scope_keys,
            technical=True,
            include_resource_metadata=context.has_permission("can_view_sql"),
        )
    if role == RequestingRole.ADMIN.value:
        _require_permission(context, "can_view_global_evaluation")
        if not context.has_global_scope:
            raise _forbidden()
        return EvaluationVisibility(
            mode=VisibilityMode.GLOBAL,
            scope_keys=frozenset(),
            technical=True,
            include_resource_metadata=context.has_permission("can_view_sql"),
        )
    raise _forbidden()


class EvaluationReadService:
    """Read-only, role-aware projection over sanitized PR2 persistence.

    It never invokes the evaluator, Query Engine, LLM provider, baseline executor, or
    product-domain query tables. Scoped metrics are recomputed from visible cases.
    """

    def __init__(self, db: Session, current_user: AppUser) -> None:
        self._db = db
        self._visibility = resolve_evaluation_visibility(db, current_user)
        self._evaluation_set = load_it_operations_evaluation_set()
        self._dataset_digest = evaluation_dataset_digest(self._evaluation_set)
        self._actor_scopes = _load_actor_scopes(db)
        domain_pack = load_it_operations_domain_pack()
        pack_queryable_tables = frozenset(
            table.name for table in domain_pack.tables if table.queryable
        )
        current_queryable_tables = (
            frozenset(
                self._db.scalars(
                    select(DataResource.table_name).where(
                        DataResource.domain == self._evaluation_set.domain_id,
                        DataResource.resource_type == "table",
                        DataResource.is_queryable.is_(True),
                        DataResource.table_name.in_(pack_queryable_tables),
                    )
                ).all()
            )
            if self._visibility.include_resource_metadata
            else frozenset()
        )
        self._queryable_tables = pack_queryable_tables & current_queryable_tables

    def overview(self, run_id: UUID | None) -> EvaluationOverview:
        snapshot = self._load_snapshot(run_id)
        return EvaluationOverview(
            run=snapshot.run_view,
            metrics=_metric_summary(snapshot),
            by_difficulty=_breakdowns(snapshot, "difficulty"),
            by_category=_breakdowns(snapshot, "category"),
            by_case_type=_breakdowns(snapshot, "case_type"),
            coverage=_coverage(snapshot),
        )

    def queries(
        self,
        run_id: UUID | None,
        filters: EvaluationQueryFilters,
        *,
        limit: int,
        offset: int,
    ) -> EvaluationQueryMetrics:
        snapshot = self._load_snapshot(run_id)
        categories = {case.category for case in snapshot.eligible_cases}
        if filters.category is not None and filters.category not in categories:
            raise EvaluationReadError(
                "INVALID_EVALUATION_FILTER",
                "Evaluation filters are invalid.",
            )
        filtered = tuple(
            result for result in snapshot.results if _matches(result, filters)
        )
        statically_eligible = tuple(
            case for case in snapshot.eligible_cases if _case_matches(case, filters)
        )
        filtered_eligible = (
            tuple(result.case for result in filtered)
            if filters.actual_outcome is not None or filters.passed is not None
            else statically_eligible
        )
        filtered_eligible_ids = {case.id for case in filtered_eligible}
        filtered_selected_ids = (
            frozenset(result.case.id for result in filtered)
            if filters.actual_outcome is not None or filters.passed is not None
            else snapshot.selected_case_ids & filtered_eligible_ids
        )
        page = filtered[offset : offset + limit]
        filtered_snapshot = _snapshot_with_results(
            snapshot,
            filtered,
            eligible_cases=filtered_eligible,
            selected_case_ids=filtered_selected_ids,
        )
        return EvaluationQueryMetrics(
            run=snapshot.run_view,
            metrics=_metric_summary(filtered_snapshot),
            by_difficulty=_breakdowns(filtered_snapshot, "difficulty"),
            by_category=_breakdowns(filtered_snapshot, "category"),
            by_case_type=_breakdowns(filtered_snapshot, "case_type"),
            items=[self._case_metric(result) for result in page],
            pagination=Pagination(
                limit=limit,
                offset=offset,
                returned=len(page),
                total=len(filtered),
            ),
        )

    def security(self, run_id: UUID | None) -> EvaluationSecurityMetrics:
        snapshot = self._load_snapshot(run_id)
        security_cases = tuple(
            case
            for case in snapshot.eligible_cases
            if case.difficulty is EvaluationDifficulty.SECURITY
        )
        security_ids = {case.id for case in security_cases}
        security_results = tuple(
            result for result in snapshot.results if result.case.id in security_ids
        )
        security_snapshot = _snapshot_with_results(
            snapshot,
            security_results,
            eligible_cases=security_cases,
            selected_case_ids=snapshot.selected_case_ids & security_ids,
        )
        return EvaluationSecurityMetrics(
            run=snapshot.run_view,
            metrics=_metric_summary(security_snapshot),
            by_expected_behavior=_security_breakdowns(security_snapshot),
            items=[self._case_metric(result) for result in security_results],
        )

    def capability(
        self,
        run_id: UUID | None,
        capability: str,
    ) -> EvaluationCapabilityMetrics:
        snapshot = self._load_snapshot(run_id)
        available = (
            CoverageAvailability.NOT_MEASURED
            if snapshot.run_view is not None
            else CoverageAvailability.UNAVAILABLE
        )
        return EvaluationCapabilityMetrics(
            run=snapshot.run_view,
            capability=capability,
            availability=available,
            measured_cases=0,
            score=None,
            reason_code=(
                "action_evaluation_not_available"
                if capability == "actions"
                else "dashboard_evaluation_not_available"
            ),
        )

    def _load_snapshot(self, run_id: UUID | None) -> _ReadSnapshot:
        eligible_cases = tuple(
            case for case in self._evaluation_set.cases if self._case_is_visible(case)
        )
        if run_id is not None:
            run = self._db.get(EvaluationRun, run_id)
            if run is None or not self._run_matches_dataset(run):
                raise _not_found()
            rows = tuple(
                self._db.scalars(
                    select(EvaluationResult)
                    .where(EvaluationResult.evaluation_run_id == run.id)
                    .order_by(EvaluationResult.case_name, EvaluationResult.id)
                ).all()
            )
            snapshot = self._build_snapshot(run, rows, eligible_cases)
            if self._visibility.mode is VisibilityMode.SCOPED and not snapshot.selected_count:
                raise _not_found()
            return snapshot

        statement = select(EvaluationRun).where(
            EvaluationRun.status == RunStatus.SUCCEEDED.value,
            EvaluationRun.completed_at.is_not(None),
            EvaluationRun.summary["provider"].as_string() == "mock",
            EvaluationRun.summary["model_label"].as_string() == MODEL_LABEL,
            EvaluationRun.summary["dataset_id"].as_string()
            == self._evaluation_set.dataset_id,
            EvaluationRun.summary["dataset_version"].as_string()
            == self._evaluation_set.version,
            EvaluationRun.summary["dataset_digest"].as_string()
            == self._dataset_digest,
        )
        if self._visibility.mode is VisibilityMode.SCOPED:
            visible_case_ids = [case.id for case in eligible_cases]
            statement = (
                statement.join(
                    EvaluationResult,
                    EvaluationResult.evaluation_run_id == EvaluationRun.id,
                )
                .where(EvaluationResult.case_name.in_(visible_case_ids))
                .distinct()
            )
        run = self._db.scalar(
            statement.order_by(
                EvaluationRun.completed_at.desc(),
                EvaluationRun.id.desc(),
            ).limit(1)
        )
        if run is None:
            return self._empty_snapshot(eligible_cases)
        rows = tuple(
            self._db.scalars(
                select(EvaluationResult)
                .where(EvaluationResult.evaluation_run_id == run.id)
                .order_by(EvaluationResult.case_name, EvaluationResult.id)
            ).all()
        )
        return self._build_snapshot(run, rows, eligible_cases)

    def _build_snapshot(
        self,
        run: EvaluationRun,
        rows: tuple[EvaluationResult, ...],
        eligible_cases: tuple[EvaluationCase, ...],
    ) -> _ReadSnapshot:
        cases_by_id = {case.id: case for case in eligible_cases}
        visible_rows = tuple(row for row in rows if row.case_name in cases_by_id)
        counts = Counter(row.case_name for row in visible_rows)
        parsed: list[_ParsedResult] = []
        for row in visible_rows:
            if counts[row.case_name] != 1:
                continue
            result = _parse_result(row, cases_by_id[row.case_name])
            if result is not None:
                parsed.append(result)
        return _ReadSnapshot(
            run=run,
            run_view=_run_view(run),
            eligible_cases=eligible_cases,
            selected_case_ids=frozenset(counts),
            results=tuple(parsed),
        )

    def _empty_snapshot(
        self,
        eligible_cases: tuple[EvaluationCase, ...],
    ) -> _ReadSnapshot:
        return _ReadSnapshot(
            run=None,
            run_view=None,
            eligible_cases=eligible_cases,
            selected_case_ids=frozenset(),
            results=(),
        )

    def _run_matches_dataset(self, run: EvaluationRun) -> bool:
        summary = run.summary
        return bool(
            isinstance(summary, dict)
            and summary.get("dataset_id") == self._evaluation_set.dataset_id
            and summary.get("dataset_version") == self._evaluation_set.version
            and summary.get("dataset_digest") == self._dataset_digest
            and summary.get("provider") == "mock"
            and summary.get("model_label") == MODEL_LABEL
        )

    def _case_is_visible(self, case: EvaluationCase) -> bool:
        if self._visibility.mode is VisibilityMode.GLOBAL:
            return True
        actor_scope_keys = self._actor_scopes.get(case.requesting_role)
        return bool(actor_scope_keys and actor_scope_keys & self._visibility.scope_keys)

    def _case_metric(self, result: _ParsedResult) -> EvaluationCaseMetric:
        technical = None
        if self._visibility.technical:
            technical = EvaluationTechnicalDetails(
                expected_outcome=result.expected_outcome,
                actual_outcome=result.actual_outcome,
                execution_succeeded=result.execution_succeeded,
                query_execution_attempted=result.query_execution_attempted,
                expected_row_count=result.expected_row_count,
                actual_row_count=result.actual_row_count,
                missing_row_count=result.missing_row_count,
                extra_row_count=result.extra_row_count,
                failure_reasons=list(result.failure_reasons),
                error_code=result.error_code,
                duration_ms=result.duration_ms,
                referenced_tables=(
                    [
                        table
                        for table in result.referenced_tables
                        if table in self._queryable_tables
                    ]
                    if self._visibility.include_resource_metadata
                    else None
                ),
            )
        return EvaluationCaseMetric(
            case_id=result.case.id,
            category=result.case.category,
            difficulty=result.case.difficulty.value,
            case_type=result.case.case_type.value,
            passed=result.passed,
            score=result.score,
            technical=technical,
        )


def _load_actor_scopes(db: Session) -> dict[RequestingRole, frozenset[str]]:
    expected = {role: email for role, email in EVALUATION_ACTOR_EMAILS.items()}
    rows = db.execute(
        select(AppUser, Role)
        .join(Role, Role.id == AppUser.role_id)
        .where(AppUser.email.in_(expected.values()))
    ).all()
    by_email = {user.email: (user, role) for user, role in rows}
    scopes: dict[RequestingRole, frozenset[str]] = {}
    for requesting_role, email in expected.items():
        row = by_email.get(email)
        if row is None:
            raise _scope_attribution_unavailable()
        user, role = row
        if user.status != "active" or role.name != requesting_role.value:
            raise _scope_attribution_unavailable()
        context = build_user_access_context(user, db)
        department_scopes = _department_scope_keys(context)
        if requesting_role is RequestingRole.ADMIN:
            if not context.has_global_scope:
                raise _scope_attribution_unavailable()
        elif not department_scopes or context.has_global_scope:
            raise _scope_attribution_unavailable()
        scopes[requesting_role] = department_scopes
    return scopes


def _parse_result(
    row: EvaluationResult,
    case: EvaluationCase,
) -> _ParsedResult | None:
    expected = row.expected_output
    actual = row.actual_output
    metrics = row.metrics
    if (
        not isinstance(expected, dict)
        or not isinstance(actual, dict)
        or not isinstance(metrics, dict)
    ):
        return None
    if row.status not in SAFE_RESULT_STATUSES or row.status == "skipped":
        return None
    expected_outcome = expected.get("outcome")
    actual_outcome = actual.get("outcome")
    if expected_outcome != case.expected_outcome.value:
        return None
    if actual_outcome not in {item.value for item in ActualOutcome}:
        return None
    if metrics.get("difficulty") != case.difficulty.value:
        return None
    if (
        metrics.get("category") != case.category
        or metrics.get("case_type") != case.case_type.value
    ):
        return None
    if metrics.get("security_sensitive") is not case.security_sensitive:
        return None
    score = _bounded_number(row.score)
    metric_score = _bounded_number(metrics.get("score"))
    passed = metrics.get("passed")
    if (
        score is None
        or metric_score is None
        or score != metric_score
        or not isinstance(passed, bool)
    ):
        return None
    if (row.status == "succeeded") != passed:
        return None
    booleans = {
        "execution_succeeded": actual.get("execution_succeeded"),
        "query_execution_attempted": metrics.get("query_execution_attempted"),
    }
    if any(not isinstance(value, bool) for value in booleans.values()):
        return None
    if booleans["execution_succeeded"] != (actual_outcome == ActualOutcome.SUCCESS.value):
        return None
    counts = {}
    for key in (
        "expected_row_count",
        "actual_row_count",
        "missing_row_count",
        "extra_row_count",
    ):
        value = metrics.get(key)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or value > 10_000_000
        ):
            return None
        counts[key] = value
    duration_ms = _nonnegative_number(metrics.get("duration_ms"))
    if duration_ms is None or duration_ms > 86_400_000:
        return None
    failure_reasons = metrics.get("failure_reasons")
    if (
        not isinstance(failure_reasons, list)
        or len(failure_reasons) > len(SAFE_FAILURE_REASONS)
        or any(
            not isinstance(reason, str) or reason not in SAFE_FAILURE_REASONS
            for reason in failure_reasons
        )
    ):
        return None
    error_code = actual.get("error_code")
    if error_code is not None and (
        not isinstance(error_code, str)
        or len(error_code) > 64
        or error_code not in SAFE_ERROR_CODES
    ):
        error_code = "internal_error"
    references = actual.get("referenced_tables")
    if (
        not isinstance(references, list)
        or len(references) > 100
        or any(
            not isinstance(item, str) or not item or len(item) > 128
            for item in references
        )
    ):
        return None
    return _ParsedResult(
        case=case,
        passed=passed,
        score=score,
        expected_outcome=expected_outcome,
        actual_outcome=actual_outcome,
        execution_succeeded=booleans["execution_succeeded"],
        query_execution_attempted=booleans["query_execution_attempted"],
        expected_row_count=counts["expected_row_count"],
        actual_row_count=counts["actual_row_count"],
        missing_row_count=counts["missing_row_count"],
        extra_row_count=counts["extra_row_count"],
        failure_reasons=tuple(dict.fromkeys(failure_reasons)),
        error_code=error_code,
        duration_ms=duration_ms,
        referenced_tables=tuple(sorted(set(references))),
    )


def _metric_summary(snapshot: _ReadSnapshot) -> MetricSummary:
    completed = len(snapshot.results)
    passed = sum(result.passed for result in snapshot.results)
    outcome_matches = sum(
        result.expected_outcome == result.actual_outcome for result in snapshot.results
    )
    execution_results = tuple(
        result for result in snapshot.results if result.query_execution_attempted
    )
    security_results = tuple(
        result
        for result in snapshot.results
        if result.case.difficulty is EvaluationDifficulty.SECURITY
    )
    return MetricSummary(
        availability=_availability(snapshot),
        eligible_count=len(snapshot.eligible_cases),
        selected_count=snapshot.selected_count,
        completed_count=completed,
        passed_count=passed,
        failed_count=completed - passed,
        overall_score=(
            round(sum(result.score for result in snapshot.results) / completed, 6)
            if completed
            else None
        ),
        expected_behavior_match_rate=(
            round(outcome_matches / completed, 6) if completed else None
        ),
        security_pass_rate=(
            round(
                sum(result.passed for result in security_results)
                / len(security_results),
                6,
            )
            if security_results
            else None
        ),
        query_execution_succeeded_count=sum(
            result.execution_succeeded for result in execution_results
        ),
        query_execution_failed_count=sum(
            not result.execution_succeeded for result in execution_results
        ),
    )


def _availability(snapshot: _ReadSnapshot) -> CoverageAvailability:
    if snapshot.run is None:
        return CoverageAvailability.UNAVAILABLE
    terminal_complete = (
        snapshot.run.status == RunStatus.SUCCEEDED.value
        and snapshot.run.completed_at is not None
    )
    if terminal_complete and len(snapshot.results) == len(snapshot.eligible_cases) and not (
        snapshot.selected_count - len(snapshot.results)
    ):
        return CoverageAvailability.MEASURED
    if snapshot.results or snapshot.selected_count:
        return CoverageAvailability.PARTIALLY_MEASURED
    return CoverageAvailability.UNAVAILABLE


def _breakdowns(snapshot: _ReadSnapshot, dimension: str) -> list[MetricBreakdown]:
    eligible: Counter[str] = Counter(
        _case_dimension(case, dimension) for case in snapshot.eligible_cases
    )
    groups: dict[str, list[_ParsedResult]] = defaultdict(list)
    for result in snapshot.results:
        groups[_case_dimension(result.case, dimension)].append(result)
    return [
        MetricBreakdown(
            key=key,
            eligible_count=eligible[key],
            completed_count=len(groups[key]),
            passed_count=sum(result.passed for result in groups[key]),
            failed_count=sum(not result.passed for result in groups[key]),
            score=(
                round(sum(result.score for result in groups[key]) / len(groups[key]), 6)
                if groups[key]
                else None
            ),
        )
        for key in sorted(eligible)
    ]


def _coverage(snapshot: _ReadSnapshot) -> list[CoverageItem]:
    query_metrics = _metric_summary(snapshot)
    unavailable = (
        CoverageAvailability.NOT_MEASURED
        if snapshot.run is not None
        else CoverageAvailability.UNAVAILABLE
    )
    return [
        CoverageItem(
            capability="queries",
            availability=query_metrics.availability,
            measured_case_count=query_metrics.completed_count,
            score=query_metrics.overall_score,
        ),
        CoverageItem(
            capability="actions",
            availability=unavailable,
            measured_case_count=0,
            score=None,
        ),
        CoverageItem(
            capability="security",
            availability=_security_availability(snapshot),
            measured_case_count=sum(
                result.case.difficulty is EvaluationDifficulty.SECURITY
                for result in snapshot.results
            ),
            score=_security_score(snapshot),
        ),
        CoverageItem(
            capability="dashboards",
            availability=unavailable,
            measured_case_count=0,
            score=None,
        ),
    ]


def _security_availability(snapshot: _ReadSnapshot) -> CoverageAvailability:
    cases = tuple(
        case
        for case in snapshot.eligible_cases
        if case.difficulty is EvaluationDifficulty.SECURITY
    )
    results = tuple(
        result
        for result in snapshot.results
        if result.case.difficulty is EvaluationDifficulty.SECURITY
    )
    security_case_ids = {case.id for case in cases}
    selected_count = len(snapshot.selected_case_ids & security_case_ids)
    if snapshot.run is None:
        return CoverageAvailability.UNAVAILABLE
    if (
        snapshot.run.status == RunStatus.SUCCEEDED.value
        and snapshot.run.completed_at is not None
        and len(results) == len(cases)
    ):
        return CoverageAvailability.MEASURED
    if results or selected_count:
        return CoverageAvailability.PARTIALLY_MEASURED
    return CoverageAvailability.UNAVAILABLE


def _security_score(snapshot: _ReadSnapshot) -> float | None:
    results = tuple(
        result
        for result in snapshot.results
        if result.case.difficulty is EvaluationDifficulty.SECURITY
    )
    return round(sum(result.score for result in results) / len(results), 6) if results else None


def _security_breakdowns(snapshot: _ReadSnapshot) -> list[MetricBreakdown]:
    eligible: Counter[str] = Counter(
        _security_behavior(case) for case in snapshot.eligible_cases
    )
    groups: dict[str, list[_ParsedResult]] = defaultdict(list)
    for result in snapshot.results:
        groups[_security_behavior(result.case)].append(result)
    return [
        MetricBreakdown(
            key=key,
            eligible_count=eligible[key],
            completed_count=len(groups[key]),
            passed_count=sum(result.passed for result in groups[key]),
            failed_count=sum(not result.passed for result in groups[key]),
            score=(
                round(sum(result.score for result in groups[key]) / len(groups[key]), 6)
                if groups[key]
                else None
            ),
        )
        for key in sorted(eligible)
    ]


def _security_behavior(case: EvaluationCase) -> str:
    if case.scope_mode is ScopeMode.CROSS_SCOPE:
        return "scope_denial"
    if case.category == "protected_data":
        return "protected_resource_denial"
    if case.expected_outcome is ExpectedOutcome.UNSAFE_BLOCKED:
        return "unsafe_query_block"
    if case.expected_outcome is ExpectedOutcome.CLARIFICATION:
        return "clarification"
    return "authorization_denial"


def _snapshot_with_results(
    snapshot: _ReadSnapshot,
    results: tuple[_ParsedResult, ...],
    *,
    eligible_cases: tuple[EvaluationCase, ...],
    selected_case_ids: frozenset[str] | None = None,
) -> _ReadSnapshot:
    return _ReadSnapshot(
        run=snapshot.run,
        run_view=snapshot.run_view,
        eligible_cases=eligible_cases,
        selected_case_ids=(
            selected_case_ids
            if selected_case_ids is not None
            else frozenset(result.case.id for result in results)
        ),
        results=results,
    )


def _matches(result: _ParsedResult, filters: EvaluationQueryFilters) -> bool:
    return all(
        (
            filters.difficulty is None or result.case.difficulty is filters.difficulty,
            filters.category is None or result.case.category == filters.category,
            filters.case_type is None or result.case.case_type is filters.case_type,
            filters.actual_outcome is None
            or result.actual_outcome == filters.actual_outcome.value,
            filters.passed is None or result.passed is filters.passed,
        )
    )


def _case_matches(case: EvaluationCase, filters: EvaluationQueryFilters) -> bool:
    return all(
        (
            filters.difficulty is None or case.difficulty is filters.difficulty,
            filters.category is None or case.category == filters.category,
            filters.case_type is None or case.case_type is filters.case_type,
        )
    )


def _case_dimension(case: EvaluationCase, dimension: str) -> str:
    if dimension == "difficulty":
        return case.difficulty.value
    if dimension == "case_type":
        return case.case_type.value
    return case.category


def _run_view(run: EvaluationRun) -> EvaluationRunView:
    summary = run.summary if isinstance(run.summary, dict) else {}
    status = run.status if run.status in SAFE_RUN_STATUSES else "failed"
    return EvaluationRunView(
        id=run.id,
        provider="mock",
        model_label=str(summary["model_label"]),
        dataset_id=str(summary["dataset_id"]),
        dataset_version=str(summary["dataset_version"]),
        dataset_digest=str(summary["dataset_digest"]),
        status=status,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _bounded_number(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and 0 <= number <= 1 else None


def _nonnegative_number(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _department_scope_keys(context: UserAccessContext) -> frozenset[str]:
    return frozenset(scope.key for scope in context.scopes if scope.type == "department")


def _require_permission(context: UserAccessContext, permission: str) -> None:
    if not context.has_permission(permission):
        raise _forbidden()


def _forbidden() -> EvaluationReadError:
    return EvaluationReadError(
        "FORBIDDEN",
        "You are not authorized to view evaluation metrics.",
    )


def _not_found() -> EvaluationReadError:
    return EvaluationReadError(
        "EVALUATION_RUN_NOT_FOUND",
        "Evaluation run was not found.",
    )


def _scope_attribution_unavailable() -> EvaluationReadError:
    return EvaluationReadError(
        "EVALUATION_SCOPE_ATTRIBUTION_UNAVAILABLE",
        "Evaluation metrics are unavailable.",
    )
