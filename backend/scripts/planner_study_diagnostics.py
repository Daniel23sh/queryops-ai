"""Bounded study diagnostics, never scoring or execution authority."""
import json

from app.evaluation.identity import IdentityProof
from app.query_engine.openai_provider import CLARIFICATION_REASONS
from app.query_engine.semantic_plan import _is_proven_fk_to_unique_identity


AXES = frozenset({"entities", "rules", "metric", "relationships", "outputs", "aggregations",
                  "grouping", "having", "ordering", "limit", "distinct", "missing_predicates",
                  "changed_predicates", "extra_predicates"})
COMPARISONS = frozenset({"strict_match", "equivalent", "unestablished", "not_evaluated"})
REASONS = CLARIFICATION_REASONS | {"unestablished"}


def bounded_diagnostics(value):
    if value is None:
        return True  # Legacy observations have no diagnostic record.
    return (isinstance(value, dict)
            and set(value) == {"version", "outcome", "clarification_reason", "plan_comparison",
                               "mismatch_axes", "result_multiset_match"}
            and type(value["version"]) is int and value["version"] == 1
            and isinstance(value["outcome"], str)
            and value["outcome"] in {"plan", "clarification", "unsafe_request", "provider_failure"}
            and (value["clarification_reason"] is None or isinstance(value["clarification_reason"], str)
                 and value["clarification_reason"] in REASONS)
            and isinstance(value["plan_comparison"], str) and value["plan_comparison"] in COMPARISONS
            and isinstance(value["mismatch_axes"], list) and len(value["mismatch_axes"]) <= len(AXES)
            and all(isinstance(axis, str) and axis in AXES for axis in value["mismatch_axes"])
            and (type(value["result_multiset_match"]) is bool
                 or value["result_multiset_match"] == "not_evaluated"))


def _field(field):
    return field.entity_id, field.column


def _proof(actual, expected, pack):
    # Equality is shared only by the same selected INNER graph, never candidates or LEFT joins.
    if set(actual.relationships) != set(expected.relationships):
        return IdentityProof()
    entities = pack.semantic_catalog.entities_by_id
    relationships = {item.id: item for item in pack.semantic_catalog.relationships}
    pairs = []
    for selected in actual.relationships:
        relation = relationships[selected.relationship_id]
        source = (entities[relation.from_entity].table, relation.from_column)
        target = (entities[relation.to_entity].table, relation.to_column)
        if selected.join_type == "inner" and _is_proven_fk_to_unique_identity(*source, *target):
            # IdentityProof keys here use semantic entity IDs, not physical table aliases.
            pairs.append(((relation.from_entity, relation.from_column),
                          (relation.to_entity, relation.to_column)))
    return IdentityProof(tuple(pairs))


def _aggregate(aggregate, proof):
    target = _field(aggregate.field) if aggregate.field else None
    if target is not None and aggregate.function == "count" and aggregate.distinct:
        target = proof.field(target)
    return aggregate.function, target, aggregate.distinct


def _predicates(validated):
    values = [(p.entity_id, p.column, p.operator.value, p.value) for p in validated.effective_predicates]
    values += [(p.field.entity_id, p.field.column, p.operator, p.value) for p in validated.plan.literal_filters]
    predicates = set()
    for entity, column, operator, value in values:
        if operator == "in" and isinstance(value, tuple) and len(value) == 1:
            operator, value = "equals", value[0]
        predicates.add((entity, column, operator, json.dumps(value, sort_keys=True)))
    return frozenset(predicates)


def compare_plans(actual, expected, pack):
    """Prove only the demonstrated spellings; every other difference is unresolved."""
    proof = _proof(actual.plan, expected.plan, pack)

    def parts(value):
        plan = value.plan
        referenced = {h.aggregation_id for h in plan.having} | {
            o.aggregation_id for o in plan.order_by if o.target_kind == "aggregation"}
        return {
            "entities": frozenset(plan.entity_ids), "rules": frozenset(plan.composition_rule_ids),
            "metric": plan.metric_id, "relationships": frozenset(plan.relationships),
            "outputs": frozenset(plan.output_fields),
            # Referenced labels retain their expression binding; unreferenced aliases carry no meaning.
            "aggregations": sorted(((_aggregate(a, proof), a.id if a.id in referenced else None)
                                    for a in plan.aggregations), key=repr),
            "grouping": frozenset(plan.group_by), "having": plan.having, "ordering": plan.order_by,
            "limit": plan.limit, "distinct": plan.distinct, "predicates": _predicates(value),
        }

    left, right = parts(actual), parts(expected)
    mismatches = [axis for axis in left if axis != "predicates" and left[axis] != right[axis]]
    left_fields, right_fields = ({p[:2] for p in side["predicates"]} for side in (left, right))
    if right_fields - left_fields:
        mismatches.append("missing_predicates")
    if left_fields - right_fields:
        mismatches.append("extra_predicates")
    if any({p[2:] for p in left["predicates"] if p[:2] == field}
           != {p[2:] for p in right["predicates"] if p[:2] == field}
           for field in left_fields & right_fields):
        mismatches.append("changed_predicates")
    return {"plan_comparison": "unestablished" if mismatches else "equivalent", "mismatch_axes": mismatches}


def result_indices(actual, expected, pack):
    """Align known output identities, never infer them from matching row values."""
    proof = _proof(actual, expected, pack)

    def keys(plan):
        return [("field", _field(f)) for f in plan.output_fields] + [
            ("aggregation", _aggregate(a, proof)) for a in plan.aggregations]

    left, right = keys(actual), keys(expected)
    if len(set(left)) != len(left) or len(set(right)) != len(right) or set(left) != set(right):
        return None
    return [left.index(key) for key in right]
