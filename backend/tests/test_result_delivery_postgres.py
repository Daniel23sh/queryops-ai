"""Real QueryRun → save → repeated refresh → CSV delivery under PostgreSQL RLS."""
from __future__ import annotations

import csv
import json
import os
from collections.abc import Generator
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.product import AppAuditLog, DashboardCard, QueryRun, SavedQuery
from scripts.prepare_delivery_e2e import prepare_delivery_state
from scripts.prepare_m8_e2e import validated_e2e_database_url


@pytest.fixture(scope="module")
def delivery_database():
    target = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not target:
        pytest.skip("Delivery integration requires an explicit disposable PostgreSQL database.")
    validated_e2e_database_url(
        target,
        disposable_opt_in=os.environ.get("POSTGRES_TEST_DATABASE_DISPOSABLE"),
        application_url=os.environ.get("DATABASE_URL"),
        application_database_name=os.environ.get("POSTGRES_DB", "queryops"),
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = target
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    engine = create_engine(target)
    try:
        with Session(engine) as db:
            state = prepare_delivery_state(db)
        yield engine, state
    finally:
        engine.dispose()


@pytest.fixture
def delivery_client(delivery_database) -> Generator[TestClient, None, None]:
    engine, _ = delivery_database

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("source,card_count,card_delivery,csv_count,csv_delivery,origin", [
    ("below_cap", 99, "complete", 99, "complete", "safety_added"),
    ("at_cap", 100, "safety_limited", 100, "safety_limited", "safety_added"),
    ("above_cap", 100, "safety_limited", 100, "safety_limited", "safety_added"),
    ("top_100", 100, "complete", 100, "complete", "input"),
    ("top_500", 100, "safety_limited", 500, "complete", "input"),
    ("clamped", 100, "safety_limited", 500, "safety_limited", "safety_clamped"),
    ("legacy", 100, "unknown", 100, "unknown", None),
])
def test_delivery_survives_save_reload_refresh_and_csv(
    delivery_database, delivery_client,
    source, card_count, card_delivery, csv_count, csv_delivery, origin,
):
    engine, state = delivery_database
    client = delivery_client
    token = client.post("/api/v1/demo/login", json={"email": "demo.analyst@queryops.local"}).json()["data"]["csrf_token"]
    headers = {"X-CSRF-Token": token}
    run_id = state["query_runs"][source]
    initial_csv = client.post(f"/api/v1/query-runs/{run_id}/export-csv", headers={**headers, "Origin": "http://localhost:5173"}, json={})
    exposed = initial_csv.headers["access-control-expose-headers"]
    assert "X-QueryOps-Delivery-Completeness" in exposed
    assert "X-QueryOps-Returned-Row-Count" in exposed
    assert "Content-Disposition" in exposed
    assert_csv(initial_csv, csv_count, csv_delivery)
    saved = client.post(f"/api/v1/query-runs/{run_id}/save-card", headers=headers, json={
        "dashboard_id": state["dashboard_id"], "title": f"Delivery {source}", "card_type": "table",
    })
    assert saved.status_code == 201, saved.text
    card_id = saved.json()["data"]["id"]
    for _ in range(2):
        response = client.post(f"/api/v1/cards/{card_id}/refresh", headers=headers, json={})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["row_count"] == len(data["rows"]) == card_count
        assert data["delivery_completeness"] == card_delivery
        assert bool(data["warnings"]) == (card_delivery != "complete")
        assert "total_row_count" not in data
        if source in {"at_cap", "above_cap"}:
            assert data["truncated"] is False
        with Session(engine) as db:
            run = db.get(QueryRun, UUID(data["query_run_id"]))
            assert run is not None
            assert run.query_metadata["validation"]["limit_source"] == origin
            assert run.query_metadata["execution"]["delivery_completeness"] == card_delivery
            assert "rows" not in json.dumps(run.query_metadata)
            card = db.get(DashboardCard, UUID(card_id))
            assert card is not None
            saved_query = db.get(SavedQuery, card.saved_query_id)
            assert saved_query is not None
            assert saved_query.result_schema is None
            assert "rows" not in json.dumps(card.config or {})
            assert "rows" not in json.dumps(saved_query.parameters or {})
    csv_result = client.post(f"/api/v1/cards/{card_id}/export-csv", headers=headers, json={"filename": "delivery.csv"})
    assert_csv(csv_result, csv_count, csv_delivery)
    detail = client.get(f"/api/v1/dashboards/{state['dashboard_id']}")
    assert detail.status_code == 200
    assert "Delivery 0001" not in detail.text
    with Session(engine) as db:
        audit = db.scalar(select(AppAuditLog).where(
            AppAuditLog.entity_id == UUID(card_id), AppAuditLog.event_type == "csv_export",
        ).order_by(AppAuditLog.created_at.desc()))
        assert audit is not None
        assert audit.audit_metadata["delivery_completeness"] == csv_delivery
        assert audit.audit_metadata["row_count"] == csv_count
        assert "rows" not in json.dumps(audit.audit_metadata)
        assert "Delivery 0001" not in json.dumps(audit.audit_metadata)


def assert_csv(response, count, delivery):
    assert response.status_code == 200, response.text
    assert response.headers["X-QueryOps-Delivery-Completeness"] == delivery
    assert response.headers["X-QueryOps-Returned-Row-Count"] == str(count)
    rows = list(csv.DictReader(StringIO(response.text)))
    assert len(rows) == count
    assert set(rows[0]) == {"product_name", "monthly_cost_usd"}
    assert "completeness" not in response.text
    suffix = {"complete": ".csv", "safety_limited": "-partial.csv", "unknown": "-completeness-unknown.csv"}[delivery]
    assert response.headers["Content-Disposition"].endswith(f'{suffix}"')


@pytest.mark.parametrize("source,provenance,count", [
    ("table_11", {"valid": True, "input_limit": None, "effective_limit": 100, "limit_source": "safety_added"}, 11),
    ("table_24", None, 24),
])
def test_mismatched_or_legacy_provenance_below_cap_never_claims_complete(
    delivery_database, delivery_client, source, provenance, count,
):
    engine, state = delivery_database
    run_id = state["query_runs"][source]
    with Session(engine) as db:
        run = db.get(QueryRun, UUID(run_id))
        assert run is not None
        run.query_metadata = {"referenced_tables": ["licenses"], "validation": provenance}
        db.commit()
    client = delivery_client
    token = client.post("/api/v1/demo/login", json={"email": "demo.analyst@queryops.local"}).json()["data"]["csrf_token"]
    headers = {"X-CSRF-Token": token}
    exported = client.post(f"/api/v1/query-runs/{run_id}/export-csv", headers=headers, json={})
    assert_csv(exported, count, "unknown")
    saved = client.post(f"/api/v1/query-runs/{run_id}/save-card", headers=headers, json={
        "dashboard_id": state["dashboard_id"], "title": f"Unknown {source}",
    })
    assert saved.status_code == 201
    card_id = saved.json()["data"]["id"]
    refreshed = client.post(f"/api/v1/cards/{card_id}/refresh", headers=headers, json={})
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["row_count"] == count
    assert refreshed.json()["data"]["delivery_completeness"] == "unknown"


def test_delivery_reauthorizes_after_scope_revocation_without_disclosing_headers(
    delivery_database, delivery_client,
):
    from sqlalchemy import delete

    from app.auth.access_context import build_user_access_context
    from app.models.product import AppUser, DataResource, UserAccessScope
    from app.query_engine.delivery import bound_metadata
    from app.query_engine.schema_context import build_schema_context
    from app.query_engine.sql_validator import validate_sql

    engine, state = delivery_database
    client = delivery_client
    with Session(engine) as db:
        analyst = db.scalar(select(AppUser).where(AppUser.email == "demo.analyst@queryops.local"))
        assert analyst is not None
        analyst_id = analyst.id
        access = build_user_access_context(analyst, db)
        validation = validate_sql("SELECT email FROM directory_users ORDER BY email", build_schema_context(db, access))
        assert validation.valid
        run = QueryRun(
            user_id=analyst_id, status="succeeded", natural_language_question="Scoped delivery proof",
            executed_sql=validation.sanitized_sql, row_count=1, duration_ms=1,
            query_metadata={"referenced_tables": validation.referenced_tables, "validation": bound_metadata(validation)},
        )
        resource = db.scalar(select(DataResource).where(DataResource.table_name == "directory_users"))
        assert resource is not None
        exportable_before = resource.is_exportable
        resource.is_exportable = True
        db.add(run)
        db.commit()
        run_id = str(run.id)
        scopes = [(scope.scope_id, scope.access_level, scope.is_default) for scope in db.scalars(
            select(UserAccessScope).where(UserAccessScope.user_id == analyst_id)
        )]
    try:
        token = client.post("/api/v1/demo/login", json={"email": "demo.analyst@queryops.local"}).json()["data"]["csrf_token"]
        headers = {"X-CSRF-Token": token}
        saved = client.post(f"/api/v1/query-runs/{run_id}/save-card", headers=headers, json={
            "dashboard_id": state["dashboard_id"], "title": "Revoked scoped source",
        })
        assert saved.status_code == 201
        card_id = saved.json()["data"]["id"]
        before = client.post(f"/api/v1/cards/{card_id}/export-csv", headers=headers, json={})
        assert before.status_code == 200, before.text
        assert before.headers["X-QueryOps-Delivery-Completeness"] == "complete"
        with Session(engine) as db:
            db.execute(delete(UserAccessScope).where(UserAccessScope.user_id == analyst_id))
            db.commit()
        for path in (
            f"/api/v1/cards/{card_id}/refresh",
            f"/api/v1/cards/{card_id}/export-csv",
            f"/api/v1/query-runs/{run_id}/export-csv",
        ):
            response = client.post(path, headers=headers, json={})
            assert response.status_code == 403, response.text
            assert "X-QueryOps-Delivery-Completeness" not in response.headers
            assert "X-QueryOps-Returned-Row-Count" not in response.headers
            assert "delivery_completeness" not in response.text
            assert "rows" not in response.text
            assert "directory_users" not in response.text
        with Session(engine) as db:
            audits = list(db.scalars(select(AppAuditLog).where(
                AppAuditLog.entity_id == UUID(card_id), AppAuditLog.event_type == "csv_export",
            )))
            assert len(audits) == 1
    finally:
        with Session(engine) as db:
            db.execute(delete(UserAccessScope).where(UserAccessScope.user_id == analyst_id))
            db.add_all([UserAccessScope(user_id=analyst_id, scope_id=scope_id, access_level=level, is_default=default)
                        for scope_id, level, default in scopes])
            resource = db.scalar(select(DataResource).where(DataResource.table_name == "directory_users"))
            assert resource is not None
            resource.is_exportable = exportable_before
            db.commit()
