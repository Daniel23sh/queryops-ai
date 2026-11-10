"""Deterministic activation tests. Every provider response is synthetic."""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys

import httpx
import pytest

from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from scripts import planner_study as study
from scripts import planner_study_launch as launch
from scripts.semantic_ownership_fixtures import offline_schema


KEY = "synthetic-study-key-not-a-credential"
PROJECT = "proj_synthetic_study"


@pytest.fixture
def state(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    monkeypatch.setattr(launch, "STATE", root)
    monkeypatch.setattr(launch, "CLAIM", root / "test-claim")
    monkeypatch.setattr(launch, "EVIDENCE", launch.CLAIM / "evidence")
    return root


def test_concurrent_claim_from_different_working_directories(state):
    callers = [state / "checkout-a", state / "checkout-b"]
    for caller in callers:
        caller.mkdir()
        shutil.copyfile(launch.__file__, caller / "launcher.py")
    program = f"""
from pathlib import Path
import launcher as launch
import os
launch.STATE = Path({str(state)!r})
launch.CLAIM = launch.STATE / "test-claim"
launch.EVIDENCE = launch.CLAIM / "evidence"
try:
    launch.claim("a" * 64, os.getuid(), os.getgid())
except FileExistsError:
    raise SystemExit(2)
"""
    env = {"PATH": os.environ["PATH"]}
    commands = [subprocess.Popen([sys.executable, "-B", "-c", program], cwd=path, env=env) for path in callers]
    assert sorted(p.wait(timeout=15) for p in commands) == [0, 2]
    assert (launch.CLAIM / "approval.sha256").read_text() == "a" * 64 + "\n"
    with pytest.raises(FileExistsError):
        launch.claim("b" * 64, os.getuid(), os.getgid())


def test_claim_sync_error_and_ledger_init_failure_leave_claim(state, monkeypatch):
    with monkeypatch.context() as patch:
        def fail(path):
            raise OSError("synthetic sync failure")

        patch.setattr(launch, "sync_directory", fail)
        with pytest.raises(OSError):
            launch.claim("a" * 64, os.getuid(), os.getgid())
    assert launch.CLAIM.is_dir()
    with pytest.raises(FileExistsError):
        launch.claim("a" * 64, os.getuid(), os.getgid())
    test_ledger = state / "test-ledger"
    monkeypatch.setattr(sqlite3, "connect", lambda *args: (_ for _ in ()).throw(OSError("synthetic I/O")))
    with pytest.raises(OSError):
        study.Ledger(test_ledger, "a" * 64)
    assert launch.CLAIM.is_dir()
    with pytest.raises(FileExistsError):
        study.Ledger(test_ledger, "a" * 64)


@pytest.mark.parametrize("stage", ["claim", "reserved", "received"])
def test_killed_claimant_and_pending_slot_block_replay(state, stage):
    program = f"""
from pathlib import Path
from scripts import planner_study_launch as launch
from scripts import planner_study as study
import os, signal
launch.STATE = Path({str(state)!r})
launch.CLAIM = launch.STATE / "test-claim"
launch.EVIDENCE = launch.CLAIM / "evidence"
launch.claim("a" * 64, os.getuid(), os.getgid())
if {stage!r} != "claim":
    ledger = study.Ledger(launch.EVIDENCE / "ledger", "b" * 64)
    ledger.reserve(0, {{"slot": 0}})
    if {stage!r} == "received":
        ledger.record_transport(0, {{"state": "received", "attempt_count": 1}})
os.kill(os.getpid(), signal.SIGKILL)
"""
    result = subprocess.run([sys.executable, "-B", "-c", program], cwd=study.ROOT / "backend", timeout=15)
    assert result.returncode == -9
    if stage != "claim":
        record = study.encode({"state": "received", "attempt_count": 1}) if stage == "received" else None
        with sqlite3.connect(launch.EVIDENCE / "ledger" / "slots.sqlite3") as db:
            assert db.execute("SELECT ordinal, transport, result FROM slots").fetchall() == [(0, record, None)]
    with pytest.raises(FileExistsError):
        launch.claim("b" * 64, os.getuid(), os.getgid())


def test_live_rejects_no_grant_and_forged_socket(monkeypatch):
    import socket

    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: pytest.fail("real transport constructed"))
    monkeypatch.setattr(sys, "argv", ["planner_study", "live"])
    with pytest.raises(SystemExit, match="1"):
        study.main()
    if sys.platform != "linux":
        with pytest.raises(launch.ActivationError, match="activation_runner_invalid"):
            launch.operator_channel(-1)
        return
    first, second = socket.socketpair(type=socket.SOCK_SEQPACKET)
    with first, second:
        with pytest.raises(launch.ActivationError, match="activation_(operator_unverified|runner_invalid)"):
            launch.operator_channel(os.dup(first.fileno()))


def fake_response(payload=None):
    body = study.responses_payload(payload or study.supplied(study.CASES[0].plans[0]))
    body["usage"] = {"input_tokens": 20, "input_tokens_details": {"cached_tokens": 0},
                     "output_tokens": 10, "total_tokens": 30}
    return body


@pytest.fixture
def dispatch(tmp_path):
    ledger = study.Ledger(tmp_path.resolve() / "ledger", "a" * 64)
    yield ledger
    ledger.close()


def request(payload=None, **changes):
    return httpx.Request("POST", study.RESPONSES, json={"synthetic": True} if payload is None else payload,
                         headers={"authorization": "Bearer " + KEY, "openai-project": PROJECT,
                                  "accept-encoding": "identity", **changes})


def transport(dispatch, handler, *, ordinal=0, verify=lambda: None, gate=lambda: 10):
    block, index, arm = study.slots()[ordinal]
    identity = {"block": block, "case": study.CASES[index].id, "arm": arm,
                "request_sha256": study.digest({"synthetic": True})}
    return study.SlotTransport(httpx.MockTransport(handler), dispatch, ordinal, identity, KEY, PROJECT, verify, gate)


def test_dispatch_commits_before_forward_and_never_forwards_twice(dispatch):
    forwards = []

    def handler(req):
        assert dispatch.db.execute("SELECT ordinal, transport, result FROM slots").fetchall() == [(0, None, None)]
        assert req.extensions["timeout"]["read"] == 10
        forwards.append(req)
        return httpx.Response(200, json=fake_response())

    guard = transport(dispatch, handler)
    assert guard.handle_request(request()).status_code == 200
    assert json.loads(dispatch.db.execute("SELECT transport FROM slots").fetchone()[0])["attempt_count"] == 1
    with pytest.raises(study.StudyStop, match="duplicate_transport_attempt"):
        guard.handle_request(request())
    assert len(forwards) == 1
    with pytest.raises(study.StudyStop, match="slot_replay"):
        transport(dispatch, handler, ordinal=1).handle_request(request())


@pytest.mark.parametrize(("code", "mutate"), [
    ("returned_model_mismatch", lambda data: data.update(model="unexpected")),
    ("returned_model_mismatch", lambda data: data.pop("model")),
    ("response_incomplete", lambda data: data.update(status="incomplete")),
    ("provider_usage_invalid", lambda data: data.pop("usage")),
    ("provider_usage_invalid", lambda data: data["usage"].update(output_tokens=2049, total_tokens=2069)),
])
def test_untrusted_response_fails_closed(dispatch, code, mutate):
    data = fake_response()
    mutate(data)
    guard = transport(dispatch, lambda req: httpx.Response(200, json=data))
    with pytest.raises(study.StudyStop, match=code):
        guard.handle_request(request())
    record = json.loads(dispatch.db.execute("SELECT transport FROM slots").fetchone()[0])
    assert record["failure"] == code and record["state"] == "uncertain"
    assert "unexpected" not in study.encode(record)
    with pytest.raises(study.StudyStop, match="slot_replay"):
        dispatch.reserve(1)


@pytest.mark.parametrize(("status", "code"), [
    (307, "unexpected_redirect"), (401, "provider_authorization_or_quota"),
    (403, "provider_authorization_or_quota"), (429, "provider_authorization_or_quota"),
    (500, "provider_http_failure"), (None, "transport_timeout"),
])
def test_http_failures_are_single_uncertain_attempts(dispatch, status, code):
    count = 0

    def reply(req):
        nonlocal count
        count += 1
        if status is None:
            raise httpx.ReadTimeout("synthetic private detail")
        return httpx.Response(status, headers={"location": "https://example.invalid"}, content=b"private body")

    with pytest.raises(study.StudyStop, match=code):
        transport(dispatch, reply).handle_request(request())
    record = dispatch.db.execute("SELECT transport FROM slots").fetchone()[0]
    assert count == 1 and "private" not in record
    assert json.loads(record)["attempt_count"] == 1


@pytest.mark.parametrize("kind", ["body", "bearer", "project", "host", "slot", "profile", "source",
                                  "database", "order", "write"])
def test_dispatch_rejection_never_forwards(dispatch, kind):
    def drift():
        if kind in {"profile", "source", "database"}:
            raise study.StudyStop(f"{kind}_changed")

    if kind == "write":
        dispatch.db.execute("CREATE TRIGGER fail_reserve BEFORE INSERT ON slots BEGIN SELECT RAISE(ABORT, 'test'); END")
    guard = transport(dispatch, lambda _: pytest.fail("dispatched"), ordinal=1 if kind == "order" else 0, verify=drift)
    if kind == "slot":
        guard.identity["arm"] = "medium"
    req = request({"drifted": True} if kind == "body" else None)
    headers = {"bearer": "authorization", "project": "openai-project", "host": "host"}
    if kind in headers:
        req.headers[headers[kind]] = "drifted"
    with pytest.raises(study.StudyStop):
        guard.handle_request(req)
    assert dispatch.db.execute("SELECT count(*) FROM slots").fetchone() == (0,)


@pytest.mark.parametrize("reason", ["activation_outside_window", "activation_operator_stopped"])
def test_stop_between_reservation_and_forward(dispatch, reason):
    def gate():
        if dispatch.db.execute("SELECT count(*) FROM slots").fetchone()[0]:
            raise launch.ActivationError(reason)
        return 10

    guard = transport(dispatch, lambda _: pytest.fail("dispatched"), gate=gate)
    with pytest.raises(study.StudyStop, match=reason):
        guard.handle_request(request())
    record = json.loads(dispatch.db.execute("SELECT transport FROM slots").fetchone()[0])
    assert record["state"] == "stopped_before_forward" and record["attempt_count"] == 0


def test_failed_transport_evidence_leaves_pending(dispatch):
    dispatch.db.execute("CREATE TRIGGER fail_evidence BEFORE UPDATE ON slots BEGIN SELECT RAISE(ABORT, 'test'); END")
    with pytest.raises(study.StudyStop, match="transport_evidence_write_failed"):
        transport(dispatch, lambda req: httpx.Response(200, json=fake_response())).handle_request(request())
    assert dispatch.db.execute("SELECT transport, result FROM slots").fetchone() == (None, None)
    with pytest.raises(study.StudyStop, match="slot_replay"):
        dispatch.reserve(1)


def fake_manifest(pack):
    schema = offline_schema(pack)
    user = {"scope_type": "department", "scope_reference_resolved": True, "has_global_scope": False}
    contexts = {}
    for case in study.CASES:
        projection = build_semantic_catalog_projection(pack.semantic_catalog, case.question, schema, user)
        prompt = study.build_safe_prompt_projection(case.question, schema, user, projection)
        contexts[case.id] = None, schema, user, projection, prompt
    manifest = {"source": "a" * 40, "profiles": study.profile_specs(study.profiles()),
                "cases": {case.id: {"request_sha256": {
                    arm: study.digest(study.body(contexts[case.id][-1], arm)) for arm in study.ARMS
                }} for case in study.CASES},
                "schedule": [[block, study.CASES[index].id, arm] for block, index, arm in study.slots()]}
    manifest["schedule_sha256"] = study.digest(manifest["schedule"])
    manifest["fingerprint"] = study.digest(manifest)
    return manifest, contexts


def test_all_32_sdk_requests_remain_paired_and_complete(dispatch, monkeypatch):
    pack = study.load_it_operations_domain_pack()
    manifest, contexts = fake_manifest(pack)
    monkeypatch.setattr(study, "checked_snapshot", lambda _, pack, owner, manifest, case:
                        None if case is None else contexts[case.id])
    monkeypatch.setattr(study, "score", lambda *args: "pass")
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: pytest.fail("real transport constructed"))
    requests = []

    def factory():
        def handler(req):
            _, i, _ = study.slots()[len(requests)]
            requests.append(json.loads(req.content))
            return httpx.Response(200, json=fake_response(study.supplied(next(iter(study.CASES[i].plans), None))))
        return httpx.MockTransport(handler)

    verdict = study.run_live(None, "synthetic", manifest, {"project": PROJECT}, KEY, dispatch, lambda: 10, factory)
    assert verdict["passes"] == {"low": 16, "medium": 16}
    assert len(requests) == 32
    for i in range(0, len(requests), 2):
        assert {k for k in requests[i] if requests[i][k] != requests[i + 1][k]} == {"reasoning"}
    assert json.loads(dispatch.db.execute("SELECT seal FROM study").fetchone()[0])["state"] == "complete"


@pytest.mark.parametrize("failure", ["profile", "source", "parser"])
def test_runner_stops_and_seals_before_a_second_slot(dispatch, monkeypatch, failure):
    manifest, contexts = fake_manifest(study.load_it_operations_domain_pack())
    if failure == "profile":
        manifest["profiles"]["medium"]["fingerprint"] = "0" * 64
    if failure == "source":
        monkeypatch.setattr(study, "source", lambda: "0" * 40)
    if failure == "parser":
        monkeypatch.setattr(study, "checked_snapshot", lambda _, pack, owner, manifest, case:
                            None if case is None else contexts[case.id])
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: pytest.fail("real transport constructed"))
    forwards = []

    def reply(req):
        forwards.append(req)
        return httpx.Response(200, json=fake_response("malformed structured output"))

    reason = {"profile": "profile_identity_changed", "source": "live_source_mismatch",
              "parser": "provider_invalid"}[failure]
    with pytest.raises(study.StudyStop, match=reason):
        study.run_live(None, "synthetic", manifest, {"project": PROJECT}, KEY, dispatch,
                       lambda: 10, lambda: httpx.MockTransport(reply))
    assert len(forwards) == (failure == "parser")
    assert json.loads(dispatch.db.execute("SELECT seal FROM study").fetchone()[0]) == {
        "state": "stopped", "reason": reason}


def synthetic_approval(manifest, identity, uid, gid):
    return {"schema": "queryops-planner-study-approval-v1", "approved": True, "study_id": launch.STUDY_ID,
                **identity, "runner_uid": uid, "runner_gid": gid,
                "source": manifest["source"], "manifest_sha256": manifest["fingerprint"],
                "profiles": {arm: manifest["profiles"][arm]["fingerprint"] for arm in study.ARMS},
                "requests": {case: spec["request_sha256"] for case, spec in manifest["cases"].items()},
                "schedule": manifest["schedule"], "schedule_sha256": manifest["schedule_sha256"],
                "endpoint": study.RESPONSES, "model": study.MODEL, "returned_model": study.MODEL,
                "logical_slots": 32, "physical_dispatches": 32, "output_tokens_per_slot": 2048,
                "total_output_tokens": 65536, "median_latency_ratio": 2, "uncached_cost_ratio": 2,
                "project": PROJECT, "credential_version": "synthetic", "starts_utc": "2000-01-01T00:00:00Z",
                "expires_utc": "2099-01-01T00:00:00Z", "estimated_input_tokens": 4000,
                "estimated_cost_usd": "0.40", "credential_sha256": hashlib.sha256(KEY.encode()).hexdigest()}


def test_owner_approval_binds_all_exact_identities(monkeypatch):
    identity = {"host_sha256": "b" * 64, "state_root": str(launch.STATE), "state_device": 1, "state_inode": 2}
    monkeypatch.setattr(launch, "state_identity", lambda: identity)
    pack = study.load_it_operations_domain_pack()
    manifest, _ = fake_manifest(pack)
    approval = synthetic_approval(manifest, identity, os.getuid(), os.getgid())
    assert study.verify_approval(approval, manifest) > 0
    for key in ("source", "host_sha256", "state_root", "state_device", "state_inode", "manifest_sha256",
                "profiles", "requests", "schedule", "physical_dispatches", "median_latency_ratio"):
        with pytest.raises(study.StudyStop, match="approval_mismatch"):
            study.verify_approval({**approval, key: None}, manifest)
    with pytest.raises(launch.ActivationError, match="activation_outside_window"):
        study.verify_approval({**approval, "expires_utc": "2001-01-01T00:00:00Z"}, manifest)


@pytest.mark.parametrize("flag", ["h", "S"])
def test_live_source_rejects_hidden_index_entries(monkeypatch, flag):
    expected = "a" * 40
    answers = {"status": "", "rev-parse": expected, "symbolic-ref": "main",
               "ls-files": f"H AGENTS.md\n{flag} backend/scripts/planner_study.py"}
    monkeypatch.setattr(study, "git", lambda command, *_: answers[command])
    with pytest.raises(study.StudyStop, match="live_source_mismatch"):
        study.check_source(expected)
