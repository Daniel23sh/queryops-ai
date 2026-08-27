from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any

from app.query_engine.domain_pack import DomainTable
from app.query_engine.errors import DomainPackValidationError
from app.query_engine.semantic_catalog import (
    SemanticAggregation,
    SemanticAuthorizationGuidance,
    SemanticCatalog,
    SemanticConcept,
    SemanticCompositionRule,
    SemanticEntity,
    SemanticExample,
    SemanticExampleFieldRef,
    SemanticExampleLiteralFilter,
    SemanticExampleRelationshipIntent,
    SemanticKnownValues,
    SemanticMetric,
    SemanticPredicate,
    SemanticPredicateOperator,
    SemanticRelationship,
    SemanticRelationshipCardinality,
    SemanticScalar,
)


SUPPORTED_CATALOG_VERSION = "3"
MAX_ENTITIES = 64
MAX_CONCEPTS = 128
MAX_METRICS = 32
MAX_RELATIONSHIPS = 128
MAX_COMPOSITION_RULES = 32
MAX_RULE_CONCEPTS = 16
MAX_SUPERSEDED_CONCEPTS = 16
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
    _validate_concept_supersedence(concepts)
    _validate_concept_composition(concepts)
    metrics = _parse_metrics(
        _bounded_list(document, "metrics", MAX_METRICS, allow_empty=True),
        entity_map,
        {concept.id: concept for concept in concepts},
    )
    composition_rules = _parse_composition_rules(
        _bounded_list(
            document,
            "composition_rules",
            MAX_COMPOSITION_RULES,
            allow_empty=True,
        ),
        concept_ids,
    )

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
        entity_map,
        tables_by_name,
        concept_ids,
        {metric.id for metric in metrics},
        {rule.id for rule in composition_rules},
        {relationship.id for relationship in relationships},
    )
    return SemanticCatalog(
        id=catalog_id,
        version=version,
        domain_id=catalog_domain_id,
        dataset_id=dataset_id,
        entities=tuple(sorted(entities, key=lambda item: item.id)),
        relationships=tuple(sorted(relationships, key=lambda item: item.id)),
        concepts=tuple(sorted(concepts, key=lambda item: item.id)),
        metrics=tuple(sorted(metrics, key=lambda item: item.id)),
        composition_rules=tuple(
            sorted(composition_rules, key=lambda item: item.id)
        ),
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
            sorted(
                (
                    _typed_scalar(value, column.data_type, f"{path}.values")
                    for value in values
                ),
                key=_semantic_scalar_sort_key,
            )
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
        predicate_items = _list(
            item,
            "required_predicates",
            f"{path}.required_predicates",
            default=[],
        )
        all_of_concept_ids = _unique_identifiers(
            _list(
                item,
                "all_of_concept_ids",
                f"{path}.all_of_concept_ids",
                default=[],
            ),
            f"{path}.all_of_concept_ids",
            limit=MAX_RULE_CONCEPTS,
        )
        if bool(predicate_items) == bool(all_of_concept_ids):
            raise DomainPackValidationError(
                f"{path} must define exactly one of required_predicates or "
                "all_of_concept_ids"
            )
        predicates = (
            _parse_predicates(predicate_items, table, entity, path)
            if predicate_items
            else ()
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
                all_of_concept_ids=all_of_concept_ids,
                aggregation=_parse_aggregation(item.get("aggregation"), path),
                supersedes=_unique_identifiers(
                    _list(
                        item,
                        "supersedes",
                        f"{path}.supersedes",
                        default=[],
                    ),
                    f"{path}.supersedes",
                    limit=MAX_SUPERSEDED_CONCEPTS,
                ),
            )
        )
    return tuple(concepts)


def _validate_concept_composition(
    concepts: Sequence[SemanticConcept],
) -> None:
    concepts_by_id = {concept.id: concept for concept in concepts}
    for concept in concepts:
        for component_id in concept.all_of_concept_ids:
            component = concepts_by_id.get(component_id)
            if component is None:
                raise DomainPackValidationError(
                    "Semantic concept composes an unknown concept"
                )
            if component.id == concept.id:
                raise DomainPackValidationError(
                    "Semantic concept cannot compose itself"
                )
            if component.entity_id != concept.entity_id:
                raise DomainPackValidationError(
                    "Semantic concept may compose only concepts on the same entity"
                )

    visited: set[str] = set()
    active: set[str] = set()

    def visit(concept_id: str) -> None:
        if concept_id in active:
            raise DomainPackValidationError(
                "Semantic concept composition contains a cycle"
            )
        if concept_id in visited:
            return
        active.add(concept_id)
        for component_id in concepts_by_id[concept_id].all_of_concept_ids:
            visit(component_id)
        active.remove(concept_id)
        visited.add(concept_id)

    for concept_id in sorted(concepts_by_id):
        visit(concept_id)


def _parse_metrics(
    items: Sequence[Any],
    entities: Mapping[str, SemanticEntity],
    concepts: Mapping[str, SemanticConcept],
) -> tuple[SemanticMetric, ...]:
    metrics: list[SemanticMetric] = []
    for index, raw in enumerate(items):
        path = f"semantic_catalog.metrics[{index}]"
        item = _ensure_mapping(raw, path)
        entity_id = _identifier(item, "entity_id", f"{path}.entity_id")
        if entity_id not in entities:
            raise DomainPackValidationError(f"{path} references unknown entity")
        required_concepts = _unique_identifiers(
            _list(
                item,
                "required_concept_ids",
                f"{path}.required_concept_ids",
            ),
            f"{path}.required_concept_ids",
            limit=MAX_RULE_CONCEPTS,
        )
        if not required_concepts:
            raise DomainPackValidationError(
                f"{path}.required_concept_ids must not be empty"
            )
        for concept_id in required_concepts:
            concept = concepts.get(concept_id)
            if concept is None:
                raise DomainPackValidationError(f"{path} references unknown concept")
            if concept.entity_id != entity_id:
                raise DomainPackValidationError(
                    f"{path} references a concept on a different entity"
                )
        aggregation = _parse_aggregation(item.get("aggregation"), path)
        if aggregation is None:
            raise DomainPackValidationError(f"{path}.aggregation is required")
        metrics.append(
            SemanticMetric(
                id=_identifier(item, "id", f"{path}.id"),
                entity_id=entity_id,
                description=_text(item, "description", f"{path}.description"),
                natural_language_references=_references(
                    item,
                    "natural_language_references",
                    path,
                ),
                required_concept_ids=required_concepts,
                aggregation=aggregation,
            )
        )
    ids = [metric.id for metric in metrics]
    if len(ids) != len(set(ids)):
        raise DomainPackValidationError("Duplicate semantic catalog metric id")
    return tuple(metrics)


def _validate_concept_supersedence(
    concepts: Sequence[SemanticConcept],
) -> None:
    concepts_by_id = {concept.id: concept for concept in concepts}
    for concept in concepts:
        for superseded_id in concept.supersedes:
            superseded = concepts_by_id.get(superseded_id)
            if superseded is None:
                raise DomainPackValidationError(
                    "Semantic concept supersedes an unknown concept"
                )
            if superseded.id == concept.id:
                raise DomainPackValidationError(
                    "Semantic concept cannot supersede itself"
                )
            if superseded.entity_id != concept.entity_id:
                raise DomainPackValidationError(
                    "Semantic concept may supersede only a concept on the same entity"
                )

    visited: set[str] = set()
    active: set[str] = set()

    def visit(concept_id: str) -> None:
        if concept_id in active:
            raise DomainPackValidationError(
                "Semantic concept supersedence contains a cycle"
            )
        if concept_id in visited:
            return
        active.add(concept_id)
        for superseded_id in concepts_by_id[concept_id].supersedes:
            visit(superseded_id)
        active.remove(concept_id)
        visited.add(concept_id)

    for concept_id in sorted(concepts_by_id):
        visit(concept_id)


def _parse_composition_rules(
    items: Sequence[Any],
    concept_ids: set[str],
) -> tuple[SemanticCompositionRule, ...]:
    rules: list[SemanticCompositionRule] = []
    for index, raw in enumerate(items):
        path = f"semantic_catalog.composition_rules[{index}]"
        item = _ensure_mapping(raw, path)
        all_of = _unique_identifiers(
            _list(
                item,
                "all_of_concept_ids",
                f"{path}.all_of_concept_ids",
                default=[],
            ),
            f"{path}.all_of_concept_ids",
            limit=MAX_RULE_CONCEPTS,
        )
        or_concepts = _unique_identifiers(
            _list(
                item,
                "or_concept_ids",
                f"{path}.or_concept_ids",
                default=[],
            ),
            f"{path}.or_concept_ids",
            limit=MAX_RULE_CONCEPTS,
        )
        if len(all_of) + len(or_concepts) > MAX_RULE_CONCEPTS:
            raise DomainPackValidationError(
                f"{path} references too many concepts"
            )
        if not all_of and not or_concepts:
            raise DomainPackValidationError(
                f"{path} must reference at least one concept"
            )
        if or_concepts and len(or_concepts) < 2:
            raise DomainPackValidationError(
                f"{path}.or_concept_ids must contain at least two concepts"
            )
        if set(all_of).intersection(or_concepts):
            raise DomainPackValidationError(
                f"{path} repeats a concept across composition groups"
            )
        if not set((*all_of, *or_concepts)) <= concept_ids:
            raise DomainPackValidationError(f"{path} references unknown concept")
        rules.append(
            SemanticCompositionRule(
                id=_identifier(item, "id", f"{path}.id"),
                description=_text(item, "description", f"{path}.description"),
                natural_language_references=_references(
                    item,
                    "natural_language_references",
                    path,
                ),
                all_of_concept_ids=all_of,
                or_concept_ids=or_concepts,
            )
        )
    ids = [rule.id for rule in rules]
    if len(ids) != len(set(ids)):
        raise DomainPackValidationError(
            "Duplicate semantic catalog composition rule id"
        )
    return tuple(rules)


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
                sorted(
                    (
                        _typed_scalar(value, column.data_type, f"{path}.value")
                        for value in raw_value
                    ),
                    key=_semantic_scalar_sort_key,
                )
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
    entities: Mapping[str, SemanticEntity],
    tables_by_name: Mapping[str, DomainTable],
    concept_ids: set[str],
    metric_ids: set[str],
    rule_ids: set[str],
    relationship_ids: set[str],
) -> tuple[SemanticExample, ...]:
    if len(items) > 16:
        raise DomainPackValidationError("Too many semantic catalog examples")
    result: list[SemanticExample] = []
    for index, raw in enumerate(items):
        path = f"semantic_catalog.examples[{index}]"
        item = _ensure_mapping(raw, path)
        entity_references = _unique_identifiers(
            _list(item, "entity_ids", f"{path}.entity_ids", default=[]),
            f"{path}.entity_ids",
        )
        concept_references = _unique_identifiers(
            _list(item, "concept_ids", f"{path}.concept_ids", default=[]),
            f"{path}.concept_ids",
        )
        rule_references = _unique_identifiers(
            _list(
                item,
                "composition_rule_ids",
                f"{path}.composition_rule_ids",
                default=[],
            ),
            f"{path}.composition_rule_ids",
        )
        relationship_references = _parse_example_relationships(
            _list(item, "relationships", f"{path}.relationships", default=[]),
            relationship_ids,
            path,
        )
        if not set(entity_references) <= entities.keys():
            raise DomainPackValidationError(f"{path} references unknown entity")
        if not set(concept_references) <= concept_ids:
            raise DomainPackValidationError(f"{path} references unknown concept")
        if not set(rule_references) <= rule_ids:
            raise DomainPackValidationError(f"{path} references unknown rule")
        raw_metric_id = item.get("metric_id")
        metric_id = None
        if raw_metric_id is not None:
            metric_id = _safe_identifier_value(raw_metric_id, f"{path}.metric_id")
            if metric_id not in metric_ids:
                raise DomainPackValidationError(f"{path} references unknown metric")
        aggregation_functions = tuple(
            sorted(
                _safe_text_value(value, f"{path}.aggregation_functions", 16)
                for value in _list(
                    item,
                    "aggregation_functions",
                    f"{path}.aggregation_functions",
                    default=[],
                )
            )
        )
        if any(value not in {"count", "sum"} for value in aggregation_functions):
            raise DomainPackValidationError(
                f"{path}.aggregation_functions contains an unsupported function"
            )
        if len(aggregation_functions) != len(set(aggregation_functions)):
            raise DomainPackValidationError(
                f"{path}.aggregation_functions contains duplicates"
            )
        literal_filters = _parse_example_literal_filters(
            _list(
                item,
                "literal_filters",
                f"{path}.literal_filters",
                default=[],
            ),
            entities,
            tables_by_name,
            path,
        )
        group_by = tuple(
            sorted(
                (
                    _parse_example_field_ref(
                        raw_field,
                        entities,
                        tables_by_name,
                        f"{path}.group_by[{field_index}]",
                    )
                    for field_index, raw_field in enumerate(
                        _list(item, "group_by", f"{path}.group_by", default=[])
                    )
                ),
                key=lambda value: (value.entity_id, value.column),
            )
        )
        clarification_reason = item.get("clarification_reason")
        if clarification_reason is not None:
            clarification_reason = _safe_text_value(
                clarification_reason,
                f"{path}.clarification_reason",
                64,
            )
            if clarification_reason not in {
                "ambiguous_question",
                "missing_information",
                "unsupported_request",
                "unresolved_scope",
            }:
                raise DomainPackValidationError(
                    f"{path}.clarification_reason is not supported"
                )
        if not any(
            (
                entity_references,
                concept_references,
                rule_references,
                metric_id,
                literal_filters,
                relationship_references,
                aggregation_functions,
                group_by,
                clarification_reason,
            )
        ):
            raise DomainPackValidationError(f"{path} has no semantic plan content")
        result.append(
            SemanticExample(
                id=_identifier(item, "id", f"{path}.id"),
                request=_text(item, "request", f"{path}.request"),
                entity_ids=entity_references,
                concept_ids=concept_references,
                composition_rule_ids=rule_references,
                metric_id=metric_id,
                distinct=_required_bool(item, "distinct", f"{path}.distinct"),
                literal_filters=literal_filters,
                relationships=relationship_references,
                aggregation_functions=aggregation_functions,
                group_by=group_by,
                clarification_reason=clarification_reason,
            )
        )
    ids = [item.id for item in result]
    if len(ids) != len(set(ids)):
        raise DomainPackValidationError("Duplicate semantic catalog example id")
    return tuple(result)


def _parse_example_field_ref(
    raw: Any,
    entities: Mapping[str, SemanticEntity],
    tables_by_name: Mapping[str, DomainTable],
    path: str,
) -> SemanticExampleFieldRef:
    item = _ensure_mapping(raw, path)
    entity_id = _identifier(item, "entity_id", f"{path}.entity_id")
    entity = entities.get(entity_id)
    if entity is None:
        raise DomainPackValidationError(f"{path} references unknown entity")
    column = _identifier(item, "column", f"{path}.column")
    if column not in tables_by_name[entity.table].columns_by_name:
        raise DomainPackValidationError(f"{path} references unknown column")
    return SemanticExampleFieldRef(entity_id=entity_id, column=column)


def _parse_example_literal_filters(
    items: Sequence[Any],
    entities: Mapping[str, SemanticEntity],
    tables_by_name: Mapping[str, DomainTable],
    example_path: str,
) -> tuple[SemanticExampleLiteralFilter, ...]:
    if len(items) > 16:
        raise DomainPackValidationError(
            f"{example_path}.literal_filters has invalid size"
        )
    result: list[SemanticExampleLiteralFilter] = []
    for index, raw in enumerate(items):
        path = f"{example_path}.literal_filters[{index}]"
        item = _ensure_mapping(raw, path)
        field = _parse_example_field_ref(
            _required(item, "field", f"{path}.field"),
            entities,
            tables_by_name,
            f"{path}.field",
        )
        operator = _text(item, "operator", f"{path}.operator", 32)
        if operator not in {"equals", "not_equals", "in", "not_in"}:
            raise DomainPackValidationError(
                f"{path}.operator is not supported"
            )
        column = tables_by_name[entities[field.entity_id].table].columns_by_name[
            field.column
        ]
        raw_value = _required(item, "value", f"{path}.value")
        if operator in {"in", "not_in"}:
            if not isinstance(raw_value, list) or not raw_value:
                raise DomainPackValidationError(
                    f"{path}.value must be a non-empty list"
                )
            value: SemanticScalar | tuple[SemanticScalar, ...] = tuple(
                _typed_scalar(entry, column.data_type, f"{path}.value")
                for entry in raw_value
            )
        else:
            if isinstance(raw_value, list | dict):
                raise DomainPackValidationError(f"{path}.value must be scalar")
            value = _typed_scalar(raw_value, column.data_type, f"{path}.value")
        result.append(
            SemanticExampleLiteralFilter(
                field=field,
                operator=operator,
                value=value,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda value: (
                value.field.entity_id,
                value.field.column,
                value.operator,
                json.dumps(value.value, sort_keys=True),
            ),
        )
    )


def _parse_example_relationships(
    items: Sequence[Any],
    relationship_ids: set[str],
    example_path: str,
) -> tuple[SemanticExampleRelationshipIntent, ...]:
    if len(items) > 16:
        raise DomainPackValidationError(
            f"{example_path}.relationships has invalid size"
        )
    result: list[SemanticExampleRelationshipIntent] = []
    for index, raw in enumerate(items):
        path = f"{example_path}.relationships[{index}]"
        item = _ensure_mapping(raw, path)
        relationship_id = _identifier(
            item,
            "relationship_id",
            f"{path}.relationship_id",
        )
        if relationship_id not in relationship_ids:
            raise DomainPackValidationError(
                f"{path} references unknown relationship"
            )
        join_type = _text(item, "join_type", f"{path}.join_type", 16)
        if join_type not in {"inner", "left"}:
            raise DomainPackValidationError(f"{path}.join_type is not supported")
        result.append(
            SemanticExampleRelationshipIntent(
                relationship_id=relationship_id,
                join_type=join_type,
            )
        )
    ids = [item.relationship_id for item in result]
    if len(ids) != len(set(ids)):
        raise DomainPackValidationError(
            f"{example_path}.relationships contains duplicates"
        )
    return tuple(sorted(result, key=lambda item: item.relationship_id))


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


def _semantic_scalar_sort_key(value: SemanticScalar) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


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


def _unique_identifiers(
    values: Sequence[Any],
    path: str,
    *,
    limit: int | None = None,
) -> tuple[str, ...]:
    if limit is not None and len(values) > limit:
        raise DomainPackValidationError(f"{path} has invalid size")
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
