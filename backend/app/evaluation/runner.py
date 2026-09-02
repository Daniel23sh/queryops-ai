from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.access_policy import authorize_resource_access
from app.evaluation.baseline import (
    EvaluationBaselineError,
    execute_evaluation_baseline,
)
from app.evaluation.context import (
    EvaluationIdentity,
    EvaluationSetupError,
    resolve_evaluation_identity,
)
from app.evaluation.environment import EvaluationEnvironmentIdentity
from app.evaluation.contracts import (
    ActualOutcome,
    CaseType,
    EvaluationComparisonProvenance,
    EvaluationCase,
    EvaluationQueryProvenance,
    EvaluationSet,
    ExpectedOutcome,
    ProvenanceAuthorizationEvidence,
)
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.provenance import (
    EvaluationProvenanceError,
    extract_evaluation_query_provenance,
)
from app.evaluation.scoring import (
    EvaluationScore,
    EvaluationSemanticScore,
    score_evaluation_case,
    score_evaluation_semantic_contract,
)
from app.evaluation.selection import (
    EvaluationFilters,
    EvaluationSuite,
    EvaluationSuiteSelection,
    evaluation_dataset_digest,
    select_evaluation_suite,
)
from app.models.product import (
    DataResource,
    EvaluationResult,
    EvaluationRun,
    QueryRun,
    RunStatus,
)
from app.query_engine.domain_pack import DomainPack
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import LLMProvider, sanitize_provider_measurement
from app.query_engine.mock_llm_provider import MockLLMProvider
from app.query_engine.provider_config import ProviderDescriptor, ProviderId
from app.query_engine.request_authorization import authorize_query_request
from app.query_engine.result_formatter import QueryEngineServiceResult
from app.query_engine.semantic_catalog import semantic_catalog_identity
from app.query_engine.service import QueryEngineRequest, QueryEngineService


SAFE_UNSAFE_VALIDATION_CODES = frozenset(
    {"multiple_statements", "not_read_only_select", "prohibited_statement"}
)
SAFE_ACTUAL_ERROR_CODES = frozenset(
    {
        "access_denied",
        "clarification_required",
        "execution_failed",
        "internal_error",
        "unsafe_sql_blocked",
        "provider_authentication_failed",
        "provider_timeout",
        "provider_unavailable",
        "provider_response_invalid",
        "semantic_conformance_failed",
        "semantic_sql_render_failed",
        "validation_failed",
    }
)
SAFE_PIPELINE_STAGES = frozenset(
    {
        "grounding",
        "plan_generation",
        "plan_validation",
        "sql_rendering",
        "sql_safety",
        "semantic_conformance",
        "execution",
        "result_comparison",
        "setup",
    }
)
EVALUATION_CATALOG_DATASET_IDS = {
    "it_operations_v1": "it_operations_v1",
    "it_operations_v2": "it_operations_v1",
}


class EvaluationRunnerError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        run_id: UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.run_id = run_id


@dataclass(frozen=True)
class EvaluationCaseSummary:
    case_id: str
    difficulty: str
    category: str
    case_type: str
    expected_outcome: str
    actual_outcome: str
    passed: bool
    score: float
    error_code: str | None


@dataclass(frozen=True)
class EvaluationRunSummary:
    run_id: UUID
    provider: str
    model_label: str
    dataset_id: str
    dataset_version: str
    dataset_digest: str
    status: str
    selected_count: int
    completed_count: int
    passed_count: int
    failed_count: int
    overall_score: float
    expected_behavior_match_rate: float
    security_pass_rate: float | None
    query_execution_succeeded_count: int
    query_execution_failed_count: int
    by_difficulty: dict[str, dict[str, int | float]]
    by_category: dict[str, dict[str, int | float]]
    by_case_type: dict[str, dict[str, int | float]]
    cases: tuple[EvaluationCaseSummary, ...]
    provider_usage: dict[str, int | float] = field(default_factory=dict)
    planner_metrics: dict[str, int | float | None] = field(default_factory=dict)
    semantic_catalog: dict[str, str] = field(default_factory=dict)
    evaluation_environment: dict[str, str | int] = field(default_factory=dict)
    evaluation_suite: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _CaseExecution:
    actual_outcome: ActualOutcome
    execution_succeeded: bool
    query_invoked: bool
    query_execution_attempted: bool
    query_run_id: UUID | None
    actual_rows: tuple[Mapping[str, Any], ...]
    actual_referenced_tables: tuple[str, ...]
    error_code: str | None
    failure_stage: str | None = None
    stage_reason_code: str | None = None
    provider_measurement: dict[str, Any] | None = None
    provider_failure_fatal: bool = False
    plan_validation_status: str | None = None
    required_intent_status: str | None = None
    renderer_status: str | None = None
    conformance_status: str | None = None
    semantic_plan_observation: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class _CompletedCase:
    case: EvaluationCase
    execution: _CaseExecution
    score: EvaluationScore
    semantic_score: EvaluationSemanticScore
    duration_ms: float
    provenance: EvaluationComparisonProvenance | None = None


SessionFactory = Callable[[], Session]
QueryServiceFactory = Callable[[DomainPack], QueryEngineService]
ProviderFactory = Callable[[DomainPack], LLMProvider]


class EvaluationRunner:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        dataset_loader: Callable[[], EvaluationSet] = load_it_operations_evaluation_set,
        domain_pack_loader: Callable[[], DomainPack] = load_it_operations_domain_pack,
        query_service_factory: QueryServiceFactory | None = None,
        provider_factory: ProviderFactory | None = None,
        provider_descriptor: ProviderDescriptor | None = None,
        evaluation_environment: EvaluationEnvironmentIdentity | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._dataset_loader = dataset_loader
        self._domain_pack_loader = domain_pack_loader
        if query_service_factory is not None and provider_factory is not None:
            raise ValueError("Choose a query service factory or a provider factory")
        self._provider_descriptor = provider_descriptor or ProviderDescriptor(
            provider=ProviderId.MOCK,
            model_label=MockLLMProvider.model_name,
        )
        self._evaluation_environment = evaluation_environment
        selected_provider_factory = provider_factory or (
            lambda pack: MockLLMProvider(pack)
        )
        self._query_service_factory = query_service_factory or (
            lambda pack: QueryEngineService(
                provider=selected_provider_factory(pack),
                domain_pack_loader=lambda: pack,
            )
        )

    def run(
        self,
        filters: EvaluationFilters | None = None,
        *,
        suite: EvaluationSuite = EvaluationSuite.FULL,
    ) -> EvaluationRunSummary:
        selected_filters = filters or EvaluationFilters()
        evaluation_set = self._dataset_loader()
        suite_selection = select_evaluation_suite(
            evaluation_set,
            suite,
            selected_filters,
        )
        cases = suite_selection.cases
        domain_pack = self._domain_pack_loader()
        digest = evaluation_dataset_digest(evaluation_set)
        catalog_identity = self._verify_catalog_identity(
            evaluation_set,
            domain_pack,
        )
        if (
            self._provider_descriptor.provider is ProviderId.OPENAI
            and self._evaluation_environment is None
        ):
            raise EvaluationRunnerError(
                "evaluation_environment_missing",
                "OpenAI evaluation requires verified environment evidence.",
            )
        self._verify_prerequisites(cases)
        query_service = self._query_service_factory(domain_pack)
        run_id = self._create_run(
            evaluation_set,
            digest,
            cases,
            selected_filters,
            suite_selection,
            catalog_identity,
            self._environment_identity(),
        )

        completed: list[_CompletedCase] = []
        fatal_error: EvaluationRunnerError | None = None
        for case in cases:
            started_at = perf_counter()
            provenance: EvaluationComparisonProvenance | None = None
            try:
                execution, expected_rows, provenance = self._execute_case(
                    case, domain_pack, query_service
                )
                score = score_evaluation_case(
                    case,
                    actual_outcome=execution.actual_outcome,
                    execution_succeeded=execution.execution_succeeded,
                    actual_referenced_tables=execution.actual_referenced_tables,
                    expected_rows=expected_rows,
                    actual_rows=execution.actual_rows,
                    provenance=provenance,
                )
                if execution.provider_failure_fatal:
                    fatal_error = EvaluationRunnerError(
                        execution.error_code or "provider_unavailable",
                        "The selected evaluation provider is unavailable.",
                        run_id=run_id,
                    )
            except EvaluationBaselineError as exc:
                execution = _internal_failure("internal_error")
                score = score_evaluation_case(
                    case,
                    actual_outcome=execution.actual_outcome,
                    execution_succeeded=False,
                )
                fatal_error = EvaluationRunnerError(
                    exc.code,
                    exc.safe_message,
                    run_id=run_id,
                )
            except EvaluationSetupError as exc:
                execution = _internal_failure("internal_error")
                score = score_evaluation_case(
                    case,
                    actual_outcome=execution.actual_outcome,
                    execution_succeeded=False,
                )
                fatal_error = EvaluationRunnerError(
                    exc.code,
                    exc.safe_message,
                    run_id=run_id,
                )
            except Exception:
                # Case failures are deliberately isolated. Diagnostics are bounded
                # classifications; exception text and tracebacks are never persisted.
                execution = _internal_failure("internal_error")
                score = score_evaluation_case(
                    case,
                    actual_outcome=execution.actual_outcome,
                    execution_succeeded=False,
                )

            semantic_score = score_evaluation_semantic_contract(
                case,
                (
                    execution.semantic_plan_observation
                    if execution.plan_validation_status == "passed"
                    else None
                ),
            )
            completed_case = _CompletedCase(
                case=case,
                execution=execution,
                score=score,
                semantic_score=semantic_score,
                duration_ms=(perf_counter() - started_at) * 1000,
                provenance=provenance,
            )
            completed.append(completed_case)
            self._persist_result(run_id, completed_case)
            if fatal_error is not None:
                break

        status = (
            RunStatus.FAILED.value
            if fatal_error is not None
            else RunStatus.SUCCEEDED.value
        )
        summary = _build_summary(
            run_id,
            evaluation_set,
            digest,
            cases,
            completed,
            self._provider_descriptor,
            suite_selection,
            catalog_identity,
            self._environment_identity(),
            status=status,
        )
        self._finalize_run(run_id, summary, fatal_error, selected_filters)
        if fatal_error is not None:
            raise fatal_error
        return summary

    def _verify_catalog_identity(
        self,
        evaluation_set: EvaluationSet,
        domain_pack: DomainPack,
    ) -> dict[str, str]:
        catalog = domain_pack.semantic_catalog
        expected_catalog_dataset_id = EVALUATION_CATALOG_DATASET_IDS.get(
            evaluation_set.dataset_id
        )
        if (
            catalog.domain_id != evaluation_set.domain_id
            or expected_catalog_dataset_id is None
            or catalog.dataset_id != expected_catalog_dataset_id
        ):
            raise EvaluationRunnerError(
                "evaluation_catalog_mismatch",
                "Evaluation semantic catalog identity is invalid.",
            )
        return semantic_catalog_identity(catalog)

    def _environment_identity(self) -> dict[str, str | int]:
        return (
            self._evaluation_environment.as_dict()
            if self._evaluation_environment is not None
            else {}
        )

    def _verify_prerequisites(self, cases: Sequence[EvaluationCase]) -> None:
        try:
            with self._session_factory() as db:
                if db.get_bind().dialect.name != "postgresql":
                    raise EvaluationRunnerError(
                        "postgres_required",
                        "Evaluation requires a configured PostgreSQL database.",
                    )
                for case in cases:
                    resolve_evaluation_identity(db, case)
                table_names = sorted({table for case in cases for table in case.expected_tables})
                resources = db.scalars(
                    select(DataResource).where(
                        DataResource.resource_type == "table",
                        DataResource.domain == "it_operations",
                        DataResource.table_name.in_(table_names),
                    )
                ).all()
                if {resource.table_name for resource in resources} != set(table_names):
                    raise EvaluationRunnerError(
                        "evaluation_resources_missing",
                        "Required seeded evaluation resources are missing.",
                    )
        except EvaluationRunnerError:
            raise
        except EvaluationSetupError as exc:
            raise EvaluationRunnerError(exc.code, exc.safe_message) from exc
        except SQLAlchemyError as exc:
            raise EvaluationRunnerError(
                "database_unavailable",
                "Evaluation database prerequisites could not be verified safely.",
            ) from exc

    def _create_run(
        self,
        evaluation_set: EvaluationSet,
        digest: str,
        cases: Sequence[EvaluationCase],
        filters: EvaluationFilters,
        suite_selection: EvaluationSuiteSelection,
        catalog_identity: dict[str, str],
        environment_identity: dict[str, str | int],
    ) -> UUID:
        run = EvaluationRun(
            requested_by_user_id=None,
            name=f"{evaluation_set.dataset_id}:{self._provider_descriptor.provider.value}",
            run_type="manual_evaluation",
            status=RunStatus.RUNNING.value,
            started_at=datetime.now(UTC),
            summary={
                "provider": self._provider_descriptor.provider.value,
                "model_label": self._provider_descriptor.model_label,
                "dataset_id": evaluation_set.dataset_id,
                "dataset_version": evaluation_set.version,
                "dataset_digest": digest,
                "selected_count": len(cases),
                "evaluation_suite": suite_selection.as_safe_dict(),
                "filters": filters.as_safe_dict(),
                "semantic_catalog": catalog_identity,
                "evaluation_environment": environment_identity,
            },
        )
        try:
            with self._session_factory() as db:
                db.add(run)
                db.commit()
                db.refresh(run)
                return run.id
        except SQLAlchemyError as exc:
            raise EvaluationRunnerError(
                "evaluation_persistence_failed",
                "Evaluation run could not be persisted safely.",
            ) from exc

    def _execute_case(
        self,
        case: EvaluationCase,
        domain_pack: DomainPack,
        query_service: QueryEngineService,
    ) -> tuple[
        _CaseExecution,
        tuple[Mapping[str, Any], ...],
        EvaluationComparisonProvenance | None,
    ]:
        with self._session_factory() as db:
            identity = resolve_evaluation_identity(db, case)
            execution = self._execute_actual(
                db, identity, case, domain_pack, query_service
            )
            provenance = _build_case_provenance(db, case, execution)
            expected_rows: tuple[Mapping[str, Any], ...] = ()
            if (
                case.expected_outcome is ExpectedOutcome.SUCCESS
                and not execution.provider_failure_fatal
            ):
                baseline = execute_evaluation_baseline(
                    db,
                    identity.access_context,
                    case,
                    domain_pack,
                )
                expected_rows = baseline.rows
            return execution, expected_rows, provenance

    def _execute_actual(
        self,
        db: Session,
        identity: EvaluationIdentity,
        case: EvaluationCase,
        domain_pack: DomainPack,
        query_service: QueryEngineService,
    ) -> _CaseExecution:
        authorization = authorize_query_request(
            identity.access_context,
            domain_pack,
            template_id=case.template_id,
        )
        if not authorization.allowed:
            return _denied_execution(())

        denied_tables = _denied_case_resources(db, identity, case)
        if denied_tables is not None:
            return _denied_execution(denied_tables)

        result = query_service.run(
            db,
            identity.user,
            QueryEngineRequest(
                question=case.question,
                template_id=case.template_id,
            ),
        )
        if case.template_id is None and not self._result_provider_matches_run(result):
            return _provider_identity_failure()
        return _classify_query_result(result)

    def _result_provider_matches_run(
        self,
        result: QueryEngineServiceResult,
    ) -> bool:
        provider = result.metadata.get("provider")
        model_label = result.metadata.get("model")
        if provider is None and model_label is None:
            return self._provider_descriptor.provider is ProviderId.MOCK
        return (
            provider == self._provider_descriptor.provider.value
            and model_label == self._provider_descriptor.model_label
        )

    def _persist_result(self, run_id: UUID, completed: _CompletedCase) -> None:
        score_metrics = completed.score.as_safe_metrics()
        expected_count = completed.score.expected_row_count
        actual_count = completed.score.actual_row_count
        metrics: dict[str, Any] = {
            **score_metrics,
            "difficulty": completed.case.difficulty.value,
            "category": completed.case.category,
            "case_type": completed.case.case_type.value,
            "security_sensitive": completed.case.security_sensitive,
            "duration_ms": round(completed.duration_ms, 3),
            "missing_row_count": max(0, expected_count - actual_count),
            "extra_row_count": max(0, actual_count - expected_count),
            "query_invoked": completed.execution.query_invoked,
            "query_execution_attempted": (
                completed.execution.query_execution_attempted
            ),
        }
        failure_stage = completed.execution.failure_stage
        if (
            failure_stage is None
            and completed.execution.execution_succeeded
            and not completed.score.passed
        ):
            failure_stage = "result_comparison"
        if failure_stage in SAFE_PIPELINE_STAGES:
            metrics["failure_stage"] = failure_stage
        if completed.execution.stage_reason_code is not None:
            metrics["stage_reason_code"] = completed.execution.stage_reason_code
        if completed.execution.provider_measurement is not None:
            metrics["provider_measurement"] = dict(
                completed.execution.provider_measurement
            )
        planner_metrics = _planner_case_metrics(completed)
        if planner_metrics is not None:
            metrics["planner"] = planner_metrics
        if completed.provenance is not None:
            metrics["result_provenance"] = completed.provenance.as_safe_dict()
        result = EvaluationResult(
            evaluation_run_id=run_id,
            query_run_id=completed.execution.query_run_id,
            case_name=completed.case.id,
            status="succeeded" if completed.score.passed else "failed",
            score=completed.score.score,
            expected_output={
                "outcome": completed.case.expected_outcome.value,
                "referenced_tables": list(completed.case.expected_tables),
            },
            actual_output={
                "outcome": completed.execution.actual_outcome.value,
                "referenced_tables": list(
                    completed.execution.actual_referenced_tables
                ),
                "execution_succeeded": completed.execution.execution_succeeded,
                "error_code": completed.execution.error_code,
            },
            metrics=metrics,
            error_message=None,
        )
        try:
            with self._session_factory() as db:
                db.add(result)
                db.commit()
        except SQLAlchemyError as exc:
            self._best_effort_fail_run(run_id, "evaluation_persistence_failed")
            raise EvaluationRunnerError(
                "evaluation_persistence_failed",
                "Evaluation result could not be persisted safely.",
                run_id=run_id,
            ) from exc

    def _finalize_run(
        self,
        run_id: UUID,
        summary: EvaluationRunSummary,
        fatal_error: EvaluationRunnerError | None,
        filters: EvaluationFilters,
    ) -> None:
        try:
            with self._session_factory() as db:
                run = db.get(EvaluationRun, run_id)
                if run is None:
                    raise EvaluationRunnerError(
                        "evaluation_run_missing",
                        "Evaluation run could not be finalized safely.",
                        run_id=run_id,
                    )
                run.status = summary.status
                run.completed_at = datetime.now(UTC)
                run.summary = _summary_for_persistence(
                    summary,
                    fatal_error,
                    filters,
                )
                db.commit()
        except EvaluationRunnerError:
            raise
        except SQLAlchemyError as exc:
            raise EvaluationRunnerError(
                "evaluation_persistence_failed",
                "Evaluation run could not be finalized safely.",
                run_id=run_id,
            ) from exc

    def _best_effort_fail_run(self, run_id: UUID, failure_code: str) -> None:
        try:
            with self._session_factory() as db:
                run = db.get(EvaluationRun, run_id)
                if run is None:
                    return
                run.status = RunStatus.FAILED.value
                run.completed_at = datetime.now(UTC)
                prior = dict(run.summary or {})
                run.summary = {**prior, "failure_code": failure_code}
                db.commit()
        except SQLAlchemyError:
            return


def _denied_case_resources(
    db: Session,
    identity: EvaluationIdentity,
    case: EvaluationCase,
) -> tuple[str, ...] | None:
    if case.case_type is not CaseType.AUTHORIZATION or not case.expected_tables:
        return None
    resources = db.scalars(
        select(DataResource)
        .where(
            DataResource.resource_type == "table",
            DataResource.domain == "it_operations",
            DataResource.table_name.in_(case.expected_tables),
        )
        .order_by(DataResource.table_name)
    ).all()
    if len(resources) != len(case.expected_tables):
        raise EvaluationSetupError(
            "evaluation_resources_missing",
            "Required seeded evaluation resources are missing.",
        )
    target = identity.target_scope
    runtime_context = (
        {"scope_type": target.scope_type, "scope_key": target.scope_key}
        if target is not None
        else {}
    )
    decisions = [
        authorize_resource_access(
            identity.access_context,
            "query:scoped_data",
            resource,
            runtime_context,
        )
        for resource in resources
    ]
    if any(not decision.allowed for decision in decisions):
        return tuple(sorted(resource.table_name for resource in resources))
    return None


def _build_case_provenance(
    db: Session,
    case: EvaluationCase,
    execution: _CaseExecution,
) -> EvaluationComparisonProvenance | None:
    expected = _safe_query_provenance(
        case.baseline_sql,
        ProvenanceAuthorizationEvidence.FROZEN_BASELINE_VALIDATED,
    )
    actual = None
    if execution.query_run_id is not None:
        query_run = db.get(QueryRun, execution.query_run_id)
        if query_run is not None and isinstance(query_run.executed_sql, str):
            validation = (
                query_run.query_metadata.get("validation")
                if isinstance(query_run.query_metadata, dict)
                else None
            )
            evidence = (
                ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED
                if (
                    execution.execution_succeeded
                    and isinstance(validation, dict)
                    and validation.get("valid") is True
                )
                else ProvenanceAuthorizationEvidence.UNVERIFIED
            )
            actual = _safe_query_provenance(query_run.executed_sql, evidence)
    if expected is None and actual is None:
        return None
    return EvaluationComparisonProvenance(expected=expected, actual=actual)


def _safe_query_provenance(
    sql: str | None,
    authorization_evidence: ProvenanceAuthorizationEvidence,
) -> EvaluationQueryProvenance | None:
    if sql is None:
        return None
    try:
        return extract_evaluation_query_provenance(
            sql,
            authorization_evidence=authorization_evidence,
        )
    except EvaluationProvenanceError:
        # Provenance is supplemental scoring evidence. Unsupported structure must
        # fail closed by omitting it, without changing established case outcomes.
        return None


def _classify_query_result(result: QueryEngineServiceResult) -> _CaseExecution:
    query_run_id = UUID(result.query_run_id) if result.query_run_id else None
    referenced_tables = tuple(
        sorted(str(item) for item in result.metadata.get("referenced_tables", []))
    )
    provider_measurement = sanitize_provider_measurement(
        result.metadata.get("provider_measurement")
    )
    provider_failure_code = result.metadata.get("provider_failure_code")
    planner = _planner_execution_fields(result.metadata)
    if provider_failure_code in {
        "provider_authentication_failed",
        "provider_timeout",
        "provider_unavailable",
        "provider_response_invalid",
    }:
        plan_validation = result.metadata.get("semantic_plan_validation")
        grounding = result.metadata.get("semantic_grounding")
        if isinstance(plan_validation, dict) and plan_validation.get("status") == "failed":
            failure_stage = "plan_validation"
            stage_reason_code = _safe_stage_reason(
                plan_validation.get("reason_code")
            )
        elif isinstance(grounding, dict) and grounding.get("status") == "failed":
            failure_stage = "grounding"
            stage_reason_code = _safe_stage_reason(grounding.get("reason_code"))
        else:
            failure_stage = "plan_generation"
            stage_reason_code = provider_failure_code
        return _CaseExecution(
            actual_outcome=ActualOutcome.INTERNAL_ERROR,
            execution_succeeded=False,
            query_invoked=True,
            query_execution_attempted=False,
            query_run_id=query_run_id,
            actual_rows=(),
            actual_referenced_tables=referenced_tables,
            error_code=provider_failure_code,
            failure_stage=failure_stage,
            stage_reason_code=stage_reason_code,
            provider_measurement=provider_measurement,
            provider_failure_fatal=(
                result.metadata.get("provider_failure_fatal") is True
            ),
            **planner,
        )
    if result.status == "succeeded":
        return _CaseExecution(
            actual_outcome=ActualOutcome.SUCCESS,
            execution_succeeded=True,
            query_invoked=True,
            query_execution_attempted=True,
            query_run_id=query_run_id,
            actual_rows=tuple(dict(row) for row in result.rows),
            actual_referenced_tables=referenced_tables,
            error_code=None,
            provider_measurement=provider_measurement,
            **planner,
        )
    if (
        result.error_code == "unsafe_sql_blocked"
        and not isinstance(result.metadata.get("execution"), dict)
        and result.row_count == 0
        and not result.rows
    ):
        return _CaseExecution(
            actual_outcome=ActualOutcome.UNSAFE_BLOCKED,
            execution_succeeded=False,
            query_invoked=True,
            query_execution_attempted=False,
            query_run_id=query_run_id,
            actual_rows=(),
            actual_referenced_tables=referenced_tables,
            error_code="unsafe_sql_blocked",
            failure_stage="sql_safety",
            stage_reason_code="unsafe_request",
            provider_measurement=provider_measurement,
            **planner,
        )
    if result.clarification_required:
        return _CaseExecution(
            actual_outcome=ActualOutcome.CLARIFICATION,
            execution_succeeded=False,
            query_invoked=True,
            query_execution_attempted=False,
            query_run_id=query_run_id,
            actual_rows=(),
            actual_referenced_tables=referenced_tables,
            error_code="clarification_required",
            failure_stage="grounding",
            stage_reason_code=_safe_stage_reason(
                result.metadata.get("unsupported_reason")
            ),
            provider_measurement=provider_measurement,
            **planner,
        )
    validation = result.metadata.get("validation")
    validation_code = validation.get("error_code") if isinstance(validation, dict) else None
    if validation_code in SAFE_UNSAFE_VALIDATION_CODES:
        return _CaseExecution(
            actual_outcome=ActualOutcome.UNSAFE_BLOCKED,
            execution_succeeded=False,
            query_invoked=True,
            query_execution_attempted=False,
            query_run_id=query_run_id,
            actual_rows=(),
            actual_referenced_tables=referenced_tables,
            error_code="unsafe_sql_blocked",
            failure_stage="sql_safety",
            stage_reason_code=validation_code,
            provider_measurement=provider_measurement,
            **planner,
        )
    conformance = result.metadata.get("semantic_conformance")
    if (
        result.error_code == "semantic_conformance_failed"
        and isinstance(conformance, dict)
        and conformance.get("status") == "failed"
        and not isinstance(result.metadata.get("execution"), dict)
    ):
        return _CaseExecution(
            actual_outcome=ActualOutcome.EXECUTION_FAILED,
            execution_succeeded=False,
            query_invoked=True,
            query_execution_attempted=False,
            query_run_id=query_run_id,
            actual_rows=(),
            actual_referenced_tables=referenced_tables,
            error_code="semantic_conformance_failed",
            failure_stage="semantic_conformance",
            stage_reason_code=_safe_stage_reason(conformance.get("reason_code")),
            provider_measurement=provider_measurement,
            **planner,
        )
    render = result.metadata.get("semantic_sql_render")
    failure_stage = (
        "sql_rendering"
        if (
            result.error_code == "semantic_sql_render_failed"
            and isinstance(render, dict)
            and render.get("status") == "failed"
        )
        else "execution"
        if isinstance(result.metadata.get("execution"), dict)
        else "sql_safety"
        if isinstance(validation, dict)
        else "plan_generation"
    )
    return _CaseExecution(
        actual_outcome=ActualOutcome.EXECUTION_FAILED,
        execution_succeeded=False,
        query_invoked=True,
        query_execution_attempted=isinstance(result.metadata.get("execution"), dict),
        query_run_id=query_run_id,
        actual_rows=(),
        actual_referenced_tables=referenced_tables,
        error_code=(
            result.error_code
            if result.error_code in SAFE_ACTUAL_ERROR_CODES
            else "execution_failed"
        ),
        failure_stage=failure_stage,
        stage_reason_code=(
            _safe_stage_reason(validation_code)
            if failure_stage == "sql_safety"
            else "execution_failed"
            if failure_stage == "execution"
            else _safe_stage_reason(render.get("reason_code"))
            if failure_stage == "sql_rendering" and isinstance(render, dict)
            else _safe_stage_reason(result.error_code)
        ),
        provider_measurement=provider_measurement,
        **planner,
    )


def _planner_execution_fields(metadata: Mapping[str, Any]) -> dict[str, Any]:
    validation = metadata.get("semantic_plan_validation")
    plan_validation_status = (
        validation.get("status")
        if isinstance(validation, Mapping)
        and validation.get("status") in {"passed", "failed"}
        else None
    )
    required_intent_status = (
        validation.get("required_intent_status")
        if isinstance(validation, Mapping)
        and validation.get("required_intent_status")
        in {"passed", "failed", "not_evaluated"}
        else None
    )
    renderer = metadata.get("semantic_sql_render")
    renderer_status = (
        renderer.get("status")
        if isinstance(renderer, Mapping)
        and renderer.get("status") in {"passed", "failed"}
        else None
    )
    conformance = metadata.get("semantic_conformance")
    conformance_status = (
        conformance.get("status")
        if isinstance(conformance, Mapping)
        and conformance.get("status") in {"passed", "failed"}
        else None
    )
    plan_observation = metadata.get("semantic_plan")
    return {
        "plan_validation_status": plan_validation_status,
        "required_intent_status": required_intent_status,
        "renderer_status": renderer_status,
        "conformance_status": conformance_status,
        "semantic_plan_observation": (
            plan_observation if isinstance(plan_observation, Mapping) else None
        ),
    }


def _denied_execution(referenced_tables: Sequence[str]) -> _CaseExecution:
    return _CaseExecution(
        actual_outcome=ActualOutcome.DENIED,
        execution_succeeded=False,
        query_invoked=False,
        query_execution_attempted=False,
        query_run_id=None,
        actual_rows=(),
        actual_referenced_tables=tuple(sorted(referenced_tables)),
        error_code="access_denied",
    )


def _internal_failure(error_code: str) -> _CaseExecution:
    safe_code = error_code if error_code in SAFE_ACTUAL_ERROR_CODES else "internal_error"
    return _CaseExecution(
        actual_outcome=ActualOutcome.INTERNAL_ERROR,
        execution_succeeded=False,
        query_invoked=False,
        query_execution_attempted=False,
        query_run_id=None,
        actual_rows=(),
        actual_referenced_tables=(),
        error_code=safe_code,
        failure_stage="setup",
        stage_reason_code=safe_code,
    )


def _provider_identity_failure() -> _CaseExecution:
    return _CaseExecution(
        actual_outcome=ActualOutcome.INTERNAL_ERROR,
        execution_succeeded=False,
        query_invoked=True,
        query_execution_attempted=False,
        query_run_id=None,
        actual_rows=(),
        actual_referenced_tables=(),
        error_code="provider_response_invalid",
        failure_stage="plan_generation",
        stage_reason_code="provider_response_invalid",
        provider_failure_fatal=True,
    )


def _safe_stage_reason(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if not value or len(value) > 128:
        return None
    if not all(character.islower() or character.isdigit() or character == "_" for character in value):
        return None
    return value


def _planner_case_metrics(completed: _CompletedCase) -> dict[str, Any] | None:
    if (
        completed.case.template_id is not None
        or completed.case.expected_outcome is not ExpectedOutcome.SUCCESS
    ):
        return None
    execution = completed.execution
    return {
        "plan_generated": execution.plan_validation_status in {"passed", "failed"},
        "plan_validation_status": execution.plan_validation_status or "not_reached",
        "required_intent_status": execution.required_intent_status or "not_reached",
        "renderer_status": execution.renderer_status or "not_reached",
        "conformance_status": execution.conformance_status or "not_reached",
        "semantic_contract": completed.semantic_score.as_safe_metrics(),
    }


def _aggregate_planner_metrics(
    completed: Sequence[_CompletedCase],
) -> dict[str, int | float | None]:
    eligible = [
        item
        for item in completed
        if item.case.template_id is None
        and item.case.expected_outcome is ExpectedOutcome.SUCCESS
    ]
    generated = [
        item
        for item in eligible
        if item.execution.plan_validation_status in {"passed", "failed"}
    ]
    validated = [
        item
        for item in generated
        if item.execution.plan_validation_status == "passed"
    ]
    required_evaluated = [
        item
        for item in generated
        if item.execution.required_intent_status in {"passed", "failed"}
    ]
    required_passed = [
        item
        for item in required_evaluated
        if item.execution.required_intent_status == "passed"
    ]
    semantic_evaluated = [item for item in eligible if item.semantic_score.evaluated]
    semantic_passed = [
        item for item in semantic_evaluated if item.semantic_score.passed is True
    ]
    return {
        "eligible_case_count": len(eligible),
        "generated_plan_count": len(generated),
        "validated_plan_count": len(validated),
        "semantic_plan_validation_pass_rate": (
            round(len(validated) / len(generated), 6) if generated else None
        ),
        "required_intent_evaluated_count": len(required_evaluated),
        "required_intent_passed_count": len(required_passed),
        "required_intent_adherence_rate": (
            round(len(required_passed) / len(required_evaluated), 6)
            if required_evaluated
            else None
        ),
        "renderer_defect_count": sum(
            item.execution.renderer_status == "failed" for item in validated
        ),
        "conformance_defect_count": sum(
            item.execution.conformance_status == "failed" for item in validated
        ),
        "semantic_contract_evaluated_count": len(semantic_evaluated),
        "semantic_contract_passed_count": len(semantic_passed),
        "semantic_contract_pass_rate": (
            round(len(semantic_passed) / len(semantic_evaluated), 6)
            if semantic_evaluated
            else None
        ),
    }


def _build_summary(
    run_id: UUID,
    evaluation_set: EvaluationSet,
    digest: str,
    selected: Sequence[EvaluationCase],
    completed: Sequence[_CompletedCase],
    descriptor: ProviderDescriptor,
    suite_selection: EvaluationSuiteSelection,
    catalog_identity: dict[str, str],
    environment_identity: dict[str, str | int],
    *,
    status: str,
) -> EvaluationRunSummary:
    completed_count = len(completed)
    passed_count = sum(item.score.passed for item in completed)
    overall_score = (
        sum(item.score.score for item in completed) / completed_count
        if completed_count
        else 0.0
    )
    outcome_match_count = sum(item.score.outcome_correct for item in completed)
    security = [
        item for item in completed if item.case.difficulty.value == "security"
    ]
    execution_attempts = [
        item for item in completed if item.execution.query_execution_attempted
    ]
    return EvaluationRunSummary(
        run_id=run_id,
        provider=descriptor.provider.value,
        model_label=descriptor.model_label,
        dataset_id=evaluation_set.dataset_id,
        dataset_version=evaluation_set.version,
        dataset_digest=digest,
        status=status,
        selected_count=len(selected),
        completed_count=completed_count,
        passed_count=passed_count,
        failed_count=completed_count - passed_count,
        overall_score=round(overall_score, 6),
        expected_behavior_match_rate=round(
            outcome_match_count / completed_count if completed_count else 0.0,
            6,
        ),
        security_pass_rate=(
            round(sum(item.score.passed for item in security) / len(security), 6)
            if security
            else None
        ),
        query_execution_succeeded_count=sum(
            item.execution.execution_succeeded for item in execution_attempts
        ),
        query_execution_failed_count=sum(
            not item.execution.execution_succeeded for item in execution_attempts
        ),
        by_difficulty=_group_metrics(completed, lambda item: item.case.difficulty.value),
        by_category=_group_metrics(completed, lambda item: item.case.category),
        by_case_type=_group_metrics(completed, lambda item: item.case.case_type.value),
        cases=tuple(
            EvaluationCaseSummary(
                case_id=item.case.id,
                difficulty=item.case.difficulty.value,
                category=item.case.category,
                case_type=item.case.case_type.value,
                expected_outcome=item.case.expected_outcome.value,
                actual_outcome=item.execution.actual_outcome.value,
                passed=item.score.passed,
                score=item.score.score,
                error_code=item.execution.error_code,
            )
            for item in completed
        ),
        provider_usage=_aggregate_provider_usage(completed),
        planner_metrics=_aggregate_planner_metrics(completed),
        semantic_catalog=dict(catalog_identity),
        evaluation_environment=dict(environment_identity),
        evaluation_suite=suite_selection.as_safe_dict(),
    )


def _group_metrics(
    completed: Sequence[_CompletedCase],
    key: Callable[[_CompletedCase], str],
) -> dict[str, dict[str, int | float]]:
    groups: dict[str, list[_CompletedCase]] = defaultdict(list)
    for item in completed:
        groups[key(item)].append(item)
    return {
        name: {
            "completed": len(items),
            "passed": sum(item.score.passed for item in items),
            "failed": sum(not item.score.passed for item in items),
            "score": round(sum(item.score.score for item in items) / len(items), 6),
        }
        for name, items in sorted(groups.items())
    }


def _aggregate_provider_usage(
    completed: Sequence[_CompletedCase],
) -> dict[str, int | float]:
    measurements = [
        item.execution.provider_measurement
        for item in completed
        if item.execution.provider_measurement is not None
    ]
    totals: dict[str, int | float] = {
        "call_count": len(measurements),
        "attempt_count": sum(
            int(item.get("attempt_count", 0)) for item in measurements
        ),
        "duration_ms": round(
            min(
                sum(float(item.get("duration_ms", 0.0)) for item in measurements),
                86_400_000.0,
            ),
            3,
        ),
    }
    for key in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
    ):
        totals[key] = min(
            sum(int(item.get(key, 0)) for item in measurements),
            1_000_000_000,
        )
    return totals


def _summary_for_persistence(
    summary: EvaluationRunSummary,
    fatal_error: EvaluationRunnerError | None,
    filters: EvaluationFilters,
) -> dict[str, Any]:
    return {
        "provider": summary.provider,
        "model_label": summary.model_label,
        "dataset_id": summary.dataset_id,
        "dataset_version": summary.dataset_version,
        "dataset_digest": summary.dataset_digest,
        "filters": filters.as_safe_dict(),
        "evaluation_suite": summary.evaluation_suite,
        "selected_count": summary.selected_count,
        "completed_count": summary.completed_count,
        "passed_count": summary.passed_count,
        "failed_count": summary.failed_count,
        "overall_score": summary.overall_score,
        "expected_behavior_match_rate": summary.expected_behavior_match_rate,
        "security_pass_rate": summary.security_pass_rate,
        "query_execution_succeeded_count": summary.query_execution_succeeded_count,
        "query_execution_failed_count": summary.query_execution_failed_count,
        "by_difficulty": summary.by_difficulty,
        "by_category": summary.by_category,
        "by_case_type": summary.by_case_type,
        "provider_usage": summary.provider_usage,
        "planner_metrics": summary.planner_metrics,
        "semantic_catalog": summary.semantic_catalog,
        "evaluation_environment": summary.evaluation_environment,
        "failure_code": fatal_error.code if fatal_error else None,
    }
