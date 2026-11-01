from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.access_policy import APPROVED_TEMPLATE_QUERY_ACTION, authorize_resource_access
from app.evaluation.baseline import (
    EvaluationBaselineError,
    execute_evaluation_baseline,
)
from app.evaluation.context import (
    EvaluationIdentity,
    EvaluationSetupError,
    resolve_evaluation_identity,
)
from app.evaluation.environment import (
    EvaluationEnvironmentIdentity,
    validate_persisted_environment_identity,
)
from app.evaluation.contracts import (
    ActualOutcome,
    CaseType,
    ComparisonState,
    DeliveryCompleteness,
    EvaluationComparisonProvenance,
    EvaluationCase,
    EvaluationQueryProvenance,
    EvaluationSet,
    ExpectedOutcome,
    ProvenanceAuthorizationEvidence,
)
from app.evaluation.evidence import (
    EVIDENCE_PAYLOAD_LIMIT_BYTES,
    EVIDENCE_ROW_LIMIT,
    EVIDENCE_STATEMENT_TIMEOUT_MS,
    EVIDENCE_TOTAL_TIMEOUT_MS,
    EvaluationComparisonEvidence,
    EvaluationEvidenceSide,
    auxiliary_evidence_side,
    build_auxiliary_validation,
    comparison_payload_size,
    comparison_state_counts,
    distinct_delivery_payload_rows,
    observed_evidence_side,
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
from app.query_engine.llm_provider import (
    LLMProvider,
    aggregate_provider_measurements,
    sanitize_provider_measurement,
)
from app.query_engine.mock_llm_provider import MockLLMProvider
from app.query_engine.provider_config import ProviderDescriptor, ProviderId
from app.query_engine.request_authorization import authorize_query_request
from app.query_engine.result_formatter import QueryEngineServiceResult
from app.query_engine.schema_context import SchemaContextOptions, build_schema_context
from app.query_engine.semantic_catalog import semantic_catalog_identity
from app.query_engine.service import (
    QueryEngineRequest,
    QueryEngineService,
    QueryRunPersistenceError,
)
from app.query_engine.sql_executor import (
    SQLExecutionOptions,
    SQLExecutionResult,
    execute_validated_sql,
    query_runtime_transaction,
)
from app.query_engine.sql_validator import SQLValidationResult


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
        "execution_context",
        "persistence",
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
        stage: str = "setup",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.run_id = run_id
        self.stage = stage


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
    comparison_state: str
    delivery_completeness: str


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
    unestablished_count: int
    comparison_state_counts: dict[str, int]
    overall_score: float
    expected_behavior_match_rate: float
    security_pass_rate: float | None
    query_execution_succeeded_count: int
    query_execution_failed_count: int
    by_difficulty: dict[str, dict[str, int | float]]
    by_category: dict[str, dict[str, int | float]]
    by_case_type: dict[str, dict[str, int | float]]
    cases: tuple[EvaluationCaseSummary, ...]
    provider_usage: dict[str, int | float | None] = field(default_factory=dict)
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
    validation: SQLValidationResult | None = None
    execution_result: SQLExecutionResult | None = None


@dataclass(frozen=True)
class _CompletedCase:
    case: EvaluationCase
    execution: _CaseExecution
    score: EvaluationScore
    semantic_score: EvaluationSemanticScore
    duration_ms: float
    provenance: EvaluationComparisonProvenance | None = None
    comparison_evidence: EvaluationComparisonEvidence | None = None
    evaluation_failure_stage: str | None = None


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
        if self._provider_descriptor.provider is ProviderId.OPENAI and (
            self._evaluation_environment is None
            or validate_persisted_environment_identity(
                self._evaluation_environment.as_dict()
            ) is None
            or self._evaluation_environment.provider_runtime_digest
            != self._provider_descriptor.runtime_digest
        ):
            raise EvaluationRunnerError(
                "evaluation_provider_runtime_mismatch",
                "Evaluation provider runtime does not match verified environment evidence.",
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
            execution: _CaseExecution | None = None
            expected_rows: tuple[Mapping[str, Any], ...] = ()
            provenance: EvaluationComparisonProvenance | None = None
            comparison_evidence: EvaluationComparisonEvidence | None = None
            evaluation_failure_stage: str | None = None
            try:
                (
                    execution,
                    expected_rows,
                    provenance,
                    comparison_evidence,
                    post_execution_error,
                ) = self._execute_case(case, domain_pack, query_service)
            except (EvaluationBaselineError, EvaluationSetupError) as exc:
                execution = _internal_failure("internal_error")
                semantic_score = score_evaluation_semantic_contract(case, None)
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
                # Acquisition failed before it returned an immutable observation.
                execution = _internal_failure("internal_error")
                semantic_score = score_evaluation_semantic_contract(case, None)
                score = _post_execution_failure_score(case, execution, ())
            else:
                try:
                    semantic_score = score_evaluation_semantic_contract(
                        case,
                        (
                            execution.semantic_plan_observation
                            if execution.plan_validation_status == "passed"
                            else None
                        ),
                    )
                    score = score_evaluation_case(
                        case,
                        actual_outcome=execution.actual_outcome,
                        execution_succeeded=execution.execution_succeeded,
                        actual_referenced_tables=execution.actual_referenced_tables,
                        expected_rows=expected_rows,
                        actual_rows=execution.actual_rows,
                        provenance=provenance,
                        comparison_evidence=comparison_evidence,
                        semantic_contract_passed=semantic_score.passed,
                    )
                except Exception:
                    # Judgment failures cannot replace the observed production result.
                    if execution.execution_succeeded:
                        comparison_evidence = self._comparison_context_evidence(
                            case, execution
                        )
                    semantic_score = score_evaluation_semantic_contract(case, None)
                    score = _post_execution_failure_score(
                        case, execution, expected_rows
                    )
                    evaluation_failure_stage = "result_comparison"
                if post_execution_error is not None:
                    evaluation_failure_stage = post_execution_error.stage
                    fatal_error = EvaluationRunnerError(
                        post_execution_error.code,
                        post_execution_error.safe_message,
                        run_id=run_id,
                    )
                elif execution.provider_failure_fatal:
                    fatal_error = EvaluationRunnerError(
                        execution.error_code or "provider_unavailable",
                        "The selected evaluation provider is unavailable.",
                        run_id=run_id,
                    )
            completed_case = _CompletedCase(
                case=case,
                execution=execution,
                score=score,
                semantic_score=semantic_score,
                duration_ms=(perf_counter() - started_at) * 1000,
                provenance=provenance,
                comparison_evidence=comparison_evidence,
                evaluation_failure_stage=evaluation_failure_stage,
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
        EvaluationComparisonEvidence | None,
        EvaluationRunnerError | None,
    ]:
        execution: _CaseExecution | None = None
        provenance: EvaluationComparisonProvenance | None = None
        try:
            with self._session_factory() as db:
                identity = resolve_evaluation_identity(db, case)
                with ExitStack() as stack:
                    runtime_connection: Connection | None = None

                    def execution_db_factory(
                        access_context,
                    ) -> Connection:
                        nonlocal runtime_connection
                        if runtime_connection is None:
                            runtime_connection = stack.enter_context(
                                query_runtime_transaction(
                                    db.get_bind(),
                                    access_context,
                                    isolation_level="repeatable_read",
                                    timezone_name="UTC",
                                )
                            )
                        return runtime_connection

                    execution, actual_error = self._execute_actual(
                        db,
                        identity,
                        case,
                        domain_pack,
                        query_service,
                        execution_db_factory=execution_db_factory,
                    )
                    try:
                        provenance = _build_case_provenance(db, case, execution)
                    except Exception:
                        provenance = None
                    if actual_error is not None:
                        return (
                            execution,
                            (),
                            provenance,
                            self._comparison_context_evidence(case, execution),
                            actual_error,
                        )
                    if (
                        case.expected_outcome is not ExpectedOutcome.SUCCESS
                        or not execution.execution_succeeded
                    ):
                        return execution, (), provenance, None, None
                    try:
                        baseline = execute_evaluation_baseline(
                            db,
                            identity.access_context,
                            case,
                            domain_pack,
                            executor=(
                                (
                                    lambda _db, access, validation, *, options=None: execute_validated_sql(
                                        runtime_connection,
                                        access,
                                        validation,
                                        options=options,
                                    )
                                )
                                if runtime_connection is not None
                                else execute_validated_sql
                            ),
                        )
                    except EvaluationBaselineError as exc:
                        if case.semantic_contract is None:
                            return (
                                execution,
                                (),
                                provenance,
                                None,
                                EvaluationRunnerError(exc.code, exc.safe_message),
                            )
                        return (
                            execution,
                            (),
                            provenance,
                            self._baseline_limitation_evidence(case, execution, exc),
                            None,
                        )
                    except Exception:
                        return (
                            execution,
                            (),
                            provenance,
                            self._comparison_context_evidence(case, execution),
                            None,
                        )
                    try:
                        evidence = self._comparison_evidence(
                            db,
                            identity,
                            case,
                            domain_pack,
                            execution,
                            baseline,
                            runtime_connection,
                        )
                    except Exception:
                        evidence = self._comparison_context_evidence(
                            case, execution, baseline
                        )
                    return execution, baseline.rows, provenance, evidence, None
        except Exception:
            if execution is None:
                raise
            return (
                execution,
                (),
                provenance,
                self._comparison_context_evidence(case, execution),
                EvaluationRunnerError(
                    "evaluation_execution_context_failed",
                    "The evaluation execution context could not close safely.",
                    stage="execution_context",
                ),
            )

    @staticmethod
    def _baseline_limitation_evidence(
        case: EvaluationCase,
        execution: _CaseExecution,
        error: EvaluationBaselineError,
    ) -> EvaluationComparisonEvidence | None:
        if (
            case.semantic_contract is None
            or execution.validation is None
            or execution.execution_result is None
        ):
            return None
        actual = observed_evidence_side(
            execution.actual_rows,
            execution.validation,
            execution.execution_result,
            case.semantic_contract.answer_bound,
        )
        baseline_execution = error.execution
        limitation_reason = (
            "evidence_validation_failed"
            if error.code
            in {
                "baseline_not_defined",
                "baseline_tables_mismatch",
                "baseline_validation_failed",
            }
            else "evidence_timeout"
            if baseline_execution is not None
            and baseline_execution.execution_metadata.get("timeout") is True
            else "comparison_context_unestablished"
            if error.code
            in {
                "baseline_access_denied",
                "baseline_missing_referenced_tables",
                "baseline_postgres_required",
                "baseline_resource_not_found",
                "baseline_resource_not_queryable",
            }
            else "evidence_execution_failed"
        )
        return EvaluationComparisonEvidence(
            expected=EvaluationEvidenceSide(
                rows=(
                    tuple(dict(row) for row in baseline_execution.rows)
                    if baseline_execution is not None
                    else ()
                ),
                complete=False,
                comparison_eligible=False,
                exhausted=False,
                limitation_reason=limitation_reason,
                delivery_completeness=DeliveryCompleteness.UNKNOWN,
                observed_execution_count=1 if baseline_execution is not None else 0,
                observed_duration_ms=(
                    baseline_execution.duration_ms
                    if baseline_execution is not None
                    else 0.0
                ),
            ),
            actual=actual,
            actual_delivery_completeness=actual.delivery_completeness,
            actual_delivery_row_limit=(
                execution.validation.effective_limit
                if actual.delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED
                else None
            ),
            context_compatible=(
                limitation_reason != "comparison_context_unestablished"
            ),
        )

    @staticmethod
    def _comparison_context_evidence(
        case: EvaluationCase,
        execution: _CaseExecution,
        baseline=None,
    ) -> EvaluationComparisonEvidence | None:
        if (
            case.semantic_contract is None
            or execution.validation is None
            or execution.execution_result is None
        ):
            return None
        answer_bound = case.semantic_contract.answer_bound
        actual = observed_evidence_side(
            execution.actual_rows,
            execution.validation,
            execution.execution_result,
            answer_bound,
        )
        expected = (
            observed_evidence_side(
                baseline.rows,
                baseline.validation,
                baseline.execution,
                answer_bound,
            )
            if baseline is not None
            else EvaluationEvidenceSide(
                rows=(),
                complete=False,
                comparison_eligible=False,
                exhausted=False,
                limitation_reason="comparison_context_unestablished",
                delivery_completeness=DeliveryCompleteness.UNKNOWN,
                observed_execution_count=0,
            )
        )
        return EvaluationComparisonEvidence(
            expected=expected,
            actual=actual,
            actual_delivery_completeness=actual.delivery_completeness,
            actual_delivery_row_limit=(
                execution.validation.effective_limit
                if actual.delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED
                else None
            ),
            context_compatible=False,
        )

    def _comparison_evidence(
        self,
        db: Session,
        identity: EvaluationIdentity,
        case: EvaluationCase,
        domain_pack: DomainPack,
        execution: _CaseExecution,
        baseline,
        runtime_connection: Connection | None,
    ) -> EvaluationComparisonEvidence | None:
        if (
            case.semantic_contract is None
            or runtime_connection is None
            or execution.validation is None
            or execution.execution_result is None
        ):
            return None
        answer_bound = case.semantic_contract.answer_bound
        actual_observed = observed_evidence_side(
            execution.actual_rows,
            execution.validation,
            execution.execution_result,
            answer_bound,
        )
        expected_observed = observed_evidence_side(
            baseline.rows,
            baseline.validation,
            baseline.execution,
            answer_bound,
        )
        if actual_observed.complete and expected_observed.complete:
            return EvaluationComparisonEvidence(
                expected=expected_observed,
                actual=actual_observed,
                actual_delivery_completeness=actual_observed.delivery_completeness,
            )
        query_action = (
            APPROVED_TEMPLATE_QUERY_ACTION
            if case.template_id is not None
            else "query:scoped_data"
        )
        schema_context = build_schema_context(
            db,
            identity.access_context,
            domain_pack=domain_pack,
            options=SchemaContextOptions(
                template_id=case.template_id,
                query_action=query_action,
            ),
        )
        auxiliary_started_at = perf_counter()
        total_deadline = auxiliary_started_at + EVIDENCE_TOTAL_TIMEOUT_MS / 1000
        transaction_usable = True

        def acquire(
            observed: EvaluationEvidenceSide,
            validation: SQLValidationResult,
            *,
            payload_budget: int,
        ) -> EvaluationEvidenceSide:
            nonlocal transaction_usable
            if observed.complete:
                return observed
            elapsed_ms = (perf_counter() - auxiliary_started_at) * 1000
            remaining_timeout_ms = EVIDENCE_TOTAL_TIMEOUT_MS - elapsed_ms
            if remaining_timeout_ms <= 0:
                return replace(
                    observed,
                    limitation_reason="evidence_timeout",
                )
            if payload_budget <= 2:
                return replace(
                    observed,
                    limitation_reason="evidence_payload_exceeded",
                )
            if not transaction_usable:
                return replace(
                    observed,
                    limitation_reason="evidence_timeout",
                )
            auxiliary = build_auxiliary_validation(validation, schema_context)
            if auxiliary is None:
                return EvaluationEvidenceSide(
                    rows=observed.rows,
                    complete=False,
                    comparison_eligible=observed.comparison_eligible,
                    exhausted=observed.exhausted,
                    limitation_reason="unsupported_query_shape",
                    delivery_completeness=observed.delivery_completeness,
                    observed_execution_count=observed.observed_execution_count,
                    observed_duration_ms=observed.observed_duration_ms,
                )
            remaining_timeout_ms = (total_deadline - perf_counter()) * 1000
            if remaining_timeout_ms <= 0:
                return replace(
                    observed,
                    limitation_reason="evidence_timeout",
                )
            result = execute_validated_sql(
                runtime_connection,
                identity.access_context,
                auxiliary,
                options=SQLExecutionOptions(
                    statement_timeout_ms=max(
                        1,
                        min(EVIDENCE_STATEMENT_TIMEOUT_MS, int(remaining_timeout_ms)),
                    ),
                    row_limit=EVIDENCE_ROW_LIMIT,
                    query_action=query_action,
                    max_payload_bytes=payload_budget,
                    acquisition_deadline=min(
                        total_deadline,
                        perf_counter() + EVIDENCE_STATEMENT_TIMEOUT_MS / 1000,
                    ),
                ),
            )
            side = auxiliary_evidence_side(auxiliary, result, answer_bound)
            if result.status != "succeeded":
                transaction_usable = False
            if (
                result.duration_ms > EVIDENCE_STATEMENT_TIMEOUT_MS
                or (perf_counter() - auxiliary_started_at) * 1000
                > EVIDENCE_TOTAL_TIMEOUT_MS
            ):
                side = replace(
                    side,
                    complete=False,
                    exhausted=False,
                    limitation_reason="evidence_timeout",
                    delivery_completeness=DeliveryCompleteness.UNKNOWN,
                )
            return replace(
                side,
                observed_execution_count=observed.observed_execution_count,
                observed_duration_ms=observed.observed_duration_ms,
            )

        actual_base_payload = comparison_payload_size(
            expected_observed.rows if expected_observed.complete else (),
            (),
            delivered=(
                actual_observed.rows if not actual_observed.complete else ()
            ),
        )
        actual_evidence = acquire(
            actual_observed,
            execution.validation,
            payload_budget=max(
                0,
                EVIDENCE_PAYLOAD_LIMIT_BYTES - actual_base_payload + 2,
            ),
        )
        expected_base_payload = comparison_payload_size(
            (),
            actual_evidence.rows,
            delivered=distinct_delivery_payload_rows(
                actual_evidence, actual_observed.rows
            ),
        )
        expected_evidence = acquire(
            expected_observed,
            baseline.validation,
            payload_budget=max(
                0,
                EVIDENCE_PAYLOAD_LIMIT_BYTES - expected_base_payload + 2,
            ),
        )
        return EvaluationComparisonEvidence(
            expected=expected_evidence,
            actual=actual_evidence,
            actual_delivery_completeness=actual_observed.delivery_completeness,
            actual_delivery_row_limit=(
                execution.validation.effective_limit
                if actual_observed.delivery_completeness
                is DeliveryCompleteness.SAFETY_LIMITED
                else None
            ),
        )

    def _execute_actual(
        self,
        db: Session,
        identity: EvaluationIdentity,
        case: EvaluationCase,
        domain_pack: DomainPack,
        query_service: QueryEngineService,
        *,
        execution_db_factory,
    ) -> tuple[_CaseExecution, EvaluationRunnerError | None]:
        authorization = authorize_query_request(
            identity.access_context,
            domain_pack,
            template_id=case.template_id,
        )
        if not authorization.allowed:
            return _denied_execution(()), None

        denied_tables = _denied_case_resources(db, identity, case)
        if denied_tables is not None:
            return _denied_execution(denied_tables), None

        request = QueryEngineRequest(
            question=case.question,
            template_id=case.template_id,
        )
        try:
            if isinstance(query_service, QueryEngineService):
                result = query_service.run(
                    db,
                    identity.user,
                    request,
                    execution_db_factory=execution_db_factory,
                )
            else:
                result = query_service.run(db, identity.user, request)
        except QueryRunPersistenceError as exc:
            return (
                _classify_query_result(exc.observation),
                EvaluationRunnerError(
                    "query_run_persistence_failed",
                    "The production observation could not be persisted.",
                    stage="persistence",
                ),
            )
        if case.template_id is None and not self._result_provider_matches_run(result):
            return _provider_identity_failure(), None
        return _classify_query_result(result), None

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
        failure_stage = (
            completed.evaluation_failure_stage or completed.execution.failure_stage
        )
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
        if completed.comparison_evidence is not None:
            metrics["comparison_evidence"] = (
                completed.comparison_evidence.as_safe_dict()
            )
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


def _post_execution_failure_score(
    case: EvaluationCase,
    execution: _CaseExecution,
    expected_rows: Sequence[Mapping[str, Any]],
) -> EvaluationScore:
    outcome_correct = execution.actual_outcome.value == case.expected_outcome.value
    execution_correct = execution.execution_succeeded == (
        case.expected_outcome is ExpectedOutcome.SUCCESS
    )
    tables_correct = set(execution.actual_referenced_tables) == set(
        case.expected_tables
    )
    failures = []
    if not outcome_correct:
        failures.append("unexpected_outcome")
    if not execution_correct:
        failures.append("execution_state_mismatch")
    if not tables_correct:
        failures.append("referenced_tables_mismatch")
    expects_result = case.expected_outcome is ExpectedOutcome.SUCCESS
    comparison_state = (
        ComparisonState.UNESTABLISHED
        if expects_result and execution.execution_succeeded
        else ComparisonState.NOT_REACHED
        if expects_result
        else ComparisonState.NOT_APPLICABLE
    )
    delivery = DeliveryCompleteness.NOT_APPLICABLE
    if expects_result:
        try:
            delivery = DeliveryCompleteness(
                execution.execution_result.execution_metadata.get(
                    "delivery_completeness"
                )
                if execution.execution_result is not None
                else None
            )
        except (TypeError, ValueError):
            delivery = DeliveryCompleteness.UNKNOWN
    components = [outcome_correct, execution_correct, tables_correct]
    if expects_result:
        components.append(False)
    return EvaluationScore(
        score=sum(components) / len(components),
        passed=False,
        outcome_correct=outcome_correct,
        execution_correct=execution_correct,
        tables_correct=tables_correct,
        result_correct=None,
        comparison_state=comparison_state,
        delivery_completeness=delivery,
        comparison_limitation_reason=(
            "comparison_context_unestablished"
            if comparison_state is ComparisonState.UNESTABLISHED
            else None
        ),
        expected_row_count=len(expected_rows),
        actual_row_count=len(execution.actual_rows),
        failure_reasons=tuple(failures),
    )


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
    if (
        execution.execution_succeeded
        and execution.validation is not None
        and execution.validation.valid
        and execution.validation.sanitized_sql is not None
    ):
        actual = _safe_query_provenance(
            execution.validation.sanitized_sql,
            ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED,
        )
    elif execution.query_run_id is not None:
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
    validation = result.validation_result
    execution_result = result.execution_result
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
            validation=validation,
            execution_result=execution_result,
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
            validation=validation,
            execution_result=execution_result,
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
            validation=validation,
            execution_result=execution_result,
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
            validation=validation,
            execution_result=execution_result,
        )
    validation_metadata = result.metadata.get("validation")
    validation_code = (
        validation_metadata.get("error_code")
        if isinstance(validation_metadata, dict)
        else None
    )
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
            validation=validation,
            execution_result=execution_result,
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
            validation=validation,
            execution_result=execution_result,
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
        if isinstance(validation_metadata, dict)
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
        validation=validation,
        execution_result=execution_result,
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
        unestablished_count=sum(
            item.score.comparison_state.value == "unestablished"
            for item in completed
        ),
        comparison_state_counts=comparison_state_counts(
            tuple(item.score.comparison_state for item in completed)
        ),
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
                comparison_state=item.score.comparison_state.value,
                delivery_completeness=item.score.delivery_completeness.value,
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
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[_CompletedCase]] = defaultdict(list)
    for item in completed:
        groups[key(item)].append(item)
    return {
        name: {
            "completed": len(items),
            "passed": sum(item.score.passed for item in items),
            "failed": sum(not item.score.passed for item in items),
            "unestablished": sum(
                item.score.comparison_state.value == "unestablished"
                for item in items
            ),
            "comparison_states": comparison_state_counts(
                tuple(item.score.comparison_state for item in items)
            ),
            "score": round(sum(item.score.score for item in items) / len(items), 6),
        }
        for name, items in sorted(groups.items())
    }


def _aggregate_provider_usage(
    completed: Sequence[_CompletedCase],
) -> dict[str, int | float | None]:
    measurements = [
        item.execution.provider_measurement
        for item in completed
        if item.execution.provider_measurement is not None
    ]
    return aggregate_provider_measurements(measurements)


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
        "unestablished_count": summary.unestablished_count,
        "comparison_state_counts": summary.comparison_state_counts,
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
