"""Facts about the selected V1 join tree, shared by validation and compilation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.query_engine.domain_pack import DomainPack
from app.query_engine.semantic_catalog import SemanticRelationship

if TYPE_CHECKING:
    from app.query_engine.semantic_plan import SemanticFieldRef, SemanticPlan


def selected_join_order(
    plan: SemanticPlan, domain_pack: DomainPack,
) -> tuple[str, tuple[tuple[SemanticRelationship, str, str], ...]] | None:
    """Return the existing renderer's order, or no supported LEFT orientation.

    Requires an authorized, connected, acyclic selected graph. LEFT preserves
    from_entity; INNER may be traversed in either direction. This selects no
    candidate or semantic relationship role.
    """
    by_id = {item.id: item for item in domain_pack.semantic_catalog.relationships}
    selected = [(by_id[item.relationship_id], item.join_type) for item in plan.relationships]
    for root in sorted(plan.entity_ids):
        available = {root}
        pending = sorted(selected, key=lambda item: item[0].id)
        ordered: list[tuple[SemanticRelationship, str, str]] = []
        while pending:
            for index, (relationship, join_type) in enumerate(pending):
                source = relationship.from_entity in available
                target = relationship.to_entity in available
                if (join_type == "left" and source and not target) or (
                    join_type == "inner" and source != target
                ):
                    added = relationship.to_entity if source else relationship.from_entity
                    ordered.append((relationship, join_type, added))
                    available.add(added)
                    pending.pop(index)
                    break
            else:
                break
        if not pending and available == set(plan.entity_ids):
            return root, tuple(ordered)
    return None


def field_is_non_null(
    field: SemanticFieldRef, plan: SemanticPlan, domain_pack: DomainPack,
) -> bool:
    """Conservative proof in the input relation; do not infer WHERE rejection."""
    order = selected_join_order(plan, domain_pack)
    if order is None or field.entity_id not in plan.entity_ids:
        return False
    entity = domain_pack.semantic_catalog.entities_by_id[field.entity_id]
    column = domain_pack.tables_by_name[entity.table].columns_by_name.get(field.column)
    return column is not None and not column.nullable and all(
        added != field.entity_id or join_type != "left"
        for _, join_type, added in order[1]
    )


def population_may_multiply(
    entity_id: str, plan: SemanticPlan, domain_pack: DomainPack,
) -> bool:
    """Upper bound from declared cardinality, not a guess about intended grain.

    Starting at the source population, every outward edge must be to-one.
    Filters may reduce actual multiplicity; this proof does not assume that.
    Requires the already validated tree.
    """
    by_id = {item.id: item for item in domain_pack.semantic_catalog.relationships}
    edges = [by_id[item.relationship_id] for item in plan.relationships]
    visited = {entity_id}
    while edges:
        for index, edge in enumerate(edges):
            source = edge.from_entity in visited
            target = edge.to_entity in visited
            if source != target:
                if edge.cardinality.value != "one_to_one" and not (
                    source and edge.cardinality.value == "many_to_one"
                ):
                    return True
                visited.add(edge.to_entity if source else edge.from_entity)
                edges.pop(index)
                break
        else:
            return True
    return False
