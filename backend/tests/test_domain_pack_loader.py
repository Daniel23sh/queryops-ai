from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.domains.it_operations.seed import DATA_RESOURCE_SPECS
from app.query_engine.domain_pack_loader import (
    load_domain_pack,
    load_it_operations_domain_pack,
)
from app.query_engine.errors import DomainPackValidationError


DOMAIN_PACK_DIR = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "domains"
    / "it_operations"
    / "domain_pack"
)

EXPECTED_TABLES = {spec[0] for spec in DATA_RESOURCE_SPECS}
EXPECTED_QUERYABLE_TABLES = {
    spec[0] for spec in DATA_RESOURCE_SPECS if spec[5] is True
}
EXPECTED_NON_QUERYABLE_TABLES = {
    spec[0] for spec in DATA_RESOURCE_SPECS if spec[5] is False
}


def test_it_operations_domain_pack_files_exist() -> None:
    assert (DOMAIN_PACK_DIR / "schema.yaml").is_file()
    assert (DOMAIN_PACK_DIR / "business_terms.yaml").is_file()
    assert (DOMAIN_PACK_DIR / "query_templates.yaml").is_file()


def test_load_it_operations_domain_pack_returns_typed_pack() -> None:
    pack = load_it_operations_domain_pack()

    assert pack.domain_id == "it_operations"
    assert pack.name == "IT Operations"
    assert set(pack.tables_by_name) == EXPECTED_TABLES
    assert set(pack.allowed_resource_table_names) == EXPECTED_QUERYABLE_TABLES

    directory_users = pack.table("directory_users")
    assert directory_users.scope_type == "department"
    assert directory_users.scope_column == "department_id"
    assert directory_users.queryable is True
    assert {"id", "department_id", "email", "last_login_at"}.issubset(
        directory_users.columns_by_name
    )

    departments = pack.table("departments")
    assert departments.scope_type is None
    assert departments.scope_column is None

    audit_events = pack.table("it_audit_events")
    assert audit_events.queryable is False
    assert "it_audit_events" not in pack.allowed_resource_table_names


def test_domain_pack_contains_required_templates_and_terms() -> None:
    pack = load_it_operations_domain_pack()

    assert {
        "inactive_users_by_department",
        "unused_licenses_by_department",
        "high_severity_security_events_by_department",
        "non_compliant_devices_by_department",
        "open_support_tickets_by_department",
    }.issubset(pack.templates_by_id)
    assert {"inactive user", "unused license", "non-compliant device"}.issubset(
        pack.business_terms_by_name
    )

    template = pack.template("unused_licenses_by_department")
    assert template.required_action == "query:scoped_data"
    assert template.required_permission == "can_query_scoped_data"
    assert template.scope_type == "department"
    assert template.referenced_tables == ("license_assignments", "licenses")
    assert template.sql


def test_domain_pack_ordering_is_deterministic() -> None:
    pack = load_it_operations_domain_pack()

    assert [table.name for table in pack.tables] == sorted(pack.tables_by_name)
    assert [template.id for template in pack.query_templates] == sorted(
        pack.templates_by_id
    )
    assert [term.name for term in pack.business_terms] == sorted(
        pack.business_terms_by_name
    )
    for table in pack.tables:
        assert [column.name for column in table.columns] == sorted(table.columns_by_name)


def test_query_templates_reference_only_queryable_resources() -> None:
    pack = load_it_operations_domain_pack()

    for template in pack.query_templates:
        assert template.referenced_tables
        assert set(template.referenced_tables).isdisjoint(EXPECTED_NON_QUERYABLE_TABLES)
        assert set(template.referenced_tables) <= set(pack.allowed_resource_table_names)


def test_loader_rejects_missing_required_files(tmp_path: Path) -> None:
    _write_json(tmp_path / "schema.yaml", _minimal_schema())
    _write_json(tmp_path / "query_templates.yaml", {"templates": []})

    with pytest.raises(DomainPackValidationError, match="business_terms.yaml"):
        load_domain_pack(tmp_path)


def test_loader_rejects_malformed_schema_table(tmp_path: Path) -> None:
    schema = _minimal_schema()
    schema["tables"][0].pop("columns")
    _write_minimal_pack(tmp_path, schema=schema)

    with pytest.raises(DomainPackValidationError, match="tables\\[0\\].columns"):
        load_domain_pack(tmp_path)


def test_loader_rejects_duplicate_template_ids(tmp_path: Path) -> None:
    templates = {
        "templates": [
            _minimal_template("duplicate_template"),
            _minimal_template("duplicate_template"),
        ]
    }
    _write_minimal_pack(tmp_path, templates=templates)

    with pytest.raises(DomainPackValidationError, match="Duplicate query template id"):
        load_domain_pack(tmp_path)


def test_loader_rejects_template_that_references_unknown_table(tmp_path: Path) -> None:
    templates = {
        "templates": [
            _minimal_template(
                "unknown_table_template",
                referenced_tables=["directory_users", "missing_table"],
            )
        ]
    }
    _write_minimal_pack(tmp_path, templates=templates)

    with pytest.raises(DomainPackValidationError, match="unknown table"):
        load_domain_pack(tmp_path)


def test_loader_rejects_template_that_references_non_queryable_table(
    tmp_path: Path,
) -> None:
    templates = {
        "templates": [
            _minimal_template(
                "audit_template",
                referenced_tables=["it_audit_events"],
            )
        ]
    }
    _write_minimal_pack(tmp_path, templates=templates)

    with pytest.raises(DomainPackValidationError, match="not queryable"):
        load_domain_pack(tmp_path)


def _write_minimal_pack(
    pack_dir: Path,
    *,
    schema: dict[str, Any] | None = None,
    business_terms: dict[str, Any] | None = None,
    templates: dict[str, Any] | None = None,
) -> None:
    _write_json(pack_dir / "schema.yaml", schema or _minimal_schema())
    _write_json(
        pack_dir / "business_terms.yaml",
        business_terms
        or {
            "terms": [
                {
                    "name": "inactive user",
                    "description": "Directory user without a recent login.",
                    "related_tables": ["directory_users"],
                }
            ]
        },
    )
    _write_json(
        pack_dir / "query_templates.yaml",
        templates
        or {
            "templates": [
                _minimal_template("inactive_users_by_department"),
            ]
        },
    )


def _minimal_schema() -> dict[str, Any]:
    return {
        "domain": {
            "id": "it_operations",
            "name": "IT Operations",
            "version": "1",
        },
        "allowed_resource_table_names": ["directory_users"],
        "tables": [
            {
                "name": "directory_users",
                "display_name": "Directory Users",
                "description": "Workforce identity records.",
                "scope_type": "department",
                "scope_column": "department_id",
                "queryable": True,
                "columns": [
                    {
                        "name": "id",
                        "data_type": "uuid",
                        "description": "Directory user identifier.",
                    },
                    {
                        "name": "department_id",
                        "data_type": "uuid",
                        "description": "Department scope identifier.",
                    },
                ],
            },
            {
                "name": "it_audit_events",
                "display_name": "IT Audit Events",
                "description": "Internal IT audit event records.",
                "scope_type": "department",
                "scope_column": "department_id",
                "queryable": False,
                "columns": [
                    {
                        "name": "id",
                        "data_type": "uuid",
                        "description": "Audit event identifier.",
                    },
                    {
                        "name": "department_id",
                        "data_type": "uuid",
                        "description": "Department scope identifier.",
                    },
                ],
            },
        ],
    }


def _minimal_template(
    template_id: str,
    *,
    referenced_tables: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": template_id,
        "title": "Inactive users by department",
        "description": "Find inactive directory users inside the current scope.",
        "category": "Identity",
        "natural_language_question": "Show inactive users in my department.",
        "required_action": "query:scoped_data",
        "required_permission": "can_query_scoped_data",
        "scope_type": "department",
        "referenced_tables": referenced_tables or ["directory_users"],
        "parameters": [
            {
                "name": "inactive_days",
                "data_type": "integer",
                "description": "Number of days without login activity.",
                "required": False,
                "default": 90,
            }
        ],
        "sql": "SELECT id FROM directory_users WHERE last_login_at IS NULL",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
