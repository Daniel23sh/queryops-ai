from __future__ import annotations

import re
from math import isfinite
from collections.abc import Mapping, Sequence
from typing import Any

from app.query_engine.domain_pack import DomainTable
from app.query_engine.errors import DomainPackValidationError
from app.query_engine.semantic_catalog import (
    SemanticAggregation,
    SemanticAuthorizationGuidance,
    SemanticCatalog,
    SemanticConcept,
    SemanticEntity,
    SemanticExample,
    SemanticKnownValues,
    SemanticPredicate,
    SemanticPredicateOperator,
    SemanticRelationship,
    SemanticRelationshipCardinality,
    SemanticScalar,
)


SUPPORTED_CATALOG_VERSION = "1"
MAX_ENTITIES = 64
MAX_CONCEPTS = 128
MAX_RELATIONSHIPS = 128
MAX_REFERENCES = 24
MAX_KNOWN_VALUES = 32
MAX_TEXT_LENGTH = 800
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SCALAR_TYPES = (str, int, float, bool)


def parse_semantic_catalog(
    document: Mapping[str, Any],
    *,
    domain_id: str,
    expected_catalog_id: str,
    expected_catalog_version: str,
    expected_dataset_id: str,
    tables_by_name: Mapping[str, DomainTable],
    allowed_resource_table_names: Sequence[str],
) -> SemanticCatalog:
    metadata = _mapping(document, "catalog", "semantic_catalog.catalog")
    catalog_id = _identifier(metadata, "id", "semantic_catalog.catalog.id")
    if catalog_id != expected_catalog_id:
        raise DomainPackValidationError(
            "Semantic catalog identity does not match its domain pack"
        )
    version = _text(metadata, "version", "semantic_catalog.catalog.version", 64)
    if version != SUPPORTED_CATALOG_VERSION:
        raise DomainPackValidationError(
            f"Unsupported semantic catalog version: {version}"
        )
    if version != expected_catalog_version:
        raise DomainPackValidationError(
            "Semantic catalog version does not match its domain pack"
        )
    catalog_domain_id = _identifier(
        metadata,
        "domain_id",
        "semantic_catalog.catalog.domain_id",
    )
    if catalog_domain_id != domain_id:
        raise DomainPackValidationError(
            "Semantic catalog domain does not match its domain pack"
        )
    dataset_id = _identifier(
        metadata,
        "dataset_id",
        "semantic_catalog.catalog.dataset_id",
    )
    if dataset_id != expected_dataset_id:
        raise DomainPackValidationError(
            "Semantic catalog dataset does not match its domain pack"
        )

    restricted_tables = _unique_identifiers(
        _list(document, "restricted_tables", "semantic_catalog.restricted_tables"),
        "semantic_catalog.restricted_tables",
    )
    allowed_tables = frozenset(allowed_resource_table_names)
    overlap = allowed_tables.intersection(restricted_tables)
    if overlap:
        raise DomainPackValidationError(
            "Restricted semantic catalog resource is exposed as queryable: "
            + ", ".join(sorted(overlap))
        )
    for table_name in restricted_tables:
        table = tables_by_name.get(table_name)
        if table is None:
            raise DomainPackValidationError(
                f"Semantic catalog references unknown restricted table: {table_name}"
            )
        if table.queryable:
            raise DomainPackValidationError(
                f"Semantic catalog restricted table is queryable: {table_name}"
            )

    entities = _parse_entities(
        _bounded_list(document, "entities", MAX_ENTITIES),
        tables_by_name,
        allowed_tables,
    )
    entity_map = {entity.id: entity for entity in entities}
    entity_table_map = {entity.table: entity for entity in entities}
    if len(entity_map) != len(entities):
        raise DomainPackValidationError("Duplicate semantic catalog entity id")
    if len(entity_table_map) != len(entities):
        raise DomainPackValidationError(
            "Semantic catalog may define only one entity for each table"
        )
    missing_tables = allowed_tables.difference(entity_table_map)
    if missing_tables:
        raise DomainPackValidationError(
            "Semantic catalog is missing queryable tables: "
            + ", ".join(sorted(missing_tables))
        )

    relationships = _parse_relationships(
        _bounded_list(
            document,
            "relationships",
            MAX_RELATIONSHIPS,
            allow_empty=True,
        ),
        entity_map,
        tables_by_name,
    )
    concepts = _parse_concepts(
        _bounded_list(document, "concepts", MAX_CONCEPTS),
        entity_map,
        tables_by_name,
    )
    concept_ids = {concept.id for concept in concepts}
    if len(concept_ids) != len(concepts):
        raise DomainPackValidationError("Duplicate semantic catalog concept id")

    guidance = _parse_authorization_guidance(
        _list(
            document,
            "authorization_guidance",
            "semantic_catalog.authorization_guidance",
        ),
        entity_map,
    )
    examples = _parse_examples(
        _list(document, "examples", "semantic_catalog.examples"),
        concept_ids,
    )
    return SemanticCatalog(
        id=catalog_id,
        version=version,
        domain_id=catalog_domain_id,
        dataset_id=dataset_id,
        entities=tuple(sorted(entities, key=lambda item: item.id)),
        relationships=tuple(sorted(relationships, key=lambda item: item.id)),
        concepts=tuple(sorted(concepts, key=lambda item: item.id)),
        authorization_guidance=tuple(
            sorted(guidance, key=lambda item: item.scope_type)
        ),
        restricted_tables=tuple(sorted(restricted_tables)),
        examples=tuple(sorted(examples, key=lambda item: item.id)),
    )


def _parse_entities(
    items: Sequence[Any],
    tables_by_name: Mapping[str, DomainTable],
    allowed_tables: frozenset[str],
) -> tuple[SemanticEntity, ...]:
    entities: list[SemanticEntity] = []
    for index, raw in enumerate(items):
        path = f"semantic_catalog.entities[{index}]"
        item = _ensure_mapping(raw, path)
        table_name = _identifier(item, "table", f"{path}.table")
        table = tables_by_name.get(table_name)
        if table is None:
            raise DomainPackValidationError(f"{path} references unknown table")
        if table_name not in allowed_tables or not table.queryable:
            raise DomainPackValidationError(
                f"{path} exposes a restricted resource as queryable"
            )
        known_values = _parse_known_values(
            _list(item, "known_values", f"{path}.known_values", default=[]),
            table,
            path,
        )
        entities.append(
            SemanticEntity(
                id=_identifier(item, "id", f"{path}.id"),
                table=table_name,
                description=_text(item, "description", f"{path}.description"),
                natural_language_references=_references(
                    item,
                    "natural_language_references",
                    path,
                ),
                known_values=known_values,
            )
        )
    return tuple(entities)


def _parse_known_values(
    items: Sequence[Any],
    table: DomainTable,
    entity_path: str,
) -> tuple[SemanticKnownValues, ...]:
    result: list[SemanticKnownValues] = []
    for index, raw in enumerate(items):
        path = f"{entity_path}.known_values[{index}]"
        item = _ensure_mapping(raw, path)
        column_name = _identifier(item, "column", f"{path}.column")
        column = table.columns_by_name.get(column_name)
        if column is None:
            raise DomainPackValidationError(f"{path} references unknown column")
        values = _list(item, "values", f"{path}.values")
        if not values or len(values) > MAX_KNOWN_VALUES:
            raise DomainPackValidationError(f"{path}.values has invalid size")
        parsed = tuple(
            _typed_scalar(value, column.data_type, f"{path}.values")
            for value in values
        )
        if len(set(parsed)) != len(parsed):
            raise DomainPackValidationError(f"{path}.values contains duplicates")
        result.append(SemanticKnownValues(column=column_name, values=parsed))
    columns = [item.column for item in result]
    if len(columns) != len(set(columns)):
        raise DomainPackValidationError(
            f"Duplicate known-values column in {entity_path}"
        )
    return tuple(sorted(result, key=lambda item: item.column))


def _parse_relationships(
    items: Sequence[Any],
    entities: Mapping[str, SemanticEntity],
    tables_by_name: Mapping[str, DomainTable],
) -> tuple[SemanticRelationship, ...]:
    result: list[SemanticRelationship] = []
    for index, raw in enumerate(items):
        path = f"semantic_catalog.relationships[{index}]"
        item = _ensure_mapping(raw, path)
        from_entity = _identifier(item, "from_entity", f"{path}.from_entity")
        to_entity = _identifier(item, "to_entity", f"{path}.to_entity")
        if from_entity not in entities or to_entity not in entities:
            raise DomainPackValidationError(f"{path} references unknown entity")
        from_column = _identifier(item, "from_column", f"{path}.from_column")
        to_column = _identifier(item, "to_column", f"{path}.to_column")
        if from_column not in tables_by_name[entities[from_entity].table].columns_by_name:
            raise DomainPackValidationError(f"{path} references unknown from column")
        if to_column not in tables_by_name[entities[to_entity].table].columns_by_name:
            raise DomainPackValidationError(f"{path} references unknown to column")
        result.append(
            SemanticRelationship(
                id=_identifier(item, "id", f"{path}.id"),
                from_entity=from_entity,
                from_column=from_column,
                to_entity=to_entity,
                to_column=to_column,
                cardinality=_relationship_cardinality(item, path),
                optional=_required_bool(item, "optional", f"{path}.optional"),
                description=_text(item, "description", f"{path}.description"),
            )
        )
    ids = [item.id for item in result]
    if len(ids) != len(set(ids)):
        raise DomainPackValidationError("Duplicate semantic catalog relationship id")
    return tuple(result)


def _relationship_cardinality(
    item: Mapping[str, Any],
    path: str,
) -> SemanticRelationshipCardinality:
    raw = _text(item, "cardinality", f"{path}.cardinality", 32)
    try:
        return SemanticRelationshipCardinality(raw)
    except ValueError as exc:
        raise DomainPackValidationError(
            f"Unsupported semantic relationship cardinality: {raw}"
        ) from exc


def _parse_concepts(
    items: Sequence[Any],
    entities: Mapping[str, SemanticEntity],
    tables_by_name: Mapping[str, DomainTable],
) -> tuple[SemanticConcept, ...]:
    concepts: list[SemanticConcept] = []
    for index, raw in enumerate(items):
        path = f"semantic_catalog.concepts[{index}]"
        item = _ensure_mapping(raw, path)
        entity_id = _identifier(item, "entity_id", f"{path}.entity_id")
        entity = entities.get(entity_id)
        if entity is None:
            raise DomainPackValidationError(f"{path} references unknown entity")
        table = tables_by_name[entity.table]
        predicates = _parse_predicates(
            _list(item, "required_predicates", f"{path}.required_predicates"),
            table,
            entity,
            path,
        )
        concepts.append(
            SemanticConcept(
                id=_identifier(item, "id", f"{path}.id"),
                entity_id=entity_id,
                description=_text(item, "description", f"{path}.description"),
                natural_language_references=_references(
                    item,
                    "natural_language_references",
                    path,
                ),
                required_predicates=predicates,
                aggregation=_parse_aggregation(item.get("aggregation"), path),
            )
        )
    return tuple(concepts)


def _parse_predicates(
    items: Sequence[Any],
    table: DomainTable,
    entity: SemanticEntity,
    concept_path: str,
) -> tuple[SemanticPredicate, ...]:
    if not items:
        raise DomainPackValidationError(
            f"{concept_path}.required_predicates must not be empty"
        )
    known_values = {item.column: set(item.values) for item in entity.known_values}
    predicates: list[SemanticPredicate] = []
    for index, raw in enumerate(items):
        path = f"{concept_path}.required_predicates[{index}]"
        item = _ensure_mapping(raw, path)
        column_name = _identifier(item, "column", f"{path}.column")
        column = table.columns_by_name.get(column_name)
        if column is None:
            raise DomainPackValidationError(f"{path} references unknown column")
        operator_value = _text(item, "operator", f"{path}.operator", 32)
        try:
            operator = SemanticPredicateOperator(operator_value)
        except ValueError as exc:
            raise DomainPackValidationError(
                f"Unsupported semantic predicate operator: {operator_value}"
            ) from exc
        raw_value = _required(item, "value", f"{path}.value")
        if operator in {
            SemanticPredicateOperator.IS_NULL_OR_OLDER_THAN_DAYS,
            SemanticPredicateOperator.OLDER_THAN_DAYS,
            SemanticPredicateOperator.WITHIN_LAST_DAYS,
        }:
            if column.data_type not in {"date", "timestamp"}:
                raise DomainPackValidationError(
                    f"{path} temporal operator requires a date or timestamp column"
                )
            if (
                not isinstance(raw_value, int)
                or isinstance(raw_value, bool)
                or not 1 <= raw_value <= 3650
            ):
                raise DomainPackValidationError(
                    f"{path}.value must be a bounded positive day count"
                )
            value = raw_value
        elif operator is SemanticPredicateOperator.IN:
            if not isinstance(raw_value, list) or not raw_value:
                raise DomainPackValidationError(
                    f"{path}.value must be a non-empty list for operator in"
                )
            value: SemanticScalar | tuple[SemanticScalar, ...] = tuple(
                _typed_scalar(value, column.data_type, f"{path}.value")
                for value in raw_value
            )
        else:
            if isinstance(raw_value, list | dict):
                raise DomainPackValidationError(
                    f"{path}.value must be scalar for operator equals"
                )
            value = _typed_scalar(raw_value, column.data_type, f"{path}.value")
        known = known_values.get(column_name)
        values = set(value if isinstance(value, tuple) else (value,))
        if known is not None and not values <= known:
            raise DomainPackValidationError(
                f"{path}.value is not declared in entity known_values"
            )
        predicates.append(
            SemanticPredicate(column=column_name, operator=operator, value=value)
        )
    keys = [(item.column, item.operator.value) for item in predicates]
    if len(keys) != len(set(keys)):
        raise DomainPackValidationError(
            f"Duplicate semantic predicate in {concept_path}"
        )
    return tuple(sorted(predicates, key=lambda item: (item.column, item.operator.value)))


def _parse_aggregation(value: Any, concept_path: str) -> SemanticAggregation | None:
    if value is None:
        return None
    item = _ensure_mapping(value, f"{concept_path}.aggregation")
    function = _text(item, "function", f"{concept_path}.aggregation.function", 32)
    if function not in {"count"}:
        raise DomainPackValidationError(
            f"Unsupported semantic aggregation function: {function}"
        )
    return SemanticAggregation(
        function=function,
        description=_text(
            item,
            "description",
            f"{concept_path}.aggregation.description",
        ),
    )


def _parse_authorization_guidance(
    items: Sequence[Any],
    entities: Mapping[str, SemanticEntity],
) -> tuple[SemanticAuthorizationGuidance, ...]:
    result: list[SemanticAuthorizationGuidance] = []
    for index, raw in enumerate(items):
        path = f"semantic_catalog.authorization_guidance[{index}]"
        item = _ensure_mapping(raw, path)
        enforcement = _text(item, "enforcement", f"{path}.enforcement", 64)
        if enforcement != "postgresql_rls":
            raise DomainPackValidationError(
                f"Unsupported semantic authorization enforcement: {enforcement}"
            )
        scope_entity_id = _identifier(
            item,
            "scope_entity_id",
            f"{path}.scope_entity_id",
        )
        if scope_entity_id not in entities:
            raise DomainPackValidationError(
                f"{path} references unknown scope entity"
            )
        result.append(
            SemanticAuthorizationGuidance(
                scope_type=_identifier(item, "scope_type", f"{path}.scope_type"),
                scope_entity_id=scope_entity_id,
                possessive_references=_references(
                    item,
                    "possessive_references",
                    path,
                ),
                enforcement=enforcement,
                description=_text(item, "description", f"{path}.description"),
            )
        )
    scope_types = [item.scope_type for item in result]
    if len(scope_types) != len(set(scope_types)):
        raise DomainPackValidationError(
            "Duplicate semantic authorization scope type"
        )
    return tuple(result)


def _parse_examples(
    items: Sequence[Any],
    concept_ids: set[str],
) -> tuple[SemanticExample, ...]:
    if len(items) > 16:
        raise DomainPackValidationError("Too many semantic catalog examples")
    result: list[SemanticExample] = []
    for index, raw in enumerate(items):
        path = f"semantic_catalog.examples[{index}]"
        item = _ensure_mapping(raw, path)
        references = _unique_identifiers(
            _list(item, "concept_ids", f"{path}.concept_ids"),
            f"{path}.concept_ids",
        )
        if not references or not set(references) <= concept_ids:
            raise DomainPackValidationError(f"{path} references unknown concept")
        result.append(
            SemanticExample(
                id=_identifier(item, "id", f"{path}.id"),
                request=_text(item, "request", f"{path}.request"),
                concept_ids=references,
            )
        )
    ids = [item.id for item in result]
    if len(ids) != len(set(ids)):
        raise DomainPackValidationError("Duplicate semantic catalog example id")
    return tuple(result)


def _typed_scalar(value: Any, data_type: str, path: str) -> SemanticScalar:
    if not isinstance(value, SCALAR_TYPES) or (
        isinstance(value, float) and not isfinite(value)
    ):
        raise DomainPackValidationError(f"{path} has an invalid scalar value")
    if data_type == "boolean" and not isinstance(value, bool):
        raise DomainPackValidationError(f"{path} must contain boolean values")
    if data_type in {"string", "text", "uuid", "timestamp", "date"} and not isinstance(
        value, str
    ):
        raise DomainPackValidationError(f"{path} must contain string values")
    if data_type in {"integer", "numeric", "decimal"} and (
        not isinstance(value, int | float) or isinstance(value, bool)
    ):
        raise DomainPackValidationError(f"{path} must contain numeric values")
    if isinstance(value, str) and (not value or len(value) > 120):
        raise DomainPackValidationError(f"{path} contains unsafe text")
    return value


def _references(
    mapping: Mapping[str, Any],
    key: str,
    parent_path: str,
) -> tuple[str, ...]:
    path = f"{parent_path}.{key}"
    values = _list(mapping, key, path)
    if not values or len(values) > MAX_REFERENCES:
        raise DomainPackValidationError(f"{path} has invalid size")
    parsed = tuple(_safe_text_value(value, path, 160) for value in values)
    if len(parsed) != len(set(parsed)):
        raise DomainPackValidationError(f"{path} contains duplicates")
    return tuple(sorted(parsed))


def _bounded_list(
    mapping: Mapping[str, Any],
    key: str,
    limit: int,
    *,
    allow_empty: bool = False,
) -> Sequence[Any]:
    values = _list(mapping, key, f"semantic_catalog.{key}")
    if (not values and not allow_empty) or len(values) > limit:
        raise DomainPackValidationError(f"semantic_catalog.{key} has invalid size")
    return values


def _unique_identifiers(values: Sequence[Any], path: str) -> tuple[str, ...]:
    parsed = tuple(_safe_identifier_value(value, path) for value in values)
    if len(parsed) != len(set(parsed)):
        raise DomainPackValidationError(f"{path} contains duplicates")
    return tuple(sorted(parsed))


def _mapping(mapping: Mapping[str, Any], key: str, path: str) -> Mapping[str, Any]:
    return _ensure_mapping(_required(mapping, key, path), path)


def _list(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
    *,
    default: list[Any] | None = None,
) -> Sequence[Any]:
    value = mapping.get(key, default) if default is not None else _required(mapping, key, path)
    if not isinstance(value, list):
        raise DomainPackValidationError(f"{path} must be a list")
    return value


def _identifier(mapping: Mapping[str, Any], key: str, path: str) -> str:
    return _safe_identifier_value(_required(mapping, key, path), path)


def _required_bool(mapping: Mapping[str, Any], key: str, path: str) -> bool:
    value = _required(mapping, key, path)
    if not isinstance(value, bool):
        raise DomainPackValidationError(f"{path} must be a boolean")
    return value


def _safe_identifier_value(value: Any, path: str) -> str:
    if not isinstance(value, str) or SAFE_IDENTIFIER.fullmatch(value) is None:
        raise DomainPackValidationError(f"{path} must be a safe identifier")
    return value


def _text(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
    limit: int = MAX_TEXT_LENGTH,
) -> str:
    return _safe_text_value(_required(mapping, key, path), path, limit)


def _safe_text_value(value: Any, path: str, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(character) < 32 and character not in "\n\t" for character in value)
    ):
        raise DomainPackValidationError(f"{path} must be bounded safe text")
    return value.strip()


def _required(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise DomainPackValidationError(f"Missing required field: {path}")
    return mapping[key]


def _ensure_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise DomainPackValidationError(f"{path} must be a mapping")
    return value
