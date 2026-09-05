"""Independent, hand-authored architecture examples; no evaluation assets/SQL.

Expected structures encode the stated distinction, not a baseline query. Wrong
plan variants deliberately share those expectations. Owners are review notes,
not executable validation or proof that a future check already exists.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any, Literal

from app.query_engine.domain_pack import DomainColumn, DomainPack, DomainTable
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import (
    SemanticCatalog, SemanticConcept, SemanticEntity, SemanticPredicate,
    SemanticPredicateOperator,
)
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent, SemanticFieldRef, SemanticHavingIntent,
    SemanticLiteralFilter, SemanticOrderIntent, SemanticPlan, SemanticRelationshipIntent,
)
from app.query_engine.structural_intent import (
    StructuralHaving, empty_structural_intent, known,
)
from app.query_engine.structural_intent_comparison import (
    StructuralComparisonPolicy, StructuralRequirement,
)
from scripts.semantic_ownership import OwnershipFixture


def field(entity: str, column: str) -> SemanticFieldRef:
    return SemanticFieldRef(entity_id=entity, column=column)


def count(target: SemanticFieldRef | None = None, *, distinct: bool = False) -> SemanticAggregationIntent:
    return SemanticAggregationIntent(id="quantity", function="count", field=target, distinct=distinct)


def order(target: SemanticFieldRef, direction: Literal["asc", "desc"] = "asc") -> SemanticOrderIntent:
    return SemanticOrderIntent(target_kind="field", field=target, aggregation_id=None, direction=direction)


def plan(**changes: Any) -> SemanticPlan:
    values = dict(entity_ids=(), concept_ids=(), composition_rule_ids=(), metric_id=None,
                  distinct=False, literal_filters=(), relationships=(), output_fields=(),
                  aggregations=(), group_by=(), having=(), order_by=(), limit=None)
    values.update(changes)
    return SemanticPlan.model_validate(values)


def expected(*, outputs: tuple = (), aggregates: tuple = (), groups: tuple = (),
             having: tuple = (), ordering: tuple = (), distinct: bool = False) -> StructuralRequirement:
    # Exact fixture declarations include known empty collections. They are not
    # production Required Intent and cannot be inferred from a supplied plan.
    intent = empty_structural_intent().model_copy(update={
        "output_fields": known(outputs), "aggregations": known(aggregates),
        "group_by": known(groups), "having": known(having),
        "ordering": known(ordering), "distinct": known(distinct),
    })
    return StructuralRequirement(intent=intent, binding="required", policy=StructuralComparisonPolicy(
        output_fields="exact", aggregations="exact", group_by="exact", having="exact",
        ordering="exact", distinct="exact",
    ))


def offline_schema(pack: DomainPack) -> dict[str, Any]:
    """Fixture-only schema, no actor/resource authorization evidence.

    Deliberately independent of the V2 audit loader. PR52 structural adapters are
    reused by the comparison, not its V2-specific fixture/context construction.
    """
    tables = [t for t in pack.tables if t.queryable and t.name in pack.allowed_resource_table_names]
    return {
        "allowed_tables": [t.name for t in tables],
        "allowed_columns": {t.name: [c.name for c in t.columns] for t in tables},
        "tables": [{"name": t.name, "scope_column": t.scope_column,
                    "columns": [{"name": c.name, "data_type": c.data_type, "nullable": c.nullable}
                                for c in t.columns]} for t in tables],
    }


def fixture_packs() -> dict[str, DomainPack]:
    operations = load_it_operations_domain_pack()
    samples = DomainTable("samples", "Samples", "Laboratory samples", (
        DomainColumn("id", "integer", "Sample key", False),
        DomainColumn("kind", "string", "Sample kind", False),
        DomainColumn("received_at", "timestamp", "Received timestamp", False),
    ))
    laboratory = DomainPack("laboratory", "Synthetic laboratory", "1", ("samples",),
        (samples,), (), (), SemanticCatalog(
            id="laboratory_catalog", version="1", domain_id="laboratory", dataset_id="laboratory_fixture",
            entities=(SemanticEntity("samples", "samples", "Laboratory samples", ("sample", "samples"), ()),),
            relationships=(), concepts=(SemanticConcept(
                "old_sample", "samples", "Received more than fourteen days ago",
                ("samples older than 14 days", "samples received more than 14 days ago"),
                (SemanticPredicate("received_at", SemanticPredicateOperator.OLDER_THAN_DAYS, 14),),
                (), None, (),
            ),), metrics=(), composition_rules=(), authorization_guidance=(), restricted_tables=(), examples=(),
        ))
    return {operations.domain_id: operations, laboratory.domain_id: laboratory}


def architecture_fixtures() -> tuple[OwnershipFixture, ...]:
    rows = count()
    ticket_category = field("support_tickets", "category")
    device_id, os = field("devices", "id"), field("devices", "os")
    hostname, device_type = field("devices", "hostname"), field("devices", "device_type")
    price = SemanticAggregationIntent(id="value", function="sum", field=field("licenses", "monthly_cost_usd"), distinct=False)
    cases: list[OwnershipFixture] = []

    def add(id: str, family: str, questions: tuple[str, ...], supplied: SemanticPlan,
            requirement: StructuralRequirement | None, evidence: str, owners: tuple[str, ...],
            domain: str = "it_operations") -> OwnershipFixture:
        item = OwnershipFixture(id, family, domain, questions, supplied, requirement, evidence, owners)
        cases.append(item)
        return item

    def variant(base: OwnershipFixture, id: str, supplied: SemanticPlan) -> None:
        cases.append(replace(base, id=id, plan=supplied))

    grouped = add("ticket_groups", "grouping_ordering",
        ("Count tickets by category.", "Give the number of tickets per category."),
        plan(entity_ids=("support_tickets",), output_fields=(ticket_category,), aggregations=(rows,), group_by=(ticket_category,)),
        expected(outputs=(ticket_category,), aggregates=(rows,), groups=(ticket_category,)),
        "Category is a grouping dimension, not a sort instruction.",
        ("PR56: interpret requested grouping; PR54: validate declared grouped shape",))
    variant(grouped, "ticket_groups_missing", plan(entity_ids=("support_tickets",), aggregations=(rows,)))
    add("ticket_order", "grouping_ordering", ("List tickets ordered by category.",),
        plan(entity_ids=("support_tickets",), output_fields=(ticket_category,), order_by=(order(ticket_category),)),
        expected(outputs=(ticket_category,), ordering=(order(ticket_category),)),
        "Ordering detail rows must not manufacture aggregation.", ("PR56: structure interpretation",))

    detail = add("device_outputs", "detail_aggregate", ("List device id and device hostname.",),
        plan(entity_ids=("devices",), output_fields=(device_id, hostname)),
        expected(outputs=(device_id, hostname)), "Both explicitly requested outputs are needed.",
        ("PR56: requested output completeness; no relational proof of English omission",))
    variant(detail, "device_output_missing", plan(entity_ids=("devices",), output_fields=(hostname,)))
    total = add("ticket_total", "detail_aggregate", ("Count tickets in the queue.", "How many tickets exist?"),
        plan(entity_ids=("support_tickets",), aggregations=(rows,)), expected(aggregates=(rows,)),
        "A scalar count is requested; a detail list is a different answer.",
        ("PR56: detail versus aggregate; PR54: declared scalar shape",))
    variant(total, "ticket_total_as_detail", plan(entity_ids=("support_tickets",), output_fields=(field("support_tickets", "id"),)))

    add("license_count", "multiple_aggregates", ("Count license products.",),
        plan(entity_ids=("licenses",), aggregations=(rows,)), expected(aggregates=(rows,)),
        "Single product row count.", ("PR56: requested aggregate set",))
    multi = add("license_count_value", "multiple_aggregates",
        ("Count license products and sum their monthly cost.", "Give the number of license products and their total monthly cost."),
        plan(entity_ids=("licenses",), aggregations=(rows, price)), expected(aggregates=(rows, price)),
        "Two aggregates over the same product population; this is not assignment savings.",
        ("PR54: aggregation population and numeric renderability", "PR56: requested aggregate completeness"))
    variant(multi, "license_value_missing", plan(entity_ids=("licenses",), aggregations=(rows,)))

    distinct_os = count(os, distinct=True)
    unique = add("distinct_os", "row_distinct", ("Count distinct device operating systems.",),
        plan(entity_ids=("devices",), aggregations=(distinct_os,)), expected(aggregates=(distinct_os,)),
        "Count unique operating-system values, not device rows.",
        ("PR56: counted subject and distinctness", "PR54: null-sensitive count semantics"))
    variant(unique, "distinct_os_as_rows", plan(entity_ids=("devices",), aggregations=(rows,)))
    add("device_rows", "row_distinct", ("Count devices.",),
        plan(entity_ids=("devices",), aggregations=(rows,)), expected(aggregates=(rows,)),
        "Device row count contrast to distinct values.", ("PR54: count source and grain",))

    dims = add("two_dimensions", "multiple_dimensions", ("Count devices by os and device type.",),
        plan(entity_ids=("devices",), output_fields=(os, device_type), aggregations=(rows,), group_by=(os, device_type)),
        expected(outputs=(os, device_type), aggregates=(rows,), groups=(os, device_type)),
        "Both dimensions define the requested grouping; a one-field parse is incomplete.",
        ("PR56: dimension completeness", "PR54: declared grouping legality"))
    variant(dims, "second_dimension_missing", plan(entity_ids=("devices",), output_fields=(os,), aggregations=(rows,), group_by=(os,)))

    priority = (order(os, "desc"), order(hostname))
    ranked = add("order_priority", "ranking", ("List devices ordered first by os descending, then hostname ascending.",),
        plan(entity_ids=("devices",), output_fields=(os, hostname), order_by=priority),
        expected(outputs=(os, hostname), ordering=priority),
        "Priority reversal is wrong even though both orderings are legal; legacy has no ordering requirement.",
        ("PR56: ordering interpretation; compiler preserves whichever ordering was declared",))
    variant(ranked, "order_priority_reversed", plan(entity_ids=("devices",), output_fields=(os, hostname), order_by=priority[::-1]))

    user_id = field("directory_users", "id")
    status = field("directory_users", "account_status")
    literal = SemanticLiteralFilter(field=status, operator="not_equals", value="disabled")
    # PR52 does not describe predicates: deliberately leave judgement unresolved.
    negative = add("not_disabled", "negation", ("Count users that are not disabled.",),
        plan(entity_ids=("directory_users",), aggregations=(rows,), literal_filters=(literal,)), None,
        "Predicate distinction is outside PR52 structural comparison; manually review not_equals versus equals.",
        ("PR56: negation; retained validator only checks predicate type/consistency",))
    variant(negative, "negation_reversed", plan(entity_ids=("directory_users",), aggregations=(rows,), literal_filters=(literal.model_copy(update={"operator": "equals"}),)))

    rels = tuple(SemanticRelationshipIntent(relationship_id=r, join_type="inner") for r in
                 ("user_group_membership_user", "user_group_membership_group"))
    entities = ("directory_users", "groups", "user_group_memberships")
    for subject, question in ((user_id, "How many users belong to privileged groups?"),
                              (field("groups", "id"), "How many privileged groups contain users?")):
        agg = count(subject, distinct=True)
        add("subject_" + subject.entity_id, "counted_subject", (question,),
            plan(entity_ids=entities, concept_ids=("privileged_group",), relationships=rels, aggregations=(agg,)),
            expected(aggregates=(agg,)), "Distinct count of the named subject across memberships.",
            ("PR54: joined multiplicity and distinct entity grain", "PR56: subject interpretation"))

    counted_users = count(user_id, distinct=True)
    user_grain = add("user_grain", "counted_subject", ("Count users with devices by os.",),
        plan(entity_ids=("directory_users", "devices"), output_fields=(os,),
             relationships=(SemanticRelationshipIntent(relationship_id="device_assignee", join_type="inner"),),
             aggregations=(counted_users,), group_by=(os,)),
        expected(outputs=(os,), aggregates=(counted_users,), groups=(os,)),
        "Two same-OS devices for one user distinguish joined rows from user count. The declared subject still requires PR56 interpretation.",
        ("PR54: prove declared entity grain against one-to-many multiplicity", "PR56: select users as the counted subject"))
    variant(user_grain, "user_grain_as_joined_rows", user_grain.plan.model_copy(update={"aggregations": (rows,)}))

    relationship = add("ambiguous_department", "relationship_ambiguity", ("List devices and users in departments.",),
        plan(entity_ids=("devices", "directory_users", "departments"), output_fields=(device_id, user_id),
             relationships=tuple(SemanticRelationshipIntent(relationship_id=r, join_type="inner") for r in
                                 ("device_assignee", "device_department"))), None,
        "Question does not establish device department versus assignee department. A tree check is not role interpretation.",
        ("PR55: candidate completeness", "PR56: relationship clarification", "PR54: path multiplicity"))
    variant(relationship, "ambiguous_department_alternative", relationship.plan.model_copy(update={
        "relationships": tuple(SemanticRelationshipIntent(relationship_id=r, join_type="inner") for r in
                               ("device_assignee", "directory_user_department"))}))

    sample_kind = field("samples", "kind")
    add("temporal_only", "temporal_having",
        ("Count samples received more than 14 days ago by kind.", "Count samples older than 14 days per kind."),
        plan(entity_ids=("samples",), concept_ids=("old_sample",), output_fields=(sample_kind,), aggregations=(rows,), group_by=(sample_kind,)),
        expected(outputs=(sample_kind,), aggregates=(rows,), groups=(sample_kind,)),
        "Catalog predicate owns sample age; no aggregate threshold is requested.",
        ("PR56: temporal versus aggregate attachment", "PR54: predicate phase and aggregate legality"), "laboratory")
    having = SemanticHavingIntent(aggregation_id="quantity", operator="greater_than", value=14)
    threshold = add("aggregate_threshold", "temporal_having", ("Count samples by kind with more than 14 samples.",),
        plan(entity_ids=("samples",), output_fields=(sample_kind,), aggregations=(rows,), group_by=(sample_kind,), having=(having,)),
        expected(outputs=(sample_kind,), aggregates=(rows,), groups=(sample_kind,), having=(StructuralHaving(aggregation_id="quantity", operator="greater_than", value=Decimal(14)),)),
        "Aggregate population threshold, not age. Dropping it remains legal but answers a different question.",
        ("PR56: threshold attachment/value; no deterministic English oracle", "PR54: HAVING type and target"), "laboratory")
    variant(threshold, "aggregate_threshold_missing", threshold.plan.model_copy(update={"having": ()}))

    add("scope_literal", "deterministic_protection", ("List devices.",),
        plan(entity_ids=("devices",), output_fields=(device_id,), literal_filters=(
            SemanticLiteralFilter(field=field("devices", "department_id"), operator="equals", value="synthetic_scope"),)),
        None, "Resolved scope must not be embedded as a provider literal; no real scope identity is used.",
        ("KEEP: resolved-scope literal prohibition",))
    add("metric_mandate_retained", "residual_mandates", ("Count active users.",),
        plan(entity_ids=("directory_users",), aggregations=(rows,)), None,
        "Lexical metric mandate remains in both paths; this is not the complete PR56 ownership switch.",
        ("PR56: lexical metric selection", "KEEP: selected metric definition"))

    add("unauthorized_field", "deterministic_protection", ("List device passwords.",),
        plan(entity_ids=("devices",), output_fields=(field("devices", "password"),)), None,
        "Unavailable field must fail both validators.", ("KEEP: authorized field allowlist",))
    add("broken_group_shape", "deterministic_protection", ("Count tickets by category.",),
        plan(entity_ids=("support_tickets",), output_fields=(ticket_category,), aggregations=(rows,)), None,
        "Ungrouped ordinary output alongside aggregate must fail both validators.", ("KEEP: aggregate/group consistency",))
    return tuple(cases)
