"""PR57: independent supplied interpretations, not a second English oracle."""

from dataclasses import replace

import pytest

from app.query_engine.result_intent import GroundedResultIntent
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_plan import SemanticPlanValidationError, validate_semantic_plan
from scripts.semantic_ownership_fixtures import architecture_fixtures, fixture_packs, offline_schema


# PR53's hand-authored contrasts include intentionally wrong answers. Both a
# correct and an incorrect interpretation can be legal: judging the English is
# the planner's job, not evidence inferred by the implementation under test.
CASES = [(fixture, question) for fixture in architecture_fixtures()
         if fixture.family != "deterministic_protection" for question in fixture.questions]


@pytest.mark.parametrize("fixture,question", CASES, ids=[f"{f.id}-{i}" for i, (f, _) in enumerate(CASES)])
def test_free_question_does_not_veto_legal_interpretation(fixture, question):
    pack = fixture_packs()[fixture.domain_id]
    schema = offline_schema(pack)
    projection = build_semantic_catalog_projection(pack.semantic_catalog, question, schema, {})
    assert projection.grounded_result_intent is None
    assert not any(projection.mandatory_evidence().values())
    assert "mandatory_semantic_evidence" not in projection.as_prompt_dict()
    validated = validate_semantic_plan(fixture.plan, domain_pack=pack, projection=projection,
                                       schema_context=schema, scope_reference_resolved=True)
    # Canonical presentation order may change; declared meaning must not.
    for name in type(fixture.plan).model_fields:
        supplied, actual = getattr(fixture.plan, name), getattr(validated.plan, name)
        if isinstance(supplied, tuple) and name != "order_by":
            assert set(actual) == set(supplied)
        else:
            assert actual == supplied


@pytest.mark.parametrize("question", ["Count active users.", "Count currently active user accounts.",
                                     "List users, not active users."])
def test_exact_and_nearby_catalog_wording_does_not_require_metric(question):
    fixture = next(f for f in architecture_fixtures() if f.id == "metric_mandate_retained")
    pack = fixture_packs()[fixture.domain_id]
    schema = offline_schema(pack)
    projection = build_semantic_catalog_projection(pack.semantic_catalog, question, schema, {})
    # A deliberately contradictory hint cannot veto even an ordinary row count.
    projection = replace(projection, suggested_result_intent=GroundedResultIntent(distinct=True))
    assert validate_semantic_plan(fixture.plan, domain_pack=pack, projection=projection,
                                  schema_context=schema, scope_reference_resolved=False).plan == fixture.plan


@pytest.mark.parametrize("fixture", [f for f in architecture_fixtures()
                                     if f.family == "deterministic_protection"], ids=lambda f: f.id)
def test_deterministic_protection_is_not_english_authority(fixture):
    pack = fixture_packs()[fixture.domain_id]
    schema = offline_schema(pack)
    projection = build_semantic_catalog_projection(pack.semantic_catalog, fixture.questions[0], schema, {})
    with pytest.raises(SemanticPlanValidationError):
        validate_semantic_plan(fixture.plan, domain_pack=pack, projection=projection,
                               schema_context=schema, scope_reference_resolved=True)


@pytest.mark.parametrize("question,kind,candidate", [
    ("Count non-compliant devices.", "rule_ids", "non_compliant_device_posture"),
    ("Count devices with non-compliant status.", "concept_ids", "non_compliant_device"),
    ("Count devices and directory users.", "entity_ids", "directory_users"),
])
def test_exact_lexical_context_retention_is_not_plan_obligation(question, kind, candidate):
    fixture = next(f for f in architecture_fixtures() if f.id == "device_rows")
    pack = fixture_packs()[fixture.domain_id]
    schema = offline_schema(pack)
    projection = build_semantic_catalog_projection(pack.semantic_catalog, question, schema, {})
    assert candidate in projection.lexical_evidence()[kind]
    validated = validate_semantic_plan(fixture.plan, domain_pack=pack, projection=projection,
                                       schema_context=schema, scope_reference_resolved=False)
    assert validated.plan == fixture.plan
    assert validated.effective_predicates == ()
