"""Offline-only planner study preparation. No network transport or live mode."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import re
import sqlite3
from statistics import median
import subprocess

from alembic.config import Config
from alembic.script import ScriptDirectory
import httpx
from openai import OpenAI
from openai.lib._parsing._responses import type_to_text_format_param
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth.access_context import build_user_access_context
from app.evaluation.environment import evaluation_database_fingerprint
from app.models.product import AppUser
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import PlanGenerationOutcome
from app.query_engine.openai_provider import (
    SYSTEM_INSTRUCTIONS, OpenAIProvider, _StructuredProviderOutput, build_safe_prompt_projection,
)
from app.query_engine.plan_generator import PlanGenerator
from app.query_engine.provider_config import (
    OFFICIAL_OPENAI_BASE_URL, installed_runtime_versions, load_provider_settings, provider_runtime_identity,
)
from app.query_engine.request_authorization import authorize_query_request
from app.query_engine.schema_context import build_schema_context
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_conformance import check_semantic_conformance
from app.query_engine.semantic_plan import SemanticPlanValidationError, validate_semantic_plan
from app.query_engine.service import _user_generation_context
from app.query_engine.sql_executor import execute_validated_sql, query_runtime_transaction
from app.query_engine.sql_renderer import SemanticSQLRenderError, render_validated_semantic_plan
from app.query_engine.sql_validator import validate_sql
from scripts.semantic_ownership_fixtures import count, field
from scripts.planner_study_fixtures import ACTOR, CASES, DENIED_ACTOR, add_witnesses
from scripts.w6c_live import runtime_policy_identity

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = datetime(2026, 1, 1, tzinfo=UTC)
MODEL = "gpt-6.1-terra"
ARMS = ("low", "medium")
FATAL = frozenset({
    "authorization_denied", "security", "renderer", "sql_validation", "conformance",
    "execution", "backend", "provider_fatal", "result_mismatch",
})


class StudyStop(RuntimeError):
    """Contains only a fixed, safe diagnostic code."""


def require(ok, code):
    if not ok:
        raise StudyStop(code)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True,
                          text=True, timeout=10).stdout.strip()


def source():
    require(not git("status", "--porcelain"), "source_dirty")
    return git("rev-parse", "HEAD")


def profiles():
    return {effort: load_provider_settings({
        "LLM_PROVIDER": "openai", "OPENAI_API_KEY": "offline-placeholder", "OPENAI_MODEL": MODEL,
        "OPENAI_REASONING_EFFORT": effort, "OPENAI_TIMEOUT_SECONDS": "45",
        "OPENAI_MAX_OUTPUT_TOKENS": "2048", "OPENAI_MAX_RETRIES": "2",
    }) for effort in ARMS}


def body(prompt, effort):
    return {
        "model": MODEL, "instructions": SYSTEM_INSTRUCTIONS, "input": encode(prompt),
        "text": {"format": type_to_text_format_param(_StructuredProviderOutput)},
        "reasoning": {"effort": effort}, "max_output_tokens": 2048, "store": False,
    }


def slots():
    return tuple((block + 1, i, arm) for block in range(2) for i in range(len(CASES))
                 for arm in (ARMS if (block + i) % 2 == 0 else ARMS[::-1]))


def owned_engine(url):
    parsed = make_url(url)
    require(parsed.drivername == "postgresql+psycopg" and parsed.host == "127.0.0.1"
            and parsed.port is not None and not parsed.query
            and bool(re.fullmatch(r"planner_study_test_[0-9a-f]{16}", parsed.database or "")),
            "disposable_database_required")
    return create_engine(parsed)


def database_identity(db, owner):
    row = db.execute(text("""
        SELECT current_database(), current_setting('server_version'),
               current_setting('server_version_num')::int, (pg_control_system()).system_identifier::text,
               shobj_description(d.oid, 'pg_database'), d.datdba = r.oid
        FROM pg_database d JOIN pg_roles r ON r.rolname = current_user
        WHERE d.datname = current_database()
    """)).one()
    require(row[4] == f"queryops-planner-study:{owner}" and row[5]
            and 160000 <= row[2] < 170000, "database_ownership_invalid")
    migration = db.scalar(text("SELECT version_num FROM alembic_version"))
    config = Config()
    config.set_main_option("script_location", str(ROOT / "backend/alembic"))
    require(migration == ScriptDirectory.from_config(config).get_current_head(), "migration_mismatch")
    return {"cluster_sha256": digest(row[3]), "database_sha256": digest(row[0]),
            "postgres": row[1], "alembic": migration, "policy_sha256": runtime_policy_identity(db)}


def initialize(engine, owner):
    with Session(engine) as db, db.begin():
        database_identity(db, owner)
        db.execute(text("SELECT pg_advisory_xact_lock(11765321)"))
        for name in inspect(db.connection()).get_table_names():
            if name != "alembic_version":
                quoted = engine.dialect.identifier_preparer.quote(name)
                require(db.execute(text(f"SELECT 1 FROM {quoted} LIMIT 1")).first() is None,
                        "study_database_not_empty")
        add_witnesses(db, REFERENCE)


def context(db, pack, case, actor_email=ACTOR):
    actor = db.scalar(select(AppUser).where(AppUser.email == actor_email))
    require(actor is not None, "study_actor_missing")
    access = build_user_access_context(actor, db)
    if not authorize_query_request(access, pack, template_id=None).allowed:
        return None
    require(not access.has_global_scope and len(access.scopes) == 2
            and access.has_scope("department", "it") and access.has_scope("department", "finance"),
            "study_scope_mismatch")
    user = _user_generation_context(access)
    schema = build_schema_context(db, access, domain_pack=pack)
    projection = build_semantic_catalog_projection(pack.semantic_catalog, case.question, schema, user)
    require(projection.grounded_result_intent is None and len(encode(projection.as_prompt_dict()).encode()) <= 16000,
            "projection_invalid")
    prompt = build_safe_prompt_projection(case.question, schema, user, projection)
    private = [access.user_id, *(s.department_id for s in access.scopes), actor_email, DENIED_ACTOR]
    require(not any(str(v) in encode(prompt) for v in private if v) and "it_audit_events" not in encode(prompt),
            "context_disclosure")
    require(prompt["tables"], "empty_context")
    hint = projection.suggested_result_intent
    count_rows_hint = bool(hint and any(a.function == "count" and a.target_field is None and not a.distinct
                                       for a in hint.aggregations))
    if case.family == "grain" and case.id == "grain-memberships":
        require(count_rows_hint == case.hint_sensitive, "joined_count_hint_drift")
    return access, schema, user, projection, prompt


def prepare(db, pack, owner):
    database = database_identity(db, owner)
    database["data_sha256"], database["counts"] = evaluation_database_fingerprint(db)
    runtime = installed_runtime_versions()
    profile_specs = {arm: {"provider": "openai", "endpoint": OFFICIAL_OPENAI_BASE_URL, "model": MODEL,
                           "reasoning": arm, "max_output_tokens": 2048, "timeout_seconds": 45,
                           "sdk_retries": 2, "redirects": True, "store": False,
                           "sdk_runtime": provider_runtime_identity(settings)}
                     for arm, settings in profiles().items()}
    fixture_hash = file_digest(Path(__file__).with_name("planner_study_fixtures.py"))
    cases = {}
    for case in CASES:
        value = context(db, pack, case)
        require(value is not None, "authorization_denied")
        _, schema, _, projection, prompt = value
        requests = {arm: body(prompt, arm) for arm in ARMS}
        cases[case.id] = {
            "context_sha256": digest(prompt), "schema_sha256": digest(schema),
            "projection_sha256": digest(projection.as_prompt_dict()),
            "request_sha256": {arm: digest(request) for arm, request in requests.items()},
            "input_utf8_bytes": sum(len(requests["low"][k].encode()) for k in ("instructions", "input"))
                                + len(encode(requests["low"]["text"]).encode()),
            "hint_sensitive": case.hint_sensitive,
        }
    identity = {
        "version": "queryops-planner-study-v1", "mode": "offline_only",
        "source": source(), "fixtures_sha256": fixture_hash, "database": database,
        "reference": REFERENCE.isoformat(), "catalog_sha256": pack.semantic_catalog.digest,
        "profiles": {arm: {**spec, "fingerprint": digest(spec)} for arm, spec in profile_specs.items()},
        "dependencies": runtime, "python": platform.python_version(), "dependency_manifest_sha256": file_digest(ROOT / "backend/pyproject.toml"),
        "instructions_sha256": digest(SYSTEM_INSTRUCTIONS),
        "response_schema_sha256": digest(type_to_text_format_param(_StructuredProviderOutput)),
        "cases": cases, "schedule_sha256": digest(slots()),
    }
    return {**identity, "fingerprint": digest(identity)}


def plan_shape(plan):
    # Alias, expression order, redundant DISTINCT on unique detail keys, and ordering
    # without a limit do not affect these preregistered multiset contracts.
    def sorted_models(values):
        return sorted(encode(value.model_dump(mode="json")) for value in values)

    return (
        frozenset(plan.entity_ids), frozenset(plan.composition_rule_ids), plan.metric_id,
        sorted_models(plan.relationships), sorted_models(plan.output_fields),
        sorted((a.function, a.field.entity_id if a.field else "", a.field.column if a.field else "", a.distinct)
               for a in plan.aggregations),
        sorted_models(plan.group_by), plan.having, plan.limit,
    )


def matching_plan(actual, expected):
    return (plan_shape(actual.plan) == plan_shape(expected.plan)
            and frozenset(actual.effective_predicates) == frozenset(expected.effective_predicates)
            and frozenset(encode(f.model_dump(mode="json")) for f in actual.plan.literal_filters)
            == frozenset(encode(f.model_dump(mode="json")) for f in expected.plan.literal_filters))


def checked(plan, pack, value):
    _, schema, user, projection, _ = value
    return validate_semantic_plan(plan, domain_pack=pack, projection=projection, schema_context=schema,
                                  scope_reference_resolved=user["scope_reference_resolved"])


def score(engine, pack, case, value, result):
    """Arm-blind. Returned stages are safe, finite labels, never content."""
    metadata = result.generation_metadata
    if metadata.get("provider_failure_code"):
        return "provider_fatal" if metadata.get("provider_failure_fatal") else "provider_invalid"
    if result.outcome == PlanGenerationOutcome.UNSAFE_REQUEST:
        return "provider_unsafe"
    if result.outcome == PlanGenerationOutcome.CLARIFICATION:
        if not case.plans and result.unsupported_reason == "ambiguous_question":
            return "pass"
        return "interpretation"
    try:
        actual = checked(result.semantic_plan, pack, value)
    except SemanticPlanValidationError as exc:
        return "security" if exc.reason in {"field_not_authorized", "scope_filter_not_allowed"} else "invalid_plan"
    try:
        sql = render_validated_semantic_plan(actual, pack)
    except SemanticSQLRenderError:
        return "renderer"
    access, schema, *_ = value
    safety = validate_sql(sql, schema)
    if not safety.valid or not safety.sanitized_sql:
        return "sql_validation"
    conformity = check_semantic_conformance(plan=actual, candidate_sql=sql, safety_result=safety,
                                             domain_pack=pack, schema_context=schema)
    if not conformity.valid:
        return "conformance"
    with query_runtime_transaction(engine, access, isolation_level="repeatable_read", timezone_name="UTC") as db:
        if tuple(db.execute(text("SELECT current_user, current_setting('transaction_read_only'), "
                                 "current_setting('transaction_isolation'), current_setting('TimeZone')")).one()) != (
                                     "queryops_query_runtime", "on", "repeatable read", "UTC"):
            return "security"
        output = execute_validated_sql(db, access, safety)
    if (output.status != "succeeded" or output.truncated
            or output.execution_metadata.get("delivery_completeness") != "complete"):
        return "execution"
    # Resolve column positions by semantic identity, not a provider-chosen alias.
    if any("study-hidden" in row.values() or "hidden" in row.values() for row in output.rows):
        return "security"
    fields = list(actual.plan.output_fields)
    aggregates = list(actual.plan.aggregations)
    expected = [checked(plan, pack, value) for plan in case.plans]
    match = next((candidate for candidate in expected if matching_plan(actual, candidate)), None)
    if match is None:
        return "interpretation"
    try:
        indices = [fields.index(f) for f in case.plans[0].output_fields]
        indices.extend(range(len(fields), len(fields) + len(aggregates)))
        if len(output.columns) != len(indices):
            return "conformance"
        actual_rows = Counter(tuple(row[output.columns[i]] for i in indices) for row in output.rows)
    except (ValueError, IndexError, KeyError, TypeError):
        return "conformance"
    return "pass" if actual_rows == Counter(case.rows) else "result_mismatch"


def measurement(result):
    data = result.generation_metadata.get("provider_measurement", {})
    require(isinstance(data, dict), "measurement_invalid")
    safe = {}
    for name, upper in (("call_count", 1), ("attempt_count", 64), ("input_tokens", 10**9),
                        ("output_tokens", 10**9), ("cached_input_tokens", 10**9), ("total_tokens", 10**9)):
        value = data.get(name)
        require(value is None or type(value) is int and 0 <= value <= upper, "measurement_invalid")
        safe[name] = value
    duration = data.get("duration_ms")
    require(duration is None or type(duration) in (int, float) and math.isfinite(duration)
            and 0 <= duration <= 86_400_000, "measurement_invalid")
    safe["duration_ms"] = duration
    complete = data.get("usage_complete")
    require(complete is None or type(complete) is bool, "measurement_invalid")
    safe["usage_complete"] = complete is True
    if safe["usage_complete"]:
        require(all(safe[key] is not None for key in ("input_tokens", "output_tokens", "cached_input_tokens",
                                                     "total_tokens")), "measurement_invalid")
        require(safe["cached_input_tokens"] <= safe["input_tokens"]
                and safe["total_tokens"] == safe["input_tokens"] + safe["output_tokens"], "measurement_invalid")
    return safe


@dataclass(frozen=True)
class Observation:
    stage: str
    usage: dict


def assess(observations):
    """Pure decision calculation after all 32 slots are persisted and verified."""
    require(len(observations) == len(slots()), "study_incomplete")
    indexed = dict(zip(slots(), observations, strict=True))
    require(not any(o.stage in FATAL for o in observations), "study_invalid")
    passed = {slot: o.stage == "pass" for slot, o in indexed.items()}
    differences = {
        (block, i): int(passed[block, i, "medium"]) - int(passed[block, i, "low"])
        for block in (1, 2) for i in range(len(CASES))
    }
    gains = [case.family for i, case in enumerate(CASES) if not case.hint_sensitive
             and all(passed[b, i, "medium"] for b in (1, 2))
             and any(differences[b, i] > 0 for b in (1, 2))]
    medium_score = sum(passed[key] for key in passed if key[2] == "medium")
    net = sum(differences.values())
    quality = (medium_score >= 14 and net >= 3 and len(set(gains)) >= 2
               and all(sum(differences[b, i] for i in range(len(CASES))) > 0 for b in (1, 2))
               and all(passed[b, i, "medium"] for b in (1, 2) for i, case in enumerate(CASES)
                       if case.family == "clarification"))
    complete = all(o.usage["usage_complete"] and o.usage["duration_ms"] is not None
                   and o.usage["attempt_count"] is not None for o in observations)
    cost_latency = False
    if complete:
        usage = {arm: [o.usage for key, o in indexed.items() if key[2] == arm] for arm in ARMS}
        # Uncached-equivalent cost avoids rewarding the arm that happened to be second.
        cost = {arm: sum(u["input_tokens"] + 5 * u["output_tokens"] for u in usage[arm]) for arm in ARMS}
        latency = {arm: median(u["duration_ms"] for u in usage[arm]) for arm in ARMS}
        cost_latency = cost["medium"] <= 2 * cost["low"] and latency["medium"] <= 2 * latency["low"]
    return {"medium_passes": medium_score, "net_paired_gains": net,
            "hint_sensitive": {arm: sum(passed[b, i, arm] for b in (1, 2) for i, case in enumerate(CASES)
                                        if case.hint_sensitive) for arm in ARMS},
            "advancement": ("inconclusive" if not complete else
                            "consider_medium" if quality and cost_latency else "retain_low")}


class Ledger:
    """A new local directory is the atomic, durable one-shot claim. No resume path."""

    def __init__(self, path, fingerprint):
        require(path.is_absolute() and path.parent.resolve() == path.parent
                and not path.is_relative_to(ROOT), "ledger_path_invalid")
        path.mkdir(mode=0o700)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.db = sqlite3.connect(path / "slots.sqlite3")
        with self.db:
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA fullfsync=ON")
            self.db.execute("CREATE TABLE study (fingerprint TEXT PRIMARY KEY)")
            self.db.execute("INSERT INTO study VALUES (?)", (fingerprint,))
            self.db.execute("CREATE TABLE slots (ordinal INTEGER PRIMARY KEY, result TEXT)")

    def reserve(self, ordinal):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            done, pending = self.db.execute(
                "SELECT count(*), count(*)-count(result) FROM slots").fetchone()
            require(ordinal == done and not pending and ordinal < len(slots()), "slot_replay_or_out_of_order")
            self.db.execute("INSERT INTO slots VALUES (?, NULL)", (ordinal,))

    def complete(self, ordinal, observation):
        with self.db:
            cursor = self.db.execute("UPDATE slots SET result=? WHERE ordinal=? AND result IS NULL",
                                     (encode(asdict(observation)), ordinal))
            require(cursor.rowcount == 1, "slot_not_reserved")

    def close(self):
        self.db.close()


def responses_payload(content):
    return {"id": "resp_offline", "object": "response", "created_at": 0,
            "status": "completed", "model": MODEL,
            "output": [{"id": "msg_offline", "type": "message", "status": "completed", "role": "assistant",
                        "content": [{"type": "output_text", "text": content, "annotations": []}]}]}


def offline_generate(case, value, arm, payload, expected_hash, on_dispatch):
    """Exercise the real Responses parser with a transport incapable of egress."""
    _, schema, user, projection, _ = value

    def reply(request):
        require(request.method == "POST" and str(request.url) == OFFICIAL_OPENAI_BASE_URL + "/responses"
                and digest(json.loads(request.content)) == expected_hash, "request_identity_changed")
        on_dispatch()
        return httpx.Response(200, json=responses_payload(payload))

    settings = profiles()[arm].openai
    require(settings is not None, "profile_settings_invalid")
    with OpenAI(api_key=settings.api_key, base_url=OFFICIAL_OPENAI_BASE_URL,
                max_retries=settings.max_retries, timeout=settings.timeout_seconds,
                http_client=httpx.Client(transport=httpx.MockTransport(reply), trust_env=False,
                                         follow_redirects=True)) as client:
        return PlanGenerator(OpenAIProvider(settings, client=client)).generate_plan(
            case.question, schema, user, {"semantic_catalog": projection})


def supplied(plan=None):
    return encode({"outcome": "plan" if plan else "clarification",
                   "semantic_plan": plan.model_dump(mode="json") if plan else None,
                   "clarification_reason": None if plan else "ambiguous_question"})


def offline_observe(engine, db, pack, case, arm, payload, manifest, on_dispatch, *,
                    actor=ACTOR, before_dispatch=lambda: None):
    value = context(db, pack, case, actor)
    if value is None:
        return Observation("authorization_denied", {})
    before_dispatch()
    result = offline_generate(case, value, arm, payload,
                              manifest["cases"][case.id]["request_sha256"][arm], on_dispatch)
    if result.model_name != MODEL:
        return Observation("provider_fatal", measurement(result))
    return Observation(score(engine, pack, case, value, result), measurement(result))


def offline_controls(engine, db, pack, manifest):
    posture, status, _, membership, ambiguity, critical, device, assignee = CASES
    joined = membership.plans[0].model_copy(update={"aggregations": (count(),)})
    unauthorized = status.plans[0].model_copy(update={"output_fields": (field("devices", "secret"),)})
    controls = (
        (posture, supplied(status.plans[0]), ACTOR, "interpretation"),
        (membership, supplied(joined), ACTOR, "interpretation"),
        (device, supplied(assignee.plans[0]), ACTOR, "interpretation"),
        (critical, supplied(), ACTOR, "interpretation"),
        (ambiguity, supplied(), ACTOR, "pass"),
        (posture, "{bad", ACTOR, "provider_invalid"),
        (status, supplied(unauthorized), ACTOR, "security"),
        (posture, supplied(posture.plans[0]), DENIED_ACTOR, "authorization_denied"),
    )
    dispatches = []
    for case, payload, actor, expected in controls:
        before = len(dispatches)
        result = offline_observe(engine, db, pack, case, "low", payload, manifest,
                                 lambda: dispatches.append(1), actor=actor)
        require(result.stage == expected, f"dry_run_control_{case.id}_{result.stage}")
        require(len(dispatches) - before == (actor != DENIED_ACTOR), "control_dispatch_count_invalid")
    for case in CASES:
        for alternative in case.plans[1:]:
            result = offline_observe(engine, db, pack, case, "low", supplied(alternative), manifest,
                                     lambda: dispatches.append(1))
            require(result.stage == "pass", f"dry_run_alternative_{case.id}_{result.stage}")
    return len(controls), len(dispatches)


def dry_run(engine, owner, manifest, evidence):
    pack = load_it_operations_domain_pack()
    with Session(engine) as db:
        require(prepare(db, pack, owner) == manifest, "study_identity_changed")
        controls, control_dispatches = offline_controls(engine, db, pack, manifest)
    ledger = Ledger(evidence, manifest["fingerprint"])
    mock_dispatches = 0
    try:
        for ordinal, (_, index, arm) in enumerate(slots()):
            case = CASES[index]
            with Session(engine) as db:
                require(prepare(db, pack, owner) == manifest, "study_identity_changed")

                def dispatched():
                    nonlocal mock_dispatches
                    mock_dispatches += 1

                observation = offline_observe(engine, db, pack, case, arm,
                                              supplied(next(iter(case.plans), None)), manifest, dispatched,
                                              before_dispatch=lambda: ledger.reserve(ordinal))
                require(observation.stage != "authorization_denied", "authorization_denied")
                ledger.complete(ordinal, observation)
                require(observation.stage == "pass", f"dry_run_{observation.stage}_{case.id}")
        with Session(engine) as db:
            require(prepare(db, pack, owner) == manifest, "study_identity_changed")
    finally:
        ledger.close()
    require(mock_dispatches == len(slots()), "mock_dispatch_count_invalid")
    return {"mode": "offline_supplied_plans", "mock_dispatches": mock_dispatches,
            "control_dispatches": control_dispatches, "controls": controls,
            "provider_dispatches": 0, "denied_control_dispatches": 0, "passes": len(slots())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("initialize", "manifest", "dry-run"))
    parser.add_argument("--owner-receipt", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    try:
        owner = args.owner_receipt.read_text().strip()
        require(bool(re.fullmatch(r"[0-9a-f]{32}", owner)), "ownership_receipt_invalid")
        engine = owned_engine(os.environ.get("PLANNER_STUDY_DATABASE_URL", ""))
        try:
            if args.action == "initialize":
                initialize(engine, owner)
                return 0
            require(args.manifest is not None, "manifest_path_required")
            if args.action == "manifest":
                with Session(engine) as db:
                    identity = prepare(db, load_it_operations_domain_pack(), owner)
                with args.manifest.open("x") as file:
                    file.write(encode(identity) + "\n")
                return 0
            require(args.evidence is not None, "evidence_path_required")
            print(encode(dry_run(engine, owner, json.loads(args.manifest.read_text()), args.evidence)))
            return 0
        finally:
            engine.dispose()
    except StudyStop as exc:
        parser.exit(1, f"{exc}\n")
    except Exception:
        parser.exit(1, "study_preparation_failed\n")


if __name__ == "__main__":
    raise SystemExit(main())
