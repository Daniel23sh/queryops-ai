from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.query_engine.domain_pack import (
    BusinessTerm,
    DomainColumn,
    DomainPack,
    DomainTable,
    QueryTemplate,
    QueryTemplateParameter,
)
from app.query_engine.errors import DomainPackValidationError


APP_ROOT = Path(__file__).resolve().parents[1]
IT_OPERATIONS_DOMAIN_PACK_DIR = (
    APP_ROOT / "domains" / "it_operations" / "domain_pack"
)
REQUIRED_DOMAIN_PACK_FILES = (
    "schema.yaml",
    "business_terms.yaml",
    "query_templates.yaml",
)


def load_it_operations_domain_pack() -> DomainPack:
    return load_domain_pack(IT_OPERATIONS_DOMAIN_PACK_DIR)


def load_domain_pack(pack_path: str | Path) -> DomainPack:
    base_path = Path(pack_path)
    if not base_path.is_dir():
        raise DomainPackValidationError(f"Domain pack directory not found: {base_path}")

    documents = {
        file_name: _load_required_mapping(base_path / file_name)
        for file_name in REQUIRED_DOMAIN_PACK_FILES
    }
    schema = documents["schema.yaml"]
    business_terms = documents["business_terms.yaml"]
    query_templates = documents["query_templates.yaml"]

    domain = _required_mapping(schema, "domain", "schema.domain")
    domain_id = _required_str(domain, "id", "schema.domain.id")
    name = _required_str(domain, "name", "schema.domain.name")
    version = _required_str(domain, "version", "schema.domain.version")

    tables = _parse_tables(_required_list(schema, "tables", "schema.tables"))
    tables_by_name = {table.name: table for table in tables}
    if len(tables_by_name) != len(tables):
        raise DomainPackValidationError("Duplicate table name in schema.tables")

    allowed_resource_table_names = _parse_allowed_resource_table_names(
        schema,
        tables_by_name,
    )
    terms = _parse_business_terms(
        _required_list(business_terms, "terms", "business_terms.terms"),
        tables_by_name,
    )
    templates = _parse_query_templates(
        _required_list(query_templates, "templates", "query_templates.templates"),
        tables_by_name,
    )

    return DomainPack(
        domain_id=domain_id,
        name=name,
        version=version,
        allowed_resource_table_names=allowed_resource_table_names,
        tables=tuple(sorted(tables, key=lambda table: table.name)),
        business_terms=tuple(sorted(terms, key=lambda term: term.name)),
        query_templates=tuple(sorted(templates, key=lambda template: template.id)),
    )


def _parse_tables(table_items: Sequence[Any]) -> tuple[DomainTable, ...]:
    tables: list[DomainTable] = []
    for index, item in enumerate(table_items):
        path = f"tables[{index}]"
        table = _ensure_mapping(item, path)
        columns = _parse_columns(
            _required_list(table, "columns", f"{path}.columns"),
            path,
        )
        tables.append(
            DomainTable(
                name=_required_str(table, "name", f"{path}.name"),
                display_name=_required_str(
                    table,
                    "display_name",
                    f"{path}.display_name",
                ),
                description=_required_str(
                    table,
                    "description",
                    f"{path}.description",
                ),
                columns=columns,
                scope_type=_optional_str(table, "scope_type", f"{path}.scope_type"),
                scope_column=_optional_str(
                    table,
                    "scope_column",
                    f"{path}.scope_column",
                ),
                queryable=_optional_bool(table, "queryable", True, f"{path}.queryable"),
                resource_type=_optional_str(
                    table,
                    "resource_type",
                    f"{path}.resource_type",
                    default="table",
                ),
            )
        )
    return tuple(tables)


def _parse_columns(
    column_items: Sequence[Any],
    table_path: str,
) -> tuple[DomainColumn, ...]:
    columns: list[DomainColumn] = []
    for index, item in enumerate(column_items):
        path = f"{table_path}.columns[{index}]"
        column = _ensure_mapping(item, path)
        columns.append(
            DomainColumn(
                name=_required_str(column, "name", f"{path}.name"),
                data_type=_required_str(column, "data_type", f"{path}.data_type"),
                description=_required_str(
                    column,
                    "description",
                    f"{path}.description",
                ),
                nullable=_optional_bool(column, "nullable", True, f"{path}.nullable"),
            )
        )

    names = [column.name for column in columns]
    if len(set(names)) != len(names):
        raise DomainPackValidationError(f"Duplicate column name in {table_path}.columns")
    return tuple(sorted(columns, key=lambda column: column.name))


def _parse_allowed_resource_table_names(
    schema: Mapping[str, Any],
    tables_by_name: Mapping[str, DomainTable],
) -> tuple[str, ...]:
    raw_names = _required_list(
        schema,
        "allowed_resource_table_names",
        "schema.allowed_resource_table_names",
    )
    names = tuple(
        sorted(
            _ensure_str(item, "allowed_resource_table_names") for item in raw_names
        )
    )
    if len(set(names)) != len(names):
        raise DomainPackValidationError("Duplicate allowed resource table name")

    for name in names:
        table = tables_by_name.get(name)
        if table is None:
            raise DomainPackValidationError(
                f"Allowed resource table references unknown table: {name}"
            )
        if not table.queryable:
            raise DomainPackValidationError(
                f"Allowed resource table is not queryable: {name}"
            )
    return names


def _parse_business_terms(
    term_items: Sequence[Any],
    tables_by_name: Mapping[str, DomainTable],
) -> tuple[BusinessTerm, ...]:
    terms: list[BusinessTerm] = []
    for index, item in enumerate(term_items):
        path = f"terms[{index}]"
        term = _ensure_mapping(item, path)
        related_tables = _parse_table_references(
            _required_list(term, "related_tables", f"{path}.related_tables"),
            tables_by_name,
            path,
        )
        terms.append(
            BusinessTerm(
                name=_required_str(term, "name", f"{path}.name"),
                description=_required_str(term, "description", f"{path}.description"),
                related_tables=related_tables,
            )
        )

    names = [term.name for term in terms]
    if len(set(names)) != len(names):
        raise DomainPackValidationError("Duplicate business term name")
    return tuple(terms)


def _parse_query_templates(
    template_items: Sequence[Any],
    tables_by_name: Mapping[str, DomainTable],
) -> tuple[QueryTemplate, ...]:
    templates: list[QueryTemplate] = []
    for index, item in enumerate(template_items):
        path = f"templates[{index}]"
        template = _ensure_mapping(item, path)
        referenced_tables = _parse_table_references(
            _required_list(
                template,
                "referenced_tables",
                f"{path}.referenced_tables",
            ),
            tables_by_name,
            path,
            require_queryable=True,
        )
        parameters = _parse_template_parameters(
            _optional_list(template, "parameters", [], f"{path}.parameters"),
            path,
        )
        templates.append(
            QueryTemplate(
                id=_required_str(template, "id", f"{path}.id"),
                title=_required_str(template, "title", f"{path}.title"),
                description=_required_str(
                    template,
                    "description",
                    f"{path}.description",
                ),
                category=_required_str(template, "category", f"{path}.category"),
                natural_language_question=_required_str(
                    template,
                    "natural_language_question",
                    f"{path}.natural_language_question",
                ),
                required_action=_required_str(
                    template,
                    "required_action",
                    f"{path}.required_action",
                ),
                required_permission=_required_str(
                    template,
                    "required_permission",
                    f"{path}.required_permission",
                ),
                scope_type=_optional_str(template, "scope_type", f"{path}.scope_type"),
                referenced_tables=referenced_tables,
                parameters=parameters,
                sql=_optional_str(template, "sql", f"{path}.sql"),
                generation_metadata=_optional_mapping(
                    template,
                    "generation_metadata",
                    f"{path}.generation_metadata",
                ),
            )
        )

    ids = [template.id for template in templates]
    if len(set(ids)) != len(ids):
        raise DomainPackValidationError("Duplicate query template id")
    return tuple(templates)


def _parse_template_parameters(
    parameter_items: Sequence[Any],
    template_path: str,
) -> tuple[QueryTemplateParameter, ...]:
    parameters: list[QueryTemplateParameter] = []
    for index, item in enumerate(parameter_items):
        path = f"{template_path}.parameters[{index}]"
        parameter = _ensure_mapping(item, path)
        parameters.append(
            QueryTemplateParameter(
                name=_required_str(parameter, "name", f"{path}.name"),
                data_type=_required_str(parameter, "data_type", f"{path}.data_type"),
                description=_required_str(
                    parameter,
                    "description",
                    f"{path}.description",
                ),
                required=_optional_bool(
                    parameter,
                    "required",
                    False,
                    f"{path}.required",
                ),
                default=parameter.get("default"),
            )
        )

    names = [parameter.name for parameter in parameters]
    if len(set(names)) != len(names):
        raise DomainPackValidationError(
            f"Duplicate parameter name in {template_path}.parameters"
        )
    return tuple(sorted(parameters, key=lambda parameter: parameter.name))


def _parse_table_references(
    raw_names: Sequence[Any],
    tables_by_name: Mapping[str, DomainTable],
    path: str,
    *,
    require_queryable: bool = False,
) -> tuple[str, ...]:
    names = tuple(
        sorted(_ensure_str(item, f"{path}.table_reference") for item in raw_names)
    )
    for name in names:
        table = tables_by_name.get(name)
        if table is None:
            raise DomainPackValidationError(f"{path} references unknown table: {name}")
        if require_queryable and not table.queryable:
            raise DomainPackValidationError(
                f"{path} references table that is not queryable: {name}"
            )
    return names


def _load_required_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DomainPackValidationError(f"Missing domain pack file: {path.name}")

    loaded = _load_yaml_compatible_file(path)
    if not isinstance(loaded, dict):
        raise DomainPackValidationError(f"{path.name} must contain a mapping")
    return loaded


def _load_yaml_compatible_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError:
        return _load_json_compatible_yaml(path, text)

    try:
        return yaml.safe_load(text)
    except Exception as exc:  # pragma: no cover - only exercised when PyYAML exists.
        raise DomainPackValidationError(f"Invalid domain pack YAML: {path.name}") from exc


def _load_json_compatible_yaml(path: Path, text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DomainPackValidationError(
            f"Invalid domain pack file: {path.name}. "
            "Install PyYAML or use JSON-compatible YAML."
        ) from exc


def _required_mapping(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
) -> Mapping[str, Any]:
    return _ensure_mapping(_required_value(mapping, key, path), path)


def _optional_mapping(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
) -> dict[str, Any] | None:
    value = mapping.get(key)
    if value is None:
        return None
    return dict(_ensure_mapping(value, path))


def _required_list(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
) -> Sequence[Any]:
    value = _required_value(mapping, key, path)
    if not isinstance(value, list):
        raise DomainPackValidationError(f"{path} must be a list")
    return value


def _optional_list(
    mapping: Mapping[str, Any],
    key: str,
    default: list[Any],
    path: str,
) -> Sequence[Any]:
    value = mapping.get(key, default)
    if not isinstance(value, list):
        raise DomainPackValidationError(f"{path} must be a list")
    return value


def _required_str(mapping: Mapping[str, Any], key: str, path: str) -> str:
    return _ensure_str(_required_value(mapping, key, path), path)


def _optional_str(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
    *,
    default: str | None = None,
) -> str | None:
    value = mapping.get(key, default)
    if value is None:
        return None
    return _ensure_str(value, path)


def _optional_bool(
    mapping: Mapping[str, Any],
    key: str,
    default: bool,
    path: str,
) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise DomainPackValidationError(f"{path} must be a boolean")
    return value


def _required_value(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise DomainPackValidationError(f"Missing required field: {path}")
    return mapping[key]


def _ensure_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise DomainPackValidationError(f"{path} must be a mapping")
    return value


def _ensure_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise DomainPackValidationError(f"{path} must be a non-empty string")
    return value
