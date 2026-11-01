"""Output identity through the real governed PostgreSQL executor; no provider."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.domains.it_operations.seed import seed_database
from app.domains.it_operations.models import Department, Device
from app.evaluation.baseline import execute_evaluation_baseline
from app.evaluation.context import resolve_evaluation_identity
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.provenance import extract_evaluation_query_provenance
from app.evaluation.scoring import score_evaluation_semantic_contract
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.schema_context import build_schema_context
from app.query_engine.semantic_conformance import check_semantic_conformance
from app.query_engine.semantic_grounding import build_semantic_grounding_projection
from app.query_engine.semantic_plan import SemanticPlan, validate_semantic_plan
from app.query_engine.sql_executor import (
    execute_validated_sql,
    query_runtime_transaction,
)
from app.query_engine.sql_renderer import render_validated_semantic_plan
from app.query_engine.sql_validator import validate_sql
from tests.action_postgres_test_db import validated_disposable_database_url
from tests.test_evaluation_semantic_corrections import compare
from tests.test_sql_executor_postgres import access_context_for, run_alembic_upgrade


@pytest.fixture(scope="module")
def identity_engine():
    target = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not target:
        pytest.skip(
            "Output identity requires an explicit disposable PostgreSQL database."
        )
    validated_disposable_database_url(target)
    run_alembic_upgrade(target)
    engine = create_engine(target)
    try:
        with Session(engine) as db:
            seed_database(
                db,
                profile_name="medium",
                reset=True,
                reference_now=datetime.now(UTC).replace(microsecond=0),
            )
            department = db.scalar(select(Department).where(Department.name == "IT"))
            assert department is not None
            db.add(
                Device(
                    id=UUID(int=1),
                    hostname="W6b-null-assignee",
                    department_id=department.id,
                    assigned_user_id=None,
                    os="Synthetic",
                    os_version="1",
                    device_type="laptop",
                )
            )
            db.commit()
        yield engine
    finally:
        engine.dispose()


def test_canonical_hard005_retains_both_ids_and_unchanged_v2_contract(identity_engine):
    pack = load_it_operations_domain_pack()
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-hard-005"]
    contract = asdict(case.semantic_contract)
    plan = SemanticPlan.model_validate_json(
        json.dumps(
            {
                "entity_ids": case.expected_tables,
                "concept_ids": contract["required_concept_ids"],
                "composition_rule_ids": [],
                "metric_id": None,
                "distinct": True,
                "literal_filters": [],
                "relationships": [
                    {"relationship_id": name, "join_type": "inner"}
                    for name in ("device_assignee", "software_install_device")
                ],
                "output_fields": contract["output_fields"],
                "aggregations": [],
                "group_by": [],
                "having": [],
                "order_by": [],
                "limit": None,
            }
        )
    )
    with Session(identity_engine) as db:
        actor = resolve_evaluation_identity(db, case)
        schema = build_schema_context(db, actor.access_context)
        projection = build_semantic_grounding_projection(
            pack.semantic_catalog,
            case.question,
            schema,
            {"scope_type": "department", "scope_reference_resolved": True},
        )
        checked = validate_semantic_plan(
            plan,
            domain_pack=pack,
            projection=projection,
            schema_context=schema,
            scope_reference_resolved=True,
        )
        sql = render_validated_semantic_plan(checked, pack)
        validation = validate_sql(sql, schema)
        assert validation.valid
        assert check_semantic_conformance(
            plan=checked,
            candidate_sql=sql,
            safety_result=validation,
            domain_pack=pack,
            schema_context=schema,
        ).valid
        assert score_evaluation_semantic_contract(case, checked.as_observation()).passed
        with query_runtime_transaction(
            identity_engine,
            actor.access_context,
            isolation_level="repeatable_read",
            timezone_name="UTC",
        ) as runtime:
            actual = execute_validated_sql(runtime, actor.access_context, validation)
            baseline = execute_evaluation_baseline(
                db,
                actor.access_context,
                case,
                pack,
                executor=lambda _, access, validated, *, options=None: (
                    execute_validated_sql(runtime, access, validated, options=options)
                ),
            )
        assert actual.status == "succeeded"
        assert actual.row_count == baseline.row_count > 0
        assert actual.columns == ["devices__id", "directory_users__id"]
        assert all(set(row) == set(actual.columns) for row in actual.rows)
        assert any(
            row["devices__id"] != row["directory_users__id"] for row in actual.rows
        )
        assert actual.execution_metadata["delivery_completeness"] == "complete"
        assert compare(
            case, validation.sanitized_sql, baseline.rows, actual.rows
        ).passed


@pytest.mark.parametrize(
    "select_list",
    [
        "d.id, du.id",
        "d.id AS ID, du.id AS id",
        f"d.id AS {'a' * 63}x, du.id AS {'a' * 63}y",
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_ambiguous_legacy_labels_fail_before_mapping_even_when_empty(
    identity_engine,
    select_list,
    empty,
):
    with Session(identity_engine) as db:
        actor = access_context_for(db, "demo.analyst@queryops.local")
        schema = build_schema_context(db, actor)
        sql = (
            f"SELECT {select_list} FROM devices d "
            "JOIN directory_users du ON du.id = d.assigned_user_id"
            + (" WHERE 1 = 0" if empty else "")
        )
        validation = validate_sql(sql, schema)
        assert validation.valid
        result = execute_validated_sql(identity_engine, actor, validation)
    assert result.status == "failed"
    assert result.error_code == "ambiguous_output_columns"
    assert result.rows == result.columns == []
    assert result.row_count == 0
    assert result.public_error == "Query execution failed safely."
    assert result.execution_metadata["delivery_completeness"] == "unknown"


def test_explicit_unique_quoted_aliases_and_null_values_remain_compatible(
    identity_engine,
):
    with Session(identity_engine) as db:
        actor = access_context_for(db, "demo.analyst@queryops.local")
        schema = build_schema_context(db, actor)
        validation = validate_sql(
            'SELECT d.id AS "DeviceID", du.id AS "UserID" FROM devices d '
            "LEFT JOIN directory_users du ON du.id = d.assigned_user_id "
            "WHERE d.hostname = 'W6b-null-assignee' ORDER BY d.id",
            schema,
        )
        assert validation.valid
        result = execute_validated_sql(identity_engine, actor, validation)
    assert result.status == "succeeded"
    assert result.columns == ["DeviceID", "UserID"]
    assert result.row_count > 0
    assert all(set(row) == {"DeviceID", "UserID"} for row in result.rows)
    assert any(row["UserID"] is None for row in result.rows)


def test_generated_labels_match_cursor_and_provenance_after_pg_normalization(
    identity_engine,
):
    from tests.test_sql_renderer import _aggregation, _plan

    identifiers = ("Count", "count", "x" * 100 + "a", "x" * 100 + "b")
    plan = _plan(
        entity_ids=("devices",),
        aggregations=tuple(_aggregation(value, "count") for value in identifiers),
    )
    pack = load_it_operations_domain_pack()
    with Session(identity_engine) as db:
        actor = access_context_for(db, "demo.analyst@queryops.local")
        schema = build_schema_context(db, actor)
        projection = build_semantic_grounding_projection(
            pack.semantic_catalog,
            "Count devices",
            schema,
            {"scope_type": "department", "scope_reference_resolved": True},
        )
        checked = validate_semantic_plan(
            plan,
            domain_pack=pack,
            projection=projection,
            schema_context=schema,
            scope_reference_resolved=True,
        )
        sql = render_validated_semantic_plan(checked, pack)
        validation = validate_sql(sql, schema)
        assert validation.valid
        result = execute_validated_sql(identity_engine, actor, validation)
    assert result.status == "succeeded"
    assert len(result.columns) == len(set(result.columns)) == 4
    assert all(len(name.encode()) <= 63 for name in result.columns)
    assert [
        item.presentation_name
        for item in extract_evaluation_query_provenance(
            validation.sanitized_sql
        ).outputs
    ] == result.columns
    assert set(result.rows[0]) == set(result.columns)
    assert len(set(result.rows[0].values())) == 1
