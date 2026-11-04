"""Existence hints preserve provider-selected grain under actual PostgreSQL RLS."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.it_operations.models import Department
from app.models.product import QueryRun
from tests.test_reverse_left_postgres import (
    actor,
    key,
    reverse_api as reverse_api,
    reverse_engine as reverse_engine,
    supplied_plan,
)


@pytest.mark.parametrize("threshold", ["at least 1", "more than 0"])
@pytest.mark.parametrize("detail", [False, True], ids=["unique-users", "event-details"])
def test_existence_preserves_provider_grain_and_exact_scope(reverse_api, reverse_engine, threshold, detail):
    api, token, client, executions = reverse_api
    question = f"List inactive human users on leave with {threshold} unresolved critical security events."
    if detail:
        question += " Show user ID and security event ID side by side."
    client.responses.payload["semantic_plan"] = supplied_plan(
        entity_ids=["directory_users", "security_events"],
        concept_ids=["inactive_human_directory_user", "unresolved_critical_security_event"],
        composition_rule_ids=[],
        relationships=[dict(relationship_id="security_event_user", join_type="inner")],
        distinct=not detail,
        output_fields=[dict(entity_id="directory_users", column="id")] + (
            [dict(entity_id="security_events", column="id")] if detail else []
        ),
    )
    with Session(reverse_engine) as db:
        # Affiliation differs from the assigned IT scope; Finance has matching twins.
        actor(db).department_id = db.scalar(select(Department.id).where(Department.name == "Finance"))
        db.commit()

    response = api.post("/api/v1/queries/run", headers={"X-CSRF-Token": token}, json={"question": question})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "succeeded", data
    if detail:
        assert {
            (row["directory_users__id"], row["security_events__id"])
            for row in data["rows"]
        } == {
            (str(key("IT" + user)), str(key("IT" + user + str(index))))
            for user in ("b", "both") for index in range(2)
        }
        assert data["row_count"] == 4
    else:
        assert {row["id"] for row in data["rows"]} == {str(key("IT" + user)) for user in ("b", "both")}
        assert data["row_count"] == 2

    assert len(client.responses.calls) == len(executions) == 1
    catalog = json.loads(client.responses.calls[0]["input"])["semantic_catalog"]
    assert {"inactive_human_directory_user", "unresolved_critical_security_event"} <= {
        concept["id"] for concept in catalog["concepts"]
    }
    assert catalog["result_intent"]["required"] is None
    suggested = catalog["result_intent"]["suggested"]
    assert suggested is None or (
        suggested["row_grain"] is None and suggested["distinct"] is None
        and not suggested["aggregations"] and not suggested["group_by"] and not suggested["having"]
    )
    if not detail:
        assert suggested is None
    assert executions[0].execution_metadata["runtime_role"] == "queryops_query_runtime"
    assert executions[0].execution_metadata["transaction_read_only"] == "on"


def test_existence_provider_clarification_does_not_execute(reverse_api, reverse_engine):
    api, token, client, executions = reverse_api
    client.responses.payload = dict(
        outcome="clarification", semantic_plan=None, clarification_reason="ambiguous_question",
    )
    response = api.post("/api/v1/queries/run", headers={"X-CSRF-Token": token}, json={
        "question": "List relevant users with at least one recent event.",
    })
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "clarification_required"
    assert data["rows"] == []
    assert len(client.responses.calls) == 1
    assert executions == []
    with Session(reverse_engine) as db:
        persisted = db.get(QueryRun, data["query_run_id"])
        assert persisted.generated_sql is persisted.executed_sql is None
