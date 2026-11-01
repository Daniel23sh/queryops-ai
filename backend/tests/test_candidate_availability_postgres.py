"""Authorized candidate availability through the real API and PostgreSQL RLS."""

from __future__ import annotations

import json
import os
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.api.routes.queries import get_query_engine_service
from app.auth.access_context import build_user_access_context
from app.db.session import get_db
from app.domains.it_operations.models import Device, DirectoryUser, LoginEvent
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AccessScope,
    AppUser,
    DataResource,
    Permission,
    QueryRun,
    UserAccessScope,
    UserPermission,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import PlanGenerationResult
from app.query_engine.openai_provider import build_safe_prompt_projection
from app.query_engine.semantic_catalog import MAX_SEMANTIC_PROJECTION_BYTES
from app.query_engine.semantic_plan import SemanticFieldRef, SemanticPlan
from app.query_engine.service import QueryEngineService
from app.query_engine.sql_executor import execute_validated_sql
from tests.action_postgres_test_db import validated_disposable_database_url
from tests.test_query_api_postgres import login, run_alembic_upgrade


ACTOR_EMAIL = "demo.analyst@queryops.local"


class RecordingPlanProvider:
    provider_name = "mock"
    model_name = "controlled-candidate-regression"

    def __init__(self):
        self.prompts = []
        self.projections = []
        self.executions = []
        self.entity_id = "devices"

    def execute(self, engine, access, validation, *, options=None):
        result = execute_validated_sql(engine, access, validation, options=options)
        self.executions.append(result)
        return result

    def generate_plan(self, question, schema_context, user_context, options):
        projection = options["semantic_catalog"]
        self.projections.append(projection)
        # Exercise the outbound allowlist, not the internal schema's scope keys.
        self.prompts.append(build_safe_prompt_projection(
            question, schema_context, user_context, projection,
        ))
        return PlanGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            semantic_plan=SemanticPlan(
                entity_ids=(self.entity_id,), concept_ids=(), composition_rule_ids=(),
                metric_id=None, distinct=False, literal_filters=(), relationships=(),
                output_fields=(
                    SemanticFieldRef(entity_id=self.entity_id, column="id"),
                    SemanticFieldRef(entity_id=self.entity_id, column="department_id"),
                ),
                aggregations=(), group_by=(), having=(), order_by=(), limit=None,
            ),
        )


@pytest.fixture(scope="module")
def candidate_engine():
    target = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not target:
        pytest.skip("Candidate security tests require explicit disposable PostgreSQL.")
    validated_disposable_database_url(target)
    run_alembic_upgrade(target)
    engine = create_engine(target)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def candidate_api(candidate_engine):
    with Session(candidate_engine) as db:
        seed_database(db, profile_name="small", reset=True)
        db.commit()

    def override_db():
        with Session(candidate_engine) as db:
            yield db

    provider = RecordingPlanProvider()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_query_engine_service] = lambda: QueryEngineService(
        provider=provider, executor=provider.execute,
    )
    try:
        with TestClient(app) as client:
            token = login(client, ACTOR_EMAIL)
            yield client, token, provider
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_query_engine_service, None)


def run_devices(api, question="List devices in my authorized area."):
    client, token, _ = api
    response = client.post(
        "/api/v1/queries/run", headers={"X-CSRF-Token": token},
        json={"question": question},
    )
    assert response.status_code == 200
    return response.json()["data"]


def actor(db):
    user = db.scalar(select(AppUser).where(AppUser.email == ACTOR_EMAIL))
    assert user is not None
    return user


def assert_projection_closed(projection):
    payload = projection.as_prompt_dict()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    assert len(encoded) <= MAX_SEMANTIC_PROJECTION_BYTES
    entity_ids = {entry["id"] for entry in payload["entities"]}
    concept_ids = {entry["id"] for entry in payload["concepts"]}
    for relationship in payload["relationships"]:
        assert {relationship["from_entity"], relationship["to_entity"]} <= entity_ids
    for concept in payload["concepts"]:
        assert concept["entity_id"] in entity_ids
        assert set(concept["all_of_concept_ids"]) <= concept_ids
    for metric in payload["metrics"]:
        assert metric["entity_id"] in entity_ids
        assert set(metric["required_concept_ids"]) <= concept_ids
    for rule in payload["composition_rules"]:
        assert set(rule["all_of_concept_ids"] + rule["or_concept_ids"]) <= concept_ids
    assert payload["result_intent"]["required"] is None


@pytest.mark.parametrize("question", [
    "List devices in my authorized area.",
    "Show all devices, not just non-compliant devices, in my authorized area.",
    "Show computers in my authorized area.",
])
def test_unused_candidates_never_add_filters_or_joins_under_rls(
    candidate_api, candidate_engine, question,
):
    with Session(candidate_engine) as db:
        user = actor(db)
        access = build_user_access_context(user, db)
        department_id = access.default_scope.department_id
        expected_ids = set(db.scalars(select(Device.id).where(
            Device.department_id == department_id,
        )))
        excluded_ids = set(db.scalars(select(Device.id).where(
            Device.department_id != department_id,
        )))
        assert expected_ids and excluded_ids
        # Both populations must survive when no posture definition was selected.
        assert set(db.scalars(select(Device.compliance_status).where(
            Device.department_id == department_id,
        ))) >= {"compliant", "non_compliant"}
        private_values = [str(user.id), user.email, user.full_name, str(department_id)]
        private_values.extend(scope.key for scope in access.scopes)
        private_values.extend(str(scope.id) for scope in access.scopes)
        private_values.extend(str(value) for value in expected_ids | excluded_ids)
        private_values.extend(db.scalars(select(Device.hostname)))
        private_values.extend(db.scalars(select(DirectoryUser.email)))
        private_values.extend(db.scalars(select(DirectoryUser.full_name)))

    data = run_devices(candidate_api, question)
    assert data["status"] == "succeeded"
    assert {row["id"] for row in data["rows"]} == {str(value) for value in expected_ids}
    assert {row["department_id"] for row in data["rows"]} == {str(department_id)}
    _, _, provider = candidate_api
    assert len(provider.prompts) == 1
    projection = provider.projections[0]
    assert_projection_closed(projection)
    if "computers" not in question:
        assert "non_compliant_device" in {entry["id"] for entry in projection.concepts}
    prompt = provider.prompts[0]
    assert "it_audit_events" not in {table["name"] for table in prompt["tables"]}
    serialized = json.dumps(prompt)
    # Compare scalar values, since short scope keys can occur inside descriptions.
    def scalars(value):
        if isinstance(value, dict):
            return [item for child in value.values() for item in scalars(child)]
        if isinstance(value, list):
            return [item for child in value for item in scalars(child)]
        return [value]
    assert not set(private_values) & set(value for value in scalars(prompt) if isinstance(value, str))
    assert "can_query_scoped_data" not in serialized
    assert set(prompt["authorization"]) == {
        "scope_type", "has_global_scope", "scope_reference_resolved",
    }
    with Session(candidate_engine) as db:
        run = db.get(QueryRun, data["query_run_id"])
        assert run is not None
        assert "WHERE" not in run.generated_sql.upper()
        assert "JOIN" not in run.generated_sql.upper()
    assert len(provider.executions) == 1
    runtime = provider.executions[0].execution_metadata
    assert runtime["runtime_role"] == "queryops_query_runtime"
    assert runtime["transaction_read_only"] == "on"


@pytest.mark.parametrize("question,entity_id,model", [
    ("List company personnel.", "directory_users", DirectoryUser),
    ("List authentication attempts.", "login_events", LoginEvent),
])
def test_new_vocabulary_entities_can_execute_with_only_current_scope(
    candidate_api, candidate_engine, question, entity_id, model,
):
    provider = candidate_api[2]
    provider.entity_id = entity_id
    with Session(candidate_engine) as db:
        access = build_user_access_context(actor(db), db)
        department_id = access.default_scope.department_id
        expected_ids = {str(value) for value in db.scalars(select(model.id).where(
            model.department_id == department_id,
        ))}
        hidden_ids = {str(value) for value in db.scalars(select(model.id).where(
            model.department_id != department_id,
        ))}
        assert expected_ids and hidden_ids
    data = run_devices(candidate_api, question)
    assert data["status"] == "succeeded"
    returned_ids = {row["id"] for row in data["rows"]}
    assert returned_ids and returned_ids <= expected_ids
    assert returned_ids.isdisjoint(hidden_ids)
    assert {row["department_id"] for row in data["rows"]} == {str(department_id)}
    assert len(provider.prompts) == len(provider.executions) == 1
    projection = provider.projections[0]
    assert entity_id in {entry["id"] for entry in projection.entities}
    assert_projection_closed(projection)
    assert provider.executions[0].execution_metadata["runtime_role"] == "queryops_query_runtime"


@pytest.mark.parametrize("restriction", ["nonqueryable", "no_exposure", "missing", "scope_type"])
def test_resource_revocation_removes_candidates_before_next_provider_call(
    candidate_api, candidate_engine, restriction,
):
    assert run_devices(candidate_api)["status"] == "succeeded"
    with Session(candidate_engine) as db:
        resource = db.scalar(select(DataResource).where(
            DataResource.table_name == "devices", DataResource.resource_type == "table",
        ))
        assert resource is not None
        if restriction == "nonqueryable":
            resource.is_queryable = False
        elif restriction == "no_exposure":
            resource.llm_exposure_level = "none"
        elif restriction == "scope_type":
            resource.scope_type = "unassigned_scope_type"
        else:
            db.delete(resource)
        db.commit()

    data = run_devices(candidate_api)
    assert data["status"] != "succeeded"
    assert data["rows"] == []
    _, _, provider = candidate_api
    assert len(provider.prompts) == 2
    assert len(provider.executions) == 1
    projection = provider.projections[-1]
    assert_projection_closed(projection)
    assert "devices" not in {entity["id"] for entity in projection.entities}
    assert all(concept["entity_id"] != "devices" for concept in projection.concepts)
    assert all("devices" not in {item["from_entity"], item["to_entity"]}
               for item in projection.relationships)
    assert "devices" not in {table["name"] for table in provider.prompts[-1]["tables"]}


@pytest.mark.parametrize("restriction", ["scope", "can_query_scoped_data", "can_run_free_query"])
def test_current_scope_and_effective_permission_revocation_after_login(
    candidate_api, candidate_engine, restriction,
):
    assert run_devices(candidate_api)["status"] == "succeeded"
    with Session(candidate_engine) as db:
        user = actor(db)
        if restriction == "scope":
            db.execute(delete(UserAccessScope).where(UserAccessScope.user_id == user.id))
        else:
            permission = db.scalar(select(Permission).where(Permission.key == restriction))
            assert permission is not None
            db.add(UserPermission(user_id=user.id, permission_id=permission.id, effect="deny"))
        db.commit()

    client, token, provider = candidate_api
    response = client.post(
        "/api/v1/queries/run", headers={"X-CSRF-Token": token},
        json={"question": "List devices in my authorized area."},
    )
    if restriction == "can_run_free_query":
        assert response.status_code == 403
        assert len(provider.prompts) == 1
        assert len(provider.executions) == 1
        return
    assert response.status_code == 200
    assert response.json()["data"]["status"] != "succeeded"
    assert response.json()["data"]["rows"] == []
    assert len(provider.prompts) == 2
    assert len(provider.executions) == 1
    assert "devices" not in {entity["id"] for entity in provider.projections[-1].entities}
    assert_projection_closed(provider.projections[-1])
    if restriction == "can_query_scoped_data":
        assert provider.prompts[-1]["tables"] == []
        assert provider.projections[-1].entities == ()


def test_column_allowlist_closes_known_values_definitions_and_relationships(
    candidate_api,
):
    pack = load_it_operations_domain_pack()
    restricted = {"assigned_user_id", "compliance_status", "antivirus_status"}
    pack = replace(pack, tables=tuple(
        replace(table, columns=tuple(column for column in table.columns
                                     if column.name not in restricted))
        if table.name == "devices" else table for table in pack.tables
    ))
    _, _, provider = candidate_api
    app.dependency_overrides[get_query_engine_service] = lambda: QueryEngineService(
        provider=provider, executor=provider.execute, domain_pack_loader=lambda: pack,
    )
    data = run_devices(candidate_api, "List devices and non-compliant devices with their users.")
    assert data["status"] == "succeeded"
    projection = provider.projections[-1]
    assert_projection_closed(projection)
    assert "device_assignee" not in {item["id"] for item in projection.relationships}
    assert "non_compliant_device" not in {item["id"] for item in projection.concepts}
    entity = next(item for item in projection.entities if item["id"] == "devices")
    assert not restricted & entity["known_values"].keys()
    table = next(item for item in provider.prompts[-1]["tables"] if item["name"] == "devices")
    assert not restricted & {column["name"] for column in table["columns"]}


def test_scope_reassignment_changes_rls_rows_without_provider_scope_identifiers(
    candidate_api, candidate_engine,
):
    before = run_devices(candidate_api)
    assert before["status"] == "succeeded"
    with Session(candidate_engine) as db:
        user = actor(db)
        new_scope = db.scalar(select(AccessScope).where(
            AccessScope.scope_type == "department", AccessScope.scope_key == "finance",
        ))
        assert new_scope is not None
        db.execute(delete(UserAccessScope).where(UserAccessScope.user_id == user.id))
        db.add(UserAccessScope(user_id=user.id, scope_id=new_scope.id, is_default=True))
        expected_ids = set(db.scalars(select(Device.id).where(
            Device.department_id == new_scope.department_id,
        )))
        assert expected_ids
        new_department_id = str(new_scope.department_id)
        db.commit()

    after = run_devices(candidate_api)
    assert after["status"] == "succeeded"
    assert {row["id"] for row in after["rows"]} == {str(value) for value in expected_ids}
    assert {row["department_id"] for row in after["rows"]} == {new_department_id}
    assert not {row["id"] for row in before["rows"]} & {row["id"] for row in after["rows"]}
    provider = candidate_api[2]
    assert len(provider.prompts) == 2
    # Authorization content describes scope type, never its assigned identity.
    assert provider.prompts[0] == provider.prompts[1]
