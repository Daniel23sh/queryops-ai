"""W6c v3 six-case diagnostic. Preparation/dry-run never touch live journals.

Live is disabled without a separate exact approval for a fresh clean merged main.
Shared frozen-input, authorization, SQL/oracle and SDK helpers retain v2 behavior.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

import httpx
from openai import OpenAI
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.evaluation.environment import evaluation_database_fingerprint
from app.models.product import AppUser
from app.query_engine.openai_provider import OpenAIProvider, ProviderFailure, ProviderFailureCode
from app.query_engine.provider_config import OFFICIAL_OPENAI_BASE_URL, installed_runtime_versions, provider_runtime_identity
from app.query_engine.semantic_plan import SemanticPlan
from app.query_engine.sql_executor import query_runtime_transaction
from scripts import w6c_live as v2
from scripts.w6c_dispatch import DiagnosticStop, DispatchGuard, digest
from scripts.w6c_live import (
    ROOT, ARTIFACTS, checked_sql, context, diagnostic_settings, file_hash,
    fresh_reference, initialize, oracle_comparison, request_body, require,
    source_identity, witnesses_by_id, fake_response,
)

CONFIG = ARTIFACTS / "live-v3.json"
STATE = v2.STATE.with_name("w6c-live-v3")
CASE_IDS = ("W6C-008", "W6C-011", "W6C-012", "W6C-013", "W6C-020", "W6C-007")


class V3DispatchGuard(DispatchGuard):
    max_calls = 6

    def __init__(self, transport, journal, fingerprint, requests, api_key, before_dispatch=None):
        require(tuple(r["case_id"] for r in requests) == CASE_IDS, "v3_case_order_invalid")
        super().__init__(transport, journal, fingerprint, requests, api_key, before_dispatch)


def frozen_inputs():
    historical, lock, original, pack = v2.frozen_inputs()
    config = json.loads(CONFIG.read_text())
    expected = {**historical, "schema": "queryops-w6c-live-v3", "max_logical_calls": 6,
                "max_physical_dispatches": 6,
                "cases": [next(c for c in historical["cases"] if c["id"] == i) for i in CASE_IDS],
                "acceptance": {k: v for k, v in historical["acceptance"].items()
                               if k not in {"W6C-002", "W6C-003"}}}
    require(config == expected and digest(config) == digest(expected), "v3_contract_invalid")
    cases = [next(c for c in original if c["id"] == i) for i in CASE_IDS]
    return config, lock, cases, pack


def disposable_url():
    from sqlalchemy.engine import make_url
    url = os.environ.get("POSTGRES_TEST_DATABASE_URL", "")
    require(os.environ.get("POSTGRES_TEST_DATABASE_DISPOSABLE") == "1", "disposable_database_required")
    parsed = make_url(url)
    require(parsed.drivername == "postgresql+psycopg" and parsed.host in {"localhost", "127.0.0.1"}
            and parsed.database == "queryops_w6c_v3_test" and not parsed.query,
            "disposable_database_identity_invalid")
    app = make_url(os.environ.get("DATABASE_URL", "postgresql://localhost/queryops"))
    require(not app.query and app.database != parsed.database
            and os.environ.get("POSTGRES_DB", "queryops") != parsed.database,
            "application_database_forbidden")
    return url


def artifact_path(path):
    resolved = path.resolve()
    require(not resolved.is_relative_to(ROOT)
            and not any(resolved.is_relative_to(p.resolve()) for p in (STATE, v2.STATE)),
            "artifact_path_forbidden")


def live_journal():
    # Trusted local operator, not a defense against that account deleting state.
    for directory in reversed((STATE, *STATE.parents)):
        if not directory.exists():
            directory.mkdir(mode=0o700)
            parent = os.open(directory.parent, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        info = directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                and info.st_uid in {0, os.getuid()} and not info.st_mode & 0o022,
                "journal_directory_unsafe")
    require(STATE.stat().st_uid == os.getuid() and stat.S_IMODE(STATE.stat().st_mode) == 0o700,
            "journal_owner_invalid")
    return STATE / "dispatch.jsonl"


def read_approval(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600, "approval_file_invalid")
    return json.loads(path.read_text())


def verify_approval(approval, manifest):
    expected = {"schema": "queryops-w6c-operator-approval-v3", "approved": True,
        "fingerprint": manifest["fingerprint"], "source_git_sha": manifest["source_git_sha"],
        "model": manifest["settings"]["OPENAI_MODEL"], "max_logical_calls": 6,
        "max_physical_dispatches": 6, "max_dispatches_per_question": 1, "no_retry_no_resume": True}
    require(isinstance(approval, dict) and approval == expected
            and all(type(approval[k]) is type(value) for k, value in expected.items()),
            "operator_approval_missing_or_mismatched")


def safe_failure(exc, guard):
    if isinstance(exc, KeyboardInterrupt):
        return "interrupted"
    if guard.records and guard.records[-1]["failure"] is not None:
        return "dispatch_failed"  # The durable transport record owns its bounded cause.
    if isinstance(exc, DiagnosticStop) and exc.code in {
        "sql_safety_failure", "semantic_conformance_failure", "runtime_boundary_invalid",
        "oracle_sql_invalid", "execution_incomplete", "snapshot_changed", "output_shape_mismatch",
    }:
        return exc.code
    if isinstance(exc, ProviderFailure) and exc.code in {c.value for c in ProviderFailureCode}:
        return exc.code
    return "diagnostic_failed"


def runtime_policy_identity(db):
    identity = v2.runtime_policy_identity(db)
    # Check effective privileges as well as fingerprinting ACL/policy definitions.
    role = db.execute(text("SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolbypassrls FROM pg_roles WHERE rolname='queryops_action_runtime'")).one_or_none()
    require(role is not None and not any(role), "action_runtime_role_invalid")
    tables = db.execute(text("SELECT c.oid, c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r'")).all()
    domain_tables = v2.load_it_operations_domain_pack().tables_by_name
    for oid, name, rls in tables:
        writable = db.scalar(text("SELECT has_table_privilege('queryops_query_runtime', :oid, 'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR has_any_column_privilege('queryops_query_runtime', :oid, 'INSERT,UPDATE,REFERENCES')"), {"oid": oid})
        require(not writable, "query_runtime_write_grant")
        readable = db.scalar(text("SELECT has_table_privilege('queryops_query_runtime', :oid, 'SELECT') OR has_any_column_privilege('queryops_query_runtime', :oid, 'SELECT')"), {"oid": oid})
        require(not readable or (name in domain_tables and domain_tables[name].queryable
                and (domain_tables[name].scope_type is None or rls)), "query_runtime_rls_missing")
    require(not db.scalar(text("SELECT has_schema_privilege('queryops_query_runtime', 'public', 'CREATE')")), "query_runtime_schema_write")
    assert role is not None
    columns = db.execute(text("SELECT c.relname, a.attnum, a.attname, a.attacl::text FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped AND cardinality(a.attacl)>0 ORDER BY c.relname, a.attnum")).all()
    schema = db.execute(text("SELECT nspname, nspowner::regrole::text, nspacl::text FROM pg_namespace WHERE nspname='public'")).one()
    return digest({"policy": identity, "action_role": list(role),
                   "column_grants": [list(r) for r in columns], "schema_grants": list(schema)})


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
                require(case["id"] in witnesses, "independent_witness_missing")
                if case["id"] in witnesses:
                    plan = SemanticPlan.model_validate_json(json.dumps(witnesses[case["id"]]["plan"]))
                    with query_runtime_transaction(engine, access, isolation_level="repeatable_read", timezone_name="UTC") as runtime:
                        result = oracle_comparison(runtime, access, schema, plan, witnesses[case["id"]], pack, projection)
                    require(result["oracle_equal"], "manual_witness_oracle_mismatch_" + case["id"])
                    require(all(value is True for value in result.values()), "manual_witness_contract_mismatch_" + case["id"])
                    record.update(result)
                records.append(record)
        manifest = {"schema": "queryops-w6c-preflight-v3", "source_git_sha": source,
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
        journal = live_journal()
        transport = httpx.HTTPTransport(retries=0, trust_env=False)
    def before_dispatch(case_id):
        require(source_identity() == manifest["source_git_sha"], "source_changed")
        fresh_reference(manifest["reference_time"])
        require(file_hash(CONFIG) == manifest["config_sha256"], "configuration_changed")
        frozen_inputs()
        current_settings = diagnostic_settings(config, live=not dry_run)
        require(current_settings.openai is not None and current_settings.openai.api_key == openai_settings.api_key,
                "credentials_changed")
        require(provider_runtime_identity(current_settings)
                == manifest["provider_runtime"], "runtime_changed")
        require(installed_runtime_versions() == manifest["runtime_versions"], "dependencies_changed")
        with Session(engine) as db:
            require(evaluation_database_fingerprint(db)[0] == manifest["database_fingerprint"], "database_changed")
            require(runtime_policy_identity(db) == manifest["runtime_policy_sha256"], "runtime_policy_changed")
            case = next(c for c in cases if c["id"] == case_id)
            _, _, _, _, prompt = context(db, case, pack)
            require(digest(request_body(openai_settings, prompt)) == next(
                c["body_sha256"] for c in manifest["cases"] if c["case_id"] == case_id), "authorization_changed")

    engine = create_engine(url)
    guard = V3DispatchGuard(transport, journal, manifest["fingerprint"],
                          copy.deepcopy(manifest["cases"]), openai_settings.api_key,
                          before_dispatch=before_dispatch)
    client = None
    stage = "client_setup"
    try:
        client = OpenAI(api_key=openai_settings.api_key, admin_api_key="", organization="", project="",
            webhook_secret="", base_url=OFFICIAL_OPENAI_BASE_URL, max_retries=0,
            timeout=openai_settings.timeout_seconds,
            http_client=httpx.Client(transport=guard, timeout=openai_settings.timeout_seconds,
                                     follow_redirects=False, trust_env=False))
        provider = OpenAIProvider(openai_settings, client=cast(Any, client))
        for case, frozen in zip(cases, manifest["cases"], strict=True):
            stage = "case_authorization"
            with Session(engine) as db:
                access, schema, user, projection, prompt = context(db, case, pack)
                require(digest(request_body(openai_settings, prompt)) == frozen["body_sha256"],
                        "case_context_changed")
                stage = "logical_reservation"
                guard.begin(case["id"])
                stage = "sdk_parse"
                result = provider.generate_plan(case["question"], schema, user, {"semantic_catalog": projection})
                record = {"case_id": case["id"], "outcome": result.outcome.value}
                if result.semantic_plan is not None:
                    witness = witnesses.get(case["id"])
                    stage = "plan_safety"
                    checked_sql(result.semantic_plan, pack, projection, schema)
                    if witness:
                        stage = "oracle_comparison"
                        with query_runtime_transaction(engine, access, isolation_level="repeatable_read", timezone_name="UTC") as runtime:
                            record.update(oracle_comparison(runtime, access, schema, result.semantic_plan, witness, pack, projection))
                    else:
                        record["semantic_match"] = False
                else:
                    record.update(semantic_match=False, output_contract_match=False,
                                  result_multiset_match="not_evaluated")
                # Persist safe semantic evidence before the next question. A
                # later fatal failure cannot erase earlier non-repeatable work.
                stage = "evidence_write"
                guard.finish(record)
                results.append(record)
        require(guard.logical_calls == guard.physical_dispatches == 6, "sequence_incomplete")
        guard._write({"event": "sequence_completed", "logical_calls": 6, "physical_dispatches": 6})
        return {"schema": "queryops-w6c-diagnostic-result-v3", "fingerprint": manifest["fingerprint"],
            "mode": "in_process_manual_witnesses" if dry_run else "live_diagnostic",
            "provider_interpretation": "unmeasured" if dry_run else "diagnostic_only",
            "logical_calls": guard.logical_calls, "physical_dispatches": guard.physical_dispatches,
            "measurements": guard.records, "cases": results}
    except BaseException as exc:
        guard.stopped = True
        # Safe durable counters survive every exception; no raw provider content.
        guard._write({"event": "sequence_failed", "logical_calls": guard.logical_calls,
                      "physical_dispatches": guard.physical_dispatches,
                      "failure_stage": ("http_boundary" if guard.records and guard.records[-1]["failure"]
                                        else "dispatch_revalidation" if stage == "sdk_parse" and guard.stopped
                                             and guard.physical_dispatches < guard.logical_calls else stage),
                      "failure": safe_failure(exc, guard)})
        raise
    finally:
        if client is not None:
            client.close()
        else:
            guard.close()
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
        artifact_path(args.out)
        require(not args.out.exists(), "output_must_be_new_external_file")
        for path in (args.manifest, args.approval):
            if path is not None:
                artifact_path(path)
        require(args.approval is None or args.live, "approval_only_for_live")
        require(not (args.live and args.dry_run), "mode_conflict")
        require(not args.live or (args.approval is not None and args.manifest is not None and not args.initialize),
                "explicit_approval_required")
        if args.manifest:
            manifest = json.loads(args.manifest.read_text())
        else:
            require(bool(args.reference_time), "reference_required")
            manifest = prepare(args.reference_time, initialize_database=args.initialize)
        if args.live or args.dry_run:
            approval = read_approval(args.approval) if args.approval else None
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
    except (Exception, KeyboardInterrupt):
        code = "offline_or_diagnostic_failure"
        print(f"W6c stopped: {code}; no retry or resume is permitted. Inspect the local safe journal.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
