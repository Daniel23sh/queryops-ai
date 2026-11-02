"""Permanent F1 regressions; supplied plans prove execution, never NL accuracy."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.api.routes.queries import get_query_engine_service
from app.auth.access_context import build_user_access_context
from app.db.session import get_db
from app.domains.it_operations.models import (
    Department, DirectoryUser, Group, SecurityEvent, UserGroupMembership,
)
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AppUser, DataResource, Permission, QueryRun, UserAccessScope, UserPermission,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.schema_context import build_schema_context
from app.query_engine.semantic_plan import SemanticPlan
from app.query_engine.service import QueryEngineService
from app.query_engine.sql_executor import execute_validated_sql
from app.query_engine.sql_renderer import render_validated_semantic_plan
from app.query_engine.sql_validator import validate_sql
from tests.action_postgres_test_db import validated_disposable_database_url
from tests.test_openai_provider import FakeClient, provider_for
from tests.test_query_api_postgres import login, run_alembic_upgrade


QUESTION = (
    "List inactive human directory users needing policy review before disablement "
    "in my authorized area, with privileged groups or unresolved critical security events."
)
ACTOR = "demo.analyst@queryops.local"
REFERENCE = datetime(2026, 11, 2, tzinfo=UTC)


def key(name):
    return uuid5(NAMESPACE_URL, "queryops-reverse-left-regression/" + name)


def supplied_plan(**changes):
    value = dict(
        entity_ids=["directory_users", "user_group_memberships", "groups", "security_events"],
        concept_ids=["inactive_human_directory_user"],
        composition_rule_ids=["disablement_policy_review"], metric_id=None, distinct=True,
        literal_filters=[dict(field=dict(entity_id="directory_users", column="employee_status"),
                             operator="equals", value="on_leave")],
        relationships=[dict(relationship_id=r, join_type=j) for r, j in (
            ("user_group_membership_user", "left_reverse"),
            ("user_group_membership_group", "left"),
            ("security_event_user", "left_reverse"))],
        output_fields=[dict(entity_id="directory_users", column="id")],
        aggregations=[], group_by=[], having=[], order_by=[], limit=None,
    )
    value.update(changes)
    return SemanticPlan.model_validate_json(json.dumps(value)).model_dump(mode="json")


# Independent population oracle: each witness is tested without join fanout.
ORACLE = """
SELECT du.id FROM directory_users du
WHERE du.account_type = 'human' AND du.account_status = 'active'
AND (du.last_login_at IS NULL OR du.last_login_at < CURRENT_TIMESTAMP - INTERVAL '90 days')
AND du.employee_status = 'on_leave'
AND (EXISTS (SELECT 1 FROM user_group_memberships m JOIN groups g ON g.id = m.group_id
             WHERE m.user_id = du.id AND g.is_privileged = TRUE)
     OR EXISTS (SELECT 1 FROM security_events e WHERE e.user_id = du.id
                AND e.severity = 'critical' AND e.status IN ('open', 'investigating')))
"""


def add_population(db):
    departments = {d.name: d.id for d in db.scalars(select(Department))}
    for scope in ("IT", "Finance"):
        department = departments[scope]
        for name in ("a", "b", "both", "neither", "wrong", "recent", "active", "service", "disabled", "hidden_only"):
            db.add(DirectoryUser(
                id=key(scope + name), employee_number="reverse-left-" + scope + name,
                email="reverse-left-" + scope + name + "@example.test", full_name="Synthetic " + name,
                department_id=department, account_type="service" if name == "service" else "human",
                employee_status="active" if name == "active" else "on_leave",
                account_status="disabled" if name == "disabled" else "active",
                last_login_at=datetime.now(UTC) if name == "recent" else None,
            ))
        for name, privileged in (("p1", True), ("p2", True), ("ordinary", False)):
            db.add(Group(id=key(scope + name), name="reverse-left-" + scope + name,
                         group_type="security", department_id=department,
                         is_privileged=privileged, risk_level="low"))
        db.flush()
        for name in ("a", "both", "wrong", "recent", "active", "service", "disabled"):
            groups = ("ordinary",) if name == "wrong" else ("p1", "p2")
            for group in groups:
                db.add(UserGroupMembership(user_id=key(scope + name), group_id=key(scope + group),
                                          department_id=department, added_at=REFERENCE))
        for name in ("b", "both", "wrong", "recent", "active", "service", "disabled"):
            for index in range(2):
                db.add(SecurityEvent(id=key(scope + name + str(index)), user_id=key(scope + name),
                    department_id=department, event_type="synthetic", occurred_at=REFERENCE,
                    severity="low" if name == "wrong" and index == 0 else "critical",
                    status="resolved" if name == "wrong" and index == 1 else "open"))
        # NULL user references cannot become witnesses for any preserved user.
        db.add(SecurityEvent(id=key(scope + "null"), user_id=None, department_id=department,
            event_type="synthetic", occurred_at=REFERENCE, severity="critical", status="open"))
    db.flush()
    # Visible users with only out-of-scope witnesses must remain excluded.
    db.add(SecurityEvent(id=key("hidden-event"), user_id=key("IThidden_only"),
        department_id=departments["Finance"], event_type="synthetic", occurred_at=REFERENCE,
        severity="critical", status="open"))
    db.add(UserGroupMembership(user_id=key("IThidden_only"), group_id=key("Financep1"),
                              department_id=departments["Finance"], added_at=REFERENCE))


@pytest.fixture(scope="module")
def reverse_engine():
    url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Reverse LEFT requires explicit disposable PostgreSQL.")
    engine = create_engine(validated_disposable_database_url(url))
    run_alembic_upgrade(url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def reverse_api(reverse_engine):
    with Session(reverse_engine) as db:
        seed_database(db, profile_name="small", reset=True, reference_now=REFERENCE)
        # Isolate this population from unrelated seeded witnesses without changing frozen fixtures.
        for user in db.scalars(select(DirectoryUser)):
            user.employee_status = "active"
        add_population(db)
        db.commit()

    def override_db():
        with Session(reverse_engine) as db:
            yield db

    client = FakeClient(dict(outcome="plan", semantic_plan=supplied_plan(), clarification_reason=None))
    executions = []

    def execute(engine, access, validation, *, options=None):
        result = execute_validated_sql(engine, access, validation, options=options)
        executions.append(result)
        return result

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_query_engine_service] = lambda: QueryEngineService(
        provider=provider_for(client), executor=execute,
    )
    try:
        with TestClient(app) as api:
            token = login(api, ACTOR)
            yield api, token, client, executions
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_query_engine_service, None)


def run(api):
    response = api[0].post("/api/v1/queries/run", headers={"X-CSRF-Token": api[1]},
                           json={"question": QUESTION})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def actor(db):
    return db.scalar(select(AppUser).where(AppUser.email == ACTOR))


def test_fake_openai_reverse_left_matches_independent_rls_oracle(reverse_api, reverse_engine):
    data = run(reverse_api)
    assert data["status"] == "succeeded", data
    expected = {str(key("IT" + name)) for name in ("a", "b", "both")}
    assert {row["id"] for row in data["rows"]} == expected
    assert data["row_count"] == 3
    with Session(reverse_engine) as db:
        access = build_user_access_context(actor(db), db)
        schema = build_schema_context(db, access)
        oracle_validation = validate_sql(ORACLE, schema)
        assert oracle_validation.valid, oracle_validation.reason
        oracle = execute_validated_sql(reverse_engine, access, oracle_validation)
        assert oracle.status == "succeeded"
        assert {str(row["id"]) for row in oracle.rows} == expected
        persisted = db.get(QueryRun, data["query_run_id"])
        assert persisted.query_metadata["semantic_plan"]["relationship_join_types"] == [
            {"relationship_id": r["relationship_id"], "join_type": r["join_type"]}
            for r in sorted(supplied_plan()["relationships"], key=lambda r: r["relationship_id"])]
    client, executions = reverse_api[2:]
    assert len(client.responses.calls) == len(executions) == 1
    schema = client.responses.calls[0]["text_format"].model_json_schema()
    assert schema["$defs"]["SemanticRelationshipIntent"]["properties"]["join_type"]["enum"] == [
        "inner", "left", "left_reverse"]
    prompt = json.dumps(client.responses.calls[0]["input"])
    for private in (ACTOR, str(key("ITa")), "it_audit_events", "queryops_query_runtime"):
        assert private not in prompt
    assert executions[0].execution_metadata["runtime_role"] == "queryops_query_runtime"
    assert executions[0].execution_metadata["transaction_read_only"] == "on"


def test_optional_fanout_distinct_and_count_population(reverse_api):
    client = reverse_api[2]
    client.responses.payload["semantic_plan"] = supplied_plan(distinct=False)
    rows = run(reverse_api)
    assert rows["status"] == "succeeded"
    assert rows["row_count"] == 8  # A: 2 memberships; B: 2 events; both: 2 x 2.
    client.responses.payload["semantic_plan"] = supplied_plan(
        distinct=False, output_fields=[], aggregations=[
            dict(id="joined_rows", function="count", field=None, distinct=False),
            dict(id="users", function="count", field=dict(entity_id="directory_users", column="id"), distinct=True),
            dict(id="event_rows", function="count", field=dict(entity_id="security_events", column="id"), distinct=False),
        ])
    result = run(reverse_api)
    assert result["status"] == "succeeded"
    assert result["rows"] == [dict(joined_rows=8, users=3, event_rows=6)]


@pytest.mark.parametrize("join_type,expected", [("inner", {"both"}), ("left", {"both"})])
def test_legacy_join_plans_keep_their_original_population(reverse_api, join_type, expected):
    relationships = supplied_plan()["relationships"]
    for relationship in relationships:
        relationship["join_type"] = join_type
    if join_type == "left":
        # The mixed legacy tree is supported and preserved exactly as before.
        next(r for r in relationships if r["relationship_id"] == "user_group_membership_user")["join_type"] = "inner"
    reverse_api[2].responses.payload["semantic_plan"] = supplied_plan(relationships=relationships)
    result = run(reverse_api)
    assert result["status"] == "succeeded"
    assert {row["id"] for row in result["rows"]} == {str(key("IT" + name)) for name in expected}


@pytest.mark.parametrize("restriction", ["resource", "column", "scope", "permission"])
def test_reverse_left_cannot_expand_authorization(reverse_api, reverse_engine, restriction):
    with Session(reverse_engine) as db:
        if restriction == "resource":
            resource = db.scalar(select(DataResource).where(DataResource.table_name == "security_events"))
            resource.is_queryable = False
        elif restriction == "scope":
            db.execute(delete(UserAccessScope).where(UserAccessScope.user_id == actor(db).id))
        elif restriction == "permission":
            permission = db.scalar(select(Permission).where(Permission.key == "can_query_scoped_data"))
            db.add(UserPermission(user_id=actor(db).id, permission_id=permission.id, effect="deny"))
        db.commit()
    if restriction == "column":
        from dataclasses import replace

        pack = load_it_operations_domain_pack()
        pack = replace(pack, tables=tuple(replace(t, columns=tuple(c for c in t.columns if c.name != "user_id"))
            if t.name == "security_events" else t for t in pack.tables))
        app.dependency_overrides[get_query_engine_service] = lambda: QueryEngineService(
            provider=provider_for(reverse_api[2]), domain_pack_loader=lambda: pack,
            executor=lambda *args, **kwargs: pytest.fail("unauthorized execution"),
        )
    result = run(reverse_api)
    assert result["status"] != "succeeded"
    assert result["rows"] == []
    assert reverse_api[3] == []


def test_hidden_optional_witness_is_null_extended_instead_of_required(reverse_api, reverse_engine):
    client = reverse_api[2]
    client.responses.payload["semantic_plan"] = supplied_plan(
        entity_ids=["directory_users", "security_events"], concept_ids=[], composition_rule_ids=[],
        relationships=[dict(relationship_id="security_event_user", join_type="left_reverse")],
        literal_filters=[], distinct=False,
        output_fields=[dict(entity_id=e, column="id") for e in ("directory_users", "security_events")],
    )
    result = run(reverse_api)
    assert result["status"] == "succeeded"
    hidden = [r for r in result["rows"] if r["directory_users__id"] == str(key("IThidden_only"))]
    assert hidden == [{"directory_users__id": str(key("IThidden_only")), "security_events__id": None}]
    assert all(r["directory_users__id"] != str(key("Financea")) for r in result["rows"])


def test_reverse_left_uses_assigned_scope_even_when_affiliation_differs(reverse_api, reverse_engine):
    with Session(reverse_engine) as db:
        user = actor(db)
        user.department_id = db.scalar(select(Department.id).where(Department.name == "Finance"))
        db.commit()
    data = run(reverse_api)
    assert data["status"] == "succeeded"
    assert {row["id"] for row in data["rows"]} == {str(key("IT" + name)) for name in ("a", "b", "both")}


@pytest.mark.parametrize("mutation", ["mandatory_branch", "weakened_and", "and_moved_to_on"])
def test_optional_or_sql_drift_fails_before_execution(reverse_api, mutation):
    def wrong_renderer(plan, pack):
        sql = render_validated_semantic_plan(plan, pack)
        if mutation == "mandatory_branch":
            return sql + " AND groups.is_privileged = TRUE"
        if mutation == "and_moved_to_on":
            predicate = "directory_users.employee_status = 'on_leave'"
            changed = sql.replace(" AND " + predicate, "")
            assert changed != sql
            return changed.replace(" WHERE ", " AND " + predicate + " WHERE ", 1)
        changed = sql.replace(" AND ((groups.", " OR ((groups.")
        assert changed != sql
        return changed

    app.dependency_overrides[get_query_engine_service] = lambda: QueryEngineService(
        provider=provider_for(reverse_api[2]), semantic_sql_renderer=wrong_renderer,
        executor=lambda *args, **kwargs: pytest.fail("nonconforming execution"),
    )
    result = run(reverse_api)
    assert result["status"] == "failed"
    assert result["error_code"] == "semantic_conformance_failed"
    assert result["rows"] == []
