from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.access_context import AccessScopeContext, UserAccessContext
from app.db.base import Base
from app.domains.it_operations.seed import seed_database
from app.evaluation.baseline import (
    EvaluationBaselineError,
    execute_evaluation_baseline,
)
from app.evaluation.context import resolve_evaluation_identity
from app.evaluation.contracts import EvaluationSet, RequestingRole
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.runner import EvaluationRunner, EvaluationRunnerError
from app.evaluation.selection import (
    EvaluationFilters,
    EvaluationSelectionError,
    evaluation_dataset_digest,
    select_evaluation_cases,
)
from app.models.product import AppUser, EvaluationResult, EvaluationRun
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.result_formatter import QueryEngineServiceResult
from app.query_engine.provider_config import ProviderDescriptor, ProviderId
from app.query_engine.sql_executor import SQLExecutionResult


def test_selection_preserves_dataset_order_and_digest_is_stable() -> None:
    evaluation_set = load_it_operations_evaluation_set()

    selected = select_evaluation_cases(
        evaluation_set,
        EvaluationFilters(category="licenses"),
    )

    assert [case.id for case in selected] == sorted(case.id for case in selected)
    assert evaluation_dataset_digest(evaluation_set) == evaluation_dataset_digest(
        evaluation_set
    )
    assert len(evaluation_dataset_digest(evaluation_set)) == 64


def test_selection_rejects_unknown_and_empty_filters() -> None:
    evaluation_set = load_it_operations_evaluation_set()
    with pytest.raises(EvaluationSelectionError, match="Unknown evaluation case"):
        select_evaluation_cases(
            evaluation_set,
            EvaluationFilters(case_id="itops-easy-999"),
        )
    with pytest.raises(EvaluationSelectionError, match="selected no cases"):
        select_evaluation_cases(
            evaluation_set,
            EvaluationFilters(category="not-a-category"),
        )


def test_seeded_actor_resolution_preserves_exact_roles_and_scopes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db, profile_name="small", reset=True)
        db.commit()
        cases = load_it_operations_evaluation_set().cases_by_id

        manager = resolve_evaluation_identity(db, cases["itops-easy-001"])
        admin = resolve_evaluation_identity(db, cases["itops-hard-003"])
        cross_scope = resolve_evaluation_identity(db, cases["itops-security-002"])

    assert manager.access_context.role == "manager"
    assert manager.target_scope is not None
    assert manager.target_scope.scope_key == "finance"
    assert admin.access_context.role == "admin"
    assert admin.access_context.has_global_scope is True
    assert cross_scope.target_scope is not None
    assert cross_scope.target_scope.scope_key != "finance"


def test_baseline_is_revalidated_and_uses_restricted_executor() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db, profile_name="small", reset=True)
        db.commit()
        case = load_it_operations_evaluation_set().cases_by_id["itops-easy-001"]
        identity = resolve_evaluation_identity(db, case)
        captured: dict[str, object] = {}

        def executor(_db, access_context, validation, *, options):
            captured["access_context"] = access_context
            captured["validation"] = validation
            captured["options"] = options
            return SQLExecutionResult(
                status="succeeded",
                columns=["id"],
                rows=[{"id": uuid4()}],
                row_count=1,
                duration_ms=1.0,
                truncated=False,
                referenced_tables=validation.referenced_tables,
            )

        result = execute_evaluation_baseline(
            db,
            identity.access_context,
            case,
            load_it_operations_domain_pack(),
            executor=executor,
        )

    assert result.row_count == 1
    assert result.referenced_tables == ("directory_users",)
    assert captured["access_context"] is identity.access_context
    assert captured["validation"].valid is True
    assert captured["options"].query_action == "query:approved_template"
    assert captured["options"].statement_timeout_ms == 5_000
    assert captured["options"].row_limit == 500


@pytest.mark.parametrize(
    "baseline_sql",
    [
        "UPDATE directory_users SET account_status = 'disabled'",
        "SELECT id FROM directory_users; SELECT id FROM devices",
        "SELECT id FROM it_audit_events",
    ],
)
def test_baseline_rejects_unsafe_or_protected_sql(baseline_sql: str) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db, profile_name="small", reset=True)
        db.commit()
        original = load_it_operations_evaluation_set().cases_by_id["itops-easy-001"]
        case = replace(original, baseline_sql=baseline_sql)
        identity = resolve_evaluation_identity(db, original)

        with pytest.raises(EvaluationBaselineError, match="runtime validation"):
            execute_evaluation_baseline(
                db,
                identity.access_context,
                case,
                load_it_operations_domain_pack(),
                executor=lambda *_args, **_kwargs: pytest.fail("must not execute"),
            )


def test_runner_orders_cases_invokes_service_and_persists_safe_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = _sqlite_session_factory()
    evaluation_set = _small_evaluation_set()
    service = _FakeQueryService()
    runner = EvaluationRunner(
        session_factory,
        dataset_loader=lambda: evaluation_set,
        query_service_factory=lambda _pack: service,
    )
    monkeypatch.setattr(runner, "_verify_prerequisites", lambda _cases: None)
    monkeypatch.setattr(
        "app.evaluation.runner.resolve_evaluation_identity",
        lambda _db, case: _identity(case.requesting_role),
    )
    monkeypatch.setattr(
        "app.evaluation.runner.execute_evaluation_baseline",
        lambda *_args, **_kwargs: _Baseline(({"id": "secret-row"},)),
    )

    summary = runner.run()

    assert [case.case_id for case in summary.cases] == [
        case.id for case in evaluation_set.cases
    ]
    assert service.case_questions == [case.question for case in evaluation_set.cases]
    assert summary.selected_count == summary.completed_count == 2
    assert summary.passed_count == 2
    with session_factory() as db:
        run = db.scalar(select(EvaluationRun))
        results = db.scalars(
            select(EvaluationResult).order_by(EvaluationResult.case_name)
        ).all()
    assert run is not None and run.status == "succeeded"
    assert len(results) == 2
    persisted = repr([run.summary, *[item.metrics for item in results]])
    assert "secret-row" not in persisted
    assert "SELECT " not in persisted


def test_ordinary_case_failure_does_not_prevent_later_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = _sqlite_session_factory()
    evaluation_set = _small_evaluation_set()
    service = _FakeQueryService(fail_first=True)
    runner = EvaluationRunner(
        session_factory,
        dataset_loader=lambda: evaluation_set,
        query_service_factory=lambda _pack: service,
    )
    monkeypatch.setattr(runner, "_verify_prerequisites", lambda _cases: None)
    monkeypatch.setattr(
        "app.evaluation.runner.resolve_evaluation_identity",
        lambda _db, case: _identity(case.requesting_role),
    )
    monkeypatch.setattr(
        "app.evaluation.runner.execute_evaluation_baseline",
        lambda *_args, **_kwargs: _Baseline(({"id": "secret-row"},)),
    )

    summary = runner.run()

    assert summary.completed_count == 2
    assert summary.failed_count == 1
    assert service.calls == 2


def test_fatal_baseline_failure_marks_run_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = _sqlite_session_factory()
    evaluation_set = EvaluationSet(
        dataset_id="test",
        domain_id="it_operations",
        version="1",
        cases=(_small_evaluation_set().cases[0],),
    )
    runner = EvaluationRunner(
        session_factory,
        dataset_loader=lambda: evaluation_set,
        query_service_factory=lambda _pack: _FakeQueryService(),
    )
    monkeypatch.setattr(runner, "_verify_prerequisites", lambda _cases: None)
    monkeypatch.setattr(
        "app.evaluation.runner.resolve_evaluation_identity",
        lambda _db, case: _identity(case.requesting_role),
    )

    def fail_baseline(*_args, **_kwargs):
        raise EvaluationBaselineError(
            "baseline_database_error",
            "Trusted evaluation baseline could not be executed safely.",
        )

    monkeypatch.setattr(
        "app.evaluation.runner.execute_evaluation_baseline",
        fail_baseline,
    )

    with pytest.raises(EvaluationRunnerError) as error:
        runner.run()

    with session_factory() as db:
        run = db.scalar(select(EvaluationRun))
        result_count = len(db.scalars(select(EvaluationResult)).all())
    assert error.value.code == "baseline_database_error"
    assert run is not None and run.status == "failed"
    assert run.completed_at is not None
    assert result_count == 1


def test_runner_maps_validator_rejection_to_unsafe_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = _sqlite_session_factory()
    unsafe_case = load_it_operations_evaluation_set().cases_by_id[
        "itops-security-003"
    ]
    evaluation_set = EvaluationSet(
        dataset_id="test",
        domain_id="it_operations",
        version="1",
        cases=(unsafe_case,),
    )

    class UnsafeService:
        def run(self, _db, _user, _request):
            return QueryEngineServiceResult(
                status="failed",
                query_run_id=None,
                error_code="validation_failed",
                metadata={
                    "referenced_tables": ["directory_users"],
                    "validation": {
                        "valid": False,
                        "error_code": "prohibited_statement",
                    },
                },
            )

    runner = EvaluationRunner(
        session_factory,
        dataset_loader=lambda: evaluation_set,
        query_service_factory=lambda _pack: UnsafeService(),
    )
    monkeypatch.setattr(runner, "_verify_prerequisites", lambda _cases: None)
    monkeypatch.setattr(
        "app.evaluation.runner.resolve_evaluation_identity",
        lambda _db, case: _identity(case.requesting_role),
    )

    summary = runner.run()

    assert summary.passed_count == 1
    assert summary.cases[0].actual_outcome == "unsafe_blocked"
    assert summary.cases[0].error_code == "unsafe_sql_blocked"
    assert summary.query_execution_failed_count == 0


def test_runner_persists_real_provider_identity_and_aggregates_safe_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = _sqlite_session_factory()
    evaluation_set = _small_evaluation_set()

    class MeasuredService:
        calls = 0

        def run(self, _db, _user, request):
            self.calls += 1
            clarification = request.question == "Who is inactive?"
            return QueryEngineServiceResult(
                status=("clarification_required" if clarification else "succeeded"),
                query_run_id=None,
                rows=[] if clarification else [{"id": "secret-row"}],
                row_count=0 if clarification else 1,
                clarification_required=clarification,
                metadata={
                    "provider": "openai",
                    "model": "gpt-5.6-terra",
                    "referenced_tables": [] if clarification else ["devices"],
                    "provider_measurement": {
                        "provider": "openai",
                        "model_label": "gpt-5.6-terra",
                        "duration_ms": 12.5,
                        "attempt_count": 1,
                        "input_tokens": 100,
                        "cached_input_tokens": 25,
                        "output_tokens": 20,
                        "total_tokens": 120,
                        "raw_payload": "must-not-persist",
                    },
                    "raw_prompt": "must-not-persist",
                },
            )

    service = MeasuredService()
    factory_calls = []
    runner = EvaluationRunner(
        session_factory,
        dataset_loader=lambda: evaluation_set,
        query_service_factory=lambda _pack: factory_calls.append(True) or service,
        provider_descriptor=ProviderDescriptor(
            provider=ProviderId.OPENAI,
            model_label="gpt-5.6-terra",
        ),
    )
    monkeypatch.setattr(runner, "_verify_prerequisites", lambda _cases: None)
    monkeypatch.setattr(
        "app.evaluation.runner.resolve_evaluation_identity",
        lambda _db, case: _identity(case.requesting_role),
    )
    monkeypatch.setattr(
        "app.evaluation.runner.execute_evaluation_baseline",
        lambda *_args, **_kwargs: _Baseline(({ "id": "secret-row"},)),
    )

    summary = runner.run()

    assert factory_calls == [True]
    assert service.calls == 2
    assert summary.provider == "openai"
    assert summary.model_label == "gpt-5.6-terra"
    assert summary.provider_usage == {
        "call_count": 2,
        "attempt_count": 2,
        "duration_ms": 25.0,
        "input_tokens": 200,
        "cached_input_tokens": 50,
        "output_tokens": 40,
        "total_tokens": 240,
    }
    with session_factory() as db:
        run = db.scalar(select(EvaluationRun))
        results = db.scalars(select(EvaluationResult)).all()
    assert run is not None
    assert run.name == "test:openai"
    assert run.summary["provider"] == "openai"
    assert run.summary["model_label"] == "gpt-5.6-terra"
    assert run.summary["provider_usage"] == summary.provider_usage
    assert all("provider_measurement" in result.metrics for result in results)
    persisted = repr([run.summary, *[result.metrics for result in results]])
    assert "must-not-persist" not in persisted
    assert "secret-row" not in persisted


def test_fatal_provider_authentication_failure_stops_and_finalizes_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = _sqlite_session_factory()
    evaluation_set = _small_evaluation_set()

    class AuthenticationFailureService:
        calls = 0

        def run(self, _db, _user, _request):
            self.calls += 1
            return QueryEngineServiceResult(
                status="clarification_required",
                query_run_id=None,
                clarification_required=True,
                metadata={
                    "provider": "openai",
                    "model": "gpt-5.6-terra",
                    "referenced_tables": [],
                    "provider_failure_code": "provider_authentication_failed",
                    "provider_failure_fatal": True,
                },
            )

    service = AuthenticationFailureService()
    runner = EvaluationRunner(
        session_factory,
        dataset_loader=lambda: evaluation_set,
        query_service_factory=lambda _pack: service,
        provider_descriptor=ProviderDescriptor(
            provider=ProviderId.OPENAI,
            model_label="gpt-5.6-terra",
        ),
    )
    monkeypatch.setattr(runner, "_verify_prerequisites", lambda _cases: None)
    monkeypatch.setattr(
        "app.evaluation.runner.resolve_evaluation_identity",
        lambda _db, case: _identity(case.requesting_role),
    )
    monkeypatch.setattr(
        "app.evaluation.runner.execute_evaluation_baseline",
        lambda *_args, **_kwargs: pytest.fail("baseline must not run after fatal auth"),
    )

    with pytest.raises(EvaluationRunnerError) as exc_info:
        runner.run()

    assert exc_info.value.code == "provider_authentication_failed"
    assert service.calls == 1
    with session_factory() as db:
        run = db.scalar(select(EvaluationRun))
        results = db.scalars(select(EvaluationResult)).all()
    assert run is not None
    assert run.status == "failed"
    assert run.completed_at is not None
    assert run.summary["failure_code"] == "provider_authentication_failed"
    assert len(results) == 1
    assert results[0].actual_output["error_code"] == "provider_authentication_failed"


class _Baseline:
    def __init__(self, rows):
        self.rows = rows


class _FakeQueryService:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first
        self.case_questions: list[str] = []

    def run(self, _db, _user, request):
        self.calls += 1
        self.case_questions.append(request.question)
        if self.fail_first and self.calls == 1:
            raise RuntimeError("raw secret driver failure")
        if request.question == "Who is inactive?":
            return QueryEngineServiceResult(
                status="clarification_required",
                query_run_id=None,
                clarification_required=True,
                error_code="unsupported_question",
                metadata={"referenced_tables": []},
            )
        return QueryEngineServiceResult(
            status="succeeded",
            query_run_id=None,
            rows=[{"id": "secret-row"}],
            row_count=1,
            metadata={"referenced_tables": ["devices"]},
        )


def _small_evaluation_set() -> EvaluationSet:
    cases = load_it_operations_evaluation_set().cases_by_id
    return EvaluationSet(
        dataset_id="test",
        domain_id="it_operations",
        version="1",
        cases=(cases["itops-easy-002"], cases["itops-security-005"]),
    )


def _sqlite_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _identity(role: RequestingRole):
    scope = AccessScopeContext(
        id=uuid4(),
        type="global" if role is RequestingRole.ADMIN else "department",
        key="global" if role is RequestingRole.ADMIN else "finance",
        display_name="Test",
        access_level="manage",
        is_default=True,
        department_id=None,
    )
    user = AppUser(
        id=uuid4(),
        auth_provider="demo",
        provider_user_id=f"{role.value}-test",
        email=f"{role.value}@example.invalid",
        full_name="Evaluation Test",
        status="active",
    )
    permissions = frozenset(
        {
            "can_run_free_query",
            "can_use_query_templates",
            "can_query_scoped_data",
            "can_view_scoped_data",
        }
    )
    context = UserAccessContext(
        user_id=user.id,
        role=role.value,
        permissions=permissions,
        scopes=(scope,),
        default_scope=scope,
        has_global_scope=scope.type == "global",
        subject_attributes={},
    )
    from app.evaluation.context import EvaluationIdentity, EvaluationTargetScope

    return EvaluationIdentity(
        user=user,
        access_context=context,
        target_scope=EvaluationTargetScope(scope.type, scope.key),
    )
