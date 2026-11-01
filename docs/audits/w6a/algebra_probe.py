"""W6a exploratory handwritten algebra probes; never invokes a provider.

Run from backend with PYTHONPATH=.:tests, the guarded disposable environment,
and --out ../docs/audits/w6a/algebra-results.json. --initialize migrates and
seeds the dedicated EMPTY database. No raw rows, SQL or identities are emitted.
SQL witnesses for rejected plans isolate downstream equivalence; they do not
turn rejected plans into supported product requests or model observations.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.domains.it_operations.seed import seed_database
from app.domains.it_operations.models import DirectoryUser, Group, LoginEvent, UserGroupMembership
from app.evaluation.baseline import EvaluationBaselineError, execute_evaluation_baseline
from app.evaluation.context import resolve_evaluation_identity
from app.evaluation.environment import evaluation_database_fingerprint
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.scoring import score_evaluation_semantic_contract
from app.evaluation.selection import evaluation_dataset_digest
from app.models.product import AccessScope
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.schema_context import build_schema_context
from app.query_engine.semantic_catalog import semantic_catalog_identity
from app.query_engine.semantic_conformance import check_semantic_conformance
from app.query_engine.semantic_grounding import build_semantic_grounding_projection
from app.query_engine.semantic_plan import SemanticFieldRef, SemanticLiteralFilter, SemanticPlanValidationError, validate_semantic_plan
from app.query_engine.sql_executor import execute_validated_sql, query_runtime_transaction
from app.query_engine.sql_renderer import SemanticSQLRenderError, render_validated_semantic_plan
from app.query_engine.sql_validator import validate_sql
from app.query_engine.structural_intent_adapters import validated_plan_to_structural_observation
from app.query_engine.structural_intent_comparison import StructuralComparisonPolicy, StructuralRequirement, compare_structural_requirement
from tests.action_postgres_test_db import validated_disposable_database_url
from tests.test_evaluation_semantic_corrections import compare, example


ROOT = Path(__file__).resolve().parents[3]
REFERENCE = "2026-11-01T09:20:36+00:00"


def digest(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def field(entity, column):
    return SemanticFieldRef(entity_id=entity, column=column)


def fixtures():
    for case_id, groupings in (
        ("itops-medium-006", [[("departments", "id")], [("departments", "name")], [("departments", "id"), ("departments", "name")]]),
        ("itops-hard-004", [[("login_events", "user_id")], [("directory_users", "id")]]),
        ("itops-hard-006", [None]),
    ):
        for index, grouping in enumerate(groupings):
            case, checked, _ = example(case_id, grouping=grouping)
            yield f"{case_id}_canonical_{index}", case, checked, checked.plan
    case, checked, _ = example("itops-medium-006", grouping=[("departments", "id")])
    key, name = field("departments", "id"), field("departments", "name")
    yield "medium006_hidden_dependent_name", case, checked, checked.plan.model_copy(update={"group_by": (key, name)})
    yield "medium006_name_projected_pk_grouped", case, checked, checked.plan.model_copy(update={"output_fields": (name,)})
    yield "medium006_all_group_keys_unprojected", case, checked, checked.plan.model_copy(update={"output_fields": ()})
    yield "medium006_extra_population_dimension", case, checked, checked.plan.model_copy(update={"output_fields": (key, field("directory_users", "account_status")), "group_by": (key, field("directory_users", "account_status"))})
    case, checked, _ = example("itops-hard-004", grouping=[("login_events", "user_id")])
    yield "hard004_hidden_equal_user_key", case, checked, checked.plan.model_copy(update={"group_by": (field("login_events", "user_id"), field("directory_users", "id"))})
    wrong_count = checked.plan.aggregations[0].model_copy(update={"distinct": False})
    yield "hard004_non_distinct_fanout", case, checked, checked.plan.model_copy(update={"aggregations": (wrong_count,)})
    yield "hard004_select_distinct_does_not_repair_fanout", case, checked, checked.plan.model_copy(update={"aggregations": (wrong_count,), "distinct": True})
    yield "hard004_missing_grouping", case, checked, checked.plan.model_copy(update={"group_by": ()})
    yield "hard004_outer_user_key", case, checked, checked.plan.model_copy(update={"relationships": tuple(r.model_copy(update={"join_type": "left"}) if r.relationship_id == "login_event_user" else r for r in checked.plan.relationships)})
    yield "hard004_outer_directory_key", case, checked, checked.plan.model_copy(update={"relationships": tuple(r.model_copy(update={"join_type": "left"}) if r.relationship_id == "login_event_user" else r for r in checked.plan.relationships), "output_fields": (field("directory_users", "id"),), "group_by": (field("directory_users", "id"),)})
    # The selected failed-login concept and known success literal are contradictory.
    impossible = SemanticLiteralFilter(field=field("login_events", "event_type"), operator="equals", value="success")
    yield "hard004_empty_grouped", case, checked, checked.plan.model_copy(update={"literal_filters": (impossible,)})
    yield "hard004_empty_scalar", case, checked, checked.plan.model_copy(update={"literal_filters": (impossible,), "output_fields": (), "group_by": (), "having": ()})
    case, checked, _ = example("itops-hard-006")
    yield "hard006_sum_distinct_unsupported", case, checked, checked.plan.model_copy(update={"aggregations": tuple(a.model_copy(update={"distinct": True}) for a in checked.plan.aggregations)})


def add_contrast_fixture(engine):
    """Deterministic six-versus-five events with two privileged memberships."""
    def key(value):
        return uuid5(NAMESPACE_URL, "queryops-w6a-algebra/" + value)
    with Session(engine) as db:
        assert db.get(DirectoryUser, key("user-0")) is None, "Contrast fixture already exists"
        case = load_it_operations_evaluation_v2_set().cases_by_id["itops-hard-004"]
        identity = resolve_evaluation_identity(db, case)
        scope = db.scalar(select(AccessScope).where(AccessScope.scope_type == "department", AccessScope.scope_key == identity.target_scope.scope_key))
        assert scope is not None
        now = datetime.fromisoformat(REFERENCE)
        groups = [Group(id=key(f"group-{i}"), name=f"w6a-algebra-{i}", group_type="security", department_id=scope.department_id, is_privileged=True, created_at=now, updated_at=now) for i in range(2)]
        users = [DirectoryUser(id=key(f"user-{i}"), employee_number=f"w6a-algebra-{i}", email=f"w6a-algebra-{i}@example.test", full_name="Synthetic algebra user", department_id=scope.department_id, created_at=now, updated_at=now) for i in range(2)]
        db.add_all([*groups, *users])
        db.flush()
        for index, (user, count) in enumerate(zip(users, (6, 5), strict=True)):
            db.add_all([UserGroupMembership(user_id=user.id, group_id=g.id, department_id=scope.department_id, added_at=now) for g in groups])
            db.add_all([LoginEvent(id=key(f"event-{index}-{i}"), user_id=user.id, department_id=scope.department_id, event_type="failed", occurred_at=now-timedelta(days=1)) for i in range(count)])
            db.add(LoginEvent(id=key(f"old-{index}"), user_id=user.id, department_id=scope.department_id, event_type="failed", occurred_at=now-timedelta(days=31)))
            db.add(LoginEvent(id=key(f"success-{index}"), user_id=user.id, department_id=scope.department_id, event_type="success", occurred_at=now))
        db.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--add-contrast-fixture", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads((Path(__file__).parent / "baseline.json").read_text())
    pack = load_it_operations_domain_pack()
    dataset = load_it_operations_evaluation_v2_set()
    assert evaluation_dataset_digest(dataset) == frozen["dataset"]["digest"]
    assert semantic_catalog_identity(pack.semantic_catalog) == frozen["catalog"]
    subprocess.run(["git", "diff", "--exit-code", frozen["source_commit"], "--",
                    *frozen["source_tree_paths"]], cwd=ROOT, check=True, capture_output=True)
    url = validated_disposable_database_url(os.environ["POSTGRES_TEST_DATABASE_URL"])
    endpoint = make_url(url)
    assert endpoint.host == "127.0.0.1" and endpoint.port == 55448
    assert endpoint.database == "queryops_w6a_algebra_test"
    if args.initialize:
        subprocess.run([str(ROOT / "backend/.venv/bin/alembic"), "upgrade", "head"], cwd=ROOT / "backend", env={**os.environ, "DATABASE_URL": url}, check=True)
    engine = create_engine(url)
    if args.initialize:
        with Session(engine) as db:
            summary = seed_database(db, profile_name="medium", reset=False, reference_now=datetime.fromisoformat(REFERENCE))
            assert summary.seed == 42
            db.commit()
    if args.add_contrast_fixture:
        add_contrast_fixture(engine)
    with Session(engine) as db:
        fingerprint, counts = evaluation_database_fingerprint(db)
        database = dict(db.execute(text("SELECT version() AS version, transaction_timestamp() AS transaction_time, current_setting('TimeZone') AS timezone, (SELECT version_num FROM alembic_version) AS migration_head")).mappings().one())
    results = []
    for probe_id, case, canonical, supplied in fixtures():
        result = {"probe_id": probe_id, "case_id": case.id, "plan_sha256": digest(supplied.model_dump(mode="json")), "source": "handwritten_exploratory_not_provider_output"}
        with Session(engine) as db:
            identity = resolve_evaluation_identity(db, case)
            schema = build_schema_context(db, identity.access_context, domain_pack=pack)
            projection = build_semantic_grounding_projection(pack.semantic_catalog, case.question, schema, {"scope_type": case.required_scope_type, "has_global_scope": case.scope_mode.value == "global", "scope_reference_resolved": True})
            try:
                checked = validate_semantic_plan(supplied, domain_pack=pack, projection=projection, schema_context=schema, scope_reference_resolved=True)
                result["plan_validation"] = {"valid": True, "reason": None}
            except SemanticPlanValidationError as exc:
                result["plan_validation"] = {"valid": False, "reason": exc.reason}
                checked = replace(canonical, plan=supplied)
            # Rejected shapes use an explicitly labelled SQL-only witness.
            result["downstream_is_sql_witness_only"] = not result["plan_validation"]["valid"]
            observation = checked.as_observation()
            result["semantic_contract_diagnostic"] = score_evaluation_semantic_contract(case, observation).as_safe_metrics()
            policy = StructuralComparisonPolicy(row_grain="exact", output_fields="exact", aggregations="exact", group_by="exact", having="exact", ordering="exact", distinct="exact")
            _, reference, _ = example(case.id)
            literal = compare_structural_requirement(StructuralRequirement(intent=validated_plan_to_structural_observation(reference), policy=policy, binding="required"), validated_plan_to_structural_observation(checked))
            result["literal_structural_vs_canonical"] = {"passed": literal.passed, "components": dict(literal.components), "authority": "opt_in_literal_diagnostic_not_evaluator"}
            try:
                sql = render_validated_semantic_plan(checked, pack)
            except SemanticSQLRenderError as exc:
                result["renderer"] = {"status": "failed", "safe_reason": exc.reason}
                results.append(result)
                continue
            result["renderer"] = {"status": "passed"}
            result["sql_sha256"] = digest(sql)
            safety = validate_sql(sql, schema)
            result["sql_safety"] = {"valid": safety.valid, "reason": safety.reason}
            conformance = check_semantic_conformance(plan=checked, candidate_sql=sql, safety_result=safety, domain_pack=pack, schema_context=schema)
            result["renderer_self_conformance"] = conformance.as_observation()
            result["conformance_vs_contract_canonical"] = check_semantic_conformance(plan=reference, candidate_sql=sql, safety_result=safety, domain_pack=pack, schema_context=schema).as_observation()
            if safety.valid:
                with query_runtime_transaction(engine, identity.access_context, isolation_level="repeatable_read") as connection:
                    result["runtime"] = dict(connection.execute(text("SELECT current_user AS role, current_setting('transaction_read_only') AS read_only, current_setting('transaction_isolation') AS isolation, current_setting('TimeZone') AS timezone, transaction_timestamp() AS transaction_time, pg_current_snapshot()::text AS snapshot")).mappings().one())
                    def executor(_db, access, validation, *, options=None):
                        return execute_validated_sql(connection, access, validation, options=options)
                    expected = execute_evaluation_baseline(db, identity.access_context, case, pack, executor=executor)
                    try:
                        actual = execute_evaluation_baseline(db, identity.access_context, replace(case, baseline_sql=sql), pack, executor=executor)
                        result["execution"] = {"status": "succeeded", "count": actual.row_count, "baseline_count": expected.row_count, "result_multiset_sha256": digest(sorted(json.dumps(r, sort_keys=True, default=str) for r in actual.rows)), "baseline_multiset_sha256": digest(sorted(json.dumps(r, sort_keys=True, default=str) for r in expected.rows)), "delivery_completeness": actual.execution.execution_metadata.get("delivery_completeness")}
                        assert actual.execution.execution_metadata.get("delivery_completeness") == "complete"
                        comparison = compare(case, sql, expected.rows, actual.rows)
                        result["result_only_comparison"] = {"passed": comparison.passed, "comparison_state": comparison.comparison_state.value, "semantic_pass_forced_for_isolation": True}
                    except EvaluationBaselineError as exc:
                        result["execution"] = {"status": "failed", "safe_code": exc.code}
            results.append(result)
    by_id = {r["probe_id"]: r for r in results}
    for result in results:
        if "runtime" in result:
            assert result["runtime"]["role"] == "queryops_query_runtime"
            assert result["runtime"]["read_only"] == "on"
            assert result["runtime"]["isolation"] == "repeatable read"
        if "_canonical_" in result["probe_id"]:
            assert result["plan_validation"]["valid"]
            assert result["renderer_self_conformance"]["status"] == "passed"
            assert result["semantic_contract_diagnostic"]["passed"]
            assert result["result_only_comparison"]["passed"]
        if result["plan_validation"]["valid"]:
            assert result["renderer_self_conformance"]["status"] == "passed"
    assert not by_id["medium006_hidden_dependent_name"]["plan_validation"]["valid"]
    assert by_id["medium006_hidden_dependent_name"]["result_only_comparison"]["passed"]
    assert by_id["hard004_hidden_equal_user_key"]["result_only_comparison"]["passed"]
    assert by_id["itops-hard-004_canonical_0"]["execution"]["count"] > 0, "Add the explicit contrast fixture for nonvacuous hard004 evidence"
    assert not by_id["hard004_non_distinct_fanout"]["result_only_comparison"]["passed"]
    assert not by_id["hard004_select_distinct_does_not_repair_fanout"]["result_only_comparison"]["passed"]
    assert by_id["hard004_empty_grouped"]["execution"]["count"] == 0
    assert by_id["hard004_empty_scalar"]["execution"]["count"] == 1
    report = {"schema": "queryops-w6a-algebra-v1", "provider_calls": 0, "model_behavior_tested": False, "held_out": False, "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "baseline_file_sha256": hashlib.sha256((ROOT / "docs/audits/w6a/baseline.json").read_bytes()).hexdigest(), "dataset_digest": evaluation_dataset_digest(dataset), "catalog": semantic_catalog_identity(pack.semantic_catalog), "seed": {"profile": "medium", "seed": 42, "reference_now": REFERENCE, "plain_medium_database_fingerprint": "8d027d94029ba0fd0e3a3eebcc99fec41b0084140df54a8834ea73560b0eb077", "contrast_fixture": {"users": 2, "privileged_groups": 2, "memberships_per_user": 2, "failed_events_per_user": [6, 5], "excluded_old_failed_per_user": 1, "excluded_success_per_user": 1}, "database_fingerprint": fingerprint, "table_counts": counts}, "database": database, "probes": results}
    report["sources"] = [{"id": source_id, "path": path, "lines": lines, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()} for source_id, path, lines in (
        ("F11-runtime", "backend/app/query_engine/semantic_plan.py", "435-451,460-473"),
        ("F11-renderer", "backend/app/query_engine/sql_renderer.py", "28-82,128-159,268-285"),
        ("F11-conformance", "backend/app/query_engine/semantic_conformance.py", "870-908"),
        ("F11-evaluator", "backend/app/evaluation/scoring.py", "147-197"),
        ("F11-identity", "backend/app/evaluation/identity.py", "1-118"),
        ("F11-literal", "backend/app/query_engine/structural_intent_comparison.py", "1-99"),
        ("F11-prompt", "backend/app/query_engine/openai_provider.py", "66-104"),
        ("F11-PG-counterexamples", "backend/tests/test_relational_semantics.py", "125-273"),
        ("F11-existing-corrections", "backend/tests/test_evaluation_semantic_corrections.py", "32-207"),
    )]
    report["commands"] = ["From backend with exact guarded disposable environment: PYTHONPATH=.:tests .venv/bin/python ../docs/audits/w6a/algebra_probe.py --initialize --add-contrast-fixture --out ../docs/audits/w6a/algebra-results.json (fresh EMPTY dedicated DB only)", "Read-only replay: PYTHONPATH=.:tests .venv/bin/python ../docs/audits/w6a/algebra_probe.py --out ../docs/audits/w6a/algebra-results.json", "PYTHONPATH=.:tests .venv/bin/pytest tests/test_relational_semantics.py -q -rs", ".venv/bin/ruff check ../docs/audits/w6a/algebra_probe.py", ".venv/bin/python -m py_compile ../docs/audits/w6a/algebra_probe.py"]
    args.out.write_text(json.dumps(report, default=str, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"probes": len(results), "provider_calls": 0, "output": str(args.out)}))
    engine.dispose()


if __name__ == "__main__":
    main()
