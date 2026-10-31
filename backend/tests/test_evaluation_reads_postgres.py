"""Real-PostgreSQL regression for scoped evaluation JSON reads."""
from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.it_operations.seed import seed_database
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.read_service import MAX_LATEST_RUN_CANDIDATES
from app.main import app
from app.models.product import EvaluationResult
from tests.action_postgres_test_db import validated_disposable_database_url
from tests.test_evaluation_api import LEAK_SENTINELS, _create_run, _login

PATHS = ("overview", "queries", "security", "actions", "dashboards")
SCOPED = ("manager", "analyst")


@pytest.fixture(scope="module")
def migrated_url() -> str:
    url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Scoped evaluation reads require POSTGRES_TEST_DATABASE_URL.")
    validated_disposable_database_url(url)
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    return url


@pytest.fixture
def db_session(migrated_url: str) -> Generator[Session, None, None]:
    engine = create_engine(migrated_url)
    try:
        with Session(engine) as db:
            seed_database(db, profile_name="small", reset=True)
            db.commit()
            yield db
    finally:
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as api:
            yield api
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("role", (*SCOPED, "admin"))
def test_empty_and_inaccessible_latest_reads_are_safe(
    client: TestClient, db_session: Session, role: str,
) -> None:
    _login(client, f"demo.{role}@queryops.local")
    for path in PATHS:
        response = client.get(f"/api/v1/evaluation/{path}")
        assert response.status_code == 200, response.text
        assert response.json()["data"]["run"] is None
    hidden = _create_run(db_session, case_ids={"itops-hard-003"})
    for path in PATHS:
        response = client.get(f"/api/v1/evaluation/{path}")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        if role == "admin":
            assert data["run"]["id"] == str(hidden.id)
        else:
            assert data["run"] is None
            assert str(hidden.id) not in response.text
            explicit = client.get(f"/api/v1/evaluation/{path}?run_id={hidden.id}")
            missing = client.get(f"/api/v1/evaluation/{path}?run_id={uuid4()}")
            assert explicit.status_code == missing.status_code == 404
            for key in ("code", "message", "details"):
                assert explicit.json()["error"].get(key) == missing.json()["error"].get(key)
        if "metrics" in data:
            assert data["metrics"]["completed_count"] == (1 if role == "admin" and path != "security" else 0)
            assert data["metrics"]["selected_count"] == (1 if role == "admin" and path != "security" else 0)


@pytest.mark.parametrize("role", (*SCOPED, "admin"))
def test_populated_latest_recomputes_only_visible_valid_results(
    client: TestClient, db_session: Session, role: str,
) -> None:
    now = datetime.now(UTC)
    visible = _create_run(db_session, completed_at=now)
    hidden = _create_run(db_session, case_ids={"itops-hard-003"}, completed_at=now + timedelta(seconds=1))
    _login(client, f"demo.{role}@queryops.local")
    cases = load_it_operations_evaluation_v2_set().cases
    expected_ids = {case.id for case in cases if case.requesting_role.value == role}
    if role == "admin":
        expected_ids = {"itops-hard-003"}
    for path in PATHS:
        response = client.get(f"/api/v1/evaluation/{path}?limit=100")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["run"]["id"] == str(hidden.id if role == "admin" else visible.id)
        assert set(data["run"]) == {"id", "provider", "model_label", "dataset_id", "dataset_version", "dataset_digest", "status", "started_at", "completed_at"}
        for sentinel in (*LEAK_SENTINELS, '"summary"', '"comparison_evidence"', '"expected_output"', '"actual_output"'):
            assert sentinel not in response.text
        if path in {"overview", "queries"}:
            assert data["metrics"]["selected_count"] == len(expected_ids)
            assert data["metrics"]["completed_count"] == len(expected_ids)
        if path == "queries":
            assert {item["case_id"] for item in data["items"]} == expected_ids
            assert data["pagination"]["total"] == len(expected_ids)
            assert all((item["technical"] is None) == (role == "manager") for item in data["items"])
        if path == "security":
            assert {item["case_id"] for item in data["items"]} == {case_id for case_id in expected_ids if "security" in case_id}


@pytest.mark.parametrize("role,case_id", [("manager", "itops-easy-001"), ("analyst", "itops-easy-004")])
def test_latest_order_dataset_identity_and_candidate_bound(
    client: TestClient, db_session: Session, role: str, case_id: str,
) -> None:
    now = datetime.now(UTC)
    older = _create_run(db_session, case_ids={case_id}, completed_at=now)
    tied = _create_run(db_session, case_ids={case_id}, completed_at=now)
    tied_id = max(older.id, tied.id)
    _login(client, f"demo.{role}@queryops.local")
    assert client.get("/api/v1/evaluation/overview").json()["data"]["run"]["id"] == str(tied_id)
    stale = _create_run(db_session, case_ids={case_id}, completed_at=now + timedelta(seconds=1))
    stale.summary = {**stale.summary, "dataset_digest": "0" * 64}
    db_session.commit()
    assert client.get("/api/v1/evaluation/overview").json()["data"]["run"]["id"] == str(tied_id)
    # These satisfy SQL predicates but fail validated provider/model identity.
    extra_case_id = "itops-easy-002" if role == "manager" else "itops-easy-006"
    for index in range(MAX_LATEST_RUN_CANDIDATES - 1):
        _create_run(db_session, case_ids={case_id, extra_case_id}, completed_at=now + timedelta(seconds=index + 2), model_label="invalid mock label")
    # Multiple matching result rows must not consume multiple candidate slots.
    assert client.get("/api/v1/evaluation/overview").json()["data"]["run"]["id"] == str(tied_id)
    _create_run(db_session, case_ids={case_id}, completed_at=now + timedelta(seconds=MAX_LATEST_RUN_CANDIDATES + 2), model_label="invalid mock label")
    response = client.get("/api/v1/evaluation/overview")
    assert response.status_code == 200
    assert response.json()["data"]["run"] is None
    # Explicit lookup still reaches the older visible run outside the candidate window.
    assert client.get(f"/api/v1/evaluation/overview?run_id={tied_id}").status_code == 200


@pytest.mark.parametrize("role,case_id", [("manager", "itops-easy-001"), ("analyst", "itops-easy-004")])
def test_scoped_invalid_and_duplicate_results_never_inflate_metrics(
    client: TestClient, db_session: Session, role: str, case_id: str,
) -> None:
    run = _create_run(db_session, case_ids={case_id})
    row = db_session.scalar(select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run.id))
    assert row is not None
    original_metrics = row.metrics
    row.metrics = {**row.metrics, "score": "malformed"}
    db_session.commit()
    _login(client, f"demo.{role}@queryops.local")
    response = client.get("/api/v1/evaluation/queries")
    assert response.status_code == 200
    assert response.json()["data"]["metrics"]["selected_count"] == 1
    assert response.json()["data"]["metrics"]["completed_count"] == 0
    assert response.json()["data"]["items"] == []
    row.metrics = original_metrics
    db_session.add(EvaluationResult(
        evaluation_run_id=run.id, case_name=case_id, status=row.status,
        score=row.score, expected_output=row.expected_output,
        actual_output=row.actual_output, metrics=original_metrics,
    ))
    db_session.commit()
    response = client.get("/api/v1/evaluation/queries")
    assert response.status_code == 200
    assert response.json()["data"]["metrics"]["selected_count"] == 1
    assert response.json()["data"]["metrics"]["completed_count"] == 0
    assert response.json()["data"]["pagination"]["total"] == 0


@pytest.mark.parametrize("role", (*SCOPED, "admin"))
def test_browser_fixture_persists_valid_scoped_measurements(
    client: TestClient, db_session: Session, role: str,
) -> None:
    from scripts.prepare_evaluation_e2e import prepare_state

    ids = prepare_state(db_session, "visible")
    _login(client, f"demo.{role}@queryops.local")
    for path in PATHS:
        response = client.get(f"/api/v1/evaluation/{path}")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["run"]["id"] == ids["hidden" if role == "admin" else "visible"]
        if "metrics" in data:
            assert data["metrics"]["completed_count"] == 1
            assert data["metrics"]["selected_count"] == 1
        assert "9001" not in response.text
