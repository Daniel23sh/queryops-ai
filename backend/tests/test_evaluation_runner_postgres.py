from __future__ import annotations

import json
import os
from collections.abc import Generator
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.domains.it_operations.seed import seed_database
from app.evaluation.baseline import execute_evaluation_baseline
from app.evaluation.context import resolve_evaluation_identity
from app.evaluation.contracts import RequestingRole
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.runner import EvaluationRunner
from app.models.product import EvaluationResult, EvaluationRun
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
    assert summary.passed_count == 10
    assert summary.failed_count == 30
    assert summary.security_pass_rate == 0.8
    assert summary.query_execution_succeeded_count == 6
    assert summary.query_execution_failed_count == 0
    assert any(
        case.case_id == "itops-security-003"
        and case.actual_outcome == "clarification"
        and not case.passed
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
