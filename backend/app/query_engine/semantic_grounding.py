from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Mapping
from typing import Any, Literal

from app.query_engine.errors import DomainPackValidationError
from app.query_engine.result_intent import (
    GroundedAggregationIntent,
    GroundedFieldIdentity,
    GroundedHavingIntent,
    GroundedResultIntent,
    GroundedRowGrain,
)
from app.query_engine.semantic_catalog import (
    MAX_SEMANTIC_PROJECTION_BYTES,
    SemanticCatalog,
    SemanticCatalogProjection,
    SemanticConcept,
    SemanticEntity,
    SemanticMetric,
    SemanticRelationship,
    effective_semantic_predicates,
    expand_semantic_concept_ids,
)


_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "show",
        "that",
        "the",
        "their",
        "there",
        "to",
        "which",
        "who",
        "with",
    }
)
_SINGULAR_SUFFIXES: dict[str, str] = {
    "accounts": "account",
    "assignments": "assignment",
    "departments": "department",
    "devices": "device",
    "employees": "employee",
    "endpoints": "endpoint",
    "events": "event",
    "groups": "group",
    "licenses": "license",
    "logins": "login",
    "memberships": "membership",
    "requests": "request",
    "tickets": "ticket",
    "users": "user",
}
_CONTRACTIONS = (
    (re.compile(r"\bhaven't\b", re.IGNORECASE), "have not"),
    (re.compile(r"\bhasn't\b", re.IGNORECASE), "has not"),
    (re.compile(r"\baren't\b", re.IGNORECASE), "are not"),
    (re.compile(r"\bisn't\b", re.IGNORECASE), "is not"),
)
_DISPLAY_ATTRIBUTE_TOKENS = frozenset(
    {
        "cost",
        "department",
        "description",
        "email",
        "hostname",
        "model",
        "name",
        "owner",
        "product",
        "title",
        "vendor",
    }
)
_COLUMN_SUFFIX_TOKENS = frozenset({"at", "id", "usd"})
_NUMBER_TOKENS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
_HavingOperator = Literal[
    "equals",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
]


def build_semantic_grounding_projection(
    catalog: SemanticCatalog,
    question: str,
    schema_context: Mapping[str, Any],
    user_context: Mapping[str, Any],
) -> SemanticCatalogProjection:
    """Build a deterministic, bounded candidate set from authorized semantics."""

    question_tokens = _normalize_tokens(question)
    allowed_tables = _safe_string_set(schema_context.get("allowed_tables"))
    allowed_columns = _safe_allowed_columns(schema_context.get("allowed_columns"))
    entities_by_id = catalog.entities_by_id

    eligible_entities = {
        entity.id: entity
        for entity in catalog.entities
        if entity.table in allowed_tables
    }
    eligible_concepts = {
        concept.id: concept
        for concept in catalog.concepts
        if concept.entity_id in eligible_entities
        and _concept_is_authorized(concept, catalog, allowed_columns)
    }
    eligible_metrics = {
        metric.id: metric
        for metric in catalog.metrics
        if metric.entity_id in eligible_entities
        and set(expand_semantic_concept_ids(catalog, metric.required_concept_ids))
        <= eligible_concepts.keys()
    }
    eligible_relationships = tuple(
        relationship
        for relationship in catalog.relationships
        if _relationship_is_authorized(
            relationship,
            entities_by_id,
            allowed_tables,
            allowed_columns,
        )
    )

    entity_match_spans = {
        entity.id: spans
        for entity in eligible_entities.values()
        if (
            spans := _matching_reference_spans(
                question_tokens,
                entity.natural_language_references,
            )
        )
    }
    exact_entity_ids = set(entity_match_spans)
    concept_match_spans = {
        concept.id: spans
        for concept in eligible_concepts.values()
        if (
            spans := _matching_reference_spans(
                question_tokens,
                concept.natural_language_references,
                reject_negated=True,
            )
        )
    }
    exact_concept_ids = {
        concept_id for concept_id in concept_match_spans
    }
    exact_metric_ids = {
        metric.id
        for metric in eligible_metrics.values()
        if _matches_semantic_reference(
            question_tokens,
            metric.natural_language_references,
        )
    }
    exact_rule_ids = {
        rule.id
        for rule in catalog.composition_rules
        if _matches_semantic_reference(
            question_tokens,
            rule.natural_language_references,
        )
        and set((*rule.all_of_concept_ids, *rule.or_concept_ids))
        <= eligible_concepts.keys()
    }

    rule_concept_ids = {
        concept_id
        for rule in catalog.composition_rules
        if rule.id in exact_rule_ids
        for concept_id in (*rule.all_of_concept_ids, *rule.or_concept_ids)
    }
    semantic_base_entity_ids = {
        eligible_concepts[concept_id].entity_id
        for concept_id in set(exact_concept_ids) | rule_concept_ids
    }
    semantic_base_entity_ids.update(
        eligible_metrics[metric_id].entity_id for metric_id in exact_metric_ids
    )
    semantic_match_spans_by_entity: dict[str, set[tuple[int, int]]] = {}
    for concept_id, spans in concept_match_spans.items():
        semantic_match_spans_by_entity.setdefault(
            eligible_concepts[concept_id].entity_id,
            set(),
        ).update(spans)
    mandatory_entity_ids = _specific_entity_match_ids(
        entity_match_spans,
        semantic_match_spans_by_entity,
    ) | semantic_base_entity_ids
    mandatory_entity_ids.update(
        entity_id
        for entity_id in exact_entity_ids
        if _entity_has_independently_requested_attribute(
            entity_id,
            source_entity_ids=semantic_base_entity_ids,
            entities=eligible_entities,
            allowed_columns=allowed_columns,
            question_tokens=question_tokens,
        )
    )
    mandatory_entity_ids -= _optional_lookup_entity_ids(
        mandatory_entity_ids=mandatory_entity_ids,
        semantic_base_entity_ids=semantic_base_entity_ids,
        entity_match_spans=entity_match_spans,
        relationships=eligible_relationships,
        entities=eligible_entities,
        allowed_columns=allowed_columns,
        question_tokens=question_tokens,
    )

    direct_anchor_entity_ids = set(exact_entity_ids)
    direct_anchor_entity_ids.update(
        eligible_concepts[concept_id].entity_id for concept_id in exact_concept_ids
    )
    direct_anchor_entity_ids.update(
        eligible_metrics[metric_id].entity_id for metric_id in exact_metric_ids
    )

    description_entity_ids: set[str] = set()
    if not direct_anchor_entity_ids and not exact_rule_ids:
        fallback_entity_id = _unique_description_anchor(
            question_tokens,
            eligible_entities,
        )
        if fallback_entity_id is not None:
            description_entity_ids.add(fallback_entity_id)

    anchor_entity_ids = direct_anchor_entity_ids | description_entity_ids
    anchor_entity_ids.update(
        eligible_concepts[concept_id].entity_id for concept_id in exact_concept_ids
    )
    anchor_entity_ids.update(
        eligible_metrics[metric_id].entity_id for metric_id in exact_metric_ids
    )

    rules_by_id = {rule.id: rule for rule in catalog.composition_rules}
    anchor_entity_ids.update(
        eligible_concepts[concept_id].entity_id for concept_id in rule_concept_ids
    )

    scope_type = _safe_scope_type(user_context.get("scope_type"))
    scope_resolved = user_context.get("scope_reference_resolved") is True
    matching_guidance = tuple(
        guidance
        for guidance in catalog.authorization_guidance
        if guidance.scope_type == scope_type
    )
    resolved_scope_entity_ids: set[str] = set()
    if scope_resolved:
        for guidance in catalog.authorization_guidance:
            if _matches_any_reference(question_tokens, guidance.possessive_references):
                resolved_scope_entity_ids.add(guidance.scope_entity_id)
                anchor_entity_ids.discard(guidance.scope_entity_id)
                # Possessive scope language (for example, "my department") is
                # authorization context, not a requested business entity.  Keep
                # it out of both the candidate projection and mandatory exact
                # evidence so the plan cannot be forced to materialize an RLS
                # scope table or literal scope predicate.
                exact_entity_ids.discard(guidance.scope_entity_id)
                mandatory_entity_ids.discard(guidance.scope_entity_id)

    value_context_entity_ids = {
        entity_id
        for entity_id in anchor_entity_ids
        if _entity_has_known_value_signal(eligible_entities[entity_id], question_tokens)
    }

    selected_concept_ids = {
        concept.id
        for concept in eligible_concepts.values()
        if concept.entity_id in anchor_entity_ids
    }
    selected_concept_ids.update(exact_concept_ids)
    selected_concept_ids.update(rule_concept_ids)
    selected_metric_ids = {
        metric.id
        for metric in eligible_metrics.values()
        if metric.entity_id in anchor_entity_ids
    }
    selected_metric_ids.update(exact_metric_ids)
    for metric_id in selected_metric_ids:
        selected_concept_ids.update(
            expand_semantic_concept_ids(
                catalog,
                eligible_metrics[metric_id].required_concept_ids,
            )
        )
    selected_concept_ids.update(
        expand_semantic_concept_ids(catalog, tuple(selected_concept_ids))
    )
    mandatory_concept_ids = set(
        expand_semantic_concept_ids(
            catalog,
            tuple(
                set(exact_concept_ids)
                | rule_concept_ids
                | {
                    concept_id
                    for metric_id in exact_metric_ids
                    for concept_id in eligible_metrics[
                        metric_id
                    ].required_concept_ids
                }
            ),
        )
    )
    selected_concept_ids = _remove_superseded_candidates(
        selected_concept_ids,
        trigger_concept_ids=set(exact_concept_ids) | rule_concept_ids,
        catalog=catalog,
    )
    retained_intent_concept_ids = set(selected_concept_ids)
    selected_concept_ids.update(
        expand_semantic_concept_ids(catalog, tuple(retained_intent_concept_ids))
    )
    dependency_definition_concept_ids = (
        selected_concept_ids - retained_intent_concept_ids
    )
    mandatory_concept_ids &= retained_intent_concept_ids
    required_concept_definition_ids = set(
        expand_semantic_concept_ids(catalog, tuple(mandatory_concept_ids))
    )
    anchor_entity_ids.update(
        eligible_concepts[concept_id].entity_id for concept_id in selected_concept_ids
    )
    grounded_result_intent, suggested_result_intent = _build_grounded_result_intents(
        catalog=catalog,
        question_tokens=question_tokens,
        entity_match_spans=entity_match_spans,
        resolved_scope_entity_ids=resolved_scope_entity_ids,
        concept_match_spans=concept_match_spans,
        exact_concept_ids=exact_concept_ids,
        exact_metric_ids=exact_metric_ids,
        relationships=eligible_relationships,
        entities=eligible_entities,
        allowed_columns=allowed_columns,
    )
    for result_intent in (grounded_result_intent, suggested_result_intent):
        if result_intent is None:
            continue
        entity_id_by_table = {
            entity.table: entity.id for entity in eligible_entities.values()
        }
        anchor_entity_ids.update(
            entity_id_by_table[field.table]
            for field in result_intent.referenced_fields()
            if field.table in entity_id_by_table
        )

    selected_relationship_ids, path_entity_ids = _select_shortest_relationship_paths(
        anchor_entity_ids,
        eligible_relationships,
    )
    selected_entity_ids = anchor_entity_ids | path_entity_ids

    entity_projection = tuple(
        _project_entity(entity, allowed_columns.get(entity.table, frozenset()))
        for entity in catalog.entities
        if entity.id in selected_entity_ids and entity.id in eligible_entities
    )
    concept_projection = tuple(
        _project_concept(concept, entities_by_id[concept.entity_id])
        for concept in catalog.concepts
        if concept.id in selected_concept_ids and concept.id in eligible_concepts
    )
    metric_projection = tuple(
        _project_metric(metric)
        for metric in catalog.metrics
        if metric.id in selected_metric_ids and metric.id in eligible_metrics
    )
    rule_projection = tuple(
        {
            "id": rule.id,
            "description": rule.description,
            "all_of_concept_ids": list(rule.all_of_concept_ids),
            "or_concept_ids": list(rule.or_concept_ids),
        }
        for rule in catalog.composition_rules
        if rule.id in exact_rule_ids
        and set((*rule.all_of_concept_ids, *rule.or_concept_ids))
        <= selected_concept_ids
    )
    relationship_projection = tuple(
        _project_relationship(relationship)
        for relationship in eligible_relationships
        if relationship.id in selected_relationship_ids
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

    candidate_signals = _candidate_signals(
        exact_entity_ids=exact_entity_ids,
        mandatory_entity_ids=mandatory_entity_ids,
        description_entity_ids=description_entity_ids,
        value_context_entity_ids=value_context_entity_ids,
        exact_concept_ids=exact_concept_ids,
        dependency_definition_concept_ids=dependency_definition_concept_ids,
        selected_concept_ids=selected_concept_ids,
        exact_metric_ids=exact_metric_ids,
        selected_metric_ids=selected_metric_ids,
        exact_rule_ids=exact_rule_ids,
    )
    example_projection = _select_examples(
        catalog,
        question_tokens=question_tokens,
        selected_entity_ids=selected_entity_ids,
        selected_concept_ids=selected_concept_ids,
        selected_metric_ids=selected_metric_ids,
        selected_rule_ids=exact_rule_ids,
        selected_relationship_ids=selected_relationship_ids,
        exact_entity_ids=exact_entity_ids,
        exact_concept_ids=exact_concept_ids,
        exact_metric_ids=exact_metric_ids,
        exact_rule_ids=exact_rule_ids,
        allowed_columns=allowed_columns,
    )

    projection = SemanticCatalogProjection(
        catalog_id=catalog.id,
        catalog_version=catalog.version,
        catalog_hash=catalog.digest,
        entities=entity_projection,
        relationships=relationship_projection,
        concepts=concept_projection,
        metrics=metric_projection,
        composition_rules=rule_projection,
        authorization_guidance=guidance_projection,
        examples=example_projection,
        candidate_signals=candidate_signals,
        authoritative_business_terms=tuple(
            sorted(
                {
                    _normalize_phrase(reference)
                    for concept_id in exact_concept_ids
                    for reference in eligible_concepts[
                        concept_id
                    ].natural_language_references
                }
                | {
                    _normalize_phrase(reference)
                    for metric_id in exact_metric_ids
                    for reference in eligible_metrics[
                        metric_id
                    ].natural_language_references
                }
                | {
                    _normalize_phrase(reference)
                    for rule_id in exact_rule_ids
                    for reference in rules_by_id[
                        rule_id
                    ].natural_language_references
                }
            )
        ),
        grounded_result_intent=grounded_result_intent,
        suggested_result_intent=suggested_result_intent,
    )
    projection = _fit_projection(
        projection,
        required_concept_definition_ids=required_concept_definition_ids,
        mandatory_metric_ids=set(exact_metric_ids),
    )
    _validate_projection_concept_dependency_closure(projection)
    if _projection_size(projection) > MAX_SEMANTIC_PROJECTION_BYTES:
        raise DomainPackValidationError(
            "Semantic catalog projection exceeds the safe prompt size limit"
        )
    return projection


def _concept_is_authorized(
    concept: SemanticConcept,
    catalog: SemanticCatalog,
    allowed_columns: Mapping[str, frozenset[str]],
) -> bool:
    entity = catalog.entities_by_id[concept.entity_id]
    columns = allowed_columns.get(entity.table, frozenset())
    return all(
        predicate.column in columns
        for predicate in effective_semantic_predicates(catalog, (concept.id,))
    )


def _relationship_is_authorized(
    relationship: SemanticRelationship,
    entities: Mapping[str, SemanticEntity],
    allowed_tables: frozenset[str],
    allowed_columns: Mapping[str, frozenset[str]],
) -> bool:
    from_table = entities[relationship.from_entity].table
    to_table = entities[relationship.to_entity].table
    return (
        from_table in allowed_tables
        and to_table in allowed_tables
        and relationship.from_column in allowed_columns.get(from_table, frozenset())
        and relationship.to_column in allowed_columns.get(to_table, frozenset())
    )


def _select_shortest_relationship_paths(
    anchors: set[str],
    relationships: tuple[SemanticRelationship, ...],
) -> tuple[set[str], set[str]]:
    if len(anchors) < 2:
        return set(), set(anchors)
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for relationship in relationships:
        adjacency.setdefault(relationship.from_entity, []).append(
            (relationship.to_entity, relationship.id)
        )
        adjacency.setdefault(relationship.to_entity, []).append(
            (relationship.from_entity, relationship.id)
        )
    for edges in adjacency.values():
        edges.sort()

    relationship_ids: set[str] = set()
    entity_ids = set(anchors)
    ordered = sorted(anchors)
    for index, start in enumerate(ordered):
        for target in ordered[index + 1 :]:
            paths = _all_shortest_paths(start, target, adjacency)
            for entities, path_relationships in paths[:2]:
                entity_ids.update(entities)
                relationship_ids.update(path_relationships)
    return relationship_ids, entity_ids


def _all_shortest_paths(
    start: str,
    target: str,
    adjacency: Mapping[str, list[tuple[str, str]]],
) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    frontier: deque[tuple[str, tuple[str, ...], tuple[str, ...]]] = deque(
        [(start, (start,), ())]
    )
    best_depth: int | None = None
    paths: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    while frontier:
        current, entities, relationships = frontier.popleft()
        depth = len(relationships)
        if best_depth is not None and depth >= best_depth:
            continue
        for neighbor, relationship_id in adjacency.get(current, []):
            if neighbor in entities:
                continue
            candidate_entities = (*entities, neighbor)
            candidate_relationships = (*relationships, relationship_id)
            if neighbor == target:
                best_depth = len(candidate_relationships)
                paths.append((candidate_entities, candidate_relationships))
            else:
                frontier.append(
                    (neighbor, candidate_entities, candidate_relationships)
                )
    return sorted(set(paths), key=lambda item: (item[1], item[0]))


def _project_entity(
    entity: SemanticEntity,
    allowed_columns: frozenset[str],
) -> dict[str, Any]:
    return {
        "id": entity.id,
        "table": entity.table,
        "description": entity.description,
        "known_values": {
            item.column: list(item.values)
            for item in entity.known_values
            if item.column in allowed_columns
        },
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
                "value": list(predicate.value)
                if isinstance(predicate.value, tuple)
                else predicate.value,
            }
            for predicate in concept.required_predicates
        ],
        "all_of_concept_ids": list(concept.all_of_concept_ids),
    }
    if concept.aggregation is not None:
        projected["aggregation"] = {
            "function": concept.aggregation.function,
            "description": concept.aggregation.description,
        }
    return projected


def _project_metric(metric: SemanticMetric) -> dict[str, Any]:
    return {
        "id": metric.id,
        "entity_id": metric.entity_id,
        "description": metric.description,
        "required_concept_ids": list(metric.required_concept_ids),
        "aggregation": {
            "function": metric.aggregation.function,
            "description": metric.aggregation.description,
        },
    }


def _project_relationship(relationship: SemanticRelationship) -> dict[str, Any]:
    return {
        "id": relationship.id,
        "from_entity": relationship.from_entity,
        "from_column": relationship.from_column,
        "to_entity": relationship.to_entity,
        "to_column": relationship.to_column,
        "cardinality": relationship.cardinality.value,
        "optional": relationship.optional,
        "description": relationship.description,
    }


def _candidate_signals(
    *,
    exact_entity_ids: set[str],
    mandatory_entity_ids: set[str],
    description_entity_ids: set[str],
    value_context_entity_ids: set[str],
    exact_concept_ids: set[str],
    dependency_definition_concept_ids: set[str],
    selected_concept_ids: set[str],
    exact_metric_ids: set[str],
    selected_metric_ids: set[str],
    exact_rule_ids: set[str],
) -> tuple[dict[str, str], ...]:
    signals: dict[tuple[str, str], str] = {}
    for item_id in selected_concept_ids:
        signals[("concept", item_id)] = (
            "exact_reference"
            if item_id in exact_concept_ids
            and item_id not in dependency_definition_concept_ids
            else "entity_context"
        )
    for item_id in selected_metric_ids:
        signals[("metric", item_id)] = (
            "exact_reference" if item_id in exact_metric_ids else "entity_context"
        )
    for item_id in exact_rule_ids:
        signals[("composition_rule", item_id)] = "exact_reference"
    for item_id in exact_entity_ids | mandatory_entity_ids:
        signals[("entity", item_id)] = (
            "exact_reference"
            if item_id in mandatory_entity_ids
            else "lexical_context"
        )
    for item_id in description_entity_ids - exact_entity_ids - mandatory_entity_ids:
        signals[("entity", item_id)] = "description_context"
    for item_id in value_context_entity_ids - exact_entity_ids - mandatory_entity_ids:
        signals[("entity", item_id)] = "value_context"
    return tuple(
        {"kind": kind, "id": item_id, "tier": tier}
        for (kind, item_id), tier in sorted(signals.items())
    )


def _select_examples(
    catalog: SemanticCatalog,
    *,
    question_tokens: tuple[str, ...],
    selected_entity_ids: set[str],
    selected_concept_ids: set[str],
    selected_metric_ids: set[str],
    selected_rule_ids: set[str],
    selected_relationship_ids: set[str],
    exact_entity_ids: set[str],
    exact_concept_ids: set[str],
    exact_metric_ids: set[str],
    exact_rule_ids: set[str],
    allowed_columns: Mapping[str, frozenset[str]],
) -> tuple[dict[str, Any], ...]:
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for example in catalog.examples:
        if not set(example.entity_ids) <= selected_entity_ids:
            continue
        if not set(example.concept_ids) <= selected_concept_ids:
            continue
        if not set(example.composition_rule_ids) <= selected_rule_ids:
            continue
        example_relationship_ids = {
            relationship.relationship_id for relationship in example.relationships
        }
        if not example_relationship_ids <= selected_relationship_ids:
            continue
        if example.metric_id is not None and example.metric_id not in selected_metric_ids:
            continue
        if not _example_fields_are_authorized(example, catalog, allowed_columns):
            continue
        example_tokens = {
            token
            for token in _normalize_tokens(example.request)
            if token not in _STOP_WORDS
        }
        lexical_overlap = len(
            example_tokens
            & {token for token in question_tokens if token not in _STOP_WORDS}
        )
        direct_semantic_overlap = (
            (100 if example.metric_id in exact_metric_ids else 0)
            + 24 * len(set(example.concept_ids) & exact_concept_ids)
            + 20 * len(set(example.composition_rule_ids) & exact_rule_ids)
        )
        lexical_match = (
            lexical_overlap >= 2
            and lexical_overlap / max(len(example_tokens), 1) >= 0.4
        )
        if not lexical_match and direct_semantic_overlap == 0:
            continue
        score = (
            direct_semantic_overlap
            + 6 * lexical_overlap
            + 4 * len(set(example.entity_ids) & exact_entity_ids)
            + 2 * len(example_relationship_ids & selected_relationship_ids)
        )
        candidates.append((score, example.id, _project_example(example)))
    chosen = sorted(candidates, key=lambda item: (-item[0], item[1]))[:3]
    return tuple(item[2] for item in sorted(chosen, key=lambda item: item[1]))


def _example_fields_are_authorized(
    example: Any,
    catalog: SemanticCatalog,
    allowed_columns: Mapping[str, frozenset[str]],
) -> bool:
    entities = catalog.entities_by_id
    fields = [item.field for item in example.literal_filters]
    fields.extend(example.group_by)
    return all(
        field.column
        in allowed_columns.get(entities[field.entity_id].table, frozenset())
        for field in fields
    )


def _project_example(example: Any) -> dict[str, Any]:
    return {
        "id": example.id,
        "request": example.request,
        "entity_ids": list(example.entity_ids),
        "concept_ids": list(example.concept_ids),
        "composition_rule_ids": list(example.composition_rule_ids),
        "metric_id": example.metric_id,
        "distinct": example.distinct,
        "literal_filters": [
            {
                "field": {
                    "entity_id": item.field.entity_id,
                    "column": item.field.column,
                },
                "operator": item.operator,
                "value": list(item.value)
                if isinstance(item.value, tuple)
                else item.value,
            }
            for item in example.literal_filters
        ],
        "relationships": [
            {
                "relationship_id": item.relationship_id,
                "join_type": item.join_type,
            }
            for item in example.relationships
        ],
        "aggregation_functions": list(example.aggregation_functions),
        "group_by": [
            {"entity_id": item.entity_id, "column": item.column}
            for item in example.group_by
        ],
        "clarification_reason": example.clarification_reason,
    }


def _fit_projection(
    projection: SemanticCatalogProjection,
    *,
    required_concept_definition_ids: set[str],
    mandatory_metric_ids: set[str],
) -> SemanticCatalogProjection:
    examples = list(projection.examples)
    while examples and _projection_size(projection) > MAX_SEMANTIC_PROJECTION_BYTES:
        examples.pop()
        projection = _copy_projection(projection, examples=tuple(examples))

    optional_entity_ids = sorted(
        {
            concept["entity_id"]
            for concept in projection.concepts
            if concept["id"] not in required_concept_definition_ids
        }
        | {
            metric["entity_id"]
            for metric in projection.metrics
            if metric["id"] not in mandatory_metric_ids
        },
        reverse=True,
    )
    for entity_id in optional_entity_ids:
        if _projection_size(projection) <= MAX_SEMANTIC_PROJECTION_BYTES:
            break
        retained_concepts = tuple(
            concept
            for concept in projection.concepts
            if concept["entity_id"] != entity_id
            or concept["id"] in required_concept_definition_ids
        )
        retained_concept_ids = {concept["id"] for concept in retained_concepts}
        retained_metrics = tuple(
            metric
            for metric in projection.metrics
            if (
                metric["entity_id"] != entity_id
                or metric["id"] in mandatory_metric_ids
            )
            and set(metric["required_concept_ids"]) <= retained_concept_ids
        )
        retained_metric_ids = {metric["id"] for metric in retained_metrics}
        retained_signals = tuple(
            signal
            for signal in projection.candidate_signals
            if signal["kind"] not in {"concept", "metric"}
            or (
                signal["kind"] == "concept"
                and signal["id"] in retained_concept_ids
            )
            or (
                signal["kind"] == "metric"
                and signal["id"] in retained_metric_ids
            )
        )
        projection = _copy_projection(
            projection,
            concepts=retained_concepts,
            metrics=retained_metrics,
            candidate_signals=retained_signals,
            examples=(),
        )
    return projection


def _validate_projection_concept_dependency_closure(
    projection: SemanticCatalogProjection,
) -> None:
    retained_concept_ids = {
        concept["id"] for concept in projection.concepts
    }
    if any(
        not set(concept["all_of_concept_ids"]) <= retained_concept_ids
        for concept in projection.concepts
    ):
        raise DomainPackValidationError(
            "Semantic catalog projection has incomplete concept dependency closure"
        )


def _copy_projection(
    projection: SemanticCatalogProjection,
    **changes: Any,
) -> SemanticCatalogProjection:
    values = {
        "catalog_id": projection.catalog_id,
        "catalog_version": projection.catalog_version,
        "catalog_hash": projection.catalog_hash,
        "entities": projection.entities,
        "relationships": projection.relationships,
        "concepts": projection.concepts,
        "metrics": projection.metrics,
        "composition_rules": projection.composition_rules,
        "authorization_guidance": projection.authorization_guidance,
        "examples": projection.examples,
        "candidate_signals": projection.candidate_signals,
        "authoritative_business_terms": projection.authoritative_business_terms,
        "grounded_result_intent": projection.grounded_result_intent,
        "suggested_result_intent": projection.suggested_result_intent,
    }
    values.update(changes)
    return SemanticCatalogProjection(**values)


def _projection_size(projection: SemanticCatalogProjection) -> int:
    return len(
        json.dumps(
            projection.as_prompt_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _entity_has_known_value_signal(
    entity: SemanticEntity,
    question_tokens: tuple[str, ...],
) -> bool:
    return any(
        _contains_token_sequence(question_tokens, _normalize_tokens(str(value)))
        for known_values in entity.known_values
        for value in known_values.values
    )


def _description_score(
    question_tokens: tuple[str, ...],
    description: str,
) -> int:
    question = {token for token in question_tokens if token not in _STOP_WORDS}
    described = {
        token for token in _normalize_tokens(description) if token not in _STOP_WORDS
    }
    return len(question & described)


def _unique_description_anchor(
    question_tokens: tuple[str, ...],
    entities: Mapping[str, SemanticEntity],
) -> str | None:
    scored = sorted(
        (
            (_description_score(question_tokens, entity.description), entity.id)
            for entity in entities.values()
        ),
        key=lambda item: (-item[0], item[1]),
    )
    if not scored or scored[0][0] < 2:
        return None
    if len(scored) > 1 and scored[0][0] <= scored[1][0]:
        return None
    return scored[0][1]


def _remove_superseded_candidates(
    selected_concept_ids: set[str],
    *,
    trigger_concept_ids: set[str],
    catalog: SemanticCatalog,
) -> set[str]:
    superseded: set[str] = set()
    frontier = [
        superseded_id
        for concept_id in trigger_concept_ids
        if concept_id in catalog.concepts_by_id
        for superseded_id in catalog.concepts_by_id[concept_id].supersedes
    ]
    while frontier:
        concept_id = frontier.pop()
        if concept_id in superseded:
            continue
        superseded.add(concept_id)
        concept = catalog.concepts_by_id.get(concept_id)
        if concept is not None:
            frontier.extend(concept.supersedes)
    return selected_concept_ids - superseded


def _build_grounded_result_intents(
    *,
    catalog: SemanticCatalog,
    question_tokens: tuple[str, ...],
    entity_match_spans: Mapping[str, set[tuple[int, int]]],
    resolved_scope_entity_ids: set[str],
    concept_match_spans: Mapping[str, set[tuple[int, int]]],
    exact_concept_ids: set[str],
    exact_metric_ids: set[str],
    relationships: tuple[SemanticRelationship, ...],
    entities: Mapping[str, SemanticEntity],
    allowed_columns: Mapping[str, frozenset[str]],
) -> tuple[GroundedResultIntent | None, GroundedResultIntent | None]:
    # Canonical V1 metrics already own their complete scalar result contract.
    if exact_metric_ids:
        return None, None

    exact_concept_entity_ids = {
        catalog.concepts_by_id[concept_id].entity_id
        for concept_id in exact_concept_ids
    }
    subject_entity_match_spans = {
        entity_id: spans
        for entity_id, spans in entity_match_spans.items()
        if entity_id not in resolved_scope_entity_ids
    }
    required_output_fields = set(
        _explicit_output_fields(
            question_tokens,
            entities=entities,
            allowed_columns=allowed_columns,
        )
    )
    grouping = _explicit_grouping_field(
        question_tokens,
        entity_match_spans=entity_match_spans,
        entities=entities,
        allowed_columns=allowed_columns,
    )
    threshold = _explicit_numeric_threshold(question_tokens)
    quantity_span = _explicit_quantity_span(question_tokens)
    aggregations: list[GroundedAggregationIntent] = []
    suggested_aggregations: list[GroundedAggregationIntent] = []
    having: list[GroundedHavingIntent] = []
    row_grain: GroundedRowGrain | None = None
    suggested_row_grain: GroundedRowGrain | None = None
    suggested_output_fields: set[GroundedFieldIdentity] = set()
    group_by: tuple[GroundedFieldIdentity, ...] = ()
    suggested_group_by: tuple[GroundedFieldIdentity, ...] = ()
    distinct: bool | None = None
    suggested_distinct: bool | None = None

    if grouping is not None:
        grouping_field, marker_start = grouping
        subject_entity_id = _subject_entity_id(
            question_tokens,
            subject_entity_match_spans,
            before_index=marker_start,
            excluded_entity_ids=set(),
        )
        explicit_quantity = quantity_span is not None
        implicit_quantity = (
            subject_entity_id is not None
            and _has_exact_qualifying_bridge(
                subject_entity_id=subject_entity_id,
                grouping_table=grouping_field.table,
                exact_entity_ids=set(entity_match_spans),
                relationships=relationships,
                entities=entities,
            )
        )
        if explicit_quantity or threshold is not None:
            group_by = (grouping_field,)
            required_output_fields.add(grouping_field)
            row_grain = GroundedRowGrain(
                mode="grouped",
                identity_fields=group_by,
            )
        if subject_entity_id is not None and threshold is not None:
            requested_grouping_table = grouping_field.table
            relationship_group_field = _relationship_group_field(
                source_entity_id=subject_entity_id,
                grouping_table=requested_grouping_table,
                relationships=relationships,
                entities=entities,
                allowed_columns=allowed_columns,
            )
            if relationship_group_field is not None:
                required_output_fields.discard(grouping_field)
                grouping_field = relationship_group_field
                group_by = (grouping_field,)
                required_output_fields.add(grouping_field)
                row_grain = GroundedRowGrain(
                    mode="grouped",
                    identity_fields=group_by,
                )
            target = (
                None
                if requested_grouping_table == entities[subject_entity_id].table
                else _authorized_field(
                    subject_entity_id,
                    "id",
                    entities=entities,
                    allowed_columns=allowed_columns,
                )
            )
            if (
                target is not None
                or requested_grouping_table == entities[subject_entity_id].table
            ):
                aggregation = GroundedAggregationIntent(
                    id="threshold_count",
                    function="count",
                    target_field=target,
                    distinct=False,
                )
                aggregations.append(aggregation)
                having.append(
                    GroundedHavingIntent(
                        aggregation_id=aggregation.id,
                        operator=threshold[0],
                        value=threshold[1],
                    )
                )
        elif subject_entity_id is not None and (
            explicit_quantity or implicit_quantity
        ):
            subject_table = entities[subject_entity_id].table
            target = (
                None
                if subject_table == grouping_field.table
                else _authorized_field(
                    subject_entity_id,
                    "id",
                    entities=entities,
                    allowed_columns=allowed_columns,
                )
            )
            if target is not None or subject_table == grouping_field.table:
                aggregation = GroundedAggregationIntent(
                    id="subject_count",
                    function="count",
                    target_field=target,
                    distinct=target is not None,
                )
                if explicit_quantity:
                    aggregations.append(aggregation)
                else:
                    suggested_aggregations.append(aggregation)
                    suggested_group_by = (grouping_field,)
                    suggested_output_fields.add(grouping_field)
                    suggested_row_grain = GroundedRowGrain(
                        mode="grouped",
                        identity_fields=suggested_group_by,
                    )

    if not aggregations and threshold is not None:
        counted_entity_id = _threshold_counted_entity_id(
            threshold_end=threshold[3],
            concept_match_spans=concept_match_spans,
            catalog=catalog,
        )
        if counted_entity_id is not None:
            subject_group_field = _relationship_subject_field(
                counted_entity_id=counted_entity_id,
                question_tokens=question_tokens,
                entity_match_spans=entity_match_spans,
                relationships=relationships,
                entities=entities,
                allowed_columns=allowed_columns,
            )
            target = _authorized_field(
                counted_entity_id,
                "id",
                entities=entities,
                allowed_columns=allowed_columns,
            )
            if subject_group_field is not None and target is not None:
                aggregation = GroundedAggregationIntent(
                    id="threshold_count",
                    function="count",
                    target_field=target,
                    distinct=False,
                )
                aggregations.append(aggregation)
                group_by = (subject_group_field,)
                required_output_fields.add(subject_group_field)
                row_grain = GroundedRowGrain(
                    mode="grouped",
                    identity_fields=group_by,
                )
                having.append(
                    GroundedHavingIntent(
                        aggregation_id=aggregation.id,
                        operator=threshold[0],
                        value=threshold[1],
                    )
                )

    if not aggregations and grouping is None and quantity_span is not None:
        subject_entity_id = _subject_entity_id(
            question_tokens,
            subject_entity_match_spans,
            before_index=len(question_tokens),
            excluded_entity_ids=set(),
        )
        if subject_entity_id is not None:
            aggregations.append(
                GroundedAggregationIntent(
                    id="row_count",
                    function="count",
                    target_field=None,
                    distinct=False,
                )
            )

    if (
        row_grain is None
        and suggested_row_grain is None
        and not aggregations
    ):
        detail_entity_id = _detail_fact_entity_id(
            exact_concept_entity_ids,
            relationships,
        )
        if (
            detail_entity_id is not None
            and question_tokens
            and question_tokens[0] in {"list", "show"}
        ):
            detail_identity = _authorized_field(
                detail_entity_id,
                "id",
                entities=entities,
                allowed_columns=allowed_columns,
            )
            if detail_identity is not None:
                suggested_row_grain = GroundedRowGrain(
                    mode="detail",
                    identity_fields=(detail_identity,),
                )
                suggested_output_fields.add(detail_identity)
                for entity_id in sorted(exact_concept_entity_ids):
                    identity = _authorized_field(
                        entity_id,
                        "id",
                        entities=entities,
                        allowed_columns=allowed_columns,
                    )
                    if identity is not None:
                        suggested_output_fields.add(identity)
                suggested_distinct = False

    if (
        row_grain is None
        and not required_output_fields
        and not aggregations
        and not group_by
        and not having
        and distinct is None
    ):
        required_intent = None
    else:
        required_intent = GroundedResultIntent(
            row_grain=row_grain,
            required_output_fields=tuple(
                sorted(
                    required_output_fields,
                    key=lambda item: (item.table, item.column),
                )
            ),
            aggregations=tuple(aggregations),
            group_by=group_by,
            having=tuple(having),
            distinct=distinct,
        )

    if (
        suggested_row_grain is None
        and not suggested_output_fields
        and not suggested_aggregations
        and not suggested_group_by
        and suggested_distinct is None
    ):
        suggested_intent = None
    else:
        suggested_intent = GroundedResultIntent(
            row_grain=suggested_row_grain,
            required_output_fields=tuple(
                sorted(
                    suggested_output_fields,
                    key=lambda item: (item.table, item.column),
                )
            ),
            aggregations=tuple(suggested_aggregations),
            group_by=suggested_group_by,
            distinct=suggested_distinct,
        )
    return required_intent, suggested_intent


def _explicit_grouping_field(
    question_tokens: tuple[str, ...],
    *,
    entity_match_spans: Mapping[str, set[tuple[int, int]]],
    entities: Mapping[str, SemanticEntity],
    allowed_columns: Mapping[str, frozenset[str]],
) -> tuple[GroundedFieldIdentity, int] | None:
    marker: tuple[int, int] | None = None
    for index, token in enumerate(question_tokens):
        if token in {"by", "per"}:
            marker = (index, index + 1)
            break
        if token == "for" and question_tokens[index : index + 2] == ("for", "each"):
            marker = (index, index + 2)
            break
    if marker is None:
        return None
    marker_start, value_start = marker
    entity_candidates = [
        (start - value_start, end - start, entity_id)
        for entity_id, spans in entity_match_spans.items()
        for start, end in spans
        if start >= value_start and start <= value_start + 2
    ]
    if entity_candidates:
        _, _, entity_id = min(entity_candidates)
        for column in ("name", "id"):
            field = _authorized_field(
                entity_id,
                column,
                entities=entities,
                allowed_columns=allowed_columns,
            )
            if field is not None:
                return field, marker_start

    phrase = question_tokens[value_start : value_start + 2]
    column_candidates: set[GroundedFieldIdentity] = set()
    for entity_id, entity in entities.items():
        for column in allowed_columns.get(entity.table, frozenset()):
            column_tokens = _normalize_tokens(column.replace("_", " "))
            if not column_tokens:
                continue
            references = {column_tokens}
            if column_tokens[-1] in _DISPLAY_ATTRIBUTE_TOKENS:
                references.add((column_tokens[0],))
            if any(
                len(reference) <= len(phrase)
                and phrase[: len(reference)] == reference
                for reference in references
            ):
                column_candidates.add(
                    GroundedFieldIdentity(table=entity.table, column=column)
                )
    if len(column_candidates) == 1:
        return column_candidates.pop(), marker_start
    return None


def _explicit_quantity_span(
    question_tokens: tuple[str, ...],
) -> tuple[int, int] | None:
    references = (("how", "many"), ("number", "of"), ("count",))
    for reference in references:
        for index in range(len(question_tokens) - len(reference) + 1):
            if question_tokens[index : index + len(reference)] == reference:
                return index, index + len(reference)
    return None


def _explicit_numeric_threshold(
    question_tokens: tuple[str, ...],
) -> tuple[_HavingOperator, int | float, int, int] | None:
    operators: tuple[tuple[tuple[str, ...], _HavingOperator], ...] = (
        (("more", "than"), "greater_than"),
        (("at", "least"), "greater_than_or_equal"),
        (("fewer", "than"), "less_than"),
        (("less", "than"), "less_than"),
        (("at", "most"), "less_than_or_equal"),
        (("exactly",), "equals"),
    )
    for reference, operator in operators:
        for index in range(len(question_tokens) - len(reference)):
            if question_tokens[index : index + len(reference)] != reference:
                continue
            value = _number_token_value(question_tokens[index + len(reference)])
            if value is not None:
                return operator, value, index, index + len(reference) + 1
    return None


def _number_token_value(token: str) -> int | float | None:
    if token in _NUMBER_TOKENS:
        return _NUMBER_TOKENS[token]
    try:
        return float(token) if "." in token else int(token)
    except ValueError:
        return None


def _subject_entity_id(
    question_tokens: tuple[str, ...],
    entity_match_spans: Mapping[str, set[tuple[int, int]]],
    *,
    before_index: int,
    excluded_entity_ids: set[str],
) -> str | None:
    candidates = [
        (start, end - start, entity_id)
        for entity_id, spans in entity_match_spans.items()
        if entity_id not in excluded_entity_ids
        for start, end in spans
        if end <= before_index and end - start == 1
    ]
    if not candidates:
        return None
    if question_tokens[:2] in {("how", "many"), ("number", "of")}:
        _, _, entity_id = max(candidates, key=lambda item: (item[0], -item[1], item[2]))
        return entity_id
    _, _, entity_id = min(candidates, key=lambda item: (item[0], item[1], item[2]))
    return entity_id


def _has_exact_qualifying_bridge(
    *,
    subject_entity_id: str,
    grouping_table: str,
    exact_entity_ids: set[str],
    relationships: tuple[SemanticRelationship, ...],
    entities: Mapping[str, SemanticEntity],
) -> bool:
    grouping_entity_ids = {
        entity.id for entity in entities.values() if entity.table == grouping_table
    }
    bridge_ids = exact_entity_ids - {subject_entity_id} - grouping_entity_ids
    for bridge_id in bridge_ids:
        targets = {
            relationship.to_entity
            for relationship in relationships
            if relationship.from_entity == bridge_id
            and relationship.cardinality.value == "many_to_one"
        }
        if subject_entity_id in targets and targets & grouping_entity_ids:
            return True
    return False


def _relationship_group_field(
    *,
    source_entity_id: str,
    grouping_table: str,
    relationships: tuple[SemanticRelationship, ...],
    entities: Mapping[str, SemanticEntity],
    allowed_columns: Mapping[str, frozenset[str]],
) -> GroundedFieldIdentity | None:
    grouping_entity_ids = {
        entity.id for entity in entities.values() if entity.table == grouping_table
    }
    candidates = [
        relationship
        for relationship in relationships
        if relationship.from_entity == source_entity_id
        and relationship.to_entity in grouping_entity_ids
        and relationship.cardinality.value == "many_to_one"
    ]
    if len(candidates) != 1:
        return None
    return _authorized_field(
        source_entity_id,
        candidates[0].from_column,
        entities=entities,
        allowed_columns=allowed_columns,
    )


def _threshold_counted_entity_id(
    *,
    threshold_end: int,
    concept_match_spans: Mapping[str, set[tuple[int, int]]],
    catalog: SemanticCatalog,
) -> str | None:
    candidates = {
        catalog.concepts_by_id[concept_id].entity_id
        for concept_id, spans in concept_match_spans.items()
        if any(start >= threshold_end for start, _ in spans)
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def _relationship_subject_field(
    *,
    counted_entity_id: str,
    question_tokens: tuple[str, ...],
    entity_match_spans: Mapping[str, set[tuple[int, int]]],
    relationships: tuple[SemanticRelationship, ...],
    entities: Mapping[str, SemanticEntity],
    allowed_columns: Mapping[str, frozenset[str]],
) -> GroundedFieldIdentity | None:
    subject_entity_id = _subject_entity_id(
        question_tokens,
        entity_match_spans,
        before_index=len(question_tokens),
        excluded_entity_ids={counted_entity_id},
    )
    if subject_entity_id is None:
        return None
    candidates = [
        relationship
        for relationship in relationships
        if relationship.from_entity == counted_entity_id
        and relationship.to_entity == subject_entity_id
        and relationship.cardinality.value == "many_to_one"
    ]
    if len(candidates) != 1:
        return None
    return _authorized_field(
        counted_entity_id,
        candidates[0].from_column,
        entities=entities,
        allowed_columns=allowed_columns,
    )


def _detail_fact_entity_id(
    exact_concept_entity_ids: set[str],
    relationships: tuple[SemanticRelationship, ...],
) -> str | None:
    candidates = {
        relationship.from_entity
        for relationship in relationships
        if relationship.from_entity in exact_concept_entity_ids
        and relationship.to_entity in exact_concept_entity_ids
        and relationship.cardinality.value == "many_to_one"
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def _explicit_output_fields(
    question_tokens: tuple[str, ...],
    *,
    entities: Mapping[str, SemanticEntity],
    allowed_columns: Mapping[str, frozenset[str]],
) -> tuple[GroundedFieldIdentity, ...]:
    fields: set[GroundedFieldIdentity] = set()
    for entity in entities.values():
        labels: set[tuple[str, ...]] = {
            reference
            for raw_reference in entity.natural_language_references
            if len(reference := _normalize_tokens(raw_reference)) == 1
        }
        canonical_label = _normalize_tokens(entity.id.replace("_", " "))[-1:]
        labels.add(canonical_label)
        for column in allowed_columns.get(entity.table, frozenset()):
            column_tokens = _normalize_tokens(column.replace("_", " "))
            if not column_tokens:
                continue
            if column == "id":
                references = {(*label, "id") for label in labels}
            else:
                references = {
                    (*label, *column_tokens)
                    for label in labels
                    if column_tokens[-1] in _DISPLAY_ATTRIBUTE_TOKENS
                }
            if any(
                _contains_token_sequence(question_tokens, reference)
                for reference in references
            ):
                fields.add(
                    GroundedFieldIdentity(table=entity.table, column=column)
                )
    return tuple(sorted(fields, key=lambda item: (item.table, item.column)))


def _authorized_field(
    entity_id: str,
    column: str,
    *,
    entities: Mapping[str, SemanticEntity],
    allowed_columns: Mapping[str, frozenset[str]],
) -> GroundedFieldIdentity | None:
    entity = entities.get(entity_id)
    if entity is None or column not in allowed_columns.get(entity.table, frozenset()):
        return None
    return GroundedFieldIdentity(table=entity.table, column=column)


def _specific_entity_match_ids(
    entity_match_spans: Mapping[str, set[tuple[int, int]]],
    semantic_match_spans_by_entity: Mapping[str, set[tuple[int, int]]],
) -> set[str]:
    """Keep an entity mandatory when at least one exact mention is not subsumed."""
    mandatory: set[str] = set()
    for entity_id, spans in entity_match_spans.items():
        competing_spans = {
            span
            for other_entity_id, other_spans in entity_match_spans.items()
            if other_entity_id != entity_id
            for span in other_spans
        }
        competing_spans.update(
            span
            for other_entity_id, other_spans in semantic_match_spans_by_entity.items()
            if other_entity_id != entity_id
            for span in other_spans
        )
        if any(
            not any(_strictly_contains(candidate, span) for candidate in competing_spans)
            for span in spans
        ):
            mandatory.add(entity_id)
    return mandatory


def _strictly_contains(outer: tuple[int, int], inner: tuple[int, int]) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] >= inner[1]
        and outer[1] - outer[0] > inner[1] - inner[0]
    )


def _optional_lookup_entity_ids(
    *,
    mandatory_entity_ids: set[str],
    semantic_base_entity_ids: set[str],
    entity_match_spans: Mapping[str, set[tuple[int, int]]],
    relationships: tuple[SemanticRelationship, ...],
    entities: Mapping[str, SemanticEntity],
    allowed_columns: Mapping[str, frozenset[str]],
    question_tokens: tuple[str, ...],
) -> set[str]:
    """Demote only generic lookup mentions backed by a mandatory fact identity."""
    optional: set[str] = set()
    for entity_id in mandatory_entity_ids - semantic_base_entity_ids:
        spans = entity_match_spans.get(entity_id, set())
        if not spans or any(end - start > 1 for start, end in spans):
            continue
        supporting_relationships = tuple(
            relationship
            for relationship in relationships
            if relationship.to_entity == entity_id
            and relationship.from_entity in semantic_base_entity_ids
            and relationship.cardinality.value == "many_to_one"
            and relationship.from_column
            in allowed_columns.get(
                entities[relationship.from_entity].table,
                frozenset(),
            )
        )
        if not supporting_relationships:
            continue
        source_entity_ids = {
            relationship.from_entity for relationship in supporting_relationships
        }
        if _entity_has_independently_requested_attribute(
            entity_id,
            source_entity_ids=source_entity_ids,
            entities=entities,
            allowed_columns=allowed_columns,
            question_tokens=question_tokens,
        ):
            continue
        optional.add(entity_id)
    return optional


def _entity_has_independently_requested_attribute(
    entity_id: str,
    *,
    source_entity_ids: set[str],
    entities: Mapping[str, SemanticEntity],
    allowed_columns: Mapping[str, frozenset[str]],
    question_tokens: tuple[str, ...],
) -> bool:
    source_columns = {
        column
        for source_entity_id in source_entity_ids
        for column in allowed_columns.get(
            entities[source_entity_id].table,
            frozenset(),
        )
    }
    for column in allowed_columns.get(entities[entity_id].table, frozenset()):
        if column == "id" or column in source_columns:
            continue
        tokens = list(_normalize_tokens(column.replace("_", " ")))
        while tokens and tokens[-1] in _COLUMN_SUFFIX_TOKENS:
            tokens.pop()
        if not tokens:
            continue
        references = {tuple(tokens)}
        references.update(
            (token,) for token in tokens if token in _DISPLAY_ATTRIBUTE_TOKENS
        )
        if any(_contains_token_sequence(question_tokens, reference) for reference in references):
            return True
    return False


def _matching_reference_spans(
    question: tuple[str, ...],
    references: tuple[str, ...],
    *,
    reject_negated: bool = False,
) -> set[tuple[int, int]]:
    spans: set[tuple[int, int]] = set()
    for raw_reference in references:
        reference = _normalize_tokens(raw_reference)
        if not reference or len(reference) > len(question):
            continue
        reference_contains_negation = "not" in reference
        for index in range(len(question) - len(reference) + 1):
            if question[index : index + len(reference)] != reference:
                continue
            if reject_negated and not reference_contains_negation:
                prefix = question[max(0, index - 3) : index]
                if "not" in prefix:
                    continue
            spans.add((index, index + len(reference)))
    return spans


def _matches_any_reference(
    question_tokens: tuple[str, ...],
    references: tuple[str, ...],
) -> bool:
    return any(
        _contains_token_sequence(question_tokens, _normalize_tokens(reference))
        for reference in references
    )


def _matches_semantic_reference(
    question_tokens: tuple[str, ...],
    references: tuple[str, ...],
) -> bool:
    return any(
        _contains_non_negated_sequence(
            question_tokens,
            _normalize_tokens(reference),
        )
        for reference in references
    )


def _contains_non_negated_sequence(
    question: tuple[str, ...],
    reference: tuple[str, ...],
) -> bool:
    if not reference or len(reference) > len(question):
        return False
    reference_contains_negation = "not" in reference
    for index in range(len(question) - len(reference) + 1):
        if question[index : index + len(reference)] != reference:
            continue
        if reference_contains_negation:
            return True
        prefix = question[max(0, index - 3) : index]
        if "not" not in prefix:
            return True
    return False


def _contains_token_sequence(
    question: tuple[str, ...],
    reference: tuple[str, ...],
) -> bool:
    if not reference or len(reference) > len(question):
        return False
    return any(
        question[index : index + len(reference)] == reference
        for index in range(len(question) - len(reference) + 1)
    )


def _normalize_tokens(value: str) -> tuple[str, ...]:
    normalized = value
    for pattern, replacement in _CONTRACTIONS:
        normalized = pattern.sub(replacement, normalized)
    tokens = re.findall(r"[a-z0-9]+", normalized.lower())
    return tuple(_SINGULAR_SUFFIXES.get(token) or token for token in tokens)


def _normalize_phrase(value: str) -> str:
    return " ".join(_normalize_tokens(value))


def _safe_string_set(value: Any) -> frozenset[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str))


def _safe_allowed_columns(value: Any) -> dict[str, frozenset[str]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        table: _safe_string_set(columns)
        for table, columns in value.items()
        if isinstance(table, str)
    }


def _safe_scope_type(value: Any) -> str:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        return value
    return "none"
