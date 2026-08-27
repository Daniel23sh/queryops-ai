from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Mapping
from typing import Any

from app.query_engine.errors import DomainPackValidationError
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

    exact_entity_ids = {
        entity.id
        for entity in eligible_entities.values()
        if _matches_any_reference(question_tokens, entity.natural_language_references)
    }
    exact_concept_ids = {
        concept.id
        for concept in eligible_concepts.values()
        if _matches_semantic_reference(
            question_tokens,
            concept.natural_language_references,
        )
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
    rule_concept_ids = {
        concept_id
        for rule_id in exact_rule_ids
        for concept_id in (
            *rules_by_id[rule_id].all_of_concept_ids,
            *rules_by_id[rule_id].or_concept_ids,
        )
    }
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
    if scope_resolved:
        for guidance in catalog.authorization_guidance:
            if _matches_any_reference(question_tokens, guidance.possessive_references):
                anchor_entity_ids.discard(guidance.scope_entity_id)
                # Possessive scope language (for example, "my department") is
                # authorization context, not a requested business entity.  Keep
                # it out of both the candidate projection and mandatory exact
                # evidence so the plan cannot be forced to materialize an RLS
                # scope table or literal scope predicate.
                exact_entity_ids.discard(guidance.scope_entity_id)

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
    mandatory_concept_ids &= selected_concept_ids
    anchor_entity_ids.update(
        eligible_concepts[concept_id].entity_id for concept_id in selected_concept_ids
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
        description_entity_ids=description_entity_ids,
        value_context_entity_ids=value_context_entity_ids,
        exact_concept_ids=exact_concept_ids,
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
    )
    projection = _fit_projection(
        projection,
        mandatory_concept_ids=mandatory_concept_ids,
        mandatory_metric_ids=set(exact_metric_ids),
    )
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
    description_entity_ids: set[str],
    value_context_entity_ids: set[str],
    exact_concept_ids: set[str],
    selected_concept_ids: set[str],
    exact_metric_ids: set[str],
    selected_metric_ids: set[str],
    exact_rule_ids: set[str],
) -> tuple[dict[str, str], ...]:
    signals: dict[tuple[str, str], str] = {}
    for item_id in selected_concept_ids:
        signals[("concept", item_id)] = (
            "exact_reference" if item_id in exact_concept_ids else "entity_context"
        )
    for item_id in selected_metric_ids:
        signals[("metric", item_id)] = (
            "exact_reference" if item_id in exact_metric_ids else "entity_context"
        )
    for item_id in exact_rule_ids:
        signals[("composition_rule", item_id)] = "exact_reference"
    for item_id in exact_entity_ids:
        signals[("entity", item_id)] = "exact_reference"
    for item_id in description_entity_ids - exact_entity_ids:
        signals[("entity", item_id)] = "description_context"
    for item_id in value_context_entity_ids - exact_entity_ids:
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
    mandatory_concept_ids: set[str],
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
            if concept["id"] not in mandatory_concept_ids
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
            or concept["id"] in mandatory_concept_ids
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
