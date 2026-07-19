from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainColumn:
    name: str
    data_type: str
    description: str
    nullable: bool = True


@dataclass(frozen=True)
class DomainTable:
    name: str
    display_name: str
    description: str
    columns: tuple[DomainColumn, ...]
    scope_type: str | None = None
    scope_column: str | None = None
    queryable: bool = True
    resource_type: str = "table"

    @property
    def columns_by_name(self) -> dict[str, DomainColumn]:
        return {column.name: column for column in self.columns}


@dataclass(frozen=True)
class BusinessTerm:
    name: str
    description: str
    related_tables: tuple[str, ...]


@dataclass(frozen=True)
class QueryTemplateParameter:
    name: str
    data_type: str
    description: str
    required: bool = False
    default: Any | None = None


@dataclass(frozen=True)
class QueryActionSuggestion:
    action_type: str
    label: str
    selector_kind: str
    result_identifier_column: str


@dataclass(frozen=True)
class QueryTemplate:
    id: str
    title: str
    description: str
    category: str
    natural_language_question: str
    required_action: str
    required_permission: str
    scope_type: str | None
    referenced_tables: tuple[str, ...]
    parameters: tuple[QueryTemplateParameter, ...]
    sql: str | None = None
    generation_metadata: dict[str, Any] | None = None
    suggested_action: QueryActionSuggestion | None = None


@dataclass(frozen=True)
class DomainPack:
    domain_id: str
    name: str
    version: str
    allowed_resource_table_names: tuple[str, ...]
    tables: tuple[DomainTable, ...]
    business_terms: tuple[BusinessTerm, ...]
    query_templates: tuple[QueryTemplate, ...]

    @property
    def tables_by_name(self) -> dict[str, DomainTable]:
        return {table.name: table for table in self.tables}

    @property
    def business_terms_by_name(self) -> dict[str, BusinessTerm]:
        return {term.name: term for term in self.business_terms}

    @property
    def templates_by_id(self) -> dict[str, QueryTemplate]:
        return {template.id: template for template in self.query_templates}

    def table(self, name: str) -> DomainTable:
        return self.tables_by_name[name]

    def template(self, template_id: str) -> QueryTemplate:
        return self.templates_by_id[template_id]
