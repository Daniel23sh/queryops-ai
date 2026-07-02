from __future__ import annotations

import pytest

from app.query_engine.sql_validator import (
    SQLValidationOptions,
    SQLValidationResult,
    validate_sql,
)


PUBLIC_ERROR = "SQL is not allowed for safe read-only querying."


def test_valid_select_passes() -> None:
    result = validate_sql(
        """
        SELECT email, last_login_at
        FROM directory_users
        WHERE department_id IS NOT NULL
        LIMIT 25
        """,
        schema_context(),
    )

    assert result.valid is True
    assert result.sanitized_sql == (
        "SELECT email, last_login_at FROM directory_users "
        "WHERE department_id IS NOT NULL LIMIT 25"
    )
    assert result.referenced_tables == ["directory_users"]
    assert result.referenced_columns["directory_users"] == [
        "department_id",
        "email",
        "last_login_at",
    ]
    assert result.error_code is None
    assert result.public_error is None


def test_valid_with_select_passes() -> None:
    result = validate_sql(
        """
        WITH inactive AS (
            SELECT id, department_id
            FROM directory_users
            WHERE account_status = 'active'
        )
        SELECT department_id
        FROM inactive
        LIMIT 50
        """,
        schema_context(),
    )

    assert result.valid is True
    assert result.sanitized_sql.endswith("FROM inactive LIMIT 50")
    assert result.referenced_tables == ["directory_users"]
    assert "inactive" not in result.referenced_tables


def test_select_without_limit_gets_deterministic_default_limit() -> None:
    result = validate_sql(
        "SELECT email FROM directory_users WHERE account_status = 'active'",
        schema_context(),
    )

    assert result.valid is True
    assert result.sanitized_sql == (
        "SELECT email FROM directory_users WHERE account_status = 'active' LIMIT 100"
    )


def test_too_large_limit_is_reduced_to_safe_max() -> None:
    result = validate_sql(
        "SELECT email FROM directory_users LIMIT 9999",
        schema_context(),
    )

    assert result.valid is True
    assert result.sanitized_sql == "SELECT email FROM directory_users LIMIT 500"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT email FROM directory_users; SELECT name FROM departments",
        "SELECT email FROM directory_users; DROP TABLE directory_users",
    ],
)
def test_multiple_or_semicolon_chained_statements_are_rejected(sql: str) -> None:
    result = validate_sql(sql, schema_context())

    assert_denied(result, "multiple_statements")


def test_comments_hiding_sql_are_rejected() -> None:
    result = validate_sql(
        "SELECT email FROM directory_users -- ; DROP TABLE departments\nLIMIT 10",
        schema_context(),
    )

    assert_denied(result, "comments_not_allowed")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO directory_users (email) VALUES ('x@example.com')",
        "UPDATE directory_users SET account_status = 'disabled'",
        "DELETE FROM directory_users",
        "MERGE INTO directory_users USING departments ON true WHEN MATCHED THEN DELETE",
    ],
)
def test_dml_is_rejected(sql: str) -> None:
    result = validate_sql(sql, schema_context())

    assert_denied(result, "prohibited_statement")


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE directory_users",
        "ALTER TABLE directory_users ADD COLUMN unsafe text",
        "CREATE TABLE unsafe (id uuid)",
        "TRUNCATE TABLE directory_users",
    ],
)
def test_ddl_is_rejected(sql: str) -> None:
    result = validate_sql(sql, schema_context())

    assert_denied(result, "prohibited_statement")


@pytest.mark.parametrize(
    "sql",
    [
        "GRANT SELECT ON directory_users TO public",
        "REVOKE SELECT ON directory_users FROM public",
        "COPY directory_users TO STDOUT",
        "CALL unsafe_proc()",
        "EXECUTE unsafe_plan",
        "DO $$ BEGIN RAISE NOTICE 'x'; END $$",
        "SET ROLE queryops",
        "RESET ROLE",
        "EXPLAIN ANALYZE SELECT email FROM directory_users",
    ],
)
def test_privileged_session_or_procedural_commands_are_rejected(sql: str) -> None:
    result = validate_sql(sql, schema_context())

    assert_denied(result, "prohibited_statement")


def test_unknown_table_is_rejected() -> None:
    result = validate_sql(
        "SELECT id FROM unknown_table LIMIT 10",
        schema_context(),
    )

    assert_denied(result, "table_not_allowed")
    assert "unknown_table" in result.reason


def test_non_queryable_resource_is_rejected_even_when_present_in_context() -> None:
    context = schema_context()
    context["allowed_tables"].append("security_events")
    context["tables"].append(
        table_context(
            "security_events",
            columns=["id", "department_id", "severity"],
            is_queryable=False,
        )
    )

    result = validate_sql(
        "SELECT id FROM security_events LIMIT 10",
        context,
    )

    assert_denied(result, "non_queryable_resource")


def test_it_audit_events_are_rejected() -> None:
    context = schema_context()
    context["allowed_tables"].append("it_audit_events")
    context["tables"].append(
        table_context(
            "it_audit_events",
            columns=["id", "department_id", "event_type"],
            is_queryable=False,
            llm_exposure_level="none",
        )
    )

    result = validate_sql(
        "SELECT id FROM it_audit_events LIMIT 10",
        context,
    )

    assert_denied(result, "forbidden_table")


def test_product_table_is_rejected_when_not_explicitly_in_schema_context() -> None:
    result = validate_sql(
        "SELECT id FROM app_users LIMIT 10",
        schema_context(),
    )

    assert_denied(result, "table_not_allowed")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM directory_users LIMIT 10",
        "SELECT du.* FROM directory_users du LIMIT 10",
    ],
)
def test_select_star_is_rejected(sql: str) -> None:
    result = validate_sql(sql, schema_context())

    assert_denied(result, "select_star_not_allowed")


def test_queryable_scoped_domain_tables_are_allowed() -> None:
    result = validate_sql(
        "SELECT id, compliance_status FROM devices WHERE department_id IS NOT NULL",
        schema_context(),
    )

    assert result.valid is True
    assert result.sanitized_sql.endswith("LIMIT 100")
    assert result.referenced_tables == ["devices"]


def test_reference_tables_are_allowed_when_present_in_context() -> None:
    result = validate_sql(
        "SELECT id, name FROM departments LIMIT 20",
        schema_context(),
    )

    assert result.valid is True
    assert result.referenced_tables == ["departments"]


def test_sanitized_sql_is_deterministic() -> None:
    sql = "  SELECT   email,\n last_login_at   FROM   directory_users   LIMIT 10;  "

    first = validate_sql(sql, schema_context())
    second = validate_sql(sql, schema_context())

    assert first == second
    assert first.sanitized_sql == (
        "SELECT email, last_login_at FROM directory_users LIMIT 10"
    )


def test_invalid_limit_is_rejected_safely() -> None:
    result = validate_sql(
        "SELECT email FROM directory_users LIMIT ALL",
        schema_context(),
    )

    assert_denied(result, "invalid_limit")


def test_safe_public_error_does_not_leak_parser_or_table_details() -> None:
    result = validate_sql(
        "SELECT id FROM missing_sensitive_table LIMIT 10",
        schema_context(),
    )

    assert result.valid is False
    assert result.sanitized_sql is None
    assert result.public_error == PUBLIC_ERROR
    assert "missing_sensitive_table" not in result.public_error
    assert "parser" not in result.public_error.lower()
    assert "traceback" not in result.public_error.lower()


def test_custom_limit_options_are_applied() -> None:
    result = validate_sql(
        "SELECT email FROM directory_users",
        schema_context(),
        options=SQLValidationOptions(default_limit=25, max_limit=50),
    )

    assert result.valid is True
    assert result.sanitized_sql == "SELECT email FROM directory_users LIMIT 25"


def assert_denied(result: SQLValidationResult, error_code: str) -> None:
    assert result.valid is False
    assert result.sanitized_sql is None
    assert result.referenced_tables == []
    assert result.error_code == error_code
    assert result.public_error == PUBLIC_ERROR


def schema_context() -> dict:
    tables = [
        table_context(
            "departments",
            columns=["id", "name"],
            llm_exposure_level="schema_only",
            sensitivity_level="internal",
            scope_type=None,
            scope_column=None,
        ),
        table_context(
            "devices",
            columns=["id", "department_id", "compliance_status"],
        ),
        table_context(
            "directory_users",
            columns=[
                "id",
                "department_id",
                "email",
                "last_login_at",
                "account_status",
            ],
        ),
    ]
    return {
        "domain": "it_operations",
        "allowed_tables": [table["name"] for table in tables],
        "allowed_columns": {
            table["name"]: [column["name"] for column in table["columns"]]
            for table in tables
        },
        "tables": tables,
    }


def table_context(
    table_name: str,
    *,
    columns: list[str],
    is_queryable: bool = True,
    llm_exposure_level: str = "aggregate_safe",
    sensitivity_level: str = "scoped_restricted",
    scope_type: str | None = "department",
    scope_column: str | None = "department_id",
) -> dict:
    return {
        "name": table_name,
        "display_name": table_name.replace("_", " ").title(),
        "description": f"{table_name} table.",
        "scope_type": scope_type,
        "scope_column": scope_column,
        "columns": [
            {
                "name": column,
                "data_type": "string",
                "description": f"{column} column.",
                "nullable": True,
            }
            for column in columns
        ],
        "resource": {
            "resource_type": "table",
            "schema_name": "public",
            "table_name": table_name,
            "sensitivity_level": sensitivity_level,
            "scope_type": scope_type,
            "scope_column": scope_column,
            "is_queryable": is_queryable,
            "llm_exposure_level": llm_exposure_level,
        },
    }
