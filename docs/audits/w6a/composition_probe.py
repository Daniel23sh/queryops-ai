"""Offline W6a runtime diagnostics; handwritten plans are NOT model observations.

Run from backend with the three disposable-DB environment variables documented
in composition-findings.md. --initialize migrates and seeds an EMPTY guarded DB.
Outputs contain safe counts, hashes and stage metadata, never result records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
import subprocess
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.orm import sessionmaker

from app.domains.it_operations.seed import seed_database
from app.evaluation.baseline import execute_evaluation_baseline
from app.evaluation.context import resolve_evaluation_identity
from app.evaluation.contracts import ActualOutcome, ComparisonMode, EvaluationComparisonProvenance, EvaluationSemanticField, ProvenanceAuthorizationEvidence
from app.evaluation.environment import evaluation_database_fingerprint
from app.evaluation.evidence import EvaluationComparisonEvidence, observed_evidence_side
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.provenance import EvaluationProvenanceError, extract_evaluation_query_provenance
from app.evaluation.scoring import score_evaluation_case, score_evaluation_semantic_contract
from app.evaluation.selection import evaluation_dataset_digest
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.plan_generator import PlanGeneratorResult
from app.query_engine.request_authorization import authorize_query_request
from app.query_engine.schema_context import build_schema_context
from app.query_engine.semantic_catalog import semantic_catalog_identity
from app.query_engine.semantic_plan import SemanticFieldRef, SemanticPlan, SemanticRelationshipIntent
from app.query_engine.service import QueryEngineRequest, QueryEngineService
from app.query_engine.sql_executor import execute_validated_sql, query_runtime_transaction
from app.query_engine.sql_validator import validate_sql
from tests.action_postgres_test_db import validated_disposable_database_url


REFERENCE = "2026-11-01T09:20:36+00:00"
ROOT = Path(__file__).resolve().parents[3]


def digest(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def plan(*, entities, concepts=(), rules=(), fields=(), relationships=(), distinct=False):
    return SemanticPlan(
        entity_ids=tuple(entities), concept_ids=tuple(concepts),
        composition_rule_ids=tuple(rules), metric_id=None, distinct=distinct,
        literal_filters=(), relationships=tuple(SemanticRelationshipIntent(
            relationship_id=value, join_type="inner") for value in relationships),
        output_fields=tuple(SemanticFieldRef(entity_id=entity, column=column)
                            for entity, column in fields),
        aggregations=(), group_by=(), having=(), order_by=(), limit=None,
    )


def fixtures():
    device = plan(entities=("devices", "software_installs"),
                  concepts=("outdated_software_install",),
                  rules=("non_compliant_device_posture",),
                  fields=(("devices", "id"),),
                  relationships=("software_install_device",), distinct=True)
    yield "medium009_intended_or", "itops-medium-009", device
    yield "medium009_status_only", "itops-medium-009", device.model_copy(update={
        "composition_rule_ids": (),
        "concept_ids": ("outdated_software_install", "non_compliant_device")})
    yield "medium009_rule_omitted", "itops-medium-009", device.model_copy(update={
        "composition_rule_ids": ()})
    yield "medium009_or_plus_status", "itops-medium-009", device.model_copy(update={
        "concept_ids": ("outdated_software_install", "non_compliant_device")})
    yield "medium009_or_plus_antivirus", "itops-medium-009", device.model_copy(update={
        "concept_ids": ("outdated_software_install", "antivirus_attention_device")})
    yield "medium009_or_plus_encryption", "itops-medium-009", device.model_copy(update={
        "concept_ids": ("outdated_software_install", "unencrypted_device")})
    branches = ("outdated_software_install", "non_compliant_device",
                "antivirus_attention_device", "unencrypted_device")
    yield "medium009_or_plus_all_branches", "itops-medium-009", device.model_copy(update={
        "concept_ids": branches})
    yield "medium009_all_branches_no_rule", "itops-medium-009", device.model_copy(update={
        "concept_ids": branches, "composition_rule_ids": ()})
    yield "medium009_no_distinct", "itops-medium-009", device.model_copy(update={
        "distinct": False})
    users = plan(entities=("directory_users",), concepts=("service_account",),
                 fields=(("directory_users", "id"), ("directory_users", "account_type"),
                         ("directory_users", "account_status")))
    yield "service_accounts_catalog", "itops-easy-010", users
    terminated = plan(entities=("directory_users",),
                      concepts=("terminated_employee_with_active_account",),
                      fields=(("directory_users", "id"), ("directory_users", "employee_status"),
                              ("directory_users", "account_status")))
    yield "terminated_active_catalog", "itops-medium-011", terminated
    yield "terminated_omitted_active", "itops-medium-011", terminated.model_copy(update={
        "concept_ids": ("terminated_employee",)})
    inactive = plan(entities=("devices", "directory_users", "software_installs"),
                    concepts=("high_risk_unsupported_software_install", "inactive_directory_user"),
                    fields=(("devices", "id"), ("directory_users", "id")),
                    relationships=("device_assignee", "software_install_device"), distinct=True)
    yield "inactive_null_or_90days_catalog", "itops-hard-005", inactive
    yield "inactive_human_extra_narrowing", "itops-hard-005", inactive.model_copy(update={
        "concept_ids": ("high_risk_unsupported_software_install", "inactive_human_directory_user")})
    yield "inactive_fk_equivalent_user_output", "itops-hard-005", inactive.model_copy(update={
        "output_fields": (SemanticFieldRef(entity_id="devices", column="id"),
                          SemanticFieldRef(entity_id="devices", column="assigned_user_id"))})
    yield "inactive_fk_equivalent_device_output", "itops-hard-005", inactive.model_copy(update={
        "output_fields": (SemanticFieldRef(entity_id="software_installs", column="device_id"),
                          SemanticFieldRef(entity_id="directory_users", column="id"))})
    single_user = plan(entities=("directory_users",), concepts=("inactive_directory_user",),
                       fields=(("directory_users", "id"),))
    yield "exploratory_inactive_null_or_90days", "exploratory-inactive", single_user
    yield "exploratory_inactive_human_narrowing", "exploratory-inactive", single_user.model_copy(update={
        "concept_ids": ("inactive_human_directory_user",)})


def initialize(url):
    child_environment = {**os.environ, "DATABASE_URL": url}
    subprocess.run([str(ROOT / "backend/.venv/bin/alembic"), "upgrade", "head"],
                   cwd=ROOT / "backend", env=child_environment, check=True)
    engine = create_engine(url)
    with sessionmaker(engine)() as db:
        summary = seed_database(db, profile_name="medium", reset=False,
                                reference_now=datetime.fromisoformat(REFERENCE))
        assert summary.seed == 42
        db.commit()
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    dataset = load_it_operations_evaluation_v2_set()
    pack = load_it_operations_domain_pack()
    frozen = json.loads((Path(__file__).parent / "baseline.json").read_text())
    assert evaluation_dataset_digest(dataset) == frozen["dataset"]["digest"]
    assert semantic_catalog_identity(pack.semantic_catalog) == frozen["catalog"]
    subprocess.run(["git", "diff", "--exit-code", frozen["source_commit"], "--",
                    *frozen["source_tree_paths"]], cwd=ROOT, check=True, capture_output=True)
    url = validated_disposable_database_url(os.environ["POSTGRES_TEST_DATABASE_URL"])
    endpoint = make_url(url)
    assert endpoint.host == "127.0.0.1" and endpoint.port == 55447
    assert endpoint.database == "queryops_w6a_composition_test"
    if args.initialize:
        initialize(url)
    engine = create_engine(url)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        seed_fingerprint, seed_counts = evaluation_database_fingerprint(db)
    with engine.connect() as connection:
        database = dict(connection.execute(text(
            "SELECT version() AS version, transaction_timestamp() AS transaction_time, "
            "current_setting('TimeZone') AS timezone, "
            "(SELECT version_num FROM alembic_version) AS migration_head"
        )).mappings().one())
    results = []
    for probe_id, case_id, supplied_plan in fixtures():
        observations = []
        candidates = {}
        execution_side = "actual"

        def supply(_generator, question, schema, user, options):
            projection = options["semantic_catalog"]
            candidates.update(projection.as_observation())
            return PlanGeneratorResult(
                provider_name="diagnostic_manual_fixture", model_name="no_model_called",
                semantic_plan=supplied_plan,
                generation_metadata={"source": "manually_supplied_runtime_probe"},
            )

        def observe_execution(db, access, validation, *, options=None):
            execution = execute_validated_sql(db, access, validation, options=options)
            runtime = {}
            if isinstance(db, Connection):
                runtime = dict(db.execute(text(
                    "SELECT current_user AS runtime_role, "
                    "current_setting('transaction_read_only') AS read_only, "
                    "current_setting('transaction_isolation') AS isolation, "
                    "current_setting('TimeZone') AS timezone, "
                    "transaction_timestamp() AS transaction_time, "
                    "pg_current_snapshot()::text AS snapshot"
                )).mappings().one())
            canonical = sorted(json.dumps(row, sort_keys=True, default=str)
                               for row in execution.rows)
            shape = {"columns": execution.columns,
                     "unique_column_count": len(set(execution.columns)),
                     "mapped_key_counts": sorted({len(row) for row in execution.rows})}
            if len(execution.columns) != len(set(execution.columns)):
                # Diagnostic replay stays on the already authorized read-only snapshot.
                replay = db.execute(text(validation.sanitized_sql))
                tuples = replay.fetchall()
                shape.update({"diagnostic_validated_sql_replay_count": 1,
                    "duplicate_label_positions_differ": any(
                        row[left] != row[right]
                        for row in tuples for left in range(len(execution.columns))
                        for right in range(left + 1, len(execution.columns))
                        if execution.columns[left] == execution.columns[right])})
            observations.append({
                "status": execution.status, "error_code": execution.error_code,
                "side": execution_side,
                "count": execution.row_count, "unique_count": len(set(canonical)),
                "result_multiset_sha256": digest(canonical),
                "sql_sha256": digest(validation.sanitized_sql),
                "truncated": execution.truncated,
                "limit_source": validation.limit_source,
                "delivery_completeness": execution.execution_metadata.get("delivery_completeness"),
                "runtime": runtime,
                "shape": shape,
            })
            return execution

        with factory() as db:
            if case_id == "exploratory-inactive":
                base = dataset.cases_by_id["itops-hard-005"]
                field = EvaluationSemanticField(entity_id="directory_users", column="id")
                case = replace(base, id=case_id,
                    question="Show inactive directory users including those with no successful login.",
                    expected_tables=("directory_users",), expected_columns=(),
                    baseline_sql="SELECT id FROM directory_users WHERE last_login_at IS NULL OR last_login_at < CURRENT_TIMESTAMP - INTERVAL '90 days'",
                    requires_join=False, comparison_mode=ComparisonMode.UNORDERED_ROWS,
                    stable_key_columns=(),
                    semantic_contract=replace(base.semantic_contract,
                        required_concept_ids=("inactive_directory_user",),
                        grain_fields=(field,), output_fields=(field,)))
            else:
                case = dataset.cases_by_id[case_id]
            identity = resolve_evaluation_identity(db, case)
            assert authorize_query_request(identity.access_context, pack, template_id=None).allowed
            with query_runtime_transaction(engine, identity.access_context,
                    isolation_level="repeatable_read", timezone_name="UTC") as runtime:
                with patch("app.query_engine.service.PlanGenerator.generate_plan", supply):
                    result = QueryEngineService(executor=observe_execution).run(
                        db, identity.user, QueryEngineRequest(question=case.question),
                        execution_db_factory=lambda _: runtime)
                execution_side = "expected"
                baseline = execute_evaluation_baseline(
                    db, identity.access_context, case, pack,
                    executor=lambda _db, access, validation, *, options=None:
                        observe_execution(runtime, access, validation, options=options))
                semantic = score_evaluation_semantic_contract(case, result.metadata.get("semantic_plan"))
                evidence = None
                provenance = None
                provenance_reason = None
                succeeded = result.status == "succeeded"
                if succeeded:
                    actual_side = observed_evidence_side(result.rows, result.validation_result,
                        result.execution_result, case.semantic_contract.answer_bound)
                    expected_side = observed_evidence_side(baseline.rows, baseline.validation,
                        baseline.execution, case.semantic_contract.answer_bound)
                    evidence = EvaluationComparisonEvidence(expected=expected_side,
                        actual=actual_side, actual_delivery_completeness=actual_side.delivery_completeness)
                    try:
                        provenance = EvaluationComparisonProvenance(
                            expected=extract_evaluation_query_provenance(baseline.validation.sanitized_sql,
                                authorization_evidence=ProvenanceAuthorizationEvidence.FROZEN_BASELINE_VALIDATED),
                            actual=extract_evaluation_query_provenance(result.validation_result.sanitized_sql,
                                authorization_evidence=ProvenanceAuthorizationEvidence.FINAL_SQL_VALIDATED))
                    except EvaluationProvenanceError as exc:
                        provenance_reason = exc.reason
                score = score_evaluation_case(case,
                    actual_outcome=ActualOutcome.SUCCESS if succeeded else ActualOutcome.EXECUTION_FAILED,
                    execution_succeeded=succeeded,
                    actual_referenced_tables=result.validation_result.referenced_tables
                        if result.validation_result else (),
                    expected_rows=baseline.rows, actual_rows=result.rows,
                    provenance=provenance, comparison_evidence=evidence,
                    semantic_contract_passed=semantic.passed)
                row_comparison = score_evaluation_case(case,
                    actual_outcome=ActualOutcome.SUCCESS if succeeded else ActualOutcome.EXECUTION_FAILED,
                    execution_succeeded=succeeded,
                    actual_referenced_tables=result.validation_result.referenced_tables
                        if result.validation_result else (),
                    expected_rows=baseline.rows, actual_rows=result.rows,
                    provenance=provenance, comparison_evidence=evidence,
                    semantic_contract_passed=True)
                controls = []
                if probe_id == "exploratory_inactive_null_or_90days":
                    schema = build_schema_context(db, identity.access_context, domain_pack=pack)
                    for control_id, sql in (
                        ("null_login_subset", "SELECT id FROM directory_users WHERE last_login_at IS NULL"),
                        ("older_login_subset", "SELECT id FROM directory_users WHERE last_login_at < CURRENT_TIMESTAMP - INTERVAL '90 days'"),
                    ):
                        validation = validate_sql(sql, schema)
                        assert validation.valid
                        control = execute_validated_sql(runtime, identity.access_context, validation)
                        assert control.status == "succeeded" and not control.truncated
                        controls.append({"control_id": control_id, "count": control.row_count})
                    assert sum(item["count"] for item in controls) == result.row_count
        safe_metrics = {"semantic_contract": semantic.as_safe_metrics(),
                        "row_comparison_before_semantic_contract_veto": row_comparison.comparison_state.value,
                        "provenance_reason": provenance_reason,
                        "comparison_evidence": evidence.as_safe_dict() if evidence else None,
                        "stages": {key: result.metadata.get(key) for key in (
                            "semantic_plan_validation", "semantic_sql_render", "semantic_conformance",
                            "validation", "execution")}}
        case_summary = {**asdict(score), "status": result.status, "error_code": result.error_code}
        results.append({
            "probe_id": probe_id, "case_id": case_id,
            "source": "handwritten_plan_fixture_not_model_selection",
            "plan_sha256": digest(supplied_plan.model_dump(mode="json")),
            "selected_concepts": list(supplied_plan.concept_ids),
            "selected_rules": list(supplied_plan.composition_rule_ids),
            "distinct": supplied_plan.distinct,
            "actor_role": case.requesting_role.value,
            "exploratory": case_id == "exploratory-inactive",
            "candidate_observation": candidates, "summary": case_summary,
            "metrics": safe_metrics, "executions_actual_then_expected": observations,
            "same_snapshot_subset_controls": controls,
        })
    report = {
        "schema": "queryops-w6a-composition-v1", "live_provider_calls": 0,
        "model_selection_tested": False, "seed_profile": "medium", "seed": 42,
        "seed_reference_time": REFERENCE, "database": database,
        "seed_fingerprint": seed_fingerprint, "seed_table_counts": seed_counts,
        "runtime_source_sha": frozen["source_commit"],
        "investigation_head_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "baseline_reference": "baseline.json",
        "baseline_file_sha256": hashlib.sha256((Path(__file__).parent / "baseline.json").read_bytes()).hexdigest(),
        "dataset_digest": evaluation_dataset_digest(dataset),
        "catalog": semantic_catalog_identity(pack.semantic_catalog),
        "probes": results,
    }
    # A diagnostic failure must not quietly turn into a claim about model quality.
    expected = {"medium009_intended_or": True, "medium009_status_only": False,
                "service_accounts_catalog": True, "terminated_active_catalog": True,
                "exploratory_inactive_null_or_90days": True}
    for result in results:
        if result["probe_id"] in expected:
            assert result["summary"]["passed"] is expected[result["probe_id"]], (result["probe_id"], result["summary"], result["metrics"])
        for execution in result["executions_actual_then_expected"]:
            assert execution["runtime"]["runtime_role"] == "queryops_query_runtime"
            assert execution["runtime"]["read_only"] == "on"
            assert execution["runtime"]["isolation"] == "repeatable read"
        snapshots = [item["runtime"]["snapshot"] for item in result["executions_actual_then_expected"]]
        assert len(set(snapshots)) <= 1
    candidates_by_case = {}
    for result in results:
        candidates_by_case[result["case_id"]] = result.pop("candidate_observation")
        result["candidate_observation_ref"] = result["case_id"]
        summary = result["summary"]
        result["summary"] = {key: summary[key] for key in (
            "status", "error_code", "passed", "comparison_state", "delivery_completeness",
            "comparison_limitation_reason", "failure_reasons")}
        metrics = result["metrics"]
        semantic = metrics["semantic_contract"]
        metrics["semantic_contract"] = {key: semantic[key] for key in (
            "evaluated", "passed", "rules_correct", "concepts_correct", "grain_correct",
            "outputs_correct", "failure_reasons")}
        evidence = metrics.pop("comparison_evidence")
        metrics["comparison_evidence"] = {side: {key: evidence[side][key] for key in (
            "complete", "exhausted", "limitation_reason")}
            for side in ("actual", "expected")} if evidence else None
        metrics["stages"] = {stage: {key: value[key] for key in (
            "status", "valid", "reason_code", "error_code") if key in value}
            if value else None for stage, value in metrics["stages"].items()}
        executions = result["executions_actual_then_expected"]
        result["runtime"] = executions[0]["runtime"]
        result["same_snapshot_verified"] = len({item["runtime"]["snapshot"] for item in executions}) == 1
        for execution in executions:
            execution.pop("runtime")
    report["candidate_observations_by_case"] = candidates_by_case
    # One compact line per probe keeps repeated stage evidence reviewable in Git.
    probe_lines = ",\n".join("    " + json.dumps(item, default=str, sort_keys=True,
                            separators=(",", ":")) for item in report.pop("probes"))
    header = json.dumps(report, default=str, sort_keys=True, indent=2).rstrip()[:-1].rstrip()
    args.out.write_text(header + ',\n  "probes": [\n' + probe_lines + "\n  ]\n}\n")
    print(json.dumps({"probe_count": len(results), "live_calls": 0,
                      "passed": sum(r["summary"]["passed"] for r in results),
                      "output": str(args.out)}))
    engine.dispose()


if __name__ == "__main__":
    main()
