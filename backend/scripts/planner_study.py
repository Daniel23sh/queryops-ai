"""Prepare the planner study offline or run it with a one-shot operator grant."""
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
import signal
import sqlite3
import sys
from statistics import median
import time
from typing import Any, cast

from alembic.config import Config
from alembic.script import ScriptDirectory
import httpx
from openai import OpenAI, omit
from openai.lib._parsing._responses import type_to_text_format_param
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.auth.access_context import build_user_access_context
from app.evaluation.environment import evaluation_database_fingerprint
from app.models.product import AppUser
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import PlanGenerationOutcome
from app.query_engine.openai_provider import (
    SYSTEM_INSTRUCTIONS, OpenAIProvider, _StructuredProviderOutput, _usage_counts, build_safe_prompt_projection,
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
from scripts import planner_study_activation as activation
from scripts.w6c_live import runtime_policy_identity

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = datetime(2026, 1, 1, tzinfo=UTC)
MODEL = "gpt-6.1-terra"
ARMS = ("low", "medium")
TIMEOUT = 45
OUTPUT_TOKENS = 2048
RESPONSES = OFFICIAL_OPENAI_BASE_URL + "/responses"
MAX_RESPONSE = 1_000_000
FATAL = frozenset({
    "authorization_denied", "security", "renderer", "sql_validation", "conformance",
    "execution", "provider_fatal", "result_mismatch",
})
STAGES = FATAL | {"pass", "interpretation", "invalid_plan", "provider_invalid",
                  "provider_refusal", "provider_timeout", "provider_unsafe"}


class StudyStop(RuntimeError):
    """Contains only a fixed, safe diagnostic code."""


def require(ok, code):
    if not ok:
        raise StudyStop(code)


encode = activation.encode
digest = activation.digest


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return activation.git(ROOT, *args)


def source():
    require(not git("status", "--porcelain"), "source_dirty")
    revision = git("rev-parse", "HEAD")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", revision)), "source_invalid")
    return revision


def profiles(api_key="offline-placeholder"):
    return {effort: load_provider_settings({
        "LLM_PROVIDER": "openai", "OPENAI_API_KEY": api_key, "OPENAI_MODEL": MODEL,
        "OPENAI_REASONING_EFFORT": effort, "OPENAI_TIMEOUT_SECONDS": str(TIMEOUT),
        "OPENAI_MAX_OUTPUT_TOKENS": str(OUTPUT_TOKENS), "OPENAI_MAX_RETRIES": "0",
    }) for effort in ARMS}


def body(prompt, effort):
    return {
        "model": MODEL, "instructions": SYSTEM_INSTRUCTIONS, "input": encode(prompt),
        "text": {"format": type_to_text_format_param(_StructuredProviderOutput)},
        "reasoning": {"effort": effort}, "max_output_tokens": OUTPUT_TOKENS, "store": False,
    }


def slots():
    return tuple((block + 1, i, arm) for block in range(2) for i in range(len(CASES))
                 for arm in (ARMS if (block + i) % 2 == 0 else ARMS[::-1]))


def owned_engine(url, *, live=False):
    parsed = make_url(url)
    require(parsed.drivername == "postgresql+psycopg" and parsed.host == "127.0.0.1"
            and parsed.port is not None and not parsed.query
            and bool(re.fullmatch(r"planner_study_test_[0-9a-f]{16}", parsed.database or "")),
            "disposable_database_required")
    return create_engine(parsed, poolclass=NullPool) if live else create_engine(parsed)


def database_identity(db, owner):
    row = db.execute(text("""
        SELECT current_database(), current_setting('server_version'),
               current_setting('server_version_num')::int, (pg_control_system()).system_identifier::text,
               shobj_description(d.oid, 'pg_database'), d.datdba = r.oid, d.oid, current_user
        FROM pg_database d JOIN pg_roles r ON r.rolname = current_user
        WHERE d.datname = current_database()
    """)).one()
    require(row[4] == f"queryops-planner-study:{owner}" and row[5]
            and 160000 <= row[2] < 170000, "database_ownership_invalid")
    migration = db.scalar(text("SELECT version_num FROM alembic_version"))
    config = Config()
    config.set_main_option("script_location", str(ROOT / "backend/alembic"))
    require(migration == ScriptDirectory.from_config(config).get_current_head(), "migration_mismatch")
    return {"cluster_sha256": digest(row[3]), "database_sha256": digest([row[0], row[6], row[7]]),
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
    if case.id == "grain-type":
        require(hint is None, "device_grain_hint_drift")
    if case.id == "grain-memberships":
        require(count_rows_hint == case.hint_sensitive, "joined_count_hint_drift")
    return access, schema, user, projection, prompt


def profile_specs(settings_by_arm):
    result = {}
    for arm, settings in settings_by_arm.items():
        config = settings.openai
        require(config is not None, "profile_settings_invalid")
        spec = {"provider": "openai", "endpoint": RESPONSES, "model": config.model,
                "reasoning": config.reasoning_effort, "max_output_tokens": config.max_output_tokens,
                "timeout_seconds": config.timeout_seconds, "sdk_retries": config.max_retries,
                "transport_retries": 0, "redirects": False, "trust_env": False, "tls_verify": True,
                "store": False, "sdk_runtime": provider_runtime_identity(settings)}
        result[arm] = {**spec, "fingerprint": digest(spec)}
    return result


def prepare(db, pack, owner, *, revision=None):
    database = database_identity(db, owner)
    database["data_sha256"], database["counts"] = evaluation_database_fingerprint(db)
    runtime = installed_runtime_versions()
    fixture_hash = file_digest(Path(__file__).with_name("planner_study_fixtures.py"))
    cases = {}
    for case in CASES:
        value = context(db, pack, case)
        if value is None:
            raise StudyStop("authorization_denied")
        access, schema, _, projection, prompt = value
        requests = {arm: body(prompt, arm) for arm in ARMS}
        cases[case.id] = {
            "context_sha256": digest(prompt), "schema_sha256": digest(schema),
            "actor_sha256": digest([str(access.user_id), sorted(str(s.department_id) for s in access.scopes)]),
            "projection_sha256": digest(projection.as_prompt_dict()),
            "request_sha256": {arm: digest(request) for arm, request in requests.items()},
            "input_utf8_bytes": sum(len(requests["low"][k].encode()) for k in ("instructions", "input"))
                                + len(encode(requests["low"]["text"]).encode()),
            "hint_sensitive": case.hint_sensitive,
        }
    identity = {
        "version": activation.STUDY_ID, "mode": "preparation_only",
        "source": revision if revision is not None else source(), "fixtures_sha256": fixture_hash, "database": database,
        "reference": REFERENCE.isoformat(), "catalog_sha256": pack.semantic_catalog.digest,
        "profiles": profile_specs(profiles()),
        "dependencies": runtime, "python": platform.python_version(),
        "interpreter": str(Path(sys.executable).resolve()), "environment": str(Path(sys.prefix).resolve()),
        "interpreter_sha256": file_digest(Path(sys.executable).resolve()), "dependency_manifest_sha256": file_digest(ROOT / "backend/pyproject.toml"),
        "instructions_sha256": digest(SYSTEM_INSTRUCTIONS),
        "response_schema_sha256": digest(type_to_text_format_param(_StructuredProviderOutput)),
        "cases": cases, "schedule": [[block, CASES[index].id, arm] for block, index, arm in slots()],
    }
    identity["schedule_sha256"] = digest(identity["schedule"])
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
    code = metadata.get("provider_failure_code")
    if code:
        if metadata.get("provider_failure_fatal") or code == "provider_unavailable":
            return "provider_fatal"
        return {"provider_refusal": "provider_refusal", "provider_timeout": "provider_timeout"}.get(
            code, "provider_invalid")
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
    return bounded_measurement(result.generation_metadata.get("provider_measurement", {}))


def bounded_measurement(data):
    require(isinstance(data, dict), "measurement_invalid")
    safe = {}
    for name, upper in (("call_count", 1), ("attempt_count", 1), ("input_tokens", 10**9),
                        ("output_tokens", OUTPUT_TOKENS), ("cached_input_tokens", 10**9), ("total_tokens", 10**9)):
        value = data.get(name)
        require(value is None or type(value) is int and 0 <= value <= upper, "measurement_invalid")
        safe[name] = value
    duration = data.get("duration_ms")
    require(duration is None or type(duration) in (int, float) and math.isfinite(duration)
            and 0 <= duration <= 86_400_000, "measurement_invalid")
    require(safe["call_count"] in (None, 1) and safe["attempt_count"] != 0, "measurement_invalid")
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
    require(all(o.stage in STAGES - FATAL for o in observations), "study_invalid")
    passed = {slot: o.stage == "pass" for slot, o in indexed.items()}
    differences = {
        (block, i): int(passed[block, i, "medium"]) - int(passed[block, i, "low"])
        for block in (1, 2) for i in range(len(CASES))
    }
    gains = [case.family for i, case in enumerate(CASES) if not case.hint_sensitive
             and all(passed[b, i, "medium"] for b in (1, 2))
             and any(differences[b, i] > 0 for b in (1, 2))]
    medium_score = sum(passed[key] for key in passed if key[2] == "medium")
    block_gains = [sum(differences[b, i] for i in range(len(CASES))) for b in (1, 2)]
    net = sum(block_gains)
    quality = (medium_score >= 14 and net >= 3 and len(set(gains)) >= 2
               and all(gain > 0 for gain in block_gains)
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
    return {"medium_passes": medium_score, "net_paired_gains": net, "block_net_gains": block_gains,
            "passes": {arm: sum(value for key, value in passed.items() if key[2] == arm) for arm in ARMS},
            "stages": {arm: dict(Counter(o.stage for key, o in indexed.items() if key[2] == arm)) for arm in ARMS},
            "repeat_flips": {arm: sum(passed[1, i, arm] != passed[2, i, arm]
                                      for i in range(len(CASES))) for arm in ARMS},
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
        try:
            with self.db:
                self.db.execute("PRAGMA synchronous=EXTRA")
                self.db.execute("PRAGMA fullfsync=ON")
                self.db.execute("CREATE TABLE study (fingerprint TEXT PRIMARY KEY, seal TEXT)")
                self.db.execute("INSERT INTO study (fingerprint) VALUES (?)", (fingerprint,))
                self.db.execute("CREATE TABLE slots (ordinal INTEGER PRIMARY KEY, identity TEXT, "
                                "transport TEXT, stage TEXT, result TEXT)")
            activation.sync_directory(path)
        except BaseException:
            self.db.close()
            raise

    def reserve(self, ordinal, identity=None):
        serialized = encode(identity)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            done, pending = self.db.execute(
                "SELECT count(*), count(*)-count(result) FROM slots").fetchone()
            require(type(ordinal) is int and ordinal == done and not pending
                    and ordinal < len(slots()), "slot_replay_or_out_of_order")
            previous = self.db.execute("SELECT stage FROM slots WHERE ordinal=?", (ordinal - 1,)).fetchone()
            require(previous is None or previous[0] in STAGES - FATAL, "study_terminal")
            require(self.db.execute("SELECT seal FROM study").fetchone() == (None,), "study_terminal")
            self.db.execute("INSERT INTO slots (ordinal, identity) VALUES (?, ?)", (ordinal, serialized))
        require(self.db.execute("SELECT identity, transport, result FROM slots WHERE ordinal=?",
                                (ordinal,)).fetchone() == (serialized, None, None), "reservation_readback_failed")

    def record_transport(self, ordinal, record):
        serialized = encode(record)
        with self.db:
            cursor = self.db.execute("UPDATE slots SET transport=? WHERE ordinal=? AND transport IS NULL AND result IS NULL",
                                     (serialized, ordinal))
            require(cursor.rowcount == 1, "transport_not_reserved")
        require(self.db.execute("SELECT transport FROM slots WHERE ordinal=?", (ordinal,)).fetchone()
                == (serialized,), "transport_readback_failed")

    def complete(self, ordinal, observation):
        require(observation.stage in STAGES, "observation_invalid")
        serialized = encode(asdict(observation))
        with self.db:
            cursor = self.db.execute("UPDATE slots SET stage=?, result=? WHERE ordinal=? AND result IS NULL",
                                     (observation.stage, serialized, ordinal))
            require(cursor.rowcount == 1, "slot_not_reserved")
        require(self.db.execute("SELECT stage, result FROM slots WHERE ordinal=?", (ordinal,)).fetchone()
                == (observation.stage, serialized), "observation_readback_failed")

    def seal(self, outcome, records=()):
        serialized = encode(outcome)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if records:
                require(self.db.execute("SELECT ordinal, identity, transport, stage, result FROM slots ORDER BY ordinal"
                                        ).fetchall() == records, "evidence_readback_failed")
            cursor = self.db.execute("UPDATE study SET seal=? WHERE seal IS NULL", (serialized,))
            require(cursor.rowcount == 1, "study_terminal")
        require(self.db.execute("SELECT seal FROM study").fetchone() == (serialized,), "seal_readback_failed")

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
        require(request.method == "POST" and str(request.url) == RESPONSES
                and digest(json.loads(request.content)) == expected_hash, "request_identity_changed")
        on_dispatch()
        return httpx.Response(200, json=responses_payload(payload))

    settings = profiles()[arm].openai
    if settings is None:
        raise StudyStop("profile_settings_invalid")
    with OpenAI(api_key=settings.api_key, base_url=OFFICIAL_OPENAI_BASE_URL,
                organization="", project="", admin_api_key="", webhook_secret="",
                max_retries=settings.max_retries, timeout=settings.timeout_seconds,
                http_client=httpx.Client(transport=httpx.MockTransport(reply), trust_env=False,
                                         follow_redirects=False)) as client:
        return PlanGenerator(OpenAIProvider(settings, client=cast(Any, client))).generate_plan(
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


def verify_approval(approval, manifest):
    expected = {
        "schema": "queryops-planner-study-local-approval-v1", "approved": True,
        "study_id": activation.STUDY_ID, **activation.state_identity(),
        "operator_uid": os.getuid(), "operator_gid": os.getgid(),
        "source": manifest["source"], "manifest_sha256": manifest["fingerprint"],
        "profiles": {arm: manifest["profiles"][arm]["fingerprint"] for arm in ARMS},
        "requests": {case.id: manifest["cases"][case.id]["request_sha256"] for case in CASES},
        "schedule": manifest["schedule"], "schedule_sha256": manifest["schedule_sha256"],
        "endpoint": RESPONSES, "model": MODEL, "returned_model": MODEL,
        "logical_slots": len(slots()), "physical_dispatches": len(slots()),
        "output_tokens_per_slot": OUTPUT_TOKENS, "total_output_tokens": len(slots()) * OUTPUT_TOKENS,
        "median_latency_ratio": 2, "uncached_cost_ratio": 2,
    }
    varying = {
        "project", "credential_version", "credential_sha256", "starts_utc", "expires_utc",
        "estimated_input_tokens", "estimated_cost_usd",
    }
    require(set(approval) == set(expected) | varying
            and encode({key: approval[key] for key in expected}) == encode(expected), "approval_mismatch")
    for key, pattern in (("project", r"proj_[A-Za-z0-9_-]{1,128}"),
                         ("credential_version", r"[A-Za-z0-9_-]{1,64}"),
                         ("credential_sha256", r"[a-f0-9]{64}"),
                         ("estimated_cost_usd", r"(?:0|[1-9][0-9]{0,4})\.[0-9]{2,6}")):
        value = approval[key]
        require(isinstance(value, str) and re.fullmatch(pattern, value), "approval_field_invalid")
    estimate = approval["estimated_input_tokens"]
    require(type(estimate) is int and 0 < estimate <= 10**8 and float(approval["estimated_cost_usd"]) > 0,
            "approval_exposure_invalid")
    return activation.remaining(approval)


def check_source(expected):
    activation.verify_source(ROOT, expected, git)


def checked_snapshot(engine, pack, owner, manifest, case=None):
    check_source(manifest["source"])
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            with Session(bind=connection) as db:
                current = prepare(db, pack, owner, revision=manifest["source"])
                require(encode(current) == encode(manifest), "study_identity_changed")
                return context(db, pack, case) if case is not None else None


def response_evidence(response):
    try:
        status = response.status_code
        require(not 300 <= status < 400, "unexpected_redirect")
        require(status not in {401, 403, 429}, "provider_authorization_or_quota")
        require(200 <= status < 300, "provider_http_failure")
        require(response.headers.get("content-encoding", "identity").lower() == "identity",
                "response_encoding_invalid")
        content = bytearray()
        for chunk in response.iter_bytes():
            require(len(content) + len(chunk) <= MAX_RESPONSE, "response_too_large")
            content.extend(chunk)
        try:
            data = activation.decode(content, MAX_RESPONSE)
        except (ValueError, activation.ActivationError):
            raise StudyStop("response_envelope_invalid") from None
        require(data.get("model") == MODEL, "returned_model_mismatch")
        require(data.get("status") == "completed" and data.get("error") is None
                and data.get("incomplete_details") is None, "response_incomplete")
        usage = _usage_counts(data.get("usage"))
        require(len(usage) == 4 and 0 < usage["input_tokens"]
                and usage["cached_input_tokens"] <= usage["input_tokens"]
                and usage["output_tokens"] <= OUTPUT_TOKENS
                and usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"],
                "provider_usage_invalid")
        return httpx.Response(status, headers=response.headers, content=bytes(content)), usage
    finally:
        response.close()


class SlotTransport(httpx.BaseTransport):
    """The only path to the underlying transport for one scheduled slot."""

    def __init__(self, inner, ledger, ordinal, identity, credential, project, verify, gate):
        self.inner = inner
        self.ledger = ledger
        self.ordinal = ordinal
        self.identity = identity
        self.credential = credential
        self.project = project
        self.verify = verify
        self.gate = gate
        self.entered = False
        self.failure = None
        self.record = None

    def handle_request(self, request):
        reserved = False
        forwarded = False
        started = None
        try:
            require(not self.entered, "duplicate_transport_attempt")
            self.entered = True
            require(type(self.ordinal) is int and 0 <= self.ordinal < len(slots()), "slot_identity_invalid")
            block, index, arm = slots()[self.ordinal]
            require((self.identity["block"], self.identity["case"], self.identity["arm"])
                    == (block, CASES[index].id, arm), "slot_identity_invalid")
            require(request.method == "POST" and str(request.url) == RESPONSES
                    and request.headers.get_list("host") == ["api.openai.com"]
                    and request.headers.get_list("authorization") == ["Bearer " + self.credential]
                    and request.headers.get_list("openai-project") == [self.project]
                    and "openai-organization" not in request.headers
                    and request.headers.get("accept-encoding") == "identity"
                    and digest(activation.decode(request.content)) == self.identity["request_sha256"],
                    "request_identity_changed")
            self.verify()
            self.gate()
            self.ledger.reserve(self.ordinal, self.identity)
            reserved = True
            seconds = min(TIMEOUT, self.gate())
            request.extensions["timeout"] = dict.fromkeys(("connect", "read", "write", "pool"), seconds)
            started = time.perf_counter()
            forwarded = True
            response, usage = response_evidence(self.inner.handle_request(request))
            self.record = {"state": "received", "model": MODEL, "call_count": 1, "attempt_count": 1,
                           "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                           "usage_complete": True, **usage}
            bounded_measurement(self.record)
        except Exception as exc:
            if isinstance(exc, (StudyStop, activation.ActivationError)):
                self.failure = str(exc)
            elif isinstance(exc, httpx.TimeoutException):
                self.failure = "transport_timeout"
            else:
                self.failure = "dispatch_or_persistence_failure"
            if reserved:
                self.record = {"state": "uncertain" if forwarded else "stopped_before_forward",
                               "failure": self.failure, "attempt_count": int(forwarded),
                               "duration_ms": min(86_400_000, round((time.perf_counter() - started) * 1000, 3))
                               if started is not None else None, "usage_complete": False}
                self.ledger.record_transport(self.ordinal, self.record)
            raise StudyStop(self.failure) from None
        try:
            self.ledger.record_transport(self.ordinal, self.record)
        except Exception:
            self.failure = "transport_evidence_write_failed"
            response.close()
            raise StudyStop(self.failure) from None
        return response

    def close(self):
        self.inner.close()


def run_live(engine, owner, manifest, approval, credential, ledger, gate, make_transport):
    pack = load_it_operations_domain_pack()
    settings = profiles(credential)
    observations, records = [], []

    def verify(case=None):
        gate()
        require(encode(profile_specs(settings)) == encode(manifest["profiles"]), "profile_identity_changed")
        return checked_snapshot(engine, pack, owner, manifest, case)

    try:
        for ordinal, (block, index, arm) in enumerate(slots()):
            case = CASES[index]
            value = verify(case)
            if value is None:
                raise StudyStop("authorization_denied")
            _, schema, user, projection, _ = value
            identity = {"block": block, "case": case.id, "arm": arm,
                        "profile_sha256": manifest["profiles"][arm]["fingerprint"],
                        "request_sha256": manifest["cases"][case.id]["request_sha256"][arm]}
            config = settings[arm].openai
            if config is None:
                raise StudyStop("profile_settings_invalid")
            guarded = SlotTransport(make_transport(), ledger, ordinal, identity, credential,
                                    approval["project"], verify, gate)
            with OpenAI(
                api_key=credential, base_url=OFFICIAL_OPENAI_BASE_URL, project=approval["project"],
                organization="", admin_api_key="", webhook_secret="",
                default_headers=cast(Any, {"OpenAI-Organization": omit}),
                max_retries=config.max_retries, timeout=config.timeout_seconds,
                http_client=httpx.Client(transport=guarded, trust_env=False, follow_redirects=False,
                                         headers={"accept-encoding": "identity"}),
            ) as client:
                result = PlanGenerator(OpenAIProvider(config, client=cast(Any, client))).generate_plan(
                    case.question, schema, user, {"semantic_catalog": projection})
                require(guarded.failure is None and guarded.record is not None,
                        guarded.failure or "transport_evidence_missing")
            verify()
            usage = bounded_measurement(guarded.record)
            require(usage["usage_complete"] and usage["attempt_count"] == 1, "transport_evidence_invalid")
            observation = Observation(score(engine, pack, case, value, result), usage)
            ledger.complete(ordinal, observation)
            require(observation.stage not in FATAL | {"provider_invalid", "provider_timeout"}, observation.stage)
            observations.append(observation)
            records.append((ordinal, encode(identity), encode(guarded.record), observation.stage,
                            encode(asdict(observation))))
        verify()
        verdict = assess(observations)
        gate()
        ledger.seal({"state": "complete", "verdict": verdict}, records)
        return verdict
    except Exception as exc:
        code = str(exc) if isinstance(exc, (StudyStop, activation.ActivationError)) else "study_runtime_failure"
        ledger.seal({"state": "stopped", "reason": code})
        raise StudyStop(code) from None


def live():
    require(not activation.STATE.is_relative_to(ROOT), "activation_state_path_invalid")
    activation.state_identity()
    require(not os.path.lexists(activation.CLAIM), "activation_already_claimed")
    approval = activation.decode(activation.read_private(activation.STATE / "approval.json"))
    manifest = activation.decode(activation.read_private(activation.STATE / "manifest.json"))
    deadline = time.monotonic() + verify_approval(approval, manifest)
    owner = activation.read_private(activation.STATE / "database-owner").decode().strip()
    require(bool(re.fullmatch(r"[0-9a-f]{32}", owner)), "ownership_receipt_invalid")
    database_url = activation.read_private(activation.STATE / "database-url").decode().strip()
    engine = owned_engine(database_url, live=True)
    try:
        pack = load_it_operations_domain_pack()
        checked_snapshot(engine, pack, owner, manifest)
        with Session(engine) as db:
            offline_controls(engine, db, pack, manifest)
        verify_approval(approval, manifest)
        credential = activation.read_private(
            activation.STATE / ("credential-" + approval["credential_version"])).decode().strip()
        require(bool(re.fullmatch(r"[A-Za-z0-9_-]{20,512}", credential))
                and hashlib.sha256(credential.encode()).hexdigest() == approval["credential_sha256"],
                "activation_credential_changed")
        approval_sha = digest(approval)
        activation.claim(approval_sha)
        claim_info = activation.private(activation.CLAIM, directory=True)

        def gate():
            identity = activation.state_identity()
            current_claim = activation.private(activation.CLAIM, directory=True)
            require(all(approval[key] == value for key, value in identity.items())
                    and (current_claim.st_dev, current_claim.st_ino) == (claim_info.st_dev, claim_info.st_ino)
                    and activation.read_private(activation.CLAIM / "approval.sha256").decode() == approval_sha + "\n"
                    and digest(activation.decode(activation.read_private(activation.STATE / "approval.json"))) == approval_sha,
                    "activation_claim_changed")
            seconds = min(activation.remaining(approval), deadline - time.monotonic())
            require(seconds > 0, "activation_outside_window")
            return seconds

        # HTTPX bounds I/O phases; this deadline also bounds their sum.
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM})
        signal.setitimer(signal.ITIMER_REAL, gate())
        try:
            ledger = Ledger(activation.EVIDENCE / "ledger", manifest["fingerprint"])
            try:
                return run_live(engine, owner, manifest, approval, credential, ledger, gate,
                                lambda: httpx.HTTPTransport(verify=True, trust_env=False, retries=0))
            finally:
                ledger.close()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("initialize", "manifest", "dry-run", "live"))
    parser.add_argument("--owner-receipt", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "live":
            require(args.owner_receipt is args.manifest is args.evidence is None, "offline_arguments_invalid")
            print(encode(live()))
            return 0
        if args.owner_receipt is None:
            raise StudyStop("offline_arguments_invalid")
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
    except (StudyStop, activation.ActivationError) as exc:
        parser.exit(1, f"{exc}\n")
    except Exception:
        parser.exit(1, "study_preparation_failed\n")


if __name__ == "__main__":
    raise SystemExit(main())
