from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.query_engine.errors import DomainPackValidationError


MAX_SEMANTIC_PROJECTION_BYTES = 16_000
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_DIGEST = re.compile(r"^[0-9a-f]{64}$")

SemanticScalar = str | int | float | bool


class SemanticPredicateOperator(str, Enum):
    EQUALS = "equals"
    IN = "in"
    IS_NULL_OR_OLDER_THAN_DAYS = "is_null_or_older_than_days"
    OLDER_THAN_DAYS = "older_than_days"
    WITHIN_LAST_DAYS = "within_last_days"


class SemanticRelationshipCardinality(str, Enum):
    MANY_TO_ONE = "many_to_one"
    ONE_TO_ONE = "one_to_one"


@dataclass(frozen=True)
class SemanticKnownValues:
    column: str
    values: tuple[SemanticScalar, ...]


@dataclass(frozen=True)
class SemanticEntity:
    id: str
    table: str
    description: str
    natural_language_references: tuple[str, ...]
    known_values: tuple[SemanticKnownValues, ...]


@dataclass(frozen=True)
class SemanticRelationship:
    id: str
    from_entity: str
    from_column: str
    to_entity: str
    to_column: str
    cardinality: SemanticRelationshipCardinality
    optional: bool
    description: str


@dataclass(frozen=True)
class SemanticPredicate:
    column: str
    operator: SemanticPredicateOperator
    value: SemanticScalar | tuple[SemanticScalar, ...]


@dataclass(frozen=True)
class SemanticAggregation:
    function: str
    description: str


@dataclass(frozen=True)
class SemanticConcept:
    id: str
    entity_id: str
    description: str
    natural_language_references: tuple[str, ...]
    required_predicates: tuple[SemanticPredicate, ...]
    aggregation: SemanticAggregation | None
    supersedes: tuple[str, ...]


@dataclass(frozen=True)
class SemanticCompositionRule:
    id: str
    description: str
    natural_language_references: tuple[str, ...]
    all_of_concept_ids: tuple[str, ...]
    or_concept_ids: tuple[str, ...]


@dataclass(frozen=True)
class SemanticAuthorizationGuidance:
    scope_type: str
    scope_entity_id: str
    possessive_references: tuple[str, ...]
    enforcement: str
    description: str


@dataclass(frozen=True)
class SemanticExample:
    id: str
    request: str
    concept_ids: tuple[str, ...]


@dataclass(frozen=True)
class SemanticCatalog:
    id: str
    version: str
    domain_id: str
    dataset_id: str
    entities: tuple[SemanticEntity, ...]
    relationships: tuple[SemanticRelationship, ...]
    concepts: tuple[SemanticConcept, ...]
    composition_rules: tuple[SemanticCompositionRule, ...]
    authorization_guidance: tuple[SemanticAuthorizationGuidance, ...]
    restricted_tables: tuple[str, ...]
    examples: tuple[SemanticExample, ...]

    @property
    def entities_by_id(self) -> dict[str, SemanticEntity]:
        return {entity.id: entity for entity in self.entities}

    @property
    def concepts_by_id(self) -> dict[str, SemanticConcept]:
        return {concept.id: concept for concept in self.concepts}

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            _catalog_identity_document(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SemanticCatalogProjection:
    catalog_id: str
    catalog_version: str
    catalog_hash: str
    entities: tuple[dict[str, Any], ...]
    relationships: tuple[dict[str, Any], ...]
    concepts: tuple[dict[str, Any], ...]
    composition_rules: tuple[dict[str, Any], ...]
    authorization_guidance: tuple[dict[str, Any], ...]
    examples: tuple[dict[str, Any], ...]
    authoritative_business_terms: tuple[str, ...]

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "entities": [dict(entity) for entity in self.entities],
            "relationships": [dict(relationship) for relationship in self.relationships],
            "concepts": [dict(concept) for concept in self.concepts],
            "composition_rules": [dict(rule) for rule in self.composition_rules],
            "authorization_guidance": [
                dict(guidance) for guidance in self.authorization_guidance
            ],
            "examples": [dict(example) for example in self.examples],
        }

    def as_observation(self) -> dict[str, Any]:
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "catalog_hash": self.catalog_hash,
            "selected_entity_ids": [entity["id"] for entity in self.entities],
            "selected_concept_ids": [concept["id"] for concept in self.concepts],
            "selected_rule_ids": [rule["id"] for rule in self.composition_rules],
        }


def build_semantic_catalog_projection(
    catalog: SemanticCatalog,
    question: str,
    schema_context: Mapping[str, Any],
    user_context: Mapping[str, Any],
) -> SemanticCatalogProjection:
    normalized_question = _normalize_phrase(question)
    allowed_tables = _safe_string_set(schema_context.get("allowed_tables"))
    allowed_columns = _safe_allowed_columns(schema_context.get("allowed_columns"))

    directly_matching_concepts = tuple(
        concept
        for concept in catalog.concepts
        if _matches_any_reference(
            normalized_question,
            concept.natural_language_references,
        )
    )
    matching_rules = tuple(
        rule
        for rule in catalog.composition_rules
        if _matches_any_reference(
            normalized_question,
            rule.natural_language_references,
        )
    )
    concepts_by_id = catalog.concepts_by_id
    rule_concept_ids = {
        concept_id
        for rule in matching_rules
        for concept_id in (*rule.all_of_concept_ids, *rule.or_concept_ids)
    }
    matching_concepts = _remove_superseded_concepts(
        tuple(
            concept
            for concept in catalog.concepts
            if concept in directly_matching_concepts or concept.id in rule_concept_ids
        ),
        concepts_by_id,
    )
    selected_entity_ids = {
        concept.entity_id for concept in matching_concepts
    } | {
        entity.id
        for entity in catalog.entities
        if _matches_any_reference(
            normalized_question,
            entity.natural_language_references,
        )
    }
    scope_type = _safe_scope_type(user_context.get("scope_type"))
    scope_resolved = user_context.get("scope_reference_resolved") is True
    matching_guidance = tuple(
        guidance
        for guidance in catalog.authorization_guidance
        if guidance.scope_type == scope_type
    )
    if scope_resolved:
        for guidance in matching_guidance:
            if _matches_any_reference(
                normalized_question,
                guidance.possessive_references,
            ):
                selected_entity_ids.discard(guidance.scope_entity_id)
    entities_by_id = catalog.entities_by_id
    authorized_relationships = tuple(
        relationship
        for relationship in catalog.relationships
        if _relationship_is_authorized(
            relationship,
            entities_by_id,
            allowed_tables,
            allowed_columns,
        )
    )
    selected_entity_ids = _connect_selected_entities(
        selected_entity_ids,
        authorized_relationships,
    )
    selected_entities = tuple(
        entity
        for entity in catalog.entities
        if entity.id in selected_entity_ids and entity.table in allowed_tables
    )
    selected_entity_ids = {entity.id for entity in selected_entities}

    entity_projection = tuple(
        _project_entity(entity, allowed_columns.get(entity.table, frozenset()))
        for entity in selected_entities
    )
    concept_projection = tuple(
        _project_concept(concept, entities_by_id[concept.entity_id])
        for concept in matching_concepts
        if concept.entity_id in selected_entity_ids
        and _concept_columns_are_allowed(
            concept,
            entities_by_id[concept.entity_id],
            allowed_columns,
        )
    )
    selected_concept_ids = {concept["id"] for concept in concept_projection}
    rule_projection = tuple(
        {
            "id": rule.id,
            "description": rule.description,
            "all_of_concept_ids": list(rule.all_of_concept_ids),
            "or_concept_ids": list(rule.or_concept_ids),
        }
        for rule in matching_rules
        if set((*rule.all_of_concept_ids, *rule.or_concept_ids))
        <= selected_concept_ids
    )
    relationship_projection = tuple(
        {
            "id": relationship.id,
            "from_entity": relationship.from_entity,
            "from_column": relationship.from_column,
            "to_entity": relationship.to_entity,
            "to_column": relationship.to_column,
            "cardinality": relationship.cardinality.value,
            "optional": relationship.optional,
            "description": relationship.description,
        }
        for relationship in authorized_relationships
        if relationship.from_entity in selected_entity_ids
        and relationship.to_entity in selected_entity_ids
    )

    guidance_projection = tuple(
        {
            "scope_type": guidance.scope_type,
            "possessive_references": list(guidance.possessive_references),
            "enforcement": guidance.enforcement,
            "description": guidance.description,
            "scope_reference_resolved": scope_resolved,
        }
        for guidance in matching_guidance
    )
    example_projection = tuple(
        {
            "id": example.id,
            "request": example.request,
            "concept_ids": list(example.concept_ids),
        }
        for example in catalog.examples
        if set(example.concept_ids) <= selected_concept_ids
    )

    projection = SemanticCatalogProjection(
        catalog_id=catalog.id,
        catalog_version=catalog.version,
        catalog_hash=catalog.digest,
        entities=entity_projection,
        relationships=relationship_projection,
        concepts=concept_projection,
        composition_rules=rule_projection,
        authorization_guidance=guidance_projection,
        examples=example_projection,
        authoritative_business_terms=tuple(
            sorted(
                {
                    _normalize_phrase(reference)
                    for concept in matching_concepts
                    for reference in concept.natural_language_references
                }
            )
        ),
    )
    serialized_size = len(
        json.dumps(
            projection.as_prompt_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if serialized_size > MAX_SEMANTIC_PROJECTION_BYTES:
        raise DomainPackValidationError(
            "Semantic catalog projection exceeds the safe prompt size limit"
        )
    return projection


def safe_semantic_catalog_observation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    catalog_id = value.get("catalog_id")
    catalog_version = value.get("catalog_version")
    catalog_hash = value.get("catalog_hash")
    entity_ids = _safe_identifier_list(value.get("selected_entity_ids"))
    concept_ids = _safe_identifier_list(value.get("selected_concept_ids"))
    rule_ids = _safe_identifier_list(value.get("selected_rule_ids"))
    if (
        not isinstance(catalog_id, str)
        or _SAFE_IDENTIFIER.fullmatch(catalog_id) is None
        or not isinstance(catalog_version, str)
        or not 1 <= len(catalog_version) <= 64
        or not isinstance(catalog_hash, str)
        or _SAFE_DIGEST.fullmatch(catalog_hash) is None
        or entity_ids is None
        or concept_ids is None
        or rule_ids is None
    ):
        return None
    return {
        "catalog_id": catalog_id,
        "catalog_version": catalog_version,
        "catalog_hash": catalog_hash,
        "selected_entity_ids": entity_ids,
        "selected_concept_ids": concept_ids,
        "selected_rule_ids": rule_ids,
    }


def semantic_catalog_identity(catalog: SemanticCatalog) -> dict[str, str]:
    return {
        "catalog_id": catalog.id,
        "catalog_version": catalog.version,
        "catalog_hash": catalog.digest,
    }


def _project_entity(
    entity: SemanticEntity,
    allowed_columns: frozenset[str],
) -> dict[str, Any]:
    known_values = {
        item.column: list(item.values)
        for item in entity.known_values
        if item.column in allowed_columns
    }
    return {
        "id": entity.id,
        "table": entity.table,
        "description": entity.description,
        "known_values": known_values,
    }


def _project_concept(
    concept: SemanticConcept,
    entity: SemanticEntity,
) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "id": concept.id,
        "entity_id": concept.entity_id,
        "table": entity.table,
        "description": concept.description,
        "required_predicates": [
            {
                "column": predicate.column,
                "operator": predicate.operator.value,
                "value": (
                    list(predicate.value)
                    if isinstance(predicate.value, tuple)
                    else predicate.value
                ),
            }
            for predicate in concept.required_predicates
        ],
    }
    if concept.aggregation is not None:
        projected["aggregation"] = {
            "function": concept.aggregation.function,
            "description": concept.aggregation.description,
        }
    return projected


def _concept_columns_are_allowed(
    concept: SemanticConcept,
    entity: SemanticEntity,
    allowed_columns: Mapping[str, frozenset[str]],
) -> bool:
    entity_columns = allowed_columns.get(entity.table, frozenset())
    return all(
        predicate.column in entity_columns for predicate in concept.required_predicates
    )


def _relationship_is_authorized(
    relationship: SemanticRelationship,
    entities_by_id: Mapping[str, SemanticEntity],
    allowed_tables: frozenset[str],
    allowed_columns: Mapping[str, frozenset[str]],
) -> bool:
    from_table = entities_by_id[relationship.from_entity].table
    to_table = entities_by_id[relationship.to_entity].table
    return (
        from_table in allowed_tables
        and to_table in allowed_tables
        and relationship.from_column
        in allowed_columns.get(from_table, frozenset())
        and relationship.to_column in allowed_columns.get(to_table, frozenset())
    )


def _connect_selected_entities(
    selected_entity_ids: set[str],
    relationships: tuple[SemanticRelationship, ...],
) -> set[str]:
    """Add deterministic validated join-path entities between selected anchors."""

    anchors = sorted(selected_entity_ids)
    if len(anchors) < 2:
        return set(anchors)

    adjacency: dict[str, list[str]] = {}
    for relationship in relationships:
        adjacency.setdefault(relationship.from_entity, []).append(
            relationship.to_entity
        )
        adjacency.setdefault(relationship.to_entity, []).append(
            relationship.from_entity
        )
    for neighbors in adjacency.values():
        neighbors.sort()

    connected = set(anchors)
    for index, start in enumerate(anchors):
        for target in anchors[index + 1 :]:
            path = _shortest_entity_path(start, target, adjacency)
            if path is not None:
                connected.update(path)
    return connected


def _shortest_entity_path(
    start: str,
    target: str,
    adjacency: Mapping[str, list[str]],
) -> tuple[str, ...] | None:
    frontier: list[tuple[str, tuple[str, ...]]] = [(start, (start,))]
    visited = {start}
    while frontier:
        current, path = frontier.pop(0)
        for neighbor in adjacency.get(current, []):
            if neighbor in visited:
                continue
            candidate = (*path, neighbor)
            if neighbor == target:
                return candidate
            visited.add(neighbor)
            frontier.append((neighbor, candidate))
    return None


def _catalog_identity_document(catalog: SemanticCatalog) -> dict[str, Any]:
    return {
        "catalog": {
            "id": catalog.id,
            "version": catalog.version,
            "domain_id": catalog.domain_id,
            "dataset_id": catalog.dataset_id,
        },
        "entities": [
            {
                "id": entity.id,
                "table": entity.table,
                "description": entity.description,
                "natural_language_references": list(
                    entity.natural_language_references
                ),
                "known_values": [
                    {"column": item.column, "values": list(item.values)}
                    for item in entity.known_values
                ],
            }
            for entity in catalog.entities
        ],
        "relationships": [
            {
                "id": relationship.id,
                "from_entity": relationship.from_entity,
                "from_column": relationship.from_column,
                "to_entity": relationship.to_entity,
                "to_column": relationship.to_column,
                "cardinality": relationship.cardinality.value,
                "optional": relationship.optional,
                "description": relationship.description,
            }
            for relationship in catalog.relationships
        ],
        "concepts": [
            {
                "id": concept.id,
                "entity_id": concept.entity_id,
                "description": concept.description,
                "natural_language_references": list(
                    concept.natural_language_references
                ),
                "required_predicates": [
                    {
                        "column": predicate.column,
                        "operator": predicate.operator.value,
                        "value": (
                            list(predicate.value)
                            if isinstance(predicate.value, tuple)
                            else predicate.value
                        ),
                    }
                    for predicate in concept.required_predicates
                ],
                "aggregation": (
                    {
                        "function": concept.aggregation.function,
                        "description": concept.aggregation.description,
                    }
                    if concept.aggregation is not None
                    else None
                ),
                "supersedes": list(concept.supersedes),
            }
            for concept in catalog.concepts
        ],
        "composition_rules": [
            {
                "id": rule.id,
                "description": rule.description,
                "natural_language_references": list(
                    rule.natural_language_references
                ),
                "all_of_concept_ids": list(rule.all_of_concept_ids),
                "or_concept_ids": list(rule.or_concept_ids),
            }
            for rule in catalog.composition_rules
        ],
        "authorization_guidance": [
            {
                "scope_type": guidance.scope_type,
                "scope_entity_id": guidance.scope_entity_id,
                "possessive_references": list(guidance.possessive_references),
                "enforcement": guidance.enforcement,
                "description": guidance.description,
            }
            for guidance in catalog.authorization_guidance
        ],
        "restricted_tables": list(catalog.restricted_tables),
        "examples": [
            {
                "id": example.id,
                "request": example.request,
                "concept_ids": list(example.concept_ids),
            }
            for example in catalog.examples
        ],
    }


def _normalize_phrase(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _matches_any_reference(
    normalized_question: str,
    references: tuple[str, ...],
) -> bool:
    question_tokens = normalized_question.split()
    return any(
        _contains_token_sequence(question_tokens, _normalize_phrase(reference).split())
        for reference in references
    )


def _remove_superseded_concepts(
    concepts: tuple[SemanticConcept, ...],
    concepts_by_id: Mapping[str, SemanticConcept],
) -> tuple[SemanticConcept, ...]:
    selected_ids = {concept.id for concept in concepts}
    superseded: set[str] = set()
    frontier = [
        concept_id
        for concept in concepts
        for concept_id in concept.supersedes
    ]
    while frontier:
        concept_id = frontier.pop()
        if concept_id in superseded:
            continue
        superseded.add(concept_id)
        concept = concepts_by_id.get(concept_id)
        if concept is not None:
            frontier.extend(concept.supersedes)
    return tuple(
        concept
        for concept in concepts
        if concept.id in selected_ids and concept.id not in superseded
    )


def _contains_token_sequence(question: list[str], reference: list[str]) -> bool:
    if not reference or len(reference) > len(question):
        return False
    return any(
        question[index : index + len(reference)] == reference
        for index in range(len(question) - len(reference) + 1)
    )


def _safe_string_set(value: Any) -> frozenset[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str))


def _safe_allowed_columns(value: Any) -> dict[str, frozenset[str]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(table): _safe_string_set(columns)
        for table, columns in value.items()
        if isinstance(table, str)
    }


def _safe_scope_type(value: Any) -> str:
    if isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value):
        return value
    return "none"


def _safe_identifier_list(value: Any) -> list[str] | None:
    if not isinstance(value, list | tuple) or len(value) > 100:
        return None
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or _SAFE_IDENTIFIER.fullmatch(item) is None:
            return None
        normalized.append(item)
    if normalized != sorted(set(normalized)):
        return None
    return normalized
