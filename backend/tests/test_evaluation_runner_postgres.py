from __future__ import annotations

import json
import os
from collections.abc import Generator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.domains.it_operations.seed import seed_database
from app.db.session import get_db
from app.evaluation.baseline import execute_evaluation_baseline
from app.evaluation.context import resolve_evaluation_identity
from app.evaluation.contracts import ActualOutcome, RequestingRole
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.runner import EvaluationRunner
from app.evaluation.scoring import score_evaluation_case
from app.models.product import EvaluationResult, EvaluationRun
from app.main import app
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from tests.action_postgres_test_db import validated_disposable_database_url


def test_complete_mock_evaluation_persists_exact_safe_measurement(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)

    summary = EvaluationRunner(factory).run()

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


def test_baseline_rls_context_is_scoped_per_case_without_leak(
    postgres_engine: Engine,
) -> None:
    evaluation_set = load_it_operations_evaluation_set()
    source = evaluation_set.cases_by_id["itops-easy-001"]
    case = replace(
        source,
        baseline_sql=(
            "SELECT id, department_id FROM directory_users ORDER BY id"
        ),
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
