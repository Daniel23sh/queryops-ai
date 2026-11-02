"""Offline W6c stage evidence. Hand-authored witnesses never measure a provider."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import replace
from itertools import product
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth.access_context import build_user_access_context
from app.domains.it_operations.seed import seed_database
from app.evaluation.contracts import (
    ActualOutcome, CaseType, ComparisonMode, EvaluationAnswerability,
    EvaluationCase, EvaluationComparisonProvenance, EvaluationDifficulty,
    EvaluationSemanticAggregation, EvaluationSemanticContract, EvaluationSemanticField,
    EvaluationSemanticSource, ExpectedOutcome, ProvenanceAuthorizationEvidence,
    RequestingRole, ScopeMode,
)
from app.evaluation.environment import evaluation_database_fingerprint
from app.evaluation.evidence import EvaluationComparisonEvidence, observed_evidence_side
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.provenance import extract_evaluation_query_provenance
from app.evaluation.scoring import score_evaluation_case, score_evaluation_semantic_contract
from app.evaluation.selection import evaluation_dataset_digest
from app.models.product import AppUser, DataResource
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.openai_provider import build_safe_prompt_projection
from app.query_engine.provider_config import installed_runtime_versions
from app.query_engine.request_authorization import authorize_query_request
from app.query_engine.schema_context import build_schema_context
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_conformance import check_semantic_conformance
from app.query_engine.semantic_plan import SemanticPlan, SemanticPlanValidationError, validate_semantic_plan
from app.query_engine.sql_executor import execute_validated_sql, query_runtime_transaction
from app.query_engine.sql_renderer import render_validated_semantic_plan
from app.query_engine.sql_validator import validate_sql
from tests.action_postgres_test_db import validated_disposable_database_url

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = "92bf4ca8b7df1d591cdb1b5f3e66188e19cdb5f0"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def guarded_inputs():
    lock = json.loads((HERE / "freeze.json").read_text())
    for name, expected in lock["files"].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected, name
    subprocess.run(["git", "diff", "--exit-code", BASE, "--", "backend/app",
                    "backend/alembic", "backend/pyproject.toml", ".github/workflows"],
                   cwd=ROOT, check=True, capture_output=True)
    assert evaluation_dataset_digest(load_it_operations_evaluation_v2_set()) == lock["dataset_digest"]
    assert load_it_operations_domain_pack().semantic_catalog.digest == lock["catalog_digest"]
    from witnesses import witnesses

    return json.loads((HERE / "heldout-v1.json").read_text()), witnesses(), lock


def initialize(url):
    from fixture import REFERENCE, add_contrasts

    engine = create_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")).scalar_one() == 0
    engine.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=ROOT / "backend", env={**os.environ, "DATABASE_URL": url}, check=True)
    engine = create_engine(url)
    with Session(engine) as db:
        seed_database(db, profile_name="small", reset=False, reference_now=REFERENCE)
        add_contrasts(db)
        db.commit()
    engine.dispose()


def schema_for(db, context, pack):
    user = db.scalar(select(AppUser).where(AppUser.email == "demo.analyst@queryops.local"))
    access = build_user_access_context(user, db)
    if context == "CTX_NO_FREE_QUERY":
        access = replace(access, permissions=access.permissions - {"can_run_free_query"})
    if context == "CTX_NO_LICENSE_RESOURCE":
        resource = db.scalar(select(DataResource).where(DataResource.table_name == "licenses", DataResource.resource_type == "table"))
        resource.llm_exposure_level = "none"
        db.flush()
    schema = build_schema_context(db, access, domain_pack=pack)
    if context == "CTX_LICENSE_COST_HIDDEN":
        # This exercises the existing column-allowlist seam, not a persisted field ACL.
        schema["allowed_columns"]["licenses"].remove("monthly_cost_usd")
    return access, schema


def projection_record(pack, case, schema, access):
    user = {"scope_type": access.default_scope.type if access.default_scope else "none",
            "has_global_scope": access.has_global_scope,
            "scope_reference_resolved": access.has_global_scope or access.default_scope is not None}
    if case["context"] == "CTX_SCOPE_UNRESOLVED":
        user["scope_reference_resolved"] = False
    projection = build_semantic_catalog_projection(pack.semantic_catalog, case["question"], schema, user)
    payload = projection.as_prompt_dict()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ids = {name: sorted(item["id"] for item in payload[name])
           for name in ("entities", "concepts", "metrics", "composition_rules", "relationships")}
    assert len(encoded) <= 16_000
    assert projection.grounded_result_intent is None
    assert projection.as_prompt_dict() == build_semantic_catalog_projection(pack.semantic_catalog, case["question"], schema, user).as_prompt_dict()
    entities = {item["id"]: item["table"] for item in projection.entities}
    for item in projection.concepts:
        assert item["entity_id"] in entities
        assert set(item["all_of_concept_ids"]) <= set(ids["concepts"])
        assert all(p["column"] in schema["allowed_columns"][entities[item["entity_id"]]] for p in item["required_predicates"])
    for item in projection.metrics:
        assert item["entity_id"] in entities and set(item["required_concept_ids"]) <= set(ids["concepts"])
    for item in projection.composition_rules:
        assert set(item["all_of_concept_ids"] + item["or_concept_ids"]) <= set(ids["concepts"])
    for item in projection.relationships:
        for end in ("from", "to"):
            assert item[end + "_entity"] in entities
            assert item[end + "_column"] in schema["allowed_columns"][entities[item[end + "_entity"]]]
    expected = case["candidate_expectations"]
    names = {"entity_ids": "entities", "concept_ids": "concepts", "composition_rule_ids": "composition_rules", "relationship_ids": "relationships"}
    missing = {kind: sorted(set(expected[kind]) - set(ids[attr])) for kind, attr in names.items()}
    forbidden = set(expected.get("forbidden_entity_ids", ())) & set(ids["entities"])
    forbidden |= set(expected.get("forbidden_relationship_ids", ())) & set(ids["relationships"])
    assert not forbidden
    for field_ref in expected.get("forbidden_fields", ()):
        assert field_ref["column"] not in schema["allowed_columns"][entities[field_ref["entity_id"]]]
    assert "it_audit_events" not in schema["allowed_tables"]
    prompt = build_safe_prompt_projection(case["question"], schema, user, projection)
    serialized_prompt = json.dumps(prompt, sort_keys=True)
    assert str(access.user_id) not in serialized_prompt
    assert all(str(scope.id) not in serialized_prompt and
               (scope.department_id is None or str(scope.department_id) not in serialized_prompt)
               for scope in access.scopes)
    assert not set(access.permissions) & set(serialized_prompt.split('"'))
    return projection, {"classification": "independently_verified", "bytes": len(encoded),
                        "ids": ids, "lexical": projection.lexical_evidence(),
                        "safe_prompt_identity_excluded": True,
                        "scope_reference_resolved": user["scope_reference_resolved"],
                        "intended_outcome": {"value": case["intended_outcome"], "classification": "inferred"},
                        "provider_interpretation": "unmeasured",
                        "missing": {kind: values for kind, values in missing.items() if values},
                        "all_targets_available": not any(missing.values()),
                        "deterministic": True, "authorized_closed_bounded": True}


def evaluation_case(question, witness, canonical):
    fields = tuple(EvaluationSemanticField(entity_id=f.entity_id, column=f.column) for f in canonical.output_fields)
    aggregations = tuple(EvaluationSemanticAggregation(
        id=a.id, function=a.function,
        field=EvaluationSemanticField(a.field.entity_id, a.field.column) if a.field else None,
        distinct=a.distinct) for a in canonical.aggregations)
    contract = EvaluationSemanticContract(
        answerability=EvaluationAnswerability.ANSWERABLE, semantic_source=EvaluationSemanticSource.BOTH,
        required_concept_ids=canonical.concept_ids, required_metric_id=canonical.metric_id,
        required_composition_rule_ids=canonical.composition_rule_ids,
        grain_fields=fields, output_fields=fields, aggregations=aggregations,
        group_by=tuple(EvaluationSemanticField(f.entity_id, f.column) for f in canonical.group_by),
        having=(), ordering=(),
    )
    return EvaluationCase(
        id=witness["case_id"], question=question, category="w6c_standalone_not_v2",
        difficulty=EvaluationDifficulty.HARD, case_type=CaseType.FREE_QUERY,
        requesting_role=RequestingRole.ANALYST, required_scope_type="department",
        scope_mode=ScopeMode.ASSIGNED, expected_outcome=ExpectedOutcome.SUCCESS,
        expected_tables=canonical.entity_ids, expected_columns=(), baseline_sql=witness["oracle_sql"],
        requires_join=bool(canonical.relationships), clarification_expected=False,
        security_sensitive=False, comparison_mode=ComparisonMode.GROUPED_ROWS if canonical.aggregations else ComparisonMode.UNORDERED_ROWS,
        numeric_tolerance=None, stable_key_columns=(), template_id=None, semantic_contract=contract,
    )


def execute_witness(engine, access, schema, pack, projection, case, witness):
    from fixture import key

    canonical = SemanticPlan.model_validate_json(json.dumps(witness["plan"]))
    evaluation = evaluation_case(case["question"], witness, canonical)
    variants = [{"id": "canonical", "changes": {}, "expected_result": "correct"}] + witness.get("contrasts", [])
    results = []
    expressibility = []
    with query_runtime_transaction(engine, access, isolation_level="repeatable_read", timezone_name="UTC") as runtime:
        state = dict(runtime.execute(text("SELECT current_user AS role, current_setting('transaction_read_only') AS read_only, current_setting('transaction_isolation') AS isolation, current_setting('TimeZone') AS timezone, transaction_timestamp() AS transaction_time, pg_current_snapshot()::text AS snapshot")).mappings().one())
        assert (state["role"], state["read_only"], state["isolation"], state["timezone"]) == ("queryops_query_runtime", "on", "repeatable read", "UTC")
        baseline_validation = validate_sql(witness["oracle_sql"], schema)
        assert baseline_validation.valid
        baseline = execute_validated_sql(runtime, access, baseline_validation)
        assert baseline.status == "succeeded" and baseline.row_count > 0
        for variant in variants:
            supplied = SemanticPlan.model_validate_json(json.dumps({**witness["plan"], **variant["changes"]}))
            record = {"id": variant["id"], "classification": "independently_verified",
                      "plan_source": "manual_witness_no_provider", "expected_result": variant["expected_result"]}
            try:
                checked = validate_semantic_plan(supplied, domain_pack=pack, projection=projection,
                                                schema_context=schema, scope_reference_resolved=True)
            except SemanticPlanValidationError as exc:
                record.update(plan_validation=exc.reason, result_comparison="not_reached",
                              criteria_met=variant["expected_result"] == "rejected")
                results.append(record)
                continue
            sql = render_validated_semantic_plan(checked, pack)
            assert sql == render_validated_semantic_plan(checked, pack)
            validation = validate_sql(sql, schema)
            assert validation.valid
            conformance = check_semantic_conformance(plan=checked, candidate_sql=sql,
                safety_result=validation, domain_pack=pack, schema_context=schema)
            assert conformance.valid
            actual = execute_validated_sql(runtime, access, validation)
            assert actual.status == "succeeded"
            semantic = score_evaluation_semantic_contract(evaluation, checked.as_observation())
            expected_side = observed_evidence_side(baseline.rows, baseline_validation, baseline, evaluation.semantic_contract.answer_bound)
            actual_side = observed_evidence_side(actual.rows, validation, actual, evaluation.semantic_contract.answer_bound)
            evidence = EvaluationComparisonEvidence(expected=expected_side, actual=actual_side,
                actual_delivery_completeness=actual_side.delivery_completeness)
            provenance = EvaluationComparisonProvenance(
                expected=extract_evaluation_query_provenance(baseline_validation.sanitized_sql,
                    authorization_evidence=ProvenanceAuthorizationEvidence.FROZEN_BASELINE_VALIDATED),
                actual=extract_evaluation_query_provenance(validation.sanitized_sql,
                    authorization_evidence=ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED))
            args = dict(actual_outcome=ActualOutcome.SUCCESS, execution_succeeded=True,
                        actual_referenced_tables=actual.referenced_tables,
                        expected_rows=baseline.rows, actual_rows=actual.rows,
                        provenance=provenance, comparison_evidence=evidence)
            score = score_evaluation_case(evaluation, **args, semantic_contract_passed=semantic.passed)
            rows_only = score_evaluation_case(evaluation, **args, semantic_contract_passed=True)
            record.update(plan_validation="passed", deterministic_rendering=True, sql_safety="passed",
                          conformance="passed", execution="passed", baseline_count=baseline.row_count,
                          actual_count=actual.row_count, distinct_records=len({json.dumps(r, default=str, sort_keys=True) for r in actual.rows}),
                          semantic_contract_passed=semantic.passed, semantic_failure_reasons=semantic.failure_reasons,
                          result_comparison=score.comparison_state.value,
                          result_only_before_semantic_veto=rows_only.comparison_state.value,
                          evidence_complete=actual_side.complete and expected_side.complete,
                          comparison_reason=score.comparison_limitation_reason,
                          output_columns=actual.columns, sql_sha256=digest(sql),
                          criteria_met=score.comparison_state.value == variant["expected_result"])
            # Keep fixtures honest without retaining row values or membership witnesses.
            if variant["id"] == "canonical" and case["id"] in {"W6C-001", "W6C-006", "W6C-008", "W6C-010", "W6C-020"}:
                record["hidden_scope_fixture_excluded"] = all(
                    str(key("Finance/device/" + name)) not in {str(value) for value in row.values()}
                    for name in ("compliance-only", "antivirus-only", "encryption-only", "all", "none", "no-outdated")
                    for row in actual.rows)
                assert record["hidden_scope_fixture_excluded"]
            if variant["id"] == "canonical" and case["id"] == "W6C-010":
                record["different_ids_preserved"] = any(row["devices__id"] != row["software_installs__id"] for row in actual.rows)
                assert record["different_ids_preserved"] and len(set(actual.columns)) == 2
            if variant["id"] == "canonical" and case["id"] == "W6C-006":
                record["exclusive_or_branches_present"] = all(
                    str(key("IT/device/" + name)) in {str(row["id"]) for row in actual.rows}
                    for name in ("compliance-only", "antivirus-only", "encryption-only"))
                assert record["exclusive_or_branches_present"]
            if variant["id"] == "canonical":
                # A changed SQL predicate must not pass the selected-plan conformance boundary.
                from sqlglot import parse_one
                mutated = parse_one(sql, dialect="postgres")
                mutated.set("where", None)
                if mutated.sql(dialect="postgres") != parse_one(sql, dialect="postgres").sql(dialect="postgres"):
                    tampered = mutated.sql(dialect="postgres")
                    guard = check_semantic_conformance(plan=checked, candidate_sql=tampered,
                        safety_result=validate_sql(tampered, schema), domain_pack=pack, schema_context=schema)
                    assert not guard.valid
                    record["removed_predicate_rejected"] = guard.reason_code.value
            results.append(record)
        if case["id"] == "W6C-007":
            # Exhaust the existing tree's eight INNER/LEFT assignments, without changing its oracle.
            for joins in product(("inner", "left"), repeat=len(canonical.relationships)):
                candidate = canonical.model_copy(update={"relationships": tuple(
                    item.model_copy(update={"join_type": join}) for item, join in zip(canonical.relationships, joins, strict=True))})
                row = {"joins": joins}
                try:
                    checked = validate_semantic_plan(candidate, domain_pack=pack, projection=projection,
                                                    schema_context=schema, scope_reference_resolved=True)
                except SemanticPlanValidationError as exc:
                    row["validation"] = exc.reason
                else:
                    sql = render_validated_semantic_plan(checked, pack)
                    validation = validate_sql(sql, schema)
                    assert validation.valid
                    conformance = check_semantic_conformance(plan=checked, candidate_sql=sql,
                        safety_result=validation, domain_pack=pack, schema_context=schema)
                    assert conformance.valid
                    execution = execute_validated_sql(runtime, access, validation)
                    assert execution.status == "succeeded"
                    row.update(validation="passed", count=execution.row_count,
                               same_result_multiset=digest(sorted(json.dumps(r, default=str, sort_keys=True) for r in execution.rows)) == digest(sorted(json.dumps(r, default=str, sort_keys=True) for r in baseline.rows)))
                expressibility.append(row)
        assert runtime.execute(text("SELECT pg_current_snapshot()::text")).scalar_one() == state["snapshot"]
    return {"case_id": witness["case_id"], "runtime": state, "same_snapshot": True,
            "provider_interpretation": "unmeasured", "natural_language_answer_accuracy": "unmeasured",
            "variants": results, "join_assignments": expressibility}


def known_regressions():
    from scripts.probe_candidate_availability import measure_current
    from tests.test_semantic_grounding import _schema_context, _user_context

    known = measure_current()
    question = "In my authorized area, produce one review covering stale endpoints, inactive people accounts, aging open support work, unused optional licenses, recent elevated-group grants, and unresolved critical alerts."
    projection = build_semantic_catalog_projection(load_it_operations_domain_pack().semantic_catalog,
        question, _schema_context(), _user_context("department"))
    required = {"active_directory_account", "human_directory_user", "inactive_directory_user",
                "inactive_human_directory_user", "open_support_ticket_older_than_30_days",
                "privileged_group", "recent_privileged_group_membership", "stale_device",
                "unresolved_critical_security_event", "unused_license_assignment"}
    return {"classification": "reproduced", "w6a_79_known_cases": known["summary"],
            "pr68_CA_B01_exposed_not_heldout": {
                "missing_concepts": sorted(required - {c["id"] for c in projection.concepts}),
                "bytes": len(json.dumps(projection.as_prompt_dict(), sort_keys=True, separators=(",", ":")).encode()),
                "provider_interpretation": "unmeasured"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    corpus, witnesses, lock = guarded_inputs()  # Before DB construction or initialization.
    from fixture import REFERENCE
    from witnesses import field, plan

    assert not args.out.resolve().is_relative_to(HERE)
    url = validated_disposable_database_url(os.environ["POSTGRES_TEST_DATABASE_URL"])
    parsed = make_url(url)
    assert (parsed.host, parsed.port, parsed.database) == ("127.0.0.1", 55469, "queryops_w6c_test")
    if args.initialize:
        initialize(url)
    engine = create_engine(url)
    pack = load_it_operations_domain_pack()
    candidate_results, witness_results = [], []
    by_id = {c["id"]: c for c in corpus["cases"]}
    with Session(engine) as db:
        fingerprint, counts = evaluation_database_fingerprint(db)
        for case in corpus["cases"]:
            access, schema = schema_for(db, case["context"], pack)
            gate = authorize_query_request(access, pack, template_id=None)
            if not gate.allowed:
                candidate_results.append({"case_id": case["id"], "classification": "independently_verified",
                    "request_gate": gate.error_code, "projection": "not_reached", "provider_calls": 0})
                db.rollback()
                continue
            projection, record = projection_record(pack, case, schema, access)
            record["case_id"] = case["id"]
            adversaries = []
            if case["id"] == "W6C-003":
                adversaries.append(("invented_cve_column", plan(["devices"], fields=[("devices", "cve_id")])))
            if case["id"] == "W6C-018":
                adversaries.append(("hidden_license_resource", plan(["licenses"], fields=[("licenses", "id")])))
            if case["id"] == "W6C-019":
                adversaries.extend([
                    ("hidden_cost_output", plan(["licenses"], fields=[("licenses", "monthly_cost_usd")])),
                    ("hidden_cost_aggregate", plan(["licenses"], aggregations=[dict(id="cost", function="sum", field=field("licenses", "monthly_cost_usd"), distinct=False)])),
                    ("restricted_audit", plan(["it_audit_events"], fields=[("it_audit_events", "id")])),
                ])
            record["adversaries"] = []
            for name, supplied in adversaries:
                try:
                    validate_semantic_plan(SemanticPlan.model_validate_json(json.dumps(supplied)),
                        domain_pack=pack, projection=projection, schema_context=schema, scope_reference_resolved=True)
                except SemanticPlanValidationError as exc:
                    record["adversaries"].append({"id": name, "rejected": exc.reason})
                else:
                    raise AssertionError("Unauthorized/invented plan accepted: " + name)
            candidate_results.append(record)
            db.rollback()
        for witness in witnesses:
            case = by_id[witness["case_id"]]
            access, schema = schema_for(db, "CTX_VISIBLE_ASSIGNED", pack)
            projection, _ = projection_record(pack, case, schema, access)
            witness_results.append(execute_witness(engine, access, schema, pack, projection, case, witness))
    with engine.connect() as connection:
        database = dict(connection.execute(text("SELECT version() AS version, (SELECT version_num FROM alembic_version) AS migration")).mappings().one())
    report = {"schema": "queryops-w6c-offline-v1", "runtime_source": BASE,
              "freeze_sha256": hashlib.sha256((HERE / "freeze.json").read_bytes()).hexdigest(),
              "dataset_digest": lock["dataset_digest"], "catalog_digest": pack.semantic_catalog.digest,
              "seed_profile": "small_plus_w6c_contrasts", "seed_reference": REFERENCE,
              "database": database, "database_fingerprint": fingerprint, "table_counts": counts,
              "runtime_versions": installed_runtime_versions(), "paid_provider_calls": 0,
              "python_version": platform.python_version(),
              "dependency_manifest_sha256": hashlib.sha256((ROOT / "backend/pyproject.toml").read_bytes()).hexdigest(),
              "candidates": candidate_results, "witnesses": witness_results,
              "known_regressions": known_regressions()}
    report["summary"] = {
        "candidate_projection_count": sum("bytes" in r for r in candidate_results),
        "request_denials": sum(r.get("request_gate") == "forbidden" for r in candidate_results),
        "complete_candidate_targets": sum(r.get("all_targets_available") is True for r in candidate_results),
        "canonical_manual_results_correct": sum(w["variants"][0]["result_comparison"] == "correct" for w in witness_results),
        "manual_witness_count": len(witness_results),
        "unexpected_or_unestablished_variant_ids": [w["case_id"] + "/" + v["id"]
            for w in witness_results for v in w["variants"] if not v["criteria_met"]],
        "provider_interpretation": "unmeasured", "natural_language_answer_accuracy": "unmeasured",
    }
    candidate_lines = [json.dumps(row, sort_keys=True, default=str, separators=(",", ":")) for row in report.pop("candidates")]
    witness_lines = [json.dumps(row, sort_keys=True, default=str, separators=(",", ":")) for row in report.pop("witnesses")]
    header = json.dumps(report, indent=2, sort_keys=True, default=str).rstrip()[:-1].rstrip()
    args.out.write_text(header + ',\n  "candidates": [\n    ' + ',\n    '.join(candidate_lines)
                        + '\n  ],\n  "witnesses": [\n    ' + ',\n    '.join(witness_lines) + '\n  ]\n}\n')
    print(json.dumps({"candidate_cases": len(candidate_results), "manual_witness_cases": len(witness_results),
                      "variants": sum(len(w["variants"]) for w in witness_results), "out": str(args.out)}))
    engine.dispose()


if __name__ == "__main__":
    main()
