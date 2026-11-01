"""Output identities through real saved-card and CSV APIs, under current-viewer RLS."""

from __future__ import annotations

import csv
import json
import os
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.product import (
    AppAuditLog,
    DashboardCard,
    DataResource,
    QueryRun,
    SavedQuery,
)
from scripts.prepare_m8_e2e import validated_e2e_database_url
from scripts.prepare_output_identity_e2e import prepare_output_identity_state


@pytest.fixture(scope="module")
def identity_database():
    target = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not target:
        pytest.skip("An explicit disposable PostgreSQL database is required.")
    validated_e2e_database_url(
        target,
        disposable_opt_in=os.environ.get("POSTGRES_TEST_DATABASE_DISPOSABLE"),
        application_url=os.environ.get("DATABASE_URL"),
        application_database_name=os.environ.get("POSTGRES_DB", "queryops"),
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
    )
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
            state = prepare_output_identity_state(db)
        yield engine, state
    finally:
        engine.dispose()


@pytest.fixture
def identity_client(identity_database):
    engine, _ = identity_database

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def login(client, profile="analyst"):
    response = client.post(
        "/api/v1/demo/login", json={"email": f"demo.{profile}@queryops.local"}
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


def save(client, state, kind, headers):
    response = client.post(
        f"/api/v1/query-runs/{state['query_runs'][kind]}/save-card",
        headers=headers,
        json={
            "dashboard_id": state["dashboard_id"],
            "title": f"Identity {kind}",
            "card_type": "table",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def csv_rows(response, columns):
    assert response.status_code == 200, response.text
    records = list(csv.reader(StringIO(response.text)))
    assert records[0] == columns
    assert len(records[0]) == len(set(records[0]))
    assert all(len(row) == len(columns) for row in records)
    return records[1:]


@pytest.mark.parametrize(
    "kind,columns",
    [
        (
            "identity",
            ["hostname", "devices__id", "last_seen_at", "directory_users__id"],
        ),
        ("names", ["departments__name", "groups__name"]),
        ("aggregate", ["licenses__product_name", "aggregation__product_name"]),
    ],
)
def test_unique_values_survive_save_reload_refresh_and_csv(
    identity_database, identity_client, kind, columns
):
    engine, state = identity_database
    client = identity_client
    headers = login(client)
    source_csv = client.post(
        f"/api/v1/query-runs/{state['query_runs'][kind]}/export-csv",
        headers=headers,
        json={},
    )
    original = csv_rows(source_csv, columns)
    card_id = save(client, state, kind, headers)
    for _ in range(2):
        detail = client.get(f"/api/v1/dashboards/{state['dashboard_id']}")
        assert detail.status_code == 200
        response = client.post(
            f"/api/v1/cards/{card_id}/refresh", headers=headers, json={}
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["columns"] == columns
        assert data["row_count"] == len(data["rows"]) > 0
        assert all(list(row) == columns for row in data["rows"])
        if kind == "identity":
            assert sorted(data["rows"], key=lambda row: row["hostname"]) == sorted(
                state["expected_analyst"], key=lambda row: row["hostname"]
            )
            assert all(
                row["devices__id"] != row["directory_users__id"] for row in data["rows"]
            )
        elif kind == "names":
            assert any(
                row["groups__name"] != row["departments__name"] for row in data["rows"]
            )
        else:
            assert sorted(data["rows"], key=lambda row: row[columns[0]]) == [
                {columns[0]: "=W6b", columns[1]: 2},
                {columns[0]: "Normal", columns[1]: 1},
            ]
        with Session(engine) as db:
            card = db.get(DashboardCard, UUID(card_id))
            saved_query = db.get(SavedQuery, card.saved_query_id)
            run = db.get(QueryRun, UUID(data["query_run_id"]))
            assert saved_query.result_schema is None
            assert "rows" not in json.dumps(
                [card.config, saved_query.parameters, run.query_metadata]
            )
    exported = client.post(
        f"/api/v1/cards/{card_id}/export-csv",
        headers=headers,
        json={"filename": "identity.csv"},
    )
    assert sorted(csv_rows(exported, columns)) == sorted(original)
    if kind == "aggregate":
        assert ["'=W6b", "2"] in original
    assert exported.headers["X-QueryOps-Returned-Row-Count"] == str(len(original))


def test_saved_admin_sql_reexecutes_with_current_viewer_exact_scope(
    identity_database, identity_client
):
    _, state = identity_database
    client = identity_client
    for profile, expected in (
        ("admin", state["expected_admin"]),
        ("analyst", state["expected_analyst"]),
    ):
        headers = login(client, profile)
        response = client.post(
            f"/api/v1/cards/{state['shared_card_id']}/refresh", headers=headers, json={}
        )
        assert response.status_code == 200, response.text
        assert sorted(
            response.json()["data"]["rows"], key=lambda row: row["hostname"]
        ) == sorted(expected, key=lambda row: row["hostname"])
        exported = client.post(
            f"/api/v1/cards/{state['shared_card_id']}/export-csv",
            headers=headers,
            json={},
        )
        records = csv_rows(
            exported, ["hostname", "devices__id", "last_seen_at", "directory_users__id"]
        )
        assert {row[0] for row in records} == {row["hostname"] for row in expected}


def test_ambiguous_legacy_sql_fails_without_rows_refresh_runs_or_success_audits(
    identity_database, identity_client
):
    engine, state = identity_database
    client = identity_client
    headers = login(client)
    card_id = save(client, state, "legacy", headers)
    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(QueryRun))
    for path in (
        f"/api/v1/query-runs/{state['query_runs']['legacy']}/export-csv",
        f"/api/v1/cards/{card_id}/refresh",
        f"/api/v1/cards/{card_id}/export-csv",
    ):
        response = client.post(path, headers=headers, json={})
        assert response.status_code == 500, response.text
        assert "failed safely" in response.text.lower()
        for fragment in (
            "devices",
            "directory_users",
            "SELECT",
            "rows",
            "columns",
            "ambiguous_output_columns",
        ):
            assert fragment not in response.text
        assert "X-QueryOps-Returned-Row-Count" not in response.headers
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(QueryRun)) == before
        assert (
            db.scalar(
                select(func.count())
                .select_from(AppAuditLog)
                .where(
                    AppAuditLog.event_type == "csv_export",
                    AppAuditLog.entity_id.in_(
                        [UUID(card_id), UUID(state["query_runs"]["legacy"])]
                    ),
                )
            )
            == 0
        )


def test_forbidden_export_remains_denied_without_success_audit(
    identity_database, identity_client
):
    engine, state = identity_database
    client = identity_client
    headers = login(client)
    with Session(engine) as db:
        resource = db.scalar(
            select(DataResource).where(DataResource.table_name == "directory_users")
        )
        resource.is_exportable = False
        db.commit()
        count = db.scalar(
            select(func.count())
            .select_from(AppAuditLog)
            .where(AppAuditLog.event_type == "csv_export")
        )
    try:
        response = client.post(
            f"/api/v1/query-runs/{state['query_runs']['identity']}/export-csv",
            headers=headers,
            json={},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSV_EXPORT_NOT_ALLOWED"
        assert "devices__id" not in response.text
        with Session(engine) as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AppAuditLog)
                    .where(AppAuditLog.event_type == "csv_export")
                )
                == count
            )
    finally:
        with Session(engine) as db:
            resource = db.scalar(
                select(DataResource).where(DataResource.table_name == "directory_users")
            )
            resource.is_exportable = True
            db.commit()
