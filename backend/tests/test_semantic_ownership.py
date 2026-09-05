from __future__ import annotations

import ast
import inspect
import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.selection import V2_DATASET_DIGEST, evaluation_dataset_digest
from app.evaluation.structural_conformance import build_v2_structural_conformance_report
from app.query_engine import semantic_plan
from app.query_engine.openai_provider import OpenAIProvider, SYSTEM_INSTRUCTIONS
from app.query_engine.plan_generator import PlanGenerator
from scripts import semantic_ownership as shadow
from scripts.audit_semantic_ownership import build_report, run_cli
from scripts.semantic_ownership_fixtures import architecture_fixtures, fixture_packs, offline_schema


@pytest.fixture(scope="module")
def report():
    return build_report()


def case(report, name, paraphrase=0):
    return next(c for c in report["cases"] if c["fixture_id"] == name and c["paraphrase"] == paraphrase)


def test_inventory_is_deterministic_and_explicit():
    first = json.dumps(shadow.authority_inventory(), sort_keys=True)
    assert first == json.dumps(shadow.authority_inventory(), sort_keys=True)
    items = {item.id: item for item in shadow.INVENTORY}
    assert len(items) == len(shadow.INVENTORY)
    assert set(items) == {
        "subject", "quantity", "aggregate_target", "grouping", "detail_grain", "having",
        "outputs", "distinct", "entity_mandate", "concept_mandate", "metric_mandate",
        "rule_mandate", "path_pruning", "authorization", "catalog_meaning",
        "relationship_facts", "identity_facts", "plan_algebra", "suggestions",
        "sql_boundary", "structural_audit",
    }
    assert {i.authority for i in items.values()} == set(shadow.Authority)
    assert all(i.disposition != shadow.Disposition.KEEP_BINDING
               for i in items.values() if i.authority == shadow.Authority.NL_INTERPRETATION)
    assert "suggested only" in items["detail_grain"].effect
    assert "required remains unset" in items["distinct"].effect


def test_runtime_structural_enforcement_is_fully_accounted_for():
    tree = ast.parse(inspect.getsource(semantic_plan._validate_grounded_result_intent))
    components = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                  and isinstance(n.value, ast.Name) and n.value.id == "intent"}
    assert components == {"required_output_fields", "aggregations", "group_by", "having", "distinct", "row_grain"}
    reasons = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Name) and n.func.id == "SemanticPlanValidationError"
               and n.args and isinstance(n.args[0], ast.Constant)}
    assert reasons == shadow.STRUCTURAL_REASONS == set(shadow.REASON_COMPONENT)


def test_same_plan_and_only_structural_slot_changes(monkeypatch):
    fixture = next(f for f in architecture_fixtures() if f.id == "license_count_value")
    pack = fixture_packs()[fixture.domain_id]
    before = fixture.plan.model_dump_json()
    calls = []
    original = shadow.validate_semantic_plan

    def observe(plan, **kwargs):
        calls.append((plan, kwargs))
        return original(plan, **kwargs)

    monkeypatch.setattr(shadow, "validate_semantic_plan", observe)
    shadow.compare_fixture(fixture, fixture.questions[0], pack, offline_schema(pack), {})
    assert len(calls) == 2
    assert calls[0][0] is calls[1][0] is fixture.plan
    legacy, proposed = calls[0][1]["projection"], calls[1][1]["projection"]
    assert legacy.grounded_result_intent is not None
    assert proposed == replace(legacy, grounded_result_intent=None)
    assert fixture.plan.model_dump_json() == before
    assert calls[0][1]["schema_context"] is calls[1][1]["schema_context"]


def test_no_provider_network_database_or_runtime_mutation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline harness attempted an external or execution boundary")

    for owner, name in ((socket.socket, "connect"), (socket, "create_connection"),
                        (Engine, "connect"), (Session, "execute"),
                        (OpenAIProvider, "generate_plan"), (PlanGenerator, "generate_plan")):
        monkeypatch.setattr(owner, name, forbidden)
    paths = list((Path(__file__).parents[1] / "app/query_engine").glob("*.py"))
    source_before = {p: p.read_bytes() for p in paths}
    schema_before = semantic_plan.SemanticPlan.model_json_schema()
    validator_before = semantic_plan.validate_semantic_plan
    prompt_before = SYSTEM_INSTRUCTIONS
    first = build_report()
    assert first == build_report()
    assert source_before == {p: p.read_bytes() for p in paths}
    assert schema_before == semantic_plan.SemanticPlan.model_json_schema()
    assert validator_before is semantic_plan.validate_semantic_plan
    from app.query_engine.openai_provider import SYSTEM_INSTRUCTIONS as prompt_after
    assert prompt_before == prompt_after


def test_independent_families_and_no_v2_or_domain_imports_in_generic_logic():
    fixtures = architecture_fixtures()
    assert len({f.id for f in fixtures}) == len(fixtures)
    assert {f.family for f in fixtures} >= {
        "counted_subject", "grouping_ordering", "temporal_having", "detail_aggregate",
        "multiple_aggregates", "row_distinct", "multiple_dimensions",
        "relationship_ambiguity", "negation", "ranking",
    }
    frozen_questions = {c.question.casefold() for c in load_it_operations_evaluation_v2_set().cases}
    assert not frozen_questions & {q.casefold() for f in fixtures for q in f.questions}
    scripts = Path(__file__).parents[1] / "scripts"
    for path in scripts.glob("*semantic_ownership*.py"):
        tree = ast.parse(path.read_text())
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any("evaluation" in name for name in imports)
        assert "baseline_sql" not in path.read_text()
    generic = (scripts / "semantic_ownership.py").read_text().lower()
    assert all(word not in generic for word in ("it_operations", "devices", "licenses", "samples"))
    # Production modules cannot accidentally discover/wire the experiment.
    for path in (Path(__file__).parents[1] / "app").rglob("*.py"):
        assert "scripts.semantic_ownership" not in path.read_text()


@pytest.mark.parametrize("name", ["license_count_value", "distinct_os", "two_dimensions",
                                 "subject_directory_users", "subject_groups", "temporal_only"])
def test_false_constraints_require_independent_structural_agreement(report, name):
    item = case(report, name)
    assert item["difference"] == "FALSE_CONSTRAINT"
    assert item["fixture_structure_matches"] is True
    assert not item["legacy"]["accepted"] and item["proposed"]["accepted"]


@pytest.mark.parametrize("name", ["ticket_groups_missing", "device_output_missing",
                                 "ticket_total_as_detail", "aggregate_threshold_missing",
                                 "user_grain_as_joined_rows"])
def test_useful_checks_have_independent_agreement_and_explicit_owners(report, name):
    item = case(report, name)
    assert item["difference"] == "USEFUL_BUT_NL_DERIVED_CHECK"
    assert item["fixture_structure_matches"] is False
    assert item["legacy_check_matches_expected"] == "match"
    assert item["future_owners"]
    assert any("PR56" in owner for owner in item["future_owners"])
    # Fanout can be checked once the subject is declared; English omissions cannot.
    if name == "user_grain_as_joined_rows":
        assert any("PR54" in owner and "multiplicity" in owner for owner in item["future_owners"])
    if name == "device_output_missing":
        assert any("no relational proof" in owner for owner in item["future_owners"])


def test_coincidental_bad_plan_rejection_is_not_automatically_useful(report):
    item = case(report, "second_dimension_missing")
    assert item["difference"] == "UNRESOLVED"
    assert item["fixture_structure_matches"] is False
    assert item["legacy_check_matches_expected"] == "mismatch"


@pytest.mark.parametrize("name,reason", [
    ("unauthorized_field", "field_not_authorized"),
    ("broken_group_shape", "group_by_incomplete"),
    ("scope_literal", "scope_filter_not_allowed"),
    ("metric_mandate_retained", "mandatory_metric_missing"),
])
def test_preserved_constraints_reject_both(report, name, reason):
    item = case(report, name)
    assert item["legacy"] == item["proposed"] == {"accepted": False, "first_rejection": reason}


@pytest.mark.parametrize("name", ["license_value_missing", "distinct_os_as_rows", "order_priority_reversed"])
def test_acceptance_is_not_answer_correctness(report, name):
    item = case(report, name)
    assert item["legacy"]["accepted"] and item["proposed"]["accepted"]
    assert item["fixture_structure_matches"] is False


def test_ambiguity_and_predicates_are_not_fabricated_structural_proofs(report):
    for name in ("ambiguous_department", "ambiguous_department_alternative", "negation_reversed"):
        assert case(report, name)["fixture_structure_matches"] is None
    assert not any(c["difference"] == "REAL_DETERMINISTIC_INVARIANT" for c in report["cases"])


def test_second_domain_exposes_temporal_attachment_without_engine_vocabulary(report):
    before, after = case(report, "temporal_only"), case(report, "temporal_only", 1)
    assert before["domain_id"] == after["domain_id"] == "laboratory"
    assert before["legacy"]["first_rejection"] == "grounded_having_mismatch"
    assert after["legacy"]["accepted"]
    assert before["proposed"]["accepted"] and after["proposed"]["accepted"]


def test_v2_and_pr52_remain_reproducible():
    before = build_v2_structural_conformance_report().as_safe_dict()
    build_report()
    assert before == build_v2_structural_conformance_report().as_safe_dict()
    assert evaluation_dataset_digest(load_it_operations_evaluation_v2_set()) == V2_DATASET_DIGEST


def test_cli_safe_deterministic_stdout(capsys, report):
    assert run_cli(["--json"]) == 0
    payload = capsys.readouterr().out
    assert json.loads(payload) == json.loads(json.dumps(report))
    assert all(text not in payload for text in ('"question":', '"plan":', 'SELECT ', 'baseline_sql', 'synthetic_scope'))
    assert run_cli([]) == 0
    assert "not scores" in capsys.readouterr().out
