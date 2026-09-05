"""PR53 offline experiment, not an alternate production validator.

Only current question-derived GroundedResultIntent is ablated. Candidate pruning
and lexical business mandates deliberately remain, so acceptance here is neither
the final architecture nor permission to render or execute a query.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any

from app.query_engine.domain_pack import DomainPack
from app.query_engine.semantic_catalog import SemanticCatalogProjection
from app.query_engine.semantic_grounding import build_semantic_grounding_projection
from app.query_engine.semantic_plan import (
    SemanticPlan, SemanticPlanValidationError, ValidatedSemanticPlan,
    validate_semantic_plan,
)
from app.query_engine.structural_intent_adapters import (
    grounded_to_structural_requirement, validated_plan_to_structural_observation,
)
from app.query_engine.structural_intent_comparison import (
    StructuralRequirement, compare_structural_requirement,
)


class Authority(str, Enum):
    POLICY_AUTHORIZATION_FACT = "POLICY_AUTHORIZATION_FACT"
    CATALOG_BUSINESS_FACT = "CATALOG_BUSINESS_FACT"
    RELATIONAL_FACT = "RELATIONAL_FACT"
    NL_INTERPRETATION = "NL_INTERPRETATION"
    PROVIDER_GUIDANCE = "PROVIDER_GUIDANCE"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"


class Disposition(str, Enum):
    KEEP_BINDING = "KEEP_BINDING"
    GUIDANCE_ONLY = "GUIDANCE_ONLY"
    REPLACE_WITH_CATALOG_FACT = "REPLACE_WITH_CATALOG_FACT"
    REPLACE_WITH_POST_PLAN_VALIDATION = "REPLACE_WITH_POST_PLAN_VALIDATION"
    REMOVE = "REMOVE"


class Difference(str, Enum):
    FALSE_CONSTRAINT = "FALSE_CONSTRAINT"
    USEFUL_BUT_NL_DERIVED_CHECK = "USEFUL_BUT_NL_DERIVED_CHECK"
    REAL_DETERMINISTIC_INVARIANT = "REAL_DETERMINISTIC_INVARIANT"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class Mechanism:
    id: str
    authority: Authority
    disposition: Disposition
    source: str
    effect: str


# Reviewed inventory only: never read to configure either validation path.
INVENTORY = (
    Mechanism("subject", Authority.NL_INTERPRETATION, Disposition.GUIDANCE_ONLY,
              "semantic_grounding._subject_entity_id", "Entity spans choose the counted subject."),
    Mechanism("quantity", Authority.NL_INTERPRETATION, Disposition.GUIDANCE_ONLY,
              "semantic_grounding._explicit_quantity_span", "Quantity phrases force count declarations."),
    Mechanism("aggregate_target", Authority.NL_INTERPRETATION, Disposition.REPLACE_WITH_POST_PLAN_VALIDATION,
              "semantic_grounding._build_grounded_result_intents", "Targets and distinctness inferred from subject/table; validate declared grain later, not English."),
    Mechanism("grouping", Authority.NL_INTERPRETATION, Disposition.REMOVE,
              "semantic_grounding._explicit_grouping_field", "First grouping marker chooses one exact dimension."),
    Mechanism("detail_grain", Authority.NL_INTERPRETATION, Disposition.GUIDANCE_ONLY,
              "semantic_grounding._detail_fact_entity_id", "Currently suggested only; projecting a key is not uniqueness proof."),
    Mechanism("having", Authority.NL_INTERPRETATION, Disposition.REMOVE,
              "semantic_grounding._explicit_numeric_threshold", "Threshold phrase can become exact aggregate HAVING."),
    Mechanism("outputs", Authority.NL_INTERPRETATION, Disposition.GUIDANCE_ONLY,
              "semantic_grounding._explicit_output_fields", "Field-name occurrence becomes required projection subset."),
    Mechanism("distinct", Authority.NL_INTERPRETATION, Disposition.REPLACE_WITH_POST_PLAN_VALIDATION,
              "semantic_grounding._build_grounded_result_intents", "Aggregate distinctness inferred; top-level required remains unset, suggested detail defaults false."),
    Mechanism("entity_mandate", Authority.NL_INTERPRETATION, Disposition.GUIDANCE_ONLY,
              "semantic_catalog.SemanticCatalogProjection.mandatory_evidence", "Lexical entity mandates retained in this experiment."),
    Mechanism("concept_mandate", Authority.NL_INTERPRETATION, Disposition.GUIDANCE_ONLY,
              "semantic_catalog.SemanticCatalogProjection.mandatory_evidence", "Lexical concept mandates retained, including negation/supersession heuristics."),
    Mechanism("metric_mandate", Authority.NL_INTERPRETATION, Disposition.GUIDANCE_ONLY,
              "semantic_catalog.SemanticCatalogProjection.mandatory_evidence", "Lexical metric mandates retained; exact metrics suppress structural grounding."),
    Mechanism("rule_mandate", Authority.NL_INTERPRETATION, Disposition.GUIDANCE_ONLY,
              "semantic_catalog.SemanticCatalogProjection.mandatory_evidence", "Lexical rule mandates retained."),
    Mechanism("path_pruning", Authority.NL_INTERPRETATION, Disposition.GUIDANCE_ONLY,
              "semantic_grounding._select_minimal_relationship_graph", "Deterministic heuristic restricts candidate paths; retained for PR55 evidence."),
    Mechanism("authorization", Authority.POLICY_AUTHORIZATION_FACT, Disposition.KEEP_BINDING,
              "semantic_plan.validate_semantic_plan", "Authorized fields and resolved-scope literal restrictions preserved; no actor authorization or RLS exercised offline."),
    Mechanism("catalog_meaning", Authority.CATALOG_BUSINESS_FACT, Disposition.KEEP_BINDING,
              "semantic_plan.validate_semantic_plan", "Selected concepts/metrics/rules retain definitions, dependency closure and Boolean composition."),
    Mechanism("relationship_facts", Authority.RELATIONAL_FACT, Disposition.KEEP_BINDING,
              "semantic_plan._validate_relationship_graph", "Endpoints/tree checked; tree is not fanout proof."),
    Mechanism("identity_facts", Authority.RELATIONAL_FACT, Disposition.REPLACE_WITH_CATALOG_FACT,
              "semantic_plan._distinct_count_identity_normalization", "Existing schema-backed normalization stays; future shared facts need null/join evidence."),
    Mechanism("plan_algebra", Authority.RELATIONAL_FACT, Disposition.KEEP_BINDING,
              "semantic_plan.validate_semantic_plan", "Types, references, scalar metric shape, grouping consistency preserved."),
    Mechanism("suggestions", Authority.PROVIDER_GUIDANCE, Disposition.GUIDANCE_ONLY,
              "openai_provider.SYSTEM_INSTRUCTIONS", "Suggested intent, examples and ranked candidates influence provider; no provider simulated."),
    Mechanism("sql_boundary", Authority.POLICY_AUTHORIZATION_FACT, Disposition.KEEP_BINDING,
              "service.QueryEngine", "Rendering, SQL safety, conformance, runtime role and RLS stay outside this offline experiment."),
    Mechanism("structural_audit", Authority.DIAGNOSTIC_ONLY, Disposition.GUIDANCE_ONLY,
              "structural_intent_comparison.compare_structural_requirement", "PR52 comparison describes structure, never execution authority."),
)

STRUCTURAL_REASONS = frozenset({
    "required_output_missing", "grounded_aggregation_mismatch",
    "grounded_group_by_mismatch", "grounded_having_mismatch",
    "grounded_distinct_mismatch", "result_grain_mismatch",
})
REASON_COMPONENT = {
    "required_output_missing": "output_fields",
    "grounded_aggregation_mismatch": "aggregations",
    "grounded_group_by_mismatch": "group_by",
    "grounded_having_mismatch": "having",
    "grounded_distinct_mismatch": "distinct",
    "result_grain_mismatch": "row_grain",
}


@dataclass(frozen=True)
class OwnershipFixture:
    id: str
    family: str
    domain_id: str
    questions: tuple[str, ...]
    plan: SemanticPlan
    expected: StructuralRequirement | None
    evidence: str
    future_owners: tuple[str, ...]


def _validate(
    plan: SemanticPlan, pack: DomainPack, projection: SemanticCatalogProjection,
    schema: Mapping[str, Any], scope_resolved: bool,
) -> tuple[ValidatedSemanticPlan | None, str | None]:
    try:
        return validate_semantic_plan(
            plan, domain_pack=pack, projection=projection, schema_context=schema,
            scope_reference_resolved=scope_resolved,
        ), None
    except SemanticPlanValidationError as exc:
        return None, exc.reason


def compare_fixture(
    fixture: OwnershipFixture, question: str, pack: DomainPack,
    schema: Mapping[str, Any], user_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Run the SAME supplied plan through current validation twice; no execution.

    Only the projection freshly produced here is ablated, never a caller-supplied
    trusted structural requirement. Unexpected errors propagate, not accept.
    Classification is relative to independently authored fixture expectations;
    PR52 has no relational equivalence oracle. Missing evidence is unresolved.
    """
    projection = build_semantic_grounding_projection(
        pack.semantic_catalog, question, schema, user_context,
    )
    scope_resolved = user_context.get("scope_reference_resolved") is True
    legacy, legacy_reason = _validate(fixture.plan, pack, projection, schema, scope_resolved)
    proposed, proposed_reason = _validate(
        fixture.plan, pack, replace(projection, grounded_result_intent=None),
        schema, scope_resolved,
    )
    intent_match: bool | None = None
    legacy_check_matches_expected: str | None = None
    mismatches: list[str] = []
    if proposed is not None:
        observed = validated_plan_to_structural_observation(proposed)
        if fixture.expected is not None:
            intent_match = compare_structural_requirement(fixture.expected, observed).passed
        legacy_structure = grounded_to_structural_requirement(
            projection.grounded_result_intent, pack.semantic_catalog, binding="required",
        )
        mismatches = [name for name, status in
                      compare_structural_requirement(legacy_structure, observed).components
                      if status == "mismatch"]
        if fixture.expected is not None:
            agreement = compare_structural_requirement(legacy_structure, fixture.expected.intent)
            legacy_check_matches_expected = dict(agreement.components).get(
                REASON_COMPONENT.get(legacy_reason or "", ""),
            )
    difference = None
    if (legacy is None) != (proposed is None):
        if legacy is not None or legacy_reason not in STRUCTURAL_REASONS:
            difference = Difference.REAL_DETERMINISTIC_INVARIANT
        elif intent_match is True:
            difference = Difference.FALSE_CONSTRAINT
        elif intent_match is False and legacy_check_matches_expected == "match":
            difference = Difference.USEFUL_BUT_NL_DERIVED_CHECK
        else:
            difference = Difference.UNRESOLVED
    return {
        "fixture_id": fixture.id,
        "family": fixture.family,
        "domain_id": fixture.domain_id,
        "legacy": {"accepted": legacy is not None, "first_rejection": legacy_reason},
        "proposed": {"accepted": proposed is not None, "first_rejection": proposed_reason},
        "difference": difference.value if difference is not None else None,
        "fixture_structure_matches": intent_match,
        "legacy_structural_mismatches": mismatches,
        "legacy_check_matches_expected": legacy_check_matches_expected,
        "retained_mandatory_evidence": projection.mandatory_evidence(),
        "retained_relationship_ids": sorted(item["id"] for item in projection.relationships),
        "evidence": fixture.evidence,
        "future_owners": list(fixture.future_owners),
    }


def authority_inventory() -> list[dict[str, Any]]:
    return [asdict(item) for item in INVENTORY]
