from __future__ import annotations

from dataclasses import replace
from itertools import permutations

import pytest

from app.query_engine.domain_pack import DomainColumn, DomainPack, DomainTable
from app.query_engine.semantic_catalog import (
    SemanticAggregation,
    SemanticCatalog,
    SemanticCatalogProjection,
    SemanticCompositionRule,
    SemanticConcept,
    SemanticEntity,
    SemanticMetric,
    SemanticPredicate,
    SemanticPredicateOperator,
)
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent,
    SemanticPlan,
    SemanticPlanValidationError,
    validate_semantic_plan,
)
from app.query_engine.sql_renderer import render_validated_semantic_plan


BRANCHES = ("alpha", "beta", "gamma")


@pytest.mark.parametrize("concept_ids", [(), ("beta",), ("alpha", "beta")])
def test_or_rule_and_proper_subset_narrowing_preserve_rendered_semantics(
    concept_ids: tuple[str, ...],
) -> None:
    pack, projection = _inputs()
    plan = _plan(concept_ids)

    validated = _validate(plan, pack, projection)

    assert set(validated.plan.concept_ids) == set(concept_ids)
    assert {p.column for p in validated.effective_predicates} == set(concept_ids)
    assert validated.rule_or_concept_groups == (BRANCHES,)
    conjuncts = "".join(f"records.{name} = TRUE AND " for name in sorted(concept_ids))
    assert render_validated_semantic_plan(validated, pack) == (
        "SELECT COUNT(*) AS row_count FROM records WHERE "
        f"{conjuncts}((records.alpha = TRUE) OR (records.beta = TRUE) "
        "OR (records.gamma = TRUE))"
    )


@pytest.mark.parametrize("concept_ids", list(permutations(BRANCHES)))
@pytest.mark.parametrize("reverse_branches", [False, True])
def test_full_or_conjunction_is_rejected_independently_of_order(
    concept_ids: tuple[str, ...],
    reverse_branches: bool,
) -> None:
    rule = _rule("either", tuple(reversed(BRANCHES)) if reverse_branches else BRANCHES)
    pack, projection = _inputs(rules=(rule,))

    # Candidate definitions and a mandatory OR rule do not require its conjuncts.
    assert projection.mandatory_evidence()["concept_ids"] == []
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(_plan(concept_ids), pack, projection)

    assert exc_info.value.reason == "composition_rule_overconstraint"
    assert exc_info.value.safe_observation is None


@pytest.mark.parametrize("reverse_rules", [False, True])
@pytest.mark.parametrize(
    ("concept_ids", "rejected"),
    [
        (("alpha", "gamma"), False),
        (("alpha", "beta"), True),
        (("gamma", "delta"), True),
    ],
)
def test_multiple_or_rules_are_checked_independently(
    reverse_rules: bool,
    concept_ids: tuple[str, ...],
    rejected: bool,
) -> None:
    rules = (_rule("first", ("alpha", "beta")), _rule("second", ("gamma", "delta")))
    if reverse_rules:
        rules = tuple(reversed(rules))
    pack, projection = _inputs(rules=rules)
    plan = _plan(concept_ids, rule_ids=tuple(rule.id for rule in rules))

    if rejected:
        with pytest.raises(SemanticPlanValidationError) as exc_info:
            _validate(plan, pack, projection)
        assert exc_info.value.reason == "composition_rule_overconstraint"
    else:
        assert _validate(plan, pack, projection)


def test_mandatory_exception_for_one_rule_does_not_exempt_another() -> None:
    rules = (_rule("first", ("alpha", "beta")), _rule("second", ("gamma", "delta")))
    pack, projection = _inputs(rules=rules, mandatory_concepts=("alpha", "beta"))
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(
            _plan(("alpha", "beta", "gamma", "delta"), rule_ids=("first", "second")),
            pack,
            projection,
        )
    assert exc_info.value.reason == "composition_rule_overconstraint"


@pytest.mark.parametrize("source", ["concept", "partial_concept", "metric", "rule"])
def test_effective_branches_are_not_mistaken_for_explicit_top_level_intent(
    source: str,
) -> None:
    pack, projection = _inputs(rules=(_rule("either", BRANCHES), _all_rule()))
    plan = _plan(
        ("alpha", "beta", "bundle")
        if source == "partial_concept"
        else (("bundle",) if source == "concept" else ()),
        rule_ids=("either", "all") if source == "rule" else ("either",),
    )
    # Only the selected OR rule is mandatory; the other definitions are context.
    projection = replace(
        projection,
        candidate_signals=(
            {"kind": "composition_rule", "id": "either", "tier": "exact_reference"},
        ),
    )
    if source == "metric":
        plan = plan.model_copy(update={"metric_id": "total", "aggregations": ()})

    validated = _validate(plan, pack, projection)

    assert set(BRANCHES) <= set(validated.effective_concept_ids)
    assert not set(BRANCHES) <= set(validated.plan.concept_ids)
    assert {p.column for p in validated.effective_predicates} == set(BRANCHES)


@pytest.mark.parametrize("mandatory_concepts", [("beta",), ("alpha", "beta")])
def test_partial_mandatory_overlap_does_not_authorize_full_conjunction(
    mandatory_concepts: tuple[str, ...],
) -> None:
    pack, projection = _inputs(mandatory_concepts=mandatory_concepts)
    assert _validate(_plan(mandatory_concepts), pack, projection)
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(_plan(BRANCHES), pack, projection)
    assert exc_info.value.reason == "composition_rule_overconstraint"


@pytest.mark.parametrize("source", ["explicit", "dependency", "metric", "all_of_rule"])
def test_independently_mandatory_conjunction_is_preserved(source: str) -> None:
    mandatory_concepts = (
        BRANCHES
        if source == "explicit"
        else (("bundle",) if source == "dependency" else ())
    )
    rules = (
        (_rule("either", BRANCHES), _all_rule())
        if source == "all_of_rule"
        else (_rule("either", BRANCHES),)
    )
    pack, projection = _inputs(rules=rules, mandatory_concepts=mandatory_concepts)
    plan = _plan(
        (*BRANCHES, "bundle") if source == "dependency" else BRANCHES,
        rule_ids=tuple(rule.id for rule in rules),
    )
    if source == "metric":
        projection = replace(
            projection,
            candidate_signals=(
                *projection.candidate_signals,
                {"kind": "metric", "id": "total", "tier": "exact_reference"},
            ),
        )
        plan = plan.model_copy(update={"metric_id": "total", "aggregations": ()})

    validated = _validate(plan, pack, projection)

    # Exact deterministic requirements (including unconditional dependencies)
    # justify the conjunction. Nothing selected by the provider is discarded.
    assert set(validated.plan.concept_ids) == set(plan.concept_ids)
    assert {p.column for p in validated.effective_predicates} == set(BRANCHES)


def _rule(rule_id: str, branches: tuple[str, ...]) -> SemanticCompositionRule:
    return SemanticCompositionRule(rule_id, "Synthetic OR", (), (), branches)


def _all_rule() -> SemanticCompositionRule:
    return SemanticCompositionRule("all", "Synthetic conjunction", (), BRANCHES, ())


def _inputs(
    *,
    rules: tuple[SemanticCompositionRule, ...] | None = None,
    mandatory_concepts: tuple[str, ...] = (),
) -> tuple[DomainPack, SemanticCatalogProjection]:
    rules = rules if rules is not None else (_rule("either", BRANCHES),)
    names = (*BRANCHES, "delta")
    concepts = tuple(
        SemanticConcept(
            name,
            "records",
            "Synthetic branch",
            (),
            (SemanticPredicate(name, SemanticPredicateOperator.EQUALS, True),),
            (),
            None,
            (),
        )
        for name in names
    ) + (
        SemanticConcept(
            "bundle", "records", "Synthetic dependency", (), (), BRANCHES, None, ()
        ),
    )
    catalog = SemanticCatalog(
        id="synthetic",
        version="1",
        domain_id="synthetic",
        dataset_id="synthetic",
        entities=(SemanticEntity("records", "records", "Records", (), ()),),
        concepts=concepts,
        relationships=(),
        metrics=(
            SemanticMetric(
                "total",
                "records",
                "Total",
                (),
                BRANCHES,
                SemanticAggregation("count", "Count rows"),
            ),
        ),
        composition_rules=rules,
        authorization_guidance=(),
        restricted_tables=(),
        examples=(),
    )
    pack = DomainPack(
        domain_id="synthetic",
        name="Synthetic",
        version="1",
        allowed_resource_table_names=("records",),
        tables=(
            DomainTable(
                "records",
                "Records",
                "Synthetic records",
                tuple(
                    DomainColumn(name, "boolean", "Synthetic flag") for name in names
                ),
            ),
        ),
        business_terms=(),
        query_templates=(),
        semantic_catalog=catalog,
    )
    projection = SemanticCatalogProjection(
        catalog_id=catalog.id,
        catalog_version=catalog.version,
        catalog_hash=catalog.digest,
        entities=({"id": "records"},),
        relationships=(),
        concepts=tuple({"id": concept.id} for concept in concepts),
        metrics=({"id": "total"},),
        composition_rules=tuple({"id": rule.id} for rule in rules),
        authorization_guidance=(),
        examples=(),
        authoritative_business_terms=(),
        candidate_signals=tuple(
            {"kind": "composition_rule", "id": rule.id, "tier": "exact_reference"}
            for rule in rules
        )
        + tuple(
            {"kind": "concept", "id": concept_id, "tier": "exact_reference"}
            for concept_id in mandatory_concepts
        ),
    )
    return pack, projection


def _plan(
    concepts: tuple[str, ...], *, rule_ids: tuple[str, ...] = ("either",)
) -> SemanticPlan:
    return SemanticPlan(
        entity_ids=("records",),
        concept_ids=concepts,
        composition_rule_ids=rule_ids,
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(),
        output_fields=(),
        aggregations=(
            SemanticAggregationIntent(
                id="row_count", function="count", field=None, distinct=False
            ),
        ),
        group_by=(),
        having=(),
        order_by=(),
        limit=None,
    )


def _validate(
    plan: SemanticPlan, pack: DomainPack, projection: SemanticCatalogProjection
):
    return validate_semantic_plan(
        plan,
        domain_pack=pack,
        projection=projection,
        schema_context={
            "allowed_columns": {
                "records": [column.name for column in pack.tables[0].columns]
            }
        },
        scope_reference_resolved=False,
    )
