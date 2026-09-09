"""Evaluator-only identity proofs; never execution or authorization authority."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import UniqueConstraint

from app.db.base import Base
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_plan import _is_proven_fk_to_unique_identity

FieldKey = tuple[str, str]


def catalog_equalities() -> dict[str, tuple[FieldKey, FieldKey]]:
    catalog = load_it_operations_domain_pack().semantic_catalog
    entities = catalog.entities_by_id
    return {
        r.id: (
            (entities[r.from_entity].table, r.from_column),
            (entities[r.to_entity].table, r.to_column),
        )
        for r in catalog.relationships
        if _is_proven_fk_to_unique_identity(
            entities[r.from_entity].table,
            r.from_column,
            entities[r.to_entity].table,
            r.to_column,
        )
    }


@dataclass(frozen=True)
class IdentityProof:
    equalities: tuple[tuple[FieldKey, FieldKey], ...] = ()

    def field(self, field: FieldKey) -> FieldKey:
        connected = {field}
        while True:
            expanded = connected | {
                key
                for pair in self.equalities
                if connected.intersection(pair)
                for key in pair
            }
            if expanded == connected:
                return min(connected)
            connected = expanded

    def grain(self, fields: Iterable[FieldKey]) -> frozenset[FieldKey]:
        fields = {self.field(field) for field in fields}
        # A non-null single-column unique key identifies exactly one table row.
        # Other columns of that SAME row cannot split the group. This does not
        # infer dependencies across joins or equate the values of different keys.
        for table_name in sorted({table for table, _ in fields}):
            table = Base.metadata.tables.get(table_name)
            if table is None or len(table.primary_key.columns) != 1:
                continue
            keys = [tuple(table.primary_key.columns)] + [
                tuple(c.columns)
                for c in table.constraints
                if isinstance(c, UniqueConstraint)
            ]
            if any(
                len(key) == 1
                and not key[0].nullable
                and (table_name, key[0].name) in fields
                for key in keys
            ):
                fields = {field for field in fields if field[0] != table_name}
                fields.add((table_name, next(iter(table.primary_key.columns)).name))
        return frozenset(fields)


def observation_identity_proof(observation: Mapping[str, Any]) -> IdentityProof:
    selected = observation.get("relationship_join_types")
    ids = observation.get("relationship_ids")
    entities = observation.get("entity_ids")
    if not all(isinstance(value, list) for value in (selected, ids, entities)):
        return IdentityProof()
    assert (
        isinstance(selected, list)
        and isinstance(ids, list)
        and isinstance(entities, list)
    )
    if len(selected) > 64 or not all(
        isinstance(value, str) for value in ids + entities
    ):
        return IdentityProof()
    catalog = load_it_operations_domain_pack().semantic_catalog
    table_names = {
        catalog.entities_by_id[e].table for e in entities if e in catalog.entities_by_id
    }
    available = catalog_equalities()
    pairs = []
    for item in selected:
        if not isinstance(item, dict):
            return IdentityProof()
        relationship_id = item.get("relationship_id")
        if not isinstance(relationship_id, str) or relationship_id not in ids:
            return IdentityProof()
        pair = available.get(relationship_id)
        if (
            item.get("join_type") == "inner"
            and pair
            and all(key[0] in table_names for key in pair)
        ):
            pairs.append(pair)
    return IdentityProof(tuple(pairs))
