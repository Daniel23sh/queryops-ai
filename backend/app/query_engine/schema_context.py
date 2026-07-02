from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext
from app.auth.access_policy import authorize_resource_access
from app.models.product import DataResource
from app.query_engine.domain_pack import BusinessTerm, DomainPack, DomainTable
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack


QUERY_ACTION = "query:scoped_data"
EXCLUDED_LLM_EXPOSURE_LEVELS = frozenset({"none"})


@dataclass(frozen=True)
class SchemaContextOptions:
    domain_id: str | None = None
    template_id: str | None = None
    query_action: str = QUERY_ACTION


def build_schema_context(
    db: Session,
    access_context: UserAccessContext,
    *,
    domain_pack: DomainPack | None = None,
    options: SchemaContextOptions | None = None,
) -> dict[str, Any]:
    pack = domain_pack or load_it_operations_domain_pack()
    request_options = options or SchemaContextOptions()
    context = _empty_context(pack, access_context)

    if request_options.domain_id and request_options.domain_id != pack.domain_id:
        return context

    template = None
    table_filter: frozenset[str] | None = None
    if request_options.template_id:
        template = pack.templates_by_id.get(request_options.template_id)
        table_filter = (
            frozenset(template.referenced_tables) if template is not None else frozenset()
        )

    resources_by_table = _load_data_resources_by_table(db, pack.domain_id)
    tables = _build_table_contexts(
        pack,
        resources_by_table,
        access_context,
        table_filter,
        request_options.query_action,
    )
    allowed_table_names = [table["name"] for table in tables]

    context["allowed_tables"] = allowed_table_names
    context["allowed_columns"] = {
        table["name"]: [column["name"] for column in table["columns"]]
        for table in tables
    }
    context["tables"] = tables
    context["business_terms"] = _build_business_terms(
        pack.business_terms,
        frozenset(allowed_table_names),
    )

    if template is not None:
        context["template"] = {
            "id": template.id,
            "required_action": template.required_action,
            "scope_type": template.scope_type,
        }

    return context


def _empty_context(
    domain_pack: DomainPack,
    access_context: UserAccessContext,
) -> dict[str, Any]:
    return {
        "domain": domain_pack.domain_id,
        "domain_name": domain_pack.name,
        "domain_version": domain_pack.version,
        "allowed_tables": [],
        "allowed_columns": {},
        "tables": [],
        "business_terms": [],
        "scope": _build_scope_context(access_context),
    }


def _load_data_resources_by_table(
    db: Session,
    domain_id: str,
) -> dict[str, DataResource]:
    resources = db.scalars(
        select(DataResource)
        .where(
            DataResource.domain == domain_id,
            DataResource.resource_type == "table",
        )
        .order_by(DataResource.table_name)
    ).all()
    return {resource.table_name: resource for resource in resources}


def _build_table_contexts(
    domain_pack: DomainPack,
    resources_by_table: dict[str, DataResource],
    access_context: UserAccessContext,
    table_filter: frozenset[str] | None,
    query_action: str,
) -> list[dict[str, Any]]:
    allowed_resource_names = frozenset(domain_pack.allowed_resource_table_names)
    tables: list[dict[str, Any]] = []

    for table in domain_pack.tables:
        if table_filter is not None and table.name not in table_filter:
            continue
        if table.name not in allowed_resource_names:
            continue

        resource = resources_by_table.get(table.name)
        if resource is None:
            continue
        if not _resource_is_safe_for_schema_context(resource):
            continue
        if not _resource_is_allowed(access_context, resource, query_action):
            continue

        tables.append(_serialize_table(table, resource))

    return tables


def _resource_is_safe_for_schema_context(resource: DataResource) -> bool:
    if resource.is_queryable is not True:
        return False
    return resource.llm_exposure_level not in EXCLUDED_LLM_EXPOSURE_LEVELS


def _resource_is_allowed(
    access_context: UserAccessContext,
    resource: DataResource,
    query_action: str,
) -> bool:
    runtime_context: dict[str, str] = {}
    if resource.scope_type:
        runtime_context["scope_type"] = resource.scope_type
        scope_key = _scope_key_for_resource(access_context, resource.scope_type)
        if scope_key is not None:
            runtime_context["scope_key"] = scope_key

    decision = authorize_resource_access(
        access_context,
        query_action,
        resource,
        runtime_context,
    )
    return decision.allowed


def _scope_key_for_resource(
    access_context: UserAccessContext,
    scope_type: str,
) -> str | None:
    if access_context.has_global_scope:
        return "global"

    default_scope = access_context.default_scope
    if default_scope is not None and default_scope.type == scope_type:
        return default_scope.key

    matching_keys = sorted(
        scope.key for scope in access_context.scopes if scope.type == scope_type
    )
    return matching_keys[0] if matching_keys else None


def _build_scope_context(access_context: UserAccessContext) -> dict[str, Any]:
    if access_context.has_global_scope:
        return {
            "has_global_scope": True,
            "type": "global",
            "keys": ["global"],
        }

    scope_keys = sorted(
        scope.key for scope in access_context.scopes if scope.type != "global"
    )
    scope_types = sorted(
        {scope.type for scope in access_context.scopes if scope.type != "global"}
    )
    scope_type = scope_types[0] if len(scope_types) == 1 else "none"
    return {
        "has_global_scope": False,
        "type": scope_type,
        "keys": scope_keys,
    }


def _serialize_table(table: DomainTable, resource: DataResource) -> dict[str, Any]:
    return {
        "name": table.name,
        "display_name": resource.display_name,
        "description": table.description,
        "scope_type": resource.scope_type,
        "scope_column": resource.scope_column,
        "columns": [
            {
                "name": column.name,
                "data_type": column.data_type,
                "description": column.description,
                "nullable": column.nullable,
            }
            for column in sorted(table.columns, key=lambda item: item.name)
        ],
        "resource": {
            "resource_type": resource.resource_type,
            "schema_name": resource.schema_name,
            "table_name": resource.table_name,
            "sensitivity_level": resource.sensitivity_level,
            "scope_type": resource.scope_type,
            "scope_column": resource.scope_column,
            "is_queryable": resource.is_queryable,
            "llm_exposure_level": resource.llm_exposure_level,
        },
    }


def _build_business_terms(
    business_terms: tuple[BusinessTerm, ...],
    allowed_table_names: frozenset[str],
) -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    for term in sorted(business_terms, key=lambda item: item.name):
        related_tables = sorted(
            table_name
            for table_name in term.related_tables
            if table_name in allowed_table_names
        )
        if not related_tables:
            continue
        terms.append(
            {
                "name": term.name,
                "description": term.description,
                "related_tables": related_tables,
            }
        )
    return terms
