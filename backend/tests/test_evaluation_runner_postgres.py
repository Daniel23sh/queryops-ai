from __future__ import annotations

import json
import os
from collections.abc import Generator
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.auth.access_context import build_user_access_context
from app.domains.it_operations.models import DirectoryUser, License, LicenseAssignment
from app.domains.it_operations.seed import seed_database
from app.db.session import get_db
from app.evaluation.baseline import execute_evaluation_baseline
from app.evaluation.context import resolve_evaluation_identity
from app.evaluation.contracts import (
    ActualOutcome,
    ComparisonMode,
    ComparisonState,
    DeliveryCompleteness,
    EvaluationAnswerBound,
    EvaluationAnswerBoundKind,
    EvaluationSemanticField,
    EvaluationSemanticOrdering,
    RequestingRole,
)
from app.evaluation.evidence import (
    EvaluationComparisonEvidence,
    auxiliary_evidence_side,
    build_auxiliary_validation,
    observed_evidence_side,
)
from app.evaluation.loader import (
    load_it_operations_evaluation_set,
    load_it_operations_evaluation_v2_set,
)
from app.evaluation.runner import EvaluationRunner, EvaluationRunnerError
from app.evaluation.selection import EvaluationFilters
from app.evaluation.scoring import score_evaluation_case
from app.models.product import EvaluationResult, EvaluationRun, QueryRun
from app.main import app
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import PlanGenerationResult
from app.query_engine.result_formatter import QueryEngineServiceResult
from app.query_engine.semantic_plan import (
    SemanticFieldRef,
    SemanticOrderIntent,
    SemanticPlan,
)
from app.query_engine.service import QueryEngineService
from app.query_engine.schema_context import build_schema_context
from app.query_engine.sql_executor import (
    SQLExecutionOptions,
    execute_validated_sql,
    query_runtime_transaction,
)
from app.query_engine.sql_validator import validate_sql
from tests.action_postgres_test_db import validated_disposable_database_url


def test_complete_mock_evaluation_persists_exact_safe_measurement(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)

    summary = EvaluationRunner(
        factory,
        dataset_loader=load_it_operations_evaluation_v2_set,
    ).run()

    assert summary.status == "succeeded"
    assert summary.selected_count == 40
    assert summary.completed_count == 40
    assert summary.passed_count == 11
    assert summary.failed_count == 29
    assert summary.security_pass_rate == 1.0
    assert summary.query_execution_succeeded_count == 6
    assert summary.query_execution_failed_count == 0
    assert any(
        case.case_id == "itops-security-003"
        and case.actual_outcome == "unsafe_blocked"
        and case.passed
        for case in summary.cases
    )

    with factory() as db:
        run = db.get(EvaluationRun, summary.run_id)
        results = db.scalars(
            select(EvaluationResult)
            .where(EvaluationResult.evaluation_run_id == summary.run_id)
            .order_by(EvaluationResult.case_name)
        ).all()
    assert run is not None
    assert run.status == "succeeded"
    assert run.completed_at is not None
    assert run.summary["completed_count"] == 40
    assert len(results) == 40
    assert len({result.case_name for result in results}) == 40
    assert all(result.error_message is None for result in results)
    persisted = json.dumps(
        {
            "run": run.summary,
            "results": [
                {
                    "expected": result.expected_output,
                    "actual": result.actual_output,
                    "metrics": result.metrics,
                }
                for result in results
            ],
        },
        sort_keys=True,
    )
    for forbidden in (
        "SELECT ",
        "UPDATE ",
        "@queryops.local",
        "postgresql+psycopg",
        "Traceback",
        "secret",
        "generated_sql",
        "executed_sql",
        "prompt",
        "provider_response",
        "rows",
    ):
        assert forbidden not in persisted

    def override_get_db() -> Generator[Session, None, None]:
        with factory() as api_db:
            yield api_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/demo/login",
                json={"email": "demo.admin@queryops.local"},
            )
            assert login.status_code == 200
            overview = client.get("/api/v1/evaluation/overview")
            security = client.get("/api/v1/evaluation/security")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert overview.status_code == 200
    metrics = overview.json()["data"]["metrics"]
    assert metrics["selected_count"] == 40
    assert metrics["completed_count"] == 40
    assert metrics["passed_count"] == 11
    assert metrics["failed_count"] == 29
    assert metrics["overall_score"] == summary.overall_score
    assert security.status_code == 200
    security_metrics = security.json()["data"]["metrics"]
    assert security_metrics["completed_count"] == 5
    assert security_metrics["passed_count"] == 5
    assert security_metrics["security_pass_rate"] == 1.0


def test_real_path_qualifies_different_safety_limited_subsets_with_full_evidence(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    with factory() as db:
        seed_database(db, profile_name="medium", reset=True)
        db.commit()
    try:
        provider = _DescendingActiveLicenseProvider()
        summary = EvaluationRunner(
            factory,
            dataset_loader=load_it_operations_evaluation_v2_set,
            provider_factory=lambda _pack: provider,
        ).run(EvaluationFilters(case_id="itops-easy-006"))

        with factory() as db:
            result = db.scalar(
                select(EvaluationResult).where(
                    EvaluationResult.evaluation_run_id == summary.run_id
                )
            )
        assert result is not None
        assert summary.passed_count == 1
        assert result.metrics["comparison_state"] == "correct"
        assert result.metrics["delivery_completeness"] == "safety_limited"
        evidence = result.metrics["comparison_evidence"]
        assert evidence["actual"]["complete"] is True
        assert evidence["expected"]["complete"] is True
        assert evidence["actual"]["auxiliary_execution_count"] == 1
        assert evidence["expected"]["auxiliary_execution_count"] == 1
        assert evidence["actual"]["observed_execution_count"] == 1
        assert evidence["expected"]["observed_execution_count"] == 1
        assert evidence["actual"]["observed_duration_ms"] >= 0
        assert evidence["expected"]["observed_duration_ms"] >= 0
        assert evidence["actual_delivery_completeness"] == "safety_limited"
        assert provider.call_count == 1
    finally:
        with factory() as db:
            seed_database(db, profile_name="small", reset=True)
            db.commit()


def test_runner_restores_a_safety_clamped_semantic_bound_before_comparison(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    with factory() as db:
        seed_database(db, profile_name="medium", reset=True)
        base_case = load_it_operations_evaluation_v2_set().cases_by_id[
            "itops-easy-006"
        ]
        identity = resolve_evaluation_identity(db, base_case)
        department_id = identity.access_context.default_scope.department_id
        user_id = db.scalar(
            select(DirectoryUser.id).where(
                DirectoryUser.department_id == department_id
            )
        )
        license_id = db.scalar(select(License.id))
        marker = datetime(2002, 1, 1, tzinfo=UTC)
        assert user_id is not None and license_id is not None
        db.add_all(
            [
                LicenseAssignment(
                    id=uuid4(),
                    user_id=user_id,
                    license_id=license_id,
                    department_id=department_id,
                    assigned_at=marker,
                    last_checked_at=marker,
                    status="active",
                    is_exception=False,
                )
                for _ in range(600)
            ]
        )
        db.commit()
    base_set = load_it_operations_evaluation_v2_set()
    base = base_set.cases_by_id["itops-easy-006"]
    assert base.semantic_contract is not None
    ordering = EvaluationSemanticOrdering(
        target_kind="field",
        field=EvaluationSemanticField(
            entity_id="license_assignments", column="id"
        ),
        aggregation_id=None,
        direction="desc",
    )
    case = replace(
        base,
        baseline_sql=(
            "SELECT id, user_id, license_id, status, last_used_at "
            "FROM license_assignments WHERE status = 'active' "
            "ORDER BY id DESC LIMIT 600"
        ),
        semantic_contract=replace(
            base.semantic_contract,
            answer_bound=EvaluationAnswerBound(
                EvaluationAnswerBoundKind.TOP_N, 600
            ),
            ordering=(ordering,),
        ),
    )
    pack = load_it_operations_domain_pack()
    observed_sql = (
        "SELECT id, user_id, license_id, status, last_used_at "
        "FROM license_assignments WHERE status = 'active' "
        "ORDER BY id DESC LIMIT 600"
    )
    fields = [
        {"entity_id": "license_assignments", "column": column}
        for column in ("id", "user_id", "license_id", "status", "last_used_at")
    ]
    service = _ObservedSQLQueryService(
        pack,
        observed_sql,
        {
            "effective_concept_ids": ["active_license_assignment"],
            "composition_rule_ids": [],
            "metric_id": None,
            "output_fields": fields,
            "aggregations": [],
            "group_by": [],
            "having": [],
            "order_by": [
                {
                    "target_kind": "field",
                    "field": fields[0],
                    "aggregation_id": None,
                    "direction": "desc",
                }
            ],
            "limit": 600,
        },
    )

    try:
        summary = EvaluationRunner(
            factory,
            dataset_loader=lambda: replace(base_set, cases=(case,)),
            query_service_factory=lambda _pack: service,
        ).run(EvaluationFilters(case_id=case.id))
        with factory() as db:
            result = db.scalar(
                select(EvaluationResult).where(
                    EvaluationResult.evaluation_run_id == summary.run_id
                )
            )
        assert result is not None
        evidence = result.metrics["comparison_evidence"]
        assert evidence["actual"]["auxiliary_execution_count"] == 1
        assert evidence["expected"]["auxiliary_execution_count"] == 1
        assert evidence["actual"]["row_count"] == 600
        assert evidence["expected"]["row_count"] == 600
        assert result.metrics["delivery_completeness"] == "safety_limited"
    finally:
        with factory() as db:
            seed_database(db, profile_name="small", reset=True)
            db.commit()


class _DescendingActiveLicenseProvider:
    provider_name = "mock"
    model_name = "mock-queryops-v1"

    def __init__(self, *, limit: int | None = None) -> None:
        self.call_count = 0
        self.limit = limit

    def generate_plan(self, *_args, **_kwargs) -> PlanGenerationResult:
        self.call_count += 1
        fields = tuple(
            SemanticFieldRef(entity_id="license_assignments", column=column)
            for column in ("id", "user_id", "license_id", "status", "last_used_at")
        )
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            semantic_plan=SemanticPlan(
                entity_ids=("license_assignments",),
                concept_ids=("active_license_assignment",),
                composition_rule_ids=(),
                metric_id=None,
                distinct=False,
                literal_filters=(),
                relationships=(),
                output_fields=fields,
                aggregations=(),
                group_by=(),
                having=(),
                order_by=(
                    SemanticOrderIntent(
                        target_kind="field",
                        field=fields[0],
                        aggregation_id=None,
                        direction="desc",
                    ),
                ),
                limit=self.limit,
            ),
        )


class _ObservedSQLQueryService(QueryEngineService):
    """Exercise a supplied observed SQL statement through the real runner context."""

    def __init__(self, pack, sql, plan_observation, *, executor=execute_validated_sql):
        self.pack = pack
        self.sql = sql
        self.plan_observation = plan_observation
        self.executor = executor

    def run(self, db, user, _request, *, execution_db_factory):
        access_context = build_user_access_context(user, db)
        validation = validate_sql(
            self.sql,
            build_schema_context(db, access_context, domain_pack=self.pack),
        )
        execution = self.executor(
            execution_db_factory(access_context),
            access_context,
            validation,
        )
        return QueryEngineServiceResult(
            status=execution.status,
            query_run_id=None,
            columns=execution.columns,
            rows=execution.rows,
            row_count=execution.row_count,
            duration_ms=execution.duration_ms,
            truncated=execution.truncated,
            metadata={
                "provider": "mock",
                "model": "mock-queryops-v1",
                "referenced_tables": validation.referenced_tables,
                "semantic_plan_validation": {
                    "status": "passed",
                    "required_intent_status": "passed",
                },
                "semantic_sql_render": {"status": "passed"},
                "semantic_conformance": {"status": "passed"},
                "semantic_plan": self.plan_observation,
            },
            validation_result=validation,
            execution_result=execution,
        )


class _WrongEntityProvider:
    provider_name = "mock"
    model_name = "mock-queryops-v1"

    def __init__(self) -> None:
        self.call_count = 0

    def generate_plan(self, *_args, **_kwargs) -> PlanGenerationResult:
        self.call_count += 1
        field = SemanticFieldRef(
            entity_id="license_assignments",
            column="missing_column",
        )
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            semantic_plan=SemanticPlan(
                entity_ids=("license_assignments",),
                concept_ids=(),
                composition_rule_ids=(),
                metric_id=None,
                distinct=False,
                literal_filters=(),
                relationships=(),
                output_fields=(field,),
                aggregations=(),
                group_by=(),
                having=(),
                order_by=(),
                limit=None,
            ),
        )


def test_real_actual_plan_validation_failure_never_runs_auxiliary_evidence(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    provider = _WrongEntityProvider()

    summary = EvaluationRunner(
        factory,
        dataset_loader=load_it_operations_evaluation_v2_set,
        provider_factory=lambda _pack: provider,
    ).run(EvaluationFilters(case_id="itops-easy-006"))

    with factory() as db:
        result = db.scalar(
            select(EvaluationResult).where(
                EvaluationResult.evaluation_run_id == summary.run_id
            )
        )
    assert result is not None
    assert result.metrics["comparison_state"] == "not_reached"
    assert "comparison_evidence" not in result.metrics
    assert result.actual_output["execution_succeeded"] is False
    assert provider.call_count == 1


def test_real_actual_execution_failure_never_runs_auxiliary_evidence(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    provider = _DescendingActiveLicenseProvider()

    def fail_after_governed_execution(db, access_context, validation, *, options=None):
        result = execute_validated_sql(
            db,
            access_context,
            validation,
            options=options,
        )
        assert result.status == "succeeded"
        return replace(
            result,
            status="failed",
            rows=[],
            row_count=0,
            truncated=False,
            error_code="database_error",
            public_error="Query execution failed.",
        )

    summary = EvaluationRunner(
        factory,
        dataset_loader=load_it_operations_evaluation_v2_set,
        query_service_factory=lambda _pack: QueryEngineService(
            provider=provider,
            executor=fail_after_governed_execution,
        ),
    ).run(EvaluationFilters(case_id="itops-easy-006"))

    with factory() as db:
        result = db.scalar(
            select(EvaluationResult).where(
                EvaluationResult.evaluation_run_id == summary.run_id
            )
        )
    assert result is not None
    assert result.metrics["comparison_state"] == "not_reached"
    assert "comparison_evidence" not in result.metrics
    assert result.actual_output["execution_succeeded"] is False
    assert provider.call_count == 1


def test_actual_success_survives_a_later_comparison_failure(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    provider = _DescendingActiveLicenseProvider()

    def fail_comparison(*_args, **_kwargs):
        raise ValueError("synthetic comparison failure")

    monkeypatch.setattr(
        "app.evaluation.runner.score_evaluation_case", fail_comparison
    )
    summary = EvaluationRunner(
        factory,
        dataset_loader=load_it_operations_evaluation_v2_set,
        provider_factory=lambda _pack: provider,
    ).run(EvaluationFilters(case_id="itops-easy-006"))

    with factory() as db:
        result = db.scalar(
            select(EvaluationResult).where(
                EvaluationResult.evaluation_run_id == summary.run_id
            )
        )
    assert result is not None
    assert result.actual_output["outcome"] == "success"
    assert result.actual_output["execution_succeeded"] is True
    assert result.metrics["comparison_state"] == "unestablished"
    assert result.metrics["comparison_limitation_reason"] == (
        "comparison_context_unestablished"
    )
    assert result.metrics["failure_stage"] == "result_comparison"
    assert provider.call_count == 1


class _FaultingEvaluationSession(Session):
    def __init__(self, *args, fault: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fault = fault

    def commit(self) -> None:
        if self.fault == "commit" and any(
            isinstance(item, QueryRun) for item in self.new
        ):
            self.fault = None
            raise SQLAlchemyError("synthetic QueryRun commit failure")
        super().commit()

    def refresh(self, instance, *args, **kwargs) -> None:
        if self.fault == "refresh" and isinstance(instance, QueryRun):
            self.fault = None
            raise SQLAlchemyError("synthetic QueryRun refresh failure")
        super().refresh(instance, *args, **kwargs)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        super().__exit__(exc_type, exc_value, traceback)
        if self.fault == "exit":
            self.fault = None
            raise SQLAlchemyError("synthetic evaluation context exit failure")


class _FaultingEvaluationSessionFactory:
    def __init__(self, engine: Engine, fault: str) -> None:
        self.engine = engine
        self.fault = fault
        self.calls = 0

    def __call__(self) -> Session:
        self.calls += 1
        return _FaultingEvaluationSession(
            bind=self.engine,
            expire_on_commit=False,
            fault=self.fault if self.calls == 3 else None,
        )


@pytest.mark.parametrize(
    ("fault", "error_code", "failure_stage"),
    [
        ("commit", "query_run_persistence_failed", "persistence"),
        ("refresh", "query_run_persistence_failed", "persistence"),
        ("exit", "evaluation_execution_context_failed", "execution_context"),
    ],
)
def test_actual_success_survives_query_run_persistence_and_context_failures(
    postgres_engine: Engine,
    fault: str,
    error_code: str,
    failure_stage: str,
) -> None:
    factory = _FaultingEvaluationSessionFactory(postgres_engine, fault)
    provider = _DescendingActiveLicenseProvider()
    runner = EvaluationRunner(
        factory,
        dataset_loader=load_it_operations_evaluation_v2_set,
        provider_factory=lambda _pack: provider,
    )

    with pytest.raises(EvaluationRunnerError) as exc_info:
        runner.run(EvaluationFilters(case_id="itops-easy-006"))

    assert exc_info.value.code == error_code
    assert exc_info.value.run_id is not None
    with Session(postgres_engine) as db:
        result = db.scalar(
            select(EvaluationResult).where(
                EvaluationResult.evaluation_run_id == exc_info.value.run_id
            )
        )
    assert result is not None
    assert result.status == "failed"
    assert result.actual_output["outcome"] == "success"
    assert result.actual_output["execution_succeeded"] is True
    assert result.metrics["comparison_state"] == "unestablished"
    assert result.metrics["failure_stage"] == failure_stage
    assert provider.call_count == 1


def test_actual_success_survives_baseline_failure_in_shared_transaction(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    base_set = load_it_operations_evaluation_v2_set()
    base = base_set.cases_by_id["itops-easy-006"]
    case = replace(
        base,
        baseline_sql=(
            "SELECT id, user_id, license_id, status, last_used_at, "
            "1 / CASE WHEN status = 'active' THEN 0 ELSE 1 END AS invalid_value "
            "FROM license_assignments WHERE status = 'active'"
        ),
    )
    provider = _DescendingActiveLicenseProvider()

    summary = EvaluationRunner(
        factory,
        dataset_loader=lambda: replace(base_set, cases=(case,)),
        provider_factory=lambda _pack: provider,
    ).run(EvaluationFilters(case_id=case.id))

    with factory() as db:
        result = db.scalar(
            select(EvaluationResult).where(
                EvaluationResult.evaluation_run_id == summary.run_id
            )
        )
    assert result is not None
    assert result.actual_output["outcome"] == "success"
    assert result.actual_output["execution_succeeded"] is True
    assert result.metrics["comparison_state"] == "unestablished"
    assert result.metrics["comparison_limitation_reason"] == (
        "evidence_execution_failed"
    )
    assert result.metrics["comparison_evidence"]["actual"][
        "observed_execution_count"
    ] == 1
    assert result.metrics["comparison_evidence"]["expected"][
        "observed_execution_count"
    ] == 1
    assert provider.call_count == 1


def test_evidence_deadline_preserves_the_observed_production_result(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    with factory() as db:
        seed_database(db, profile_name="medium", reset=True)
        db.commit()
    provider = _DescendingActiveLicenseProvider()

    def expire_auxiliary_acquisition(
        db, access_context, validation, *, options=None
    ):
        if options is not None and options.max_payload_bytes is not None:
            options = replace(options, acquisition_deadline=perf_counter())
        return execute_validated_sql(
            db,
            access_context,
            validation,
            options=options,
        )

    monkeypatch.setattr(
        "app.evaluation.runner.execute_validated_sql",
        expire_auxiliary_acquisition,
    )
    try:
        summary = EvaluationRunner(
            factory,
            dataset_loader=load_it_operations_evaluation_v2_set,
            provider_factory=lambda _pack: provider,
        ).run(EvaluationFilters(case_id="itops-easy-006"))
        with factory() as db:
            result = db.scalar(
                select(EvaluationResult).where(
                    EvaluationResult.evaluation_run_id == summary.run_id
                )
            )

        assert result is not None
        assert result.actual_output["outcome"] == "success"
        assert result.actual_output["execution_succeeded"] is True
        assert result.metrics["comparison_state"] == "unestablished"
        assert result.metrics["comparison_limitation_reason"] == "evidence_timeout"
        evidence = result.metrics["comparison_evidence"]
        assert sum(
            evidence[side]["auxiliary_execution_count"]
            for side in ("expected", "actual")
        ) == 2
        assert provider.call_count == 1
    finally:
        with factory() as db:
            seed_database(db, profile_name="small", reset=True)
            db.commit()


def test_runner_shares_snapshot_and_transaction_time_across_all_evidence(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    with factory() as db:
        seed_database(db, profile_name="medium", reset=True)
        db.commit()
        base_set = load_it_operations_evaluation_v2_set()
        base = base_set.cases_by_id["itops-easy-006"]
        identity = resolve_evaluation_identity(db, base)
        department_id = identity.access_context.default_scope.department_id
        user_id = db.scalar(
            select(DirectoryUser.id).where(
                DirectoryUser.department_id == department_id
            )
        )
        license_id = db.scalar(select(License.id))
        initial_count = db.scalar(
            select(func.count())
            .select_from(LicenseAssignment)
            .where(
                LicenseAssignment.department_id == department_id,
                LicenseAssignment.status == "active",
            )
        )
        assert user_id is not None and license_id is not None
        assert initial_count is not None and initial_count > 100

    sql = (
        "SELECT id, CURRENT_TIMESTAMP AS observed_at "
        "FROM license_assignments WHERE status = 'active' ORDER BY id"
    )
    assert base.semantic_contract is not None
    id_field = EvaluationSemanticField(
        entity_id="license_assignments", column="id"
    )
    case = replace(
        base,
        baseline_sql=sql,
        stable_key_columns=("id",),
        semantic_contract=replace(
            base.semantic_contract,
            output_fields=(id_field,),
            grain_fields=(id_field,),
            ordering=(),
        ),
    )
    observed_times = []
    inserted = False

    def recording_executor(db, access_context, validation, *, options=None):
        nonlocal inserted
        result = execute_validated_sql(
            db,
            access_context,
            validation,
            options=options,
        )
        if result.rows:
            observed_times.append(result.rows[0]["observed_at"])
        if not inserted:
            inserted = True
            with postgres_engine.begin() as writer:
                writer.execute(
                    LicenseAssignment.__table__.insert().values(
                        id=uuid4(),
                        user_id=user_id,
                        license_id=license_id,
                        department_id=department_id,
                        assigned_at=datetime(2003, 1, 1, tzinfo=UTC),
                        last_checked_at=datetime(2003, 1, 1, tzinfo=UTC),
                        status="active",
                        is_exception=False,
                    )
                )
        return result

    monkeypatch.setattr(
        "app.evaluation.runner.execute_validated_sql", recording_executor
    )
    service = _ObservedSQLQueryService(
        load_it_operations_domain_pack(),
        sql,
        {
            "effective_concept_ids": ["active_license_assignment"],
            "composition_rule_ids": [],
            "metric_id": None,
            "output_fields": [
                {"entity_id": "license_assignments", "column": "id"}
            ],
            "aggregations": [],
            "group_by": [],
            "having": [],
            "order_by": [],
            "limit": None,
        },
        executor=recording_executor,
    )
    try:
        summary = EvaluationRunner(
            factory,
            dataset_loader=lambda: replace(base_set, cases=(case,)),
            query_service_factory=lambda _pack: service,
        ).run(EvaluationFilters(case_id=case.id))
        with factory() as db:
            result = db.scalar(
                select(EvaluationResult).where(
                    EvaluationResult.evaluation_run_id == summary.run_id
                )
            )
            outside_count = db.scalar(
                select(func.count())
                .select_from(LicenseAssignment)
                .where(
                    LicenseAssignment.department_id == department_id,
                    LicenseAssignment.status == "active",
                )
            )

        assert result is not None
        assert result.metrics["comparison_state"] == "correct"
        evidence = result.metrics["comparison_evidence"]
        assert evidence["expected"]["row_count"] == initial_count
        assert evidence["actual"]["row_count"] == initial_count
        assert outside_count == initial_count + 1
        assert len(observed_times) == 4
        assert len(set(observed_times)) == 1
        assert sum(
            evidence[side]["auxiliary_execution_count"]
            for side in ("expected", "actual")
        ) == 2
    finally:
        with factory() as db:
            seed_database(db, profile_name="small", reset=True)
            db.commit()


def test_real_path_rejects_identical_visible_subsets_from_different_populations(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    pack = load_it_operations_domain_pack()
    with factory() as db:
        seed_database(db, profile_name="medium", reset=True)
        db.commit()
        identity = resolve_evaluation_identity(db, case)
        excluded_id = db.scalar(
            select(LicenseAssignment.id)
            .where(
                LicenseAssignment.department_id
                == identity.access_context.default_scope.department_id,
                LicenseAssignment.status == "active",
            )
            .order_by(LicenseAssignment.id)
            .offset(100)
            .limit(1)
        )
        assert excluded_id is not None
        schema = build_schema_context(db, identity.access_context, domain_pack=pack)
        expected = validate_sql(
            "SELECT id, user_id, license_id, status, last_used_at "
            "FROM license_assignments WHERE status = 'active' ORDER BY id",
            schema,
        )
        actual = validate_sql(
            "SELECT id, user_id, license_id, status, last_used_at "
            "FROM license_assignments WHERE status = 'active' "
            f"AND id <> '{excluded_id}' ORDER BY id",
            schema,
        )
        expected_aux = build_auxiliary_validation(expected, schema)
        actual_aux = build_auxiliary_validation(actual, schema)
        assert expected_aux is not None and actual_aux is not None
        with query_runtime_transaction(
            postgres_engine,
            identity.access_context,
            isolation_level="repeatable_read",
        ) as connection:
            expected_result = execute_validated_sql(
                connection, identity.access_context, expected
            )
            actual_result = execute_validated_sql(
                connection, identity.access_context, actual
            )
            expected_evidence_result = execute_validated_sql(
                connection,
                identity.access_context,
                expected_aux,
                options=SQLExecutionOptions(row_limit=1000),
            )
            actual_evidence_result = execute_validated_sql(
                connection,
                identity.access_context,
                actual_aux,
                options=SQLExecutionOptions(row_limit=1000),
            )

    try:
        assert expected_result.rows == actual_result.rows
        expected_observed = observed_evidence_side(
            expected_result.rows,
            expected,
            expected_result,
            case.semantic_contract.answer_bound,
        )
        actual_observed = observed_evidence_side(
            actual_result.rows,
            actual,
            actual_result,
            case.semantic_contract.answer_bound,
        )
        score = score_evaluation_case(
            case,
            actual_outcome=ActualOutcome.SUCCESS,
            execution_succeeded=True,
            actual_referenced_tables=case.expected_tables,
            expected_rows=expected_result.rows,
            actual_rows=actual_result.rows,
            comparison_evidence=EvaluationComparisonEvidence(
                expected=auxiliary_evidence_side(
                    expected_aux,
                    expected_evidence_result,
                    case.semantic_contract.answer_bound,
                ),
                actual=auxiliary_evidence_side(
                    actual_aux,
                    actual_evidence_result,
                    case.semantic_contract.answer_bound,
                ),
                actual_delivery_completeness=actual_observed.delivery_completeness,
            ),
        )
        assert expected_observed.delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED
        assert actual_observed.delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED
        assert score.comparison_state.value == "incorrect"
        assert score.result_correct is False
    finally:
        with factory() as db:
            seed_database(db, profile_name="small", reset=True)
            db.commit()


def test_real_evidence_path_distinguishes_exactly_1000_rows_from_1001(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    marker = datetime(2000, 1, 1, tzinfo=UTC)
    with factory() as db:
        seed_database(db, profile_name="small", reset=True)
        db.commit()
        identity = resolve_evaluation_identity(db, case)
        department_id = identity.access_context.default_scope.department_id
        user_id = db.scalar(
            select(DirectoryUser.id).where(
                DirectoryUser.department_id == department_id
            )
        )
        license_id = db.scalar(select(License.id))
        assert user_id is not None and license_id is not None
        existing = db.scalar(
            select(func.count())
            .select_from(LicenseAssignment)
            .where(
                LicenseAssignment.department_id == department_id,
                LicenseAssignment.status == "active",
            )
        )
        assert existing is not None and existing < 1000
        db.add_all(
            [
                LicenseAssignment(
                    id=uuid4(),
                    user_id=user_id,
                    license_id=license_id,
                    department_id=department_id,
                    assigned_at=marker,
                    last_checked_at=marker,
                    status="active",
                    is_exception=False,
                )
                for _ in range(1000 - existing)
            ]
        )
        db.commit()

    provider = _DescendingActiveLicenseProvider()
    runner = EvaluationRunner(
        factory,
        dataset_loader=load_it_operations_evaluation_v2_set,
        provider_factory=lambda _pack: provider,
    )
    try:
        exact_summary = runner.run(EvaluationFilters(case_id=case.id))
        with factory() as db:
            exact_result = db.scalar(
                select(EvaluationResult).where(
                    EvaluationResult.evaluation_run_id == exact_summary.run_id
                )
            )
            db.add(
                LicenseAssignment(
                    id=uuid4(),
                    user_id=user_id,
                    license_id=license_id,
                    department_id=department_id,
                    assigned_at=marker,
                    last_checked_at=marker,
                    status="active",
                    is_exception=False,
                )
            )
            db.commit()
        exceeded_summary = runner.run(EvaluationFilters(case_id=case.id))
        with factory() as db:
            exceeded_result = db.scalar(
                select(EvaluationResult).where(
                    EvaluationResult.evaluation_run_id == exceeded_summary.run_id
                )
            )

        assert exact_result is not None and exceeded_result is not None
        exact_evidence = exact_result.metrics["comparison_evidence"]
        assert exact_result.metrics["comparison_state"] == "correct"
        assert exact_evidence["expected"]["complete"] is True
        assert exact_evidence["actual"]["complete"] is True
        assert exact_evidence["expected"]["row_count"] == 1000
        assert exact_evidence["actual"]["row_count"] == 1000
        assert exceeded_result.metrics["comparison_state"] == "unestablished"
        assert exceeded_result.metrics["comparison_limitation_reason"] == (
            "evidence_row_budget_exceeded"
        )
        exceeded_evidence = exceeded_result.metrics["comparison_evidence"]
        assert exceeded_evidence["expected"]["row_count"] == 1000
        assert exceeded_evidence["actual"]["row_count"] == 1000
        assert provider.call_count == 2
    finally:
        with factory() as db:
            seed_database(db, profile_name="small", reset=True)
            db.commit()


@pytest.mark.parametrize(
    "expected_sql,actual_sql,comparison_mode,answer_bound,expected_state",
    [
        (
            "SELECT status FROM license_assignments ORDER BY status",
            "SELECT DISTINCT status FROM license_assignments ORDER BY status",
            ComparisonMode.UNORDERED_ROWS,
            EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
            ComparisonState.INCORRECT,
        ),
        (
            "SELECT DISTINCT status FROM license_assignments ORDER BY status",
            "SELECT DISTINCT status FROM license_assignments ORDER BY status",
            ComparisonMode.UNORDERED_ROWS,
            EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
            ComparisonState.CORRECT,
        ),
        (
            "SELECT status, COUNT(*) AS count FROM license_assignments "
            "GROUP BY status ORDER BY status",
            "SELECT status, COUNT(*) AS count FROM license_assignments "
            "GROUP BY status ORDER BY status",
            ComparisonMode.GROUPED_ROWS,
            EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
            ComparisonState.CORRECT,
        ),
        (
            "SELECT COUNT(*) AS count FROM license_assignments",
            "SELECT COUNT(*) AS count FROM license_assignments",
            ComparisonMode.GROUPED_ROWS,
            EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
            ComparisonState.CORRECT,
        ),
        (
            "SELECT id FROM license_assignments ORDER BY id LIMIT 5",
            "SELECT id FROM license_assignments ORDER BY id LIMIT 5",
            ComparisonMode.ORDERED_ROWS,
            EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
            ComparisonState.UNESTABLISHED,
        ),
        (
            "SELECT id, status FROM license_assignments ORDER BY status, id LIMIT 5",
            "SELECT id, status FROM license_assignments "
            "ORDER BY status, id DESC LIMIT 5",
            ComparisonMode.ORDERED_ROWS,
            EvaluationAnswerBound(EvaluationAnswerBoundKind.TOP_N, 5),
            ComparisonState.UNESTABLISHED,
        ),
        (
            "SELECT id FROM license_assignments ORDER BY id LIMIT 5",
            "SELECT id FROM license_assignments ORDER BY id DESC LIMIT 5",
            ComparisonMode.UNORDERED_ROWS,
            EvaluationAnswerBound(EvaluationAnswerBoundKind.LIMIT, 5),
            ComparisonState.UNESTABLISHED,
        ),
    ],
)
def test_real_path_preserves_bounded_and_relational_result_semantics(
    postgres_engine: Engine,
    expected_sql: str,
    actual_sql: str,
    comparison_mode: ComparisonMode,
    answer_bound: EvaluationAnswerBound,
    expected_state: ComparisonState,
) -> None:
    score = _score_real_pair(
        postgres_engine,
        expected_sql,
        actual_sql,
        comparison_mode=comparison_mode,
        answer_bound=answer_bound,
    )

    assert score.comparison_state is expected_state


def test_real_path_exact_production_cap_needs_and_accepts_exhaustion_evidence(
    postgres_engine: Engine,
) -> None:
    marker = datetime(2001, 1, 1, tzinfo=UTC)
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    with Session(postgres_engine) as db:
        identity = resolve_evaluation_identity(db, case)
        department_id = identity.access_context.default_scope.department_id
        user_id = db.scalar(
            select(DirectoryUser.id).where(
                DirectoryUser.department_id == department_id
            )
        )
        license_id = db.scalar(select(License.id))
        assert user_id is not None and license_id is not None
        db.add_all(
            [
                LicenseAssignment(
                    id=uuid4(),
                    user_id=user_id,
                    license_id=license_id,
                    department_id=department_id,
                    assigned_at=marker,
                    last_checked_at=marker,
                    status="suspended",
                    is_exception=False,
                )
                for _ in range(100)
            ]
        )
        db.commit()
    sql = (
        "SELECT id FROM license_assignments WHERE status = 'suspended' "
        "AND last_checked_at = TIMESTAMPTZ '2001-01-01 00:00:00+00' ORDER BY id"
    )
    try:
        score = _score_real_pair(
            postgres_engine,
            sql,
            sql,
            comparison_mode=ComparisonMode.STABLE_KEYS,
            answer_bound=EvaluationAnswerBound(EvaluationAnswerBoundKind.POPULATION),
        )
        assert score.comparison_state is ComparisonState.CORRECT
        assert score.delivery_completeness is DeliveryCompleteness.SAFETY_LIMITED
    finally:
        with Session(postgres_engine) as db:
            db.execute(
                delete(LicenseAssignment).where(
                    LicenseAssignment.last_checked_at == marker
                )
            )
            db.commit()


def test_real_auxiliary_payload_and_time_exhaustion_are_unestablished(
    postgres_engine: Engine,
) -> None:
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    assert case.semantic_contract is not None
    answer_bound = case.semantic_contract.answer_bound
    pack = load_it_operations_domain_pack()
    with Session(postgres_engine) as db:
        identity = resolve_evaluation_identity(db, case)
        schema = build_schema_context(db, identity.access_context, domain_pack=pack)
    simple = validate_sql(
        "SELECT id FROM license_assignments ORDER BY id",
        schema,
    )
    expensive = validate_sql(
        "SELECT a.id FROM license_assignments AS a "
        "CROSS JOIN license_assignments AS b "
        "CROSS JOIN license_assignments AS c "
        "CROSS JOIN license_assignments AS d "
        "ORDER BY a.id, b.id, c.id, d.id",
        schema,
    )
    simple_aux = build_auxiliary_validation(simple, schema)
    expensive_aux = build_auxiliary_validation(expensive, schema)
    assert simple_aux is not None and expensive_aux is not None
    with query_runtime_transaction(
        postgres_engine,
        identity.access_context,
        isolation_level="repeatable_read",
    ) as connection:
        complete_result = execute_validated_sql(
            connection,
            identity.access_context,
            simple_aux,
            options=SQLExecutionOptions(row_limit=1000),
        )
        payload_result = execute_validated_sql(
            connection,
            identity.access_context,
            simple_aux,
            options=SQLExecutionOptions(row_limit=1000, max_payload_bytes=1),
        )
    with query_runtime_transaction(
        postgres_engine,
        identity.access_context,
        isolation_level="repeatable_read",
    ) as connection:
        timeout_result = execute_validated_sql(
            connection,
            identity.access_context,
            expensive_aux,
            options=SQLExecutionOptions(
                row_limit=1000,
                statement_timeout_ms=1,
            ),
        )

    expected_side = auxiliary_evidence_side(
        simple_aux,
        complete_result,
        answer_bound,
    )
    payload_side = auxiliary_evidence_side(
        simple_aux,
        payload_result,
        answer_bound,
    )
    timeout_side = auxiliary_evidence_side(
        expensive_aux,
        timeout_result,
        answer_bound,
    )
    assert expected_side.complete is True
    assert payload_side.limitation_reason == "evidence_payload_exceeded"
    assert timeout_side.limitation_reason == "evidence_timeout"
    for actual_side, reason in (
        (payload_side, "evidence_payload_exceeded"),
        (timeout_side, "evidence_timeout"),
    ):
        score = score_evaluation_case(
            replace(case, comparison_mode=ComparisonMode.UNORDERED_ROWS),
            actual_outcome=ActualOutcome.SUCCESS,
            execution_succeeded=True,
            actual_referenced_tables=case.expected_tables,
            expected_rows=complete_result.rows,
            actual_rows=(),
            comparison_evidence=EvaluationComparisonEvidence(
                expected=expected_side,
                actual=actual_side,
                actual_delivery_completeness=DeliveryCompleteness.UNKNOWN,
            ),
            semantic_contract_passed=True,
        )
        assert score.comparison_state is ComparisonState.UNESTABLISHED
        assert score.comparison_limitation_reason == reason
def test_baseline_rls_context_is_scoped_per_case_without_leak(
    postgres_engine: Engine,
) -> None:
    evaluation_set = load_it_operations_evaluation_set()
    source = evaluation_set.cases_by_id["itops-easy-001"]
    case = replace(
        source,
        baseline_sql=("SELECT id, department_id FROM directory_users ORDER BY id"),
    )
    pack = load_it_operations_domain_pack()
    with Session(postgres_engine) as db:
        manager = resolve_evaluation_identity(db, case)
        manager_result = execute_evaluation_baseline(
            db,
            manager.access_context,
            case,
            pack,
        )
        analyst_case = replace(case, requesting_role=RequestingRole.ANALYST)
        analyst = resolve_evaluation_identity(db, analyst_case)
        analyst_result = execute_evaluation_baseline(
            db,
            analyst.access_context,
            analyst_case,
            pack,
        )

    assert manager_result.rows
    assert analyst_result.rows
    assert {str(row["department_id"]) for row in manager_result.rows} == {
        str(manager.access_context.default_scope.department_id)
    }
    assert {str(row["department_id"]) for row in analyst_result.rows} == {
        str(analyst.access_context.default_scope.department_id)
    }
    assert manager.access_context.default_scope.department_id != (
        analyst.access_context.default_scope.department_id
    )


def test_active_human_aggregate_alias_is_harmless_but_missing_predicate_fails(
    postgres_engine: Engine,
) -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-easy-005"]
    pack = load_it_operations_domain_pack()
    correct_alias_case = replace(
        case,
        baseline_sql=(
            "SELECT COUNT(*) AS active_human_user_count FROM directory_users "
            "WHERE account_type = 'human' AND employee_status = 'active' "
            "AND account_status = 'active'"
        ),
    )
    incomplete_case = replace(
        case,
        baseline_sql=(
            "SELECT COUNT(*) AS active_human_user_count FROM directory_users "
            "WHERE account_type = 'human' AND account_status = 'active'"
        ),
    )

    with Session(postgres_engine) as db:
        identity = resolve_evaluation_identity(db, case)
        expected = execute_evaluation_baseline(
            db,
            identity.access_context,
            case,
            pack,
        )
        correct_alias = execute_evaluation_baseline(
            db,
            identity.access_context,
            correct_alias_case,
            pack,
        )
        incomplete = execute_evaluation_baseline(
            db,
            identity.access_context,
            incomplete_case,
            pack,
        )

    correct_score = score_evaluation_case(
        case,
        actual_outcome=ActualOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=("directory_users",),
        expected_rows=expected.rows,
        actual_rows=correct_alias.rows,
    )
    incomplete_score = score_evaluation_case(
        case,
        actual_outcome=ActualOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=("directory_users",),
        expected_rows=expected.rows,
        actual_rows=incomplete.rows,
    )

    assert correct_score.result_correct is True
    assert correct_score.passed is True
    assert incomplete.rows != expected.rows
    assert incomplete_score.result_correct is False
    assert incomplete_score.failure_reasons == ("result_semantics_mismatch",)


def test_disablement_policy_review_requires_both_or_branches(
    postgres_engine: Engine,
) -> None:
    case = load_it_operations_evaluation_set().cases_by_id["itops-hard-007"]
    pack = load_it_operations_domain_pack()
    critical_event_only_case = replace(
        case,
        expected_tables=(
            "directory_users",
            "security_events",
        ),
        baseline_sql=(
            "SELECT DISTINCT du.id FROM directory_users du "
            "JOIN security_events se ON se.user_id = du.id "
            "WHERE du.account_type = 'human' "
            "AND du.account_status = 'active' "
            "AND (du.last_login_at IS NULL OR du.last_login_at < "
            "CURRENT_TIMESTAMP - INTERVAL '90 days') "
            "AND se.severity = 'critical' "
            "AND se.status IN ('open', 'investigating') ORDER BY du.id"
        ),
    )

    with Session(postgres_engine) as db:
        identity = resolve_evaluation_identity(db, case)
        expected = execute_evaluation_baseline(
            db,
            identity.access_context,
            case,
            pack,
        )
        critical_event_only = execute_evaluation_baseline(
            db,
            identity.access_context,
            critical_event_only_case,
            pack,
        )

    incomplete_score = score_evaluation_case(
        case,
        actual_outcome=ActualOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=expected.rows,
        actual_rows=critical_event_only.rows,
    )

    assert critical_event_only.rows != expected.rows
    assert incomplete_score.result_correct is False
    assert incomplete_score.failure_reasons == ("row_count_mismatch",)


def _score_real_pair(
    postgres_engine: Engine,
    expected_sql: str,
    actual_sql: str,
    *,
    comparison_mode: ComparisonMode,
    answer_bound: EvaluationAnswerBound,
):
    base = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-006"]
    assert base.semantic_contract is not None
    case = replace(
        base,
        comparison_mode=comparison_mode,
        stable_key_columns=("id",) if comparison_mode is ComparisonMode.STABLE_KEYS else (),
        semantic_contract=replace(
            base.semantic_contract,
            answer_bound=answer_bound,
            ordering=(
                (
                    EvaluationSemanticOrdering(
                        target_kind="field",
                        field=EvaluationSemanticField(
                            entity_id="license_assignments",
                            column="status",
                        ),
                        aggregation_id=None,
                        direction="asc",
                    ),
                )
                if answer_bound.kind is EvaluationAnswerBoundKind.TOP_N
                else ()
            ),
        ),
    )
    pack = load_it_operations_domain_pack()
    with Session(postgres_engine) as db:
        identity = resolve_evaluation_identity(db, case)
        schema = build_schema_context(db, identity.access_context, domain_pack=pack)
        expected_validation = validate_sql(expected_sql, schema)
        actual_validation = validate_sql(actual_sql, schema)
        assert expected_validation.valid and actual_validation.valid
        with query_runtime_transaction(
            postgres_engine,
            identity.access_context,
            isolation_level="repeatable_read",
        ) as connection:
            expected_result = execute_validated_sql(
                connection, identity.access_context, expected_validation
            )
            actual_result = execute_validated_sql(
                connection, identity.access_context, actual_validation
            )
            expected_observed = observed_evidence_side(
                expected_result.rows,
                expected_validation,
                expected_result,
                answer_bound,
            )
            actual_observed = observed_evidence_side(
                actual_result.rows,
                actual_validation,
                actual_result,
                answer_bound,
            )
            expected_side = expected_observed
            actual_side = actual_observed
            if not expected_observed.complete:
                expected_aux = build_auxiliary_validation(expected_validation, schema)
                if expected_aux is not None:
                    expected_side = auxiliary_evidence_side(
                        expected_aux,
                        execute_validated_sql(
                            connection,
                            identity.access_context,
                            expected_aux,
                            options=SQLExecutionOptions(row_limit=1000),
                        ),
                        answer_bound,
                    )
            if not actual_observed.complete:
                actual_aux = build_auxiliary_validation(actual_validation, schema)
                if actual_aux is not None:
                    actual_side = auxiliary_evidence_side(
                        actual_aux,
                        execute_validated_sql(
                            connection,
                            identity.access_context,
                            actual_aux,
                            options=SQLExecutionOptions(row_limit=1000),
                        ),
                        answer_bound,
                    )
    return score_evaluation_case(
        case,
        actual_outcome=ActualOutcome.SUCCESS,
        execution_succeeded=True,
        actual_referenced_tables=case.expected_tables,
        expected_rows=expected_result.rows,
        actual_rows=actual_result.rows,
        comparison_evidence=EvaluationComparisonEvidence(
            expected=expected_side,
            actual=actual_side,
            actual_delivery_completeness=actual_observed.delivery_completeness,
            actual_delivery_row_limit=(
                actual_validation.effective_limit
                if actual_observed.delivery_completeness
                is DeliveryCompleteness.SAFETY_LIMITED
                else None
            ),
        ),
        semantic_contract_passed=True,
    )


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Evaluation PostgreSQL tests require POSTGRES_TEST_DATABASE_URL.")
    validated_disposable_database_url(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    with Session(engine) as db:
        seed_database(db, profile_name="small", reset=True)
        db.commit()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "case_id,grouping",
    [
        ("itops-medium-006", [("departments", "name")]),
        ("itops-medium-006", [("departments", "id")]),
        ("itops-medium-006", [("departments", "id"), ("departments", "name")]),
        ("itops-hard-004", [("login_events", "user_id")]),
        ("itops-hard-004", [("directory_users", "id")]),
        ("itops-hard-006", None),
    ],
)
def test_corrected_baselines_and_representations_execute_under_rls(
    postgres_engine, case_id, grouping
):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from app.domains.it_operations.models import (
        DirectoryUser,
        Group,
        LoginEvent,
        UserGroupMembership,
    )
    from app.models.product import AccessScope
    from tests.test_evaluation_semantic_corrections import compare, example

    case, _, sql = example(case_id, grouping=grouping)
    pack = load_it_operations_domain_pack()
    with Session(postgres_engine) as db:
        identity = resolve_evaluation_identity(db, case)
        added = []
        if case_id == "itops-hard-004":
            scope = db.scalar(
                select(AccessScope).where(
                    AccessScope.scope_type == "department",
                    AccessScope.scope_key == identity.target_scope.scope_key,
                )
            )
            now = datetime.now(timezone.utc)
            groups = [
                Group(
                    id=uuid4(),
                    name=f"audit-test-{uuid4()}",
                    group_type="security",
                    department_id=scope.department_id,
                    is_privileged=True,
                )
                for _ in range(2)
            ]
            users = [
                DirectoryUser(
                    id=uuid4(),
                    employee_number=f"test-{uuid4()}",
                    email=f"{uuid4()}@example.test",
                    full_name="Synthetic audit user",
                    department_id=scope.department_id,
                )
                for _ in range(2)
            ]
            db.add_all([*groups, *users])
            db.flush()
            for user, count in zip(users, (6, 5), strict=True):
                db.add_all(
                    [
                        UserGroupMembership(
                            user_id=user.id,
                            group_id=group.id,
                            department_id=scope.department_id,
                            added_at=now,
                        )
                        for group in groups
                    ]
                )
                db.add_all(
                    [
                        LoginEvent(
                            user_id=user.id,
                            department_id=scope.department_id,
                            event_type="failed",
                            occurred_at=now - timedelta(days=1),
                        )
                        for _ in range(count)
                    ]
                )
                db.add(
                    LoginEvent(
                        user_id=user.id,
                        department_id=scope.department_id,
                        event_type="failed",
                        occurred_at=now - timedelta(days=31),
                    )
                )
                db.add(
                    LoginEvent(
                        user_id=user.id,
                        department_id=scope.department_id,
                        event_type="success",
                        occurred_at=now,
                    )
                )
            db.commit()
            added = [*groups, *users]
        try:
            expected = execute_evaluation_baseline(
                db, identity.access_context, case, pack
            )
            actual = execute_evaluation_baseline(
                db, identity.access_context, replace(case, baseline_sql=sql), pack
            )
            if added:
                counts = {
                    str(row["user_id"]): row["failed_login_count"]
                    for row in expected.rows
                }
                assert counts[str(users[0].id)] == 6
                assert str(users[1].id) not in counts
        finally:
            if added:
                db.execute(
                    delete(Group).where(Group.id.in_([group.id for group in groups]))
                )
                db.execute(
                    delete(DirectoryUser).where(
                        DirectoryUser.id.in_([user.id for user in users])
                    )
                )
                db.commit()
    assert expected.rows, "Seed must exercise nonempty corrected result comparison"
    assert compare(case, sql, expected.rows, actual.rows).passed
