"""W6c v2 preparation defaults to no external network and never needs an API key.

Run as `python -m scripts.w6c_live --help` from backend. Live requires a merged
source, a matching fresh manifest, a separate explicit approval and a single-use
durable transport journal. This module is not a product or release-evaluation path.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import platform
import pwd
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
from openai import OpenAI
from openai.lib._parsing._responses import type_to_text_format_param
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth.access_context import build_user_access_context
from app.domains.it_operations.seed import seed_database
from app.evaluation.environment import evaluation_database_fingerprint
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.selection import evaluation_dataset_digest
from app.models.product import AppUser
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.openai_provider import (
    SYSTEM_INSTRUCTIONS, OpenAIProvider, _StructuredProviderOutput,
    build_safe_prompt_projection,
)
from app.query_engine.provider_config import (
    OFFICIAL_OPENAI_BASE_URL, installed_runtime_versions,
    load_provider_settings, provider_runtime_identity,
)
from app.query_engine.request_authorization import authorize_query_request
from app.query_engine.schema_context import build_schema_context
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_conformance import check_semantic_conformance
from app.query_engine.semantic_plan import SemanticPlan, validate_semantic_plan
from app.query_engine.sql_executor import execute_validated_sql, query_runtime_transaction
from app.query_engine.sql_renderer import render_validated_semantic_plan
from app.query_engine.sql_validator import validate_sql
from scripts.w6c_dispatch import DiagnosticStop, DispatchGuard, digest


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "docs/audits/w6c"
CONFIG = ARTIFACTS / "live-v2.json"
# The OS account home, not caller-controlled HOME, pins one ledger across clones.
STATE = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/queryops/w6c-live-v2"


def require(condition: Any, code: str) -> None:
    if not condition:
        raise DiagnosticStop(code)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity(*, merged: bool = False) -> str:
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, check=True,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    require(not git("status", "--porcelain"), "source_not_clean")
    revision = git("rev-parse", "HEAD")
    require(len(revision) == 40, "source_invalid")
    if merged:
        require(revision == git("rev-parse", "main") == git("rev-parse", "origin/main"),
                "merged_candidate_required")
    return revision


def frozen_inputs():
    config = json.loads(CONFIG.read_text())
    require(config["schema"] == "queryops-w6c-live-v2" and config["execution_authorized"] is False,
            "diagnostic_contract_invalid")
    require((config["max_logical_calls"], config["max_physical_dispatches"],
             config["max_dispatches_per_question"]) == (12, 12, 1), "budget_invalid")
    require(file_hash(ARTIFACTS / "freeze.json") == config["freeze_sha256"], "freeze_changed")
    require(file_hash(ARTIFACTS / "live-experiment-proposal.md") == config["original_proposal_sha256"],
            "historical_proposal_changed")
    lock = json.loads((ARTIFACTS / "freeze.json").read_text())
    # Verify executable artifacts BEFORE importing or opening a database.
    for name, expected in lock["files"].items():
        require(file_hash(ARTIFACTS / name) == expected, "frozen_input_changed")
    corpus = json.loads((ARTIFACTS / "heldout-v1.json").read_text())
    by_id = {case["id"]: case for case in corpus["cases"]}
    cases = [by_id[row["id"]] for row in config["cases"]]
    require(len(cases) == len({c["id"] for c in cases}) == 12, "case_selection_invalid")
    require(config["cases"][7]["id"] == "W6C-007" and "W6C-010" not in [c["id"] for c in cases],
            "case_selection_invalid")
    for case, row in zip(cases, config["cases"], strict=True):
        require(hashlib.sha256(case["question"].encode()).hexdigest() == row["question_sha256"],
                "question_changed")
        require(case["question"] == case["question"].strip(), "question_normalization_changed")
    pack = load_it_operations_domain_pack()
    require(pack.semantic_catalog.digest == lock["catalog_digest"], "catalog_changed")
    require(evaluation_dataset_digest(load_it_operations_evaluation_v2_set()) == lock["dataset_digest"],
            "v2_dataset_changed")
    return config, lock, cases, pack


def artifact_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location("w6c_frozen_" + name, ARTIFACTS / (name + ".py"))
    if spec is None or spec.loader is None:
        raise DiagnosticStop("artifact_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def diagnostic_settings(config, *, live: bool = False):
    values = dict(os.environ)
    if live:
        require(values.get("LLM_PROVIDER") == "openai", "live_provider_not_selected")
        require(all(values.get(k) == v for k, v in config["settings"].items()), "live_settings_mismatch")
    else:
        # Identity-only configuration is not a credential and cannot dispatch.
        values.update(config["settings"], OPENAI_API_KEY="preflight-not-a-credential")
    settings = load_provider_settings(values, provider_override="openai")
    require(settings.openai is not None and settings.openai.max_retries == 0, "diagnostic_retries_invalid")
    return settings


def disposable_url() -> str:
    url = os.environ.get("POSTGRES_TEST_DATABASE_URL", "")
    require(os.environ.get("POSTGRES_TEST_DATABASE_DISPOSABLE") == "1", "disposable_database_required")
    parsed = make_url(url)
    require(parsed.drivername == "postgresql+psycopg" and parsed.host in {"localhost", "127.0.0.1"}
            and parsed.database == "queryops_w6c_v2_test" and not parsed.query,
            "disposable_database_identity_invalid")
    # No alias of the configured application DB may be used for initialization.
    app = make_url(os.environ.get("DATABASE_URL", "postgresql://localhost/queryops"))
    require(not app.query and app.database != parsed.database
            and os.environ.get("POSTGRES_DB", "queryops") != parsed.database,
            "application_database_forbidden")
    return url


def fresh_reference(raw: str) -> datetime:
    reference = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    require(reference.tzinfo is not None, "reference_invalid")
    reference = reference.astimezone(UTC)
    age = datetime.now(UTC) - reference
    require(-timedelta(minutes=5) <= age <= timedelta(hours=24), "reference_stale")
    return reference


def initialize(url: str, reference: datetime) -> None:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            require(connection.scalar(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")) == 0,
                    "database_not_empty")
    finally:
        engine.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend",
                   env={**os.environ, "DATABASE_URL": url}, check=True, capture_output=True)
    engine = create_engine(url)
    try:
        with Session(engine) as db:
            seed_database(db, profile_name="small", reset=False, reference_now=reference)
            add_fresh_contrasts(db, reference)
            db.commit()
    finally:
        engine.dispose()


def add_fresh_contrasts(db: Session, reference: datetime):
    fixture = artifact_module("fixture")
    # v2 adapter only: frozen relative ages and omitted server timestamps use
    # the approved fresh reference, making the entire fingerprint reproducible.
    fixture.REFERENCE = reference
    def anchor(session, *_):
        for row in session.new:
            for name in ("created_at", "updated_at"):
                if hasattr(row, name) and getattr(row, name) is None:
                    setattr(row, name, reference)
    event.listen(db, "before_flush", anchor)
    try:
        fixture.add_contrasts(db)
    finally:
        event.remove(db, "before_flush", anchor)


def witnesses_by_id():
    witnesses = {w["case_id"]: w for w in artifact_module("witnesses").witnesses()}
    # F1 changes only the formerly unavailable witness encoding, not its oracle.
    witness = copy.deepcopy(witnesses["W6C-007"])
    for relationship in witness["plan"]["relationships"]:
        if relationship["relationship_id"] in {"user_group_membership_user", "security_event_user"}:
            relationship["join_type"] = "left_reverse"
    witnesses["W6C-007"] = witness
    return witnesses


def context(db, case, pack):
    require(case["context"] == "CTX_VISIBLE_ASSIGNED", "context_unsupported")
    actor = db.scalar(select(AppUser).where(AppUser.email == "demo.analyst@queryops.local"))
    require(actor is not None, "actor_unavailable")
    access = build_user_access_context(actor, db)
    gate = authorize_query_request(access, pack, template_id=None)
    require(gate.allowed and not access.has_global_scope and access.default_scope is not None,
            "request_not_authorized")
    assert access.default_scope is not None
    user = {"scope_type": access.default_scope.type, "has_global_scope": False,
            "scope_reference_resolved": True}
    schema = build_schema_context(db, access, domain_pack=pack)
    projection = build_semantic_catalog_projection(pack.semantic_catalog, case["question"], schema, user)
    require(len(json.dumps(projection.as_prompt_dict(), sort_keys=True, separators=(",", ":")).encode()) <= 16000
            and projection.grounded_result_intent is None, "projection_invalid")
    expected = case["candidate_expectations"]
    for key, attr in (("entity_ids", "entities"), ("concept_ids", "concepts"),
                      ("relationship_ids", "relationships"), ("composition_rule_ids", "composition_rules")):
        require(set(expected[key]) <= {i["id"] for i in getattr(projection, attr)}, "candidate_missing")
    prompt = build_safe_prompt_projection(case["question"], schema, user, projection)
    encoded = json.dumps(prompt, sort_keys=True, separators=(",", ":"))
    private = [str(access.user_id), *(str(s.department_id) for s in access.scopes if s.department_id)]
    require(all(value not in encoded for value in private) and "it_audit_events" not in encoded,
            "prompt_disclosure")
    return access, schema, user, projection, prompt


def request_body(settings, prompt):
    return {"model": settings.model, "instructions": SYSTEM_INSTRUCTIONS,
            "input": json.dumps(prompt, sort_keys=True, separators=(",", ":")),
            "text": {"format": type_to_text_format_param(_StructuredProviderOutput)},
            "reasoning": {"effort": settings.reasoning_effort},
            "max_output_tokens": settings.max_output_tokens, "store": False}


def checked_sql(plan, pack, projection, schema):
    checked = validate_semantic_plan(plan, domain_pack=pack, projection=projection,
                                    schema_context=schema, scope_reference_resolved=True)
    sql = render_validated_semantic_plan(checked, pack)
    safety = validate_sql(sql, schema)
    require(safety.valid, "sql_safety_failure")
    conform = check_semantic_conformance(plan=checked, candidate_sql=sql,
        safety_result=safety, domain_pack=pack, schema_context=schema)
    require(conform.valid, "semantic_conformance_failure")
    return safety, checked.plan


def runtime_policy_identity(db):
    role = db.execute(text("SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolbypassrls FROM pg_roles WHERE rolname='queryops_query_runtime'" )).one_or_none()
    require(role is not None and not any(role), "query_runtime_role_invalid")
    assert role is not None
    tables = db.execute(text("SELECT c.relname, c.relrowsecurity, r.rolname, c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname")).all()
    require(all(r[2] != "queryops_query_runtime" for r in tables), "query_runtime_owns_table")
    policies = db.execute(text("SELECT tablename, policyname, roles::text, cmd, qual, with_check FROM pg_policies WHERE schemaname='public' ORDER BY tablename, policyname")).all()
    grants = db.execute(text("SELECT r.rolname, m.rolname, a.admin_option, a.inherit_option, a.set_option FROM pg_auth_members a JOIN pg_roles r ON r.oid=a.roleid JOIN pg_roles m ON m.oid=a.member ORDER BY r.rolname, m.rolname")).all()
    return digest({"role": list(role), "tables": [list(r) for r in tables],
                   "policies": [list(r) for r in policies], "memberships": [list(r) for r in grants]})


def oracle_comparison(runtime, access, schema, plan, witness, pack, projection):
    require(runtime.execute(text("SELECT current_user, current_setting('transaction_read_only'), current_setting('transaction_isolation'), current_setting('TimeZone')")).one() ==
            ("queryops_query_runtime", "on", "repeatable read", "UTC"), "runtime_boundary_invalid")
    safety, normalized = checked_sql(plan, pack, projection, schema)
    baseline = validate_sql(witness["oracle_sql"], schema)
    require(baseline.valid, "oracle_sql_invalid")
    before = runtime.scalar(text("SELECT pg_current_snapshot()::text"))
    expected = execute_validated_sql(runtime, access, baseline)
    actual = execute_validated_sql(runtime, access, safety)
    require(all(r.status == "succeeded" and not r.truncated
                and r.execution_metadata.get("delivery_completeness") == "complete"
                for r in (expected, actual)), "execution_incomplete")
    require(runtime.scalar(text("SELECT pg_current_snapshot()::text")) == before, "snapshot_changed")
    canonical = SemanticPlan.model_validate_json(json.dumps(witness["plan"]))
    def field_key(field):
        return field.entity_id, field.column
    def aggregate_key(aggregation):
        return (aggregation.function, field_key(aggregation.field) if aggregation.field else None,
                aggregation.distinct)
    output_ok = (sorted(plan.output_fields, key=field_key) == sorted(canonical.output_fields, key=field_key)
                 and sorted(map(aggregate_key, plan.aggregations), key=repr) == sorted(map(aggregate_key, canonical.aggregations), key=repr)
                 and plan.distinct == canonical.distinct and plan.metric_id == canonical.metric_id
                 and sorted(plan.group_by, key=field_key) == sorted(canonical.group_by, key=field_key)
                 and plan.having == canonical.having and plan.limit == canonical.limit)
    # The independent oracle SELECT follows the original witness order; plan
    # normalization may sort fields. Align by semantic identity, never values.
    def identities(value):
        return ["field:" + f["entity_id"] + ":" + f["column"] for f in value["output_fields"]] + [
            "aggregation:" + digest({k: a[k] for k in ("function", "field", "distinct")})
            for a in value["aggregations"]]
    def rows(result, keys):
        require(len(result.columns) == len(keys), "output_shape_mismatch")
        return sorted(json.dumps(dict(zip(keys, r.values(), strict=True)), default=str, sort_keys=True)
                      for r in result.rows)
    result = {"oracle_equal": output_ok and rows(expected, identities(witness["plan"])) == rows(
                actual, identities(normalized.model_dump(mode="json"))),
            "oracle_complete": True, "same_read_only_snapshot": True}
    if witness["case_id"] == "W6C-007":
        fixture = artifact_module("fixture")
        visible = {str(v) for row in actual.rows for v in row.values()}
        result["both_optional_arms_preserved"] = all(str(fixture.key("IT/" + arm)) in visible
                                                    for arm in ("group-only", "event-only"))
        joins = {r.relationship_id: r.join_type for r in plan.relationships}
        result["left_reverse_selected"] = joins == {"user_group_membership_user": "left_reverse",
            "security_event_user": "left_reverse", "user_group_membership_group": "left"}
        result["independent_where_restriction"] = all(f in plan.literal_filters for f in canonical.literal_filters)
        result["optional_or_rule_selected"] = "disablement_policy_review" in plan.composition_rule_ids
    return result


def prepare(reference_text: str, *, initialize_database: bool = False):
    source = source_identity()
    config, lock, cases, pack = frozen_inputs()
    settings = diagnostic_settings(config)
    reference = fresh_reference(reference_text)
    url = disposable_url()
    if initialize_database:
        initialize(url, reference)
    witnesses = witnesses_by_id()
    engine = create_engine(url)
    records = []
    try:
        with Session(engine) as db:
            seeded_at = db.scalar(select(AppUser.created_at).where(AppUser.email == "demo.analyst@queryops.local"))
            require(seeded_at == reference, "seed_reference_mismatch")
            fingerprint, counts = evaluation_database_fingerprint(db)
            policy_identity = runtime_policy_identity(db)
            database = dict(db.execute(text("SELECT current_database() AS name, current_setting('server_version') AS postgres, (SELECT version_num FROM alembic_version) AS migration")).mappings().one())
            from alembic.config import Config
            from alembic.script import ScriptDirectory
            alembic = Config(str(ROOT / "backend/alembic.ini"))
            alembic.set_main_option("script_location", str(ROOT / "backend/alembic"))
            require(database["migration"] == ScriptDirectory.from_config(alembic).get_current_head(), "migration_mismatch")
            for case in cases:
                access, schema, user, projection, prompt = context(db, case, pack)
                record = {"case_id": case["id"], "schema_sha256": digest(schema),
                          "prompt_sha256": digest(prompt), "projection_sha256": digest(projection.as_prompt_dict()),
                          "body_sha256": digest(request_body(settings.openai, prompt))}
                if case["id"] in witnesses:
                    plan = SemanticPlan.model_validate_json(json.dumps(witnesses[case["id"]]["plan"]))
                    with query_runtime_transaction(engine, access, isolation_level="repeatable_read", timezone_name="UTC") as runtime:
                        result = oracle_comparison(runtime, access, schema, plan, witnesses[case["id"]], pack, projection)
                    require(result["oracle_equal"], "manual_witness_oracle_mismatch_" + case["id"])
                    require(all(result.values()), "manual_witness_contract_mismatch_" + case["id"])
                    record.update(result)
                else:
                    record["expected_outcome"] = "clarification"
                records.append(record)
        manifest = {"schema": "queryops-w6c-preflight-v2", "source_git_sha": source,
            "config_sha256": file_hash(CONFIG), "settings": config["settings"],
            "question_identities": config["cases"], "dataset_digest": lock["dataset_digest"],
            "catalog_digest": lock["catalog_digest"], "reference_time": reference.isoformat(),
            "database_fingerprint": fingerprint, "table_counts": counts,
            "runtime_policy_sha256": policy_identity,
            "database": database, "runtime_versions": installed_runtime_versions(),
            "python": platform.python_version(), "provider_runtime": provider_runtime_identity(settings),
            "dependency_manifest_sha256": file_hash(ROOT / "backend/pyproject.toml"),
            "cases": records, "logical_calls": 0, "physical_dispatches": 0,
            "provider_interpretation": "unmeasured", "execution_authorized": False}
        manifest["fingerprint"] = digest(manifest)
        return manifest
    finally:
        engine.dispose()


def verify_approval(approval, manifest) -> None:
    expected = {"schema": "queryops-w6c-operator-approval-v2",
        "approved": True, "fingerprint": manifest["fingerprint"],
        "source_git_sha": manifest["source_git_sha"], "model": manifest["settings"]["OPENAI_MODEL"],
        "max_logical_calls": 12, "max_physical_dispatches": 12,
        "max_dispatches_per_question": 1, "no_retry_no_resume": True}
    require(isinstance(approval, dict) and approval == expected
            and all(type(approval[k]) is type(value) for k, value in expected.items()),
            "operator_approval_missing_or_mismatched")


def fake_response(plan):
    output = {"outcome": "clarification" if plan is None else "plan", "semantic_plan": plan,
              "clarification_reason": "unsupported_request" if plan is None else None}
    return {"id": "in-process", "object": "response", "created_at": 0, "status": "completed",
        "model": "gpt-6.1-terra", "output": [{"id": "in-process", "type": "message",
        "role": "assistant", "status": "completed", "content": [{"type": "output_text",
        "annotations": [], "text": json.dumps(output)}]}],
        "usage": {"input_tokens": 1, "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens": 1, "total_tokens": 2}}


def execute(manifest, *, approval=None, dry_run: bool = True):
    # Recompute all inputs, authorization and read-only oracles immediately before
    # constructing any HTTP client. Never trust a caller-supplied manifest alone.
    current = prepare(manifest["reference_time"])
    require(current == manifest, "preflight_identity_changed")
    config, _, cases, pack = frozen_inputs()
    witnesses = witnesses_by_id()
    settings = diagnostic_settings(config, live=not dry_run)
    openai_settings = settings.openai
    assert openai_settings is not None
    if not dry_run:
        source_identity(merged=True)
        verify_approval(approval, manifest)
    url = disposable_url()
    results = []
    temporary = tempfile.TemporaryDirectory(prefix="queryops-w6c-dry-") if dry_run else None
    if dry_run:
        assert temporary is not None
        journal = Path(temporary.name) / "journal.jsonl"
        plans = [witnesses.get(case["id"], {}).get("plan") for case in cases]
        index = iter(plans)
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=fake_response(next(index))))
    else:
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        journal = STATE / "dispatch.jsonl"  # Fixed across source revisions/clones/restarts.
        transport = httpx.HTTPTransport(retries=0, trust_env=False)
    def before_dispatch(case_id):
        require(source_identity() == manifest["source_git_sha"], "source_changed")
        fresh_reference(manifest["reference_time"])
        current_settings = diagnostic_settings(config, live=not dry_run)
        require(current_settings.openai is not None and current_settings.openai.api_key == openai_settings.api_key,
                "credentials_changed")
        require(provider_runtime_identity(current_settings)
                == manifest["provider_runtime"], "runtime_changed")
        with Session(engine) as db:
            require(evaluation_database_fingerprint(db)[0] == manifest["database_fingerprint"], "database_changed")
            require(runtime_policy_identity(db) == manifest["runtime_policy_sha256"], "runtime_policy_changed")
            case = next(c for c in cases if c["id"] == case_id)
            _, _, _, _, prompt = context(db, case, pack)
            require(digest(request_body(openai_settings, prompt)) == next(
                c["body_sha256"] for c in manifest["cases"] if c["case_id"] == case_id), "authorization_changed")

    engine = create_engine(url)
    guard = DispatchGuard(transport, journal, manifest["fingerprint"],
                          copy.deepcopy(manifest["cases"]), openai_settings.api_key,
                          before_dispatch=before_dispatch)
    client = OpenAI(api_key=openai_settings.api_key, admin_api_key="", organization="", project="",
        webhook_secret="", base_url=OFFICIAL_OPENAI_BASE_URL, max_retries=0,
        timeout=openai_settings.timeout_seconds,
        http_client=httpx.Client(transport=guard, timeout=openai_settings.timeout_seconds,
                                 follow_redirects=False, trust_env=False))
    provider = OpenAIProvider(openai_settings, client=cast(Any, client))
    try:
        for case, frozen in zip(cases, manifest["cases"], strict=True):
            with Session(engine) as db:
                access, schema, user, projection, prompt = context(db, case, pack)
                require(digest(request_body(openai_settings, prompt)) == frozen["body_sha256"],
                        "case_context_changed")
                guard.begin(case["id"])
                result = provider.generate_plan(case["question"], schema, user, {"semantic_catalog": projection})
                record = {"case_id": case["id"], "outcome": result.outcome.value}
                if result.semantic_plan is not None:
                    witness = witnesses.get(case["id"])
                    # A plan for an unanswerable question is a semantic failure;
                    # it still must satisfy every safety check before continuing.
                    checked_sql(result.semantic_plan, pack, projection, schema)
                    if witness:
                        with query_runtime_transaction(engine, access, isolation_level="repeatable_read", timezone_name="UTC") as runtime:
                            record.update(oracle_comparison(runtime, access, schema, result.semantic_plan, witness, pack, projection))
                    else:
                        record["semantic_match"] = False
                else:
                    record["semantic_match"] = case["id"] in {"W6C-002", "W6C-003"} and result.clarification_required
                # Persist safe semantic evidence before the next question. A
                # later fatal failure cannot erase earlier non-repeatable work.
                guard.finish(record)
                results.append(record)
        return {"schema": "queryops-w6c-diagnostic-result-v2", "fingerprint": manifest["fingerprint"],
            "mode": "in_process_manual_witnesses" if dry_run else "live_diagnostic",
            "provider_interpretation": "unmeasured" if dry_run else "diagnostic_only",
            "logical_calls": guard.logical_calls, "physical_dispatches": guard.physical_dispatches,
            "measurements": guard.records, "cases": results}
    except BaseException as exc:
        guard.stopped = True
        # Safe durable counters survive every exception; no raw provider content.
        guard._write({"event": "sequence_failed", "logical_calls": guard.logical_calls,
                      "physical_dispatches": guard.physical_dispatches,
                      "failure": exc.code if isinstance(exc, DiagnosticStop) else "provider_or_security_failure"})
        raise
    finally:
        client.close()
        engine.dispose()
        if temporary is not None:
            temporary.cleanup()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true", help="seed an EMPTY guarded disposable DB only")
    parser.add_argument("--reference-time", help="fresh UTC reference for preparation")
    parser.add_argument("--manifest", type=Path, help="existing preflight manifest")
    parser.add_argument("--out", type=Path, required=True, help="new local output file; never committed")
    parser.add_argument("--dry-run", action="store_true", help="real SDK + in-process transport, no external network")
    parser.add_argument("--live", action="store_true", help="DISABLED without separate matching operator approval")
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args(argv)
    try:
        require(not args.out.exists() and not args.out.resolve().is_relative_to(ROOT), "output_must_be_new_external_file")
        require(not (args.live and args.dry_run), "mode_conflict")
        require(not args.live or (args.approval is not None and args.manifest is not None and not args.initialize),
                "explicit_approval_required")
        if args.manifest:
            manifest = json.loads(args.manifest.read_text())
        else:
            require(bool(args.reference_time), "reference_required")
            manifest = prepare(args.reference_time, initialize_database=args.initialize)
        if args.live or args.dry_run:
            approval = json.loads(args.approval.read_text()) if args.approval else None
            output = execute(manifest, approval=approval, dry_run=not args.live)
        else:
            require(prepare(manifest["reference_time"]) == manifest, "preflight_identity_changed")
            output = manifest
        with args.out.open("x", encoding="utf-8") as file:
            json.dump(output, file, sort_keys=True, indent=2)
            file.write("\n")
        print(json.dumps({"status": "passed", "logical_calls": output["logical_calls"],
                          "physical_dispatches": output["physical_dispatches"]}))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        code = exc.code if isinstance(exc, DiagnosticStop) else "preflight_or_provider_failure"
        print(f"W6c stopped: {code}; no retry or resume is permitted. Inspect the local safe journal.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
