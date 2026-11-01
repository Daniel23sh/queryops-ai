"""Synthetic output-identity fixtures for explicitly disposable PostgreSQL only."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.access_context import build_user_access_context
from app.domains.it_operations.models import Department, Device, DirectoryUser, License
from app.domains.it_operations.seed import seed_database
from app.models.product import (
    AppUser,
    Dashboard,
    DashboardCard,
    DataResource,
    QueryRun,
    SavedQuery,
)
from app.query_engine.delivery import bound_metadata
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.schema_context import build_schema_context
from app.query_engine.semantic_catalog import SemanticCatalogProjection
from app.query_engine.semantic_conformance import check_semantic_conformance
from app.query_engine.semantic_plan import SemanticPlan, validate_semantic_plan
from app.query_engine.sql_renderer import render_validated_semantic_plan
from app.query_engine.sql_validator import validate_sql
from scripts.prepare_m8_e2e import UnsafeE2EDatabaseError, validated_e2e_database_url


def identity_plan(kind: str) -> SemanticPlan:
    def field(entity, column):
        return {"entity_id": entity, "column": column}

    values = dict(
        entity_ids=["devices", "directory_users"],
        concept_ids=[],
        composition_rule_ids=[],
        metric_id=None,
        distinct=False,
        literal_filters=[],
        relationships=[{"relationship_id": "device_assignee", "join_type": "inner"}],
        output_fields=[
            field("devices", "id"),
            field("directory_users", "id"),
            field("devices", "hostname"),
            field("devices", "last_seen_at"),
        ],
        aggregations=[],
        group_by=[],
        having=[],
        order_by=[],
        limit=50,
    )
    if kind == "aggregate":
        values.update(
            entity_ids=["licenses"],
            relationships=[],
            output_fields=[field("licenses", "product_name")],
            literal_filters=[
                {
                    "field": field("licenses", "vendor"),
                    "operator": "in",
                    "value": [
                        "W6b identity fixture 0",
                        "W6b identity fixture 1",
                        "W6b identity fixture 2",
                    ],
                }
            ],
            aggregations=[
                {
                    "id": "product_name",
                    "function": "count",
                    "field": None,
                    "distinct": False,
                }
            ],
            group_by=[field("licenses", "product_name")],
        )
    elif kind == "names":
        values.update(
            entity_ids=["groups", "departments"],
            relationships=[
                {"relationship_id": "group_department", "join_type": "inner"}
            ],
            output_fields=[field("groups", "name"), field("departments", "name")],
        )
    else:
        values["literal_filters"] = [
            {
                "field": field("devices", "hostname"),
                "operator": "in",
                "value": ["W6b-Finance-1", "W6b-IT-1", "W6b-IT-2"],
            }
        ]
    return SemanticPlan.model_validate_json(json.dumps(values))


def rendered_validation(db: Session, user: AppUser, kind: str):
    domain = load_it_operations_domain_pack()
    schema = build_schema_context(db, build_user_access_context(user, db))
    plan = identity_plan(kind)
    catalog = domain.semantic_catalog
    projection = SemanticCatalogProjection(
        catalog.id,
        catalog.version,
        catalog.digest,
        tuple({"id": item} for item in plan.entity_ids),
        tuple({"id": item.relationship_id} for item in plan.relationships),
        (),
        (),
        (),
        (),
        (),
        (),
        (),
    )
    checked = validate_semantic_plan(
        plan,
        domain_pack=domain,
        projection=projection,
        schema_context=schema,
        scope_reference_resolved=False,
    )
    sql = render_validated_semantic_plan(checked, domain)
    validation = validate_sql(sql, schema)
    assert validation.valid and validation.sanitized_sql
    conformance = check_semantic_conformance(
        plan=checked,
        candidate_sql=validation.sanitized_sql,
        safety_result=validation,
        domain_pack=domain,
        schema_context=schema,
    )
    assert conformance.valid, conformance.reason_code
    return validation


def prepare_output_identity_state(db: Session) -> dict:
    seed_database(db, profile_name="small", reset=True)
    analyst = db.scalar(
        select(AppUser).where(AppUser.email == "demo.analyst@queryops.local")
    )
    admin = db.scalar(
        select(AppUser).where(AppUser.email == "demo.admin@queryops.local")
    )
    assert analyst is not None and admin is not None
    expected = []
    departments = {}
    for name, count in (("IT", 2), ("Finance", 1)):
        department = db.scalar(select(Department).where(Department.name == name))
        assert department is not None
        departments[name] = department
        assignee = db.scalar(
            select(DirectoryUser)
            .where(DirectoryUser.department_id == department.id)
            .order_by(DirectoryUser.id)
        )
        assert assignee is not None
        for number in range(1, count + 1):
            hostname = f"W6b-{name}-{number}"
            device_id = uuid5(
                NAMESPACE_URL, f"queryops-synthetic-output-identity/{hostname}"
            )
            db.add(
                Device(
                    id=device_id,
                    hostname=hostname,
                    department_id=department.id,
                    assigned_user_id=assignee.id,
                    os="Synthetic",
                    os_version="1",
                    device_type="laptop",
                    last_seen_at=None,
                )
            )
            expected.append(
                {
                    "devices__id": str(device_id),
                    "directory_users__id": str(assignee.id),
                    "hostname": hostname,
                    "last_seen_at": None,
                }
            )
    db.add_all(
        [
            License(
                id=uuid5(
                    NAMESPACE_URL,
                    f"queryops-synthetic-output-identity/license/{number}",
                ),
                product_name=name,
                vendor=f"W6b identity fixture {number}",
                monthly_cost_usd=3,
            )
            for number, name in enumerate(("=W6b", "=W6b", "Normal"))
        ]
    )
    for resource in db.scalars(
        select(DataResource).where(
            DataResource.table_name.in_(["directory_users", "devices", "groups"])
        )
    ):
        resource.is_exportable = True
    dashboard = Dashboard(
        owner_user_id=analyst.id, title="Output identity", visibility_scope="personal"
    )
    shared = Dashboard(
        owner_user_id=admin.id,
        title="Shared output identity",
        visibility_scope="department",
        department_id=departments["IT"].id,
    )
    db.add_all([dashboard, shared])
    db.flush()
    state = {
        "dashboard_id": str(dashboard.id),
        "query_runs": {},
        "expected_admin": expected,
        "expected_analyst": [
            row for row in expected if row["hostname"].startswith("W6b-IT-")
        ],
    }
    for kind in ("identity", "aggregate", "names", "legacy"):
        validation = rendered_validation(
            db, analyst, "identity" if kind == "legacy" else kind
        )
        sql = validation.sanitized_sql
        if kind == "legacy":
            sql = "SELECT devices.id, directory_users.id FROM devices JOIN directory_users ON devices.assigned_user_id = directory_users.id LIMIT 50"
        run = QueryRun(
            user_id=analyst.id,
            status="succeeded",
            natural_language_question=f"Output identity {kind}",
            executed_sql=sql,
            row_count=1,
            duration_ms=1,
            completed_at=datetime.now(UTC),
            query_metadata={
                "referenced_tables": validation.referenced_tables,
                "validation": bound_metadata(validation),
            },
        )
        db.add(run)
        db.flush()
        state["query_runs"][kind] = str(run.id)
    validation = rendered_validation(db, admin, "identity")
    saved = SavedQuery(
        owner_user_id=admin.id,
        name="Shared identities",
        natural_language_question="Synthetic identities",
        visibility_scope="department",
        department_id=departments["IT"].id,
        parameters={},
    )
    db.add(saved)
    db.flush()
    db.add(
        QueryRun(
            user_id=admin.id,
            saved_query_id=saved.id,
            status="succeeded",
            executed_sql=validation.sanitized_sql,
            row_count=3,
            duration_ms=1,
            completed_at=datetime.now(UTC),
            query_metadata={
                "referenced_tables": validation.referenced_tables,
                "validation": bound_metadata(validation),
            },
        )
    )
    card = DashboardCard(
        dashboard_id=shared.id,
        saved_query_id=saved.id,
        title="Shared identities",
        card_type="table",
        position=0,
    )
    db.add(card)
    db.commit()
    state["shared_card_id"] = str(card.id)
    return state


def main() -> int:
    try:
        target = validated_e2e_database_url(
            os.environ.get("M8_E2E_DATABASE_URL", ""),
            disposable_opt_in=os.environ.get("M8_E2E_DATABASE_DISPOSABLE"),
            application_url=os.environ.get("DATABASE_URL"),
            application_database_name=os.environ.get("POSTGRES_DB", "queryops"),
        )
        engine = create_engine(target)
        try:
            with Session(engine) as db:
                state = prepare_output_identity_state(db)
            print(json.dumps(state))
        finally:
            engine.dispose()
    except (UnsafeE2EDatabaseError, SQLAlchemyError):
        print("Output identity fixture failed safely.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
