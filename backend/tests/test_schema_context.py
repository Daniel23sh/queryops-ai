from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.access_context import UserAccessContext, build_user_access_context
from app.db.base import Base
from app.domains.it_operations.seed import DATA_RESOURCE_SPECS, seed_database
from app.models.product import AppUser, DataResource
from app.query_engine.schema_context import SchemaContextOptions, build_schema_context


EXPECTED_QUERYABLE_TABLES = sorted(
    spec[0]
    for spec in DATA_RESOURCE_SPECS
    if spec[5] is True and spec[7] != "none"
)


def test_manager_context_includes_allowed_queryable_scoped_resources() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.manager@queryops.local")

        context = build_schema_context(session, access_context)

        assert context["domain"] == "it_operations"
        assert context["domain_name"] == "IT Operations"
        assert context["allowed_tables"] == EXPECTED_QUERYABLE_TABLES
        assert "it_audit_events" not in context["allowed_tables"]
        assert context["scope"] == {
            "has_global_scope": False,
            "type": "department",
            "keys": ["finance"],
        }

        directory_users = table_by_name(context, "directory_users")
        assert directory_users["description"]
        assert directory_users["scope_type"] == "department"
        assert directory_users["scope_column"] == "department_id"
        assert directory_users["resource"]["is_queryable"] is True
        assert directory_users["resource"]["llm_exposure_level"] == "aggregate_safe"
        assert "email" in column_names(directory_users)


def test_analyst_context_includes_allowed_department_resources() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.analyst@queryops.local")

        context = build_schema_context(session, access_context)

        assert context["scope"]["type"] == "department"
        assert context["scope"]["keys"] == ["it"]
        assert context["scope"]["has_global_scope"] is False
        assert "security_events" in context["allowed_tables"]
        assert "it_audit_events" not in context["allowed_tables"]
        assert all(
            table["resource"]["llm_exposure_level"] != "none"
            for table in context["tables"]
        )


def test_admin_context_includes_global_compatible_resources_but_not_non_queryable() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.admin@queryops.local")

        context = build_schema_context(session, access_context)

        assert context["scope"] == {
            "has_global_scope": True,
            "type": "global",
            "keys": ["global"],
        }
        assert context["allowed_tables"] == EXPECTED_QUERYABLE_TABLES
        assert "departments" in context["allowed_tables"]
        assert "licenses" in context["allowed_tables"]
        assert "it_audit_events" not in context["allowed_tables"]
        assert all(table["resource"]["is_queryable"] is True for table in context["tables"])


def test_context_uses_data_resource_queryability_as_source_of_truth() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.manager@queryops.local")
        data_resource_by_table(session, "devices").is_queryable = False

        context = build_schema_context(session, access_context)

        assert "devices" not in context["allowed_tables"]
        assert "devices" not in {table["name"] for table in context["tables"]}


def test_context_uses_data_resource_display_metadata() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.manager@queryops.local")
        resource = data_resource_by_table(session, "directory_users")
        resource.display_name = "Directory Users From DataResource"

        context = build_schema_context(session, access_context)

        assert (
            table_by_name(context, "directory_users")["display_name"]
            == "Directory Users From DataResource"
        )


def test_context_excludes_resources_with_no_llm_exposure() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.admin@queryops.local")
        data_resource_by_table(session, "security_events").llm_exposure_level = "none"

        context = build_schema_context(session, access_context)

        assert "security_events" not in context["allowed_tables"]
        assert "it_audit_events" not in context["allowed_tables"]


def test_context_excludes_tables_outside_domain_pack_and_product_tables() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.admin@queryops.local")
        session.add(
            DataResource(
                id=uuid.uuid4(),
                resource_type="table",
                domain="it_operations",
                schema_name="public",
                table_name="query_runs",
                column_name=None,
                display_name="Query Runs",
                sensitivity_level="internal",
                scope_type=None,
                scope_column=None,
                is_queryable=True,
                is_exportable=False,
                llm_exposure_level="schema_only",
                resource_metadata=None,
            )
        )
        session.add(
            DataResource(
                id=uuid.uuid4(),
                resource_type="table",
                domain="product",
                schema_name="public",
                table_name="app_users",
                column_name=None,
                display_name="Application Users",
                sensitivity_level="internal",
                scope_type=None,
                scope_column=None,
                is_queryable=True,
                is_exportable=False,
                llm_exposure_level="schema_only",
                resource_metadata=None,
            )
        )

        context = build_schema_context(session, access_context)

        serialized = json.dumps(context, sort_keys=True)
        assert "query_runs" not in context["allowed_tables"]
        assert "app_users" not in context["allowed_tables"]
        assert "query_runs" not in serialized
        assert "app_users" not in serialized


def test_context_contains_no_row_data_or_internal_policy_details() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.manager@queryops.local")
        data_resource_by_table(session, "directory_users").resource_metadata = {
            "policy_reason": "missing_scope",
            "sample_values": ["demo.manager@queryops.local"],
            "secret": "do-not-leak",
            "session_cookie": "qo_session=private",
        }

        context = build_schema_context(session, access_context)

        serialized = json.dumps(context, sort_keys=True).lower()
        for forbidden in (
            "demo.manager@queryops.local",
            "demo manager",
            "qo_session",
            "csrf",
            "session_cookie",
            "policy_reason",
            "missing_scope",
            "resource_not_queryable",
            "do-not-leak",
        ):
            assert forbidden not in serialized


def test_context_ordering_is_deterministic() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.analyst@queryops.local")

        first = build_schema_context(session, access_context)
        second = build_schema_context(session, access_context)

        assert first == second
        assert first["allowed_tables"] == sorted(first["allowed_tables"])
        assert [table["name"] for table in first["tables"]] == sorted(
            first["allowed_tables"]
        )
        for table in first["tables"]:
            assert column_names(table) == sorted(column_names(table))
        assert [term["name"] for term in first["business_terms"]] == sorted(
            term["name"] for term in first["business_terms"]
        )
        for term in first["business_terms"]:
            assert term["related_tables"] == sorted(term["related_tables"])


def test_template_filter_limits_context_without_exposing_template_sql() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.manager@queryops.local")

        context = build_schema_context(
            session,
            access_context,
            options=SchemaContextOptions(
                template_id="unused_licenses_by_department",
            ),
        )

        assert context["allowed_tables"] == ["license_assignments", "licenses"]
        assert [table["name"] for table in context["tables"]] == [
            "license_assignments",
            "licenses",
        ]
        assert context["template"] == {
            "id": "unused_licenses_by_department",
            "required_action": "query:scoped_data",
            "scope_type": "department",
        }
        assert [term["name"] for term in context["business_terms"]] == [
            "unused license"
        ]
        assert "SELECT " not in json.dumps(context)


def test_domain_filter_can_return_empty_context_for_other_domain() -> None:
    with session_scope() as session:
        seed_database(session, profile_name="small", reset=True)
        access_context = access_context_for(session, "demo.manager@queryops.local")

        context = build_schema_context(
            session,
            access_context,
            options=SchemaContextOptions(domain_id="unknown_domain"),
        )

        assert context["domain"] == "it_operations"
        assert context["allowed_tables"] == []
        assert context["tables"] == []
        assert context["business_terms"] == []


def access_context_for(session: Session, email: str) -> UserAccessContext:
    return build_user_access_context(user_by_email(session, email), session)


def user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def data_resource_by_table(session: Session, table_name: str) -> DataResource:
    resource = session.scalar(
        select(DataResource).where(DataResource.table_name == table_name)
    )
    assert resource is not None
    return resource


def table_by_name(context: dict, table_name: str) -> dict:
    table = next(
        (table for table in context["tables"] if table["name"] == table_name),
        None,
    )
    assert table is not None
    return table


def column_names(table: dict) -> list[str]:
    return [column["name"] for column in table["columns"]]


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
