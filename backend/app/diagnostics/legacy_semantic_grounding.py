"""Versioned offline PR52/PR53 reruns using pre-PR57 hint axes.

Shares retrieval/hint calculation, never installs a production mode or copies a
parser. Diagnostics restore lexical and structural checks but use current
deterministic validation, including OR protection and its rejection ordering.
This is not an exact historical validator; reproduce original evidence at its
recorded source revision.
"""

from app.query_engine.semantic_catalog import SemanticCatalogProjection
from app.query_engine.semantic_grounding import _build_candidate_context
from app.query_engine.semantic_plan import (
    SemanticPlanValidationError,
    validate_semantic_plan as validate_current_plan,
)


class LegacyProjection(SemanticCatalogProjection):
    def mandatory_evidence(self):
        return self.lexical_evidence()


def build_legacy_projection(catalog, question, schema_context, user_context):
    projection, required, suggested = _build_candidate_context(
        catalog, question, schema_context, user_context
    )
    return LegacyProjection(
        **{
            **vars(projection),
            "grounded_result_intent": required,
            "suggested_result_intent": suggested,
        }
    )


def validate_legacy_plan(plan, *, domain_pack, projection, **kwargs):
    """Apply legacy lexical checks around current deterministic proofs (v2)."""
    evidence = projection.lexical_evidence()
    for kind, selected in (("entity", plan.entity_ids), ("rule", plan.composition_rule_ids)):
        if not set(evidence[f"{kind}_ids"]) <= set(selected):
            raise SemanticPlanValidationError(f"mandatory_{kind}_missing")
    metrics = set(evidence["metric_ids"])
    if len(metrics) > 1:
        raise SemanticPlanValidationError("mandatory_metric_ambiguous")
    if metrics and plan.metric_id not in metrics:
        raise SemanticPlanValidationError("mandatory_metric_missing")
    validated = validate_current_plan(
        plan, domain_pack=domain_pack, projection=projection, **kwargs
    )
    # Check effective selected definitions, including metric/rule dependencies.
    from app.query_engine.semantic_catalog import expand_semantic_concept_ids

    selected = set(plan.concept_ids)
    catalog = domain_pack.semantic_catalog
    if plan.metric_id:
        selected.update(catalog.metrics_by_id[plan.metric_id].required_concept_ids)
    for rule in catalog.composition_rules:
        if rule.id in plan.composition_rule_ids:
            selected.update(rule.all_of_concept_ids)
            selected.update(rule.or_concept_ids)
    if not set(evidence["concept_ids"]) <= set(expand_semantic_concept_ids(catalog, selected)):
        raise SemanticPlanValidationError("mandatory_concept_missing")
    return validated
