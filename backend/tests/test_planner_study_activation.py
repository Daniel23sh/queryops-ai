"""Deterministic activation tests. Every provider response is synthetic."""
from contextlib import nullcontext
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
from scripts import planner_study_activation as launch
from scripts.semantic_ownership_fixtures import offline_schema


KEY = "synthetic-study-key-not-a-credential"


def fake_score(*args, diagnostics):
    diagnostics.update(version=1, outcome=args[-1].outcome.value, clarification_reason=None,
                       plan_comparison="not_evaluated", mismatch_axes=[], result_multiset_match="not_evaluated")
    return "pass"


@pytest.fixture
def state(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    root.chmod(0o700)
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
    launch.claim("a" * 64)
except FileExistsError:
    raise SystemExit(2)
"""
    env = {"PATH": os.environ["PATH"]}
    commands = [subprocess.Popen([sys.executable, "-B", "-c", program], cwd=path, env=env) for path in callers]
    assert sorted(p.wait(timeout=15) for p in commands) == [0, 2]
    assert (launch.CLAIM / "manifest.sha256").read_text() == "a" * 64 + "\n"
    with pytest.raises(FileExistsError):
        launch.claim("b" * 64)


def test_claim_sync_error_and_ledger_init_failure_leave_claim(state, monkeypatch):
    with monkeypatch.context() as patch:
        def fail(path):
            raise OSError("synthetic sync failure")

        patch.setattr(launch, "sync_directory", fail)
        with pytest.raises(OSError):
            launch.claim("a" * 64)
    assert launch.CLAIM.is_dir()
    with pytest.raises(FileExistsError):
        launch.claim("a" * 64)
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
from scripts import planner_study_activation as launch
from scripts import planner_study as study
import os, signal
launch.STATE = Path({str(state)!r})
launch.CLAIM = launch.STATE / "test-claim"
launch.EVIDENCE = launch.CLAIM / "evidence"
launch.claim("a" * 64)
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
        launch.claim("b" * 64)


def test_live_rejects_missing_paid_flag_despite_environment_key(state, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: pytest.fail("real transport constructed"))
    monkeypatch.setattr(sys, "argv", ["planner_study", "live"])
    with pytest.raises(SystemExit, match="1"):
        study.main()
    assert not launch.CLAIM.exists()


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
                         headers={"authorization": "Bearer " + KEY,
                                  "accept-encoding": "identity", **changes})


def transport(dispatch, handler, *, ordinal=0, verify=lambda: None, gate=lambda: 10):
    block, index, arm = study.slots()[ordinal]
    identity = {"block": block, "case": study.CASES[index].id, "arm": arm,
                "request_sha256": study.digest({"synthetic": True})}
    return study.SlotTransport(httpx.MockTransport(handler), dispatch, ordinal, identity, KEY, verify, gate)


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


@pytest.mark.parametrize("kind", ["body", "bearer", "project", "host", "slot", "profile", "source", "runtime",
                                  "database", "order", "write"])
def test_dispatch_rejection_never_forwards(dispatch, kind):
    def drift():
        if kind in {"profile", "source", "runtime", "database"}:
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


@pytest.mark.parametrize("reason", ["activation_deadline_exceeded", "activation_claim_changed"])
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
                "cases": {case.id: {"input_utf8_bytes": len(study.encode(contexts[case.id][-1]).encode()), "request_sha256": {
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
    monkeypatch.setattr(study, "score", fake_score)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: pytest.fail("real transport constructed"))
    requests = []
    monkeypatch.setenv("OPENAI_PROJECT_ID", "proj_must_not_be_inherited")

    def factory():
        def handler(req):
            assert "openai-project" not in req.headers
            _, i, _ = study.slots()[len(requests)]
            requests.append(json.loads(req.content))
            return httpx.Response(200, json=fake_response(study.supplied(next(iter(study.CASES[i].plans), None))))
        return httpx.MockTransport(handler)

    verdict = study.run_live(None, "synthetic", manifest, KEY, dispatch, lambda: 10, factory)
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
        monkeypatch.setattr(study, "git", lambda *_: "0" * 40)
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
        study.run_live(None, "synthetic", manifest, KEY, dispatch,
                       lambda: 10, lambda: httpx.MockTransport(reply))
    assert len(forwards) == (failure == "parser")
    assert json.loads(dispatch.db.execute("SELECT seal FROM study").fetchone()[0]) == {
        "state": "stopped", "reason": reason}


@pytest.mark.parametrize("flag", ["h", "S"])
def test_live_source_rejects_hidden_index_entries(monkeypatch, flag):
    expected = "a" * 40
    answers = {"rev-parse": expected, "symbolic-ref": "main",
               "ls-files": f"H AGENTS.md\n{flag} backend/scripts/planner_study.py"}
    monkeypatch.setattr(study, "git", lambda command, *_: answers[command])
    with pytest.raises(launch.ActivationError, match="live_source_mismatch"):
        study.check_source(expected)


def test_live_source_checks_raw_bytes_even_when_git_reports_clean(monkeypatch, tmp_path):
    root = tmp_path.resolve()
    source = root / "tracked.py"
    contents = b"# approved\n"
    source.write_bytes(contents)
    expected = "a" * 40
    blob = hashlib.sha1(b"blob 11\0" + contents, usedforsecurity=False).hexdigest()
    answers = {"rev-parse": expected, "symbolic-ref": "main", "diff": "",
               "ls-tree": f"100644 blob {blob}\ttracked.py\0"}
    monkeypatch.setattr(study, "ROOT", root)
    monkeypatch.setattr(study, "git", lambda command, *args:
                        ("H tracked.py" if args == ("-v",) else "") if command == "ls-files" else answers[command])
    study.check_source(expected)
    source.chmod(0o755)
    with pytest.raises(launch.ActivationError, match="live_source_mismatch"):
        study.check_source(expected)
    source.chmod(0o644)
    source.write_bytes(b"# approved\r\n")
    with pytest.raises(launch.ActivationError, match="live_source_mismatch"):
        study.check_source(expected)


@pytest.fixture
def local_activation(state, monkeypatch):
    manifest, contexts = fake_manifest(study.load_it_operations_domain_pack())
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("OPENAI_PROJECT_ID", "proj_must_not_be_inherited")
    owner = "b" * 32
    (state / "owner").write_text(owner)
    (state / "manifest.json").write_text(study.encode(manifest))

    class Engine:
        def dispose(self):
            pass

    engine = Engine()
    monkeypatch.setattr(study, "owned_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(study, "Session", lambda _: nullcontext(None))
    monkeypatch.setattr(study, "checked_snapshot", lambda _, pack, owner, manifest, case=None:
                        contexts[case.id] if case is not None else None)
    monkeypatch.setattr(study, "offline_controls", lambda *args: None)
    monkeypatch.setattr(study, "score", fake_score)
    forwards = []

    def reply(req):
        assert "openai-project" not in req.headers
        with sqlite3.connect(launch.EVIDENCE / "ledger" / "slots.sqlite3") as db:
            assert db.execute("SELECT count(*) FROM slots WHERE result IS NULL").fetchone() == (1,)
            assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert (launch.CLAIM / "manifest.sha256").read_text() == manifest["fingerprint"] + "\n"
        _, index, _ = study.slots()[len(forwards)]
        forwards.append(req)
        return httpx.Response(200, json=fake_response(study.supplied(next(iter(study.CASES[index].plans), None))))

    def factory(**kwargs):
        assert kwargs == {"verify": True, "trust_env": False, "retries": 0}
        return httpx.MockTransport(reply)

    monkeypatch.setattr(httpx, "HTTPTransport", factory)
    return engine, owner, manifest, forwards


def test_local_cli_completes_32_slots_and_cannot_repeat(local_activation, monkeypatch, capsys):
    _, _, _, forwards = local_activation
    monkeypatch.setattr(sys, "argv", ["planner_study", "live", "--allow-paid-study",
                                      "--owner-receipt", str(launch.STATE / "owner"),
                                      "--manifest", str(launch.STATE / "manifest.json")])
    assert study.main() == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["passes"] == {"low": 16, "medium": 16}
    assert len(forwards) == 32
    assert not (launch.STATE / "approval.json").exists()
    assert not list(launch.STATE.glob("credential-*"))
    with pytest.raises(study.StudyStop, match="activation_already_claimed"):
        study.live(*local_activation[:3])
    with sqlite3.connect(launch.EVIDENCE / "ledger" / "slots.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM slots WHERE result IS NOT NULL").fetchone() == (32,)
        evidence = study.encode(db.execute("SELECT * FROM slots").fetchall())
        assert KEY not in evidence and "Bearer" not in evidence and "semantic_plan" not in evidence
        assert json.loads(db.execute("SELECT seal FROM study").fetchone()[0])["state"] == "complete"


@pytest.mark.parametrize("failure", ["source", "unauthorized", "credential", "state_permissions"])
def test_local_preflight_failures_make_no_claim_or_forward(local_activation, monkeypatch, failure):
    _, _, _, forwards = local_activation
    if failure in {"source", "unauthorized"}:
        def fail(*args, **kwargs):
            raise study.StudyStop("synthetic_preflight_failure")
        monkeypatch.setattr(study, "checked_snapshot" if failure == "source" else "offline_controls", fail)
    elif failure == "credential":
        monkeypatch.setenv("OPENAI_API_KEY", "")
    else:
        launch.STATE.chmod(0o755)
    with pytest.raises((study.StudyStop, launch.ActivationError)):
        study.live(*local_activation[:3])
    assert not launch.CLAIM.exists() and forwards == []


@pytest.mark.parametrize("failure", ["claim_sync", "ledger_open", "reservation"])
def test_local_persistence_failure_never_forwards_and_cannot_resume(local_activation, monkeypatch, failure):
    _, _, _, forwards = local_activation
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic persistence failure")
    if failure == "claim_sync":
        monkeypatch.setattr(launch, "sync_directory", fail)
    elif failure == "ledger_open":
        monkeypatch.setattr(sqlite3, "connect", fail)
    else:
        monkeypatch.setattr(study.Ledger, "reserve", fail)
    with pytest.raises((sqlite3.OperationalError, study.StudyStop)):
        study.live(*local_activation[:3])
    assert launch.CLAIM.is_dir() and forwards == []
    with pytest.raises(study.StudyStop, match="activation_already_claimed"):
        study.live(*local_activation[:3])


@pytest.mark.parametrize("failure", ["source", "claim", "timeout", "model", "telemetry", "invalid_json"])
def test_local_post_dispatch_failure_is_terminal(local_activation, monkeypatch, failure):
    _, _, _, forwards = local_activation
    def reply(req):
        forwards.append(req)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic private timeout")
        if failure == "source":
            def drift(*args, **kwargs):
                raise study.StudyStop("live_source_mismatch")
            monkeypatch.setattr(study, "checked_snapshot", drift)
        if failure == "claim":
            (launch.CLAIM / "manifest.sha256").write_text("changed")
        data = fake_response()
        if failure == "model":
            data["model"] = "wrong"
        if failure == "telemetry":
            data.pop("usage")
        return httpx.Response(200, content=b"invalid" if failure == "invalid_json" else study.encode(data).encode())
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: httpx.MockTransport(reply))
    with pytest.raises((study.StudyStop, launch.ActivationError)):
        study.live(*local_activation[:3])
    assert len(forwards) == 1
    with pytest.raises(study.StudyStop, match="activation_already_claimed"):
        study.live(*local_activation[:3])


@pytest.mark.parametrize("stop", ["kill", "deadline", "race"])
def test_local_process_interruption_preserves_pending_and_blocks_restart(local_activation, stop):
    program = f"""
import os, signal, time
from pathlib import Path
from contextlib import nullcontext
import httpx
from scripts import planner_study as study
from scripts import planner_study_activation as activation
from tests.test_planner_study_activation import fake_manifest, fake_response
activation.STATE = Path({str(launch.STATE)!r})
activation.CLAIM = activation.STATE / "test-claim"
activation.EVIDENCE = activation.CLAIM / "evidence"
manifest, contexts = fake_manifest(study.load_it_operations_domain_pack())
class Engine:
    def dispose(self): pass
study.owned_engine = lambda *args, **kwargs: Engine()
study.Session = lambda _: nullcontext(None)
study.checked_snapshot = lambda _, pack, owner, manifest, case=None: contexts[case.id] if case else None
study.offline_controls = lambda *args: None
from tests.test_planner_study_activation import fake_score
study.score = fake_score
requests = []
def reply(request):
    if {stop!r} == "kill": os.kill(os.getpid(), signal.SIGKILL)
    if {stop!r} == "race":
        _, index, _ = study.slots()[len(requests)]
        requests.append(request)
        time.sleep(0.01)
        return httpx.Response(200, json=fake_response(study.supplied(next(iter(study.CASES[index].plans), None))))
    time.sleep(10)
    raise AssertionError("deadline did not stop the request")
httpx.HTTPTransport = lambda **kwargs: httpx.MockTransport(reply)
if {stop!r} == "deadline":
    set_timer = signal.setitimer
    signal.setitimer = lambda which, seconds: set_timer(which, min(seconds, 3))
try:
    study.live(Engine(), "b" * 32, manifest)
except FileExistsError:
    raise SystemExit(2)
except study.StudyStop as exc:
    if str(exc) == "activation_already_claimed": raise SystemExit(2)
    raise
"""
    if stop == "race":
        processes = [subprocess.Popen([sys.executable, "-B", "-c", program], cwd=study.ROOT / "backend")
                     for _ in range(2)]
        assert sorted(p.wait(timeout=15) for p in processes) == [0, 2]
        with sqlite3.connect(launch.EVIDENCE / "ledger" / "slots.sqlite3") as db:
            assert db.execute("SELECT count(*), count(result) FROM slots").fetchone() == (32, 32)
        with pytest.raises(study.StudyStop, match="activation_already_claimed"):
            study.live(*local_activation[:3])
        return
    result = subprocess.run([sys.executable, "-B", "-c", program], cwd=study.ROOT / "backend", timeout=15)
    assert result.returncode == (-9 if stop == "kill" else -14)
    with sqlite3.connect(launch.EVIDENCE / "ledger" / "slots.sqlite3") as db:
        assert db.execute("SELECT ordinal, transport, result FROM slots").fetchall() == [(0, None, None)]
    with pytest.raises(study.StudyStop, match="activation_already_claimed"):
        study.live(*local_activation[:3])


def test_fixed_state_uses_account_home_not_environment(monkeypatch):
    import importlib.util
    from pathlib import Path
    import pwd
    monkeypatch.setenv("HOME", "/unrelated-home")
    spec = importlib.util.spec_from_file_location("isolated_activation", launch.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.STATE == Path(pwd.getpwuid(os.getuid()).pw_dir).resolve() / (
        "Library/Application Support/QueryOps/queryops-planner-study-v1")


def test_live_source_with_real_git_allows_ignored_environment_and_rejects_changes(tmp_path):
    root = tmp_path.resolve() / "checkout"
    root.mkdir()

    def command(*args):
        return subprocess.check_output(["git", "-C", str(root), "-c", "user.name=Synthetic",
                                        "-c", "user.email=synthetic@queryops.invalid", "-c", "commit.gpgsign=false",
                                        *args], env=launch.ENV, text=True).strip()

    command("init", "-b", "main")
    (root / ".gitignore").write_text(".venv/\n.env\n")
    tracked = root / "tracked.py"
    tracked.write_bytes(b"# reviewed\n")
    command("add", ".")
    command("commit", "-m", "Synthetic source")
    expected = command("rev-parse", "HEAD")
    command("update-ref", "refs/remotes/origin/main", expected)
    (root / ".venv").mkdir()
    (root / ".venv" / "placeholder").touch()
    (root / ".env").write_text("SYNTHETIC=1\n")
    launch.verify_source(root, expected, lambda *args: launch.git(root, *args))
    untracked = root / "unexpected.py"
    untracked.touch()
    with pytest.raises(launch.ActivationError, match="live_source_mismatch"):
        launch.verify_source(root, expected, lambda *args: launch.git(root, *args))
    untracked.unlink()
    tracked.write_bytes(b"# reviewed\r\n")
    with pytest.raises(launch.ActivationError, match="live_source_mismatch"):
        launch.verify_source(root, expected, lambda *args: launch.git(root, *args))


@pytest.mark.parametrize("value", [KEY, '"' + KEY + '" # comment', "'" + KEY + "'"])
def test_existing_dotenv_key_without_project(tmp_path, monkeypatch, value):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = tmp_path / ".env"
    config.write_text("OPENAI_MODEL=ignored-application-default\nexport OPENAI_API_KEY = " + value + "\n")
    assert launch.local_api_key(config) == KEY


@pytest.mark.parametrize("content", ["", "OPENAI_API_KEY=\n", "OPENAI_API_KEY=bad value\n",
                                     "OPENAI_API_KEY=" + KEY + "\nOPENAI_API_KEY=" + KEY + "\n"])
def test_invalid_local_key_configuration_fails_closed(tmp_path, monkeypatch, content):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = tmp_path / ".env"
    config.write_text(content)
    with pytest.raises(launch.ActivationError, match="activation_credential_invalid"):
        launch.local_api_key(config)


def test_environment_key_precedence_does_not_need_a_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    assert launch.local_api_key(tmp_path / "missing") == KEY
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(launch.ActivationError, match="activation_credential_invalid"):
        launch.local_api_key(tmp_path / "missing")


def test_local_cli_reads_existing_dotenv_with_no_manual_activation_files(local_activation, monkeypatch):
    repository = launch.STATE / "checkout"
    repository.mkdir()
    (repository / ".env").write_text("OPENAI_API_KEY=" + KEY + "\nOPENAI_MODEL=ignored-default\n")
    monkeypatch.setattr(study, "ROOT", repository)
    monkeypatch.delenv("OPENAI_API_KEY")
    assert study.live(*local_activation[:3])["passes"] == {"low": 16, "medium": 16}
    assert not (launch.STATE / "approval.json").exists()
    assert not list(launch.STATE.glob("credential-*"))


@pytest.mark.parametrize("action", ["initialize", "manifest", "dry-run"])
def test_paid_flag_is_exclusive_to_live(action, state, monkeypatch):
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: pytest.fail("real transport constructed"))
    monkeypatch.setattr(sys, "argv", ["planner_study", action, "--allow-paid-study"])
    with pytest.raises(SystemExit, match="1"):
        study.main()
    assert not launch.CLAIM.exists()


@pytest.mark.parametrize("failure", ["writable", "symlink", "oversized"])
def test_unsafe_dotenv_is_rejected(tmp_path, monkeypatch, failure):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = tmp_path / ".env"
    config.write_text("OPENAI_API_KEY=" + KEY + "\n")
    if failure == "writable":
        config.chmod(0o666)
    elif failure == "symlink":
        target = tmp_path / "target"
        config.rename(target)
        config.symlink_to(target)
    else:
        config.write_text("#" * (launch.MAX_DOCUMENT + 1))
    with pytest.raises((launch.ActivationError, OSError)):
        launch.local_api_key(config)



def test_local_state_is_created_automatically_and_synced(local_activation, monkeypatch):
    parent = launch.STATE
    monkeypatch.setattr(launch, "STATE", parent / "new-parent" / "state")
    monkeypatch.setattr(launch, "CLAIM", launch.STATE / "claimed")
    monkeypatch.setattr(launch, "EVIDENCE", launch.CLAIM / "evidence")
    synced = []
    sync = launch.sync_directory
    factory = httpx.HTTPTransport

    def sync_directory(path):
        sync(path)
        synced.append(path)

    def transport(**kwargs):
        assert parent in synced and parent / "new-parent" in synced
        return factory(**kwargs)

    monkeypatch.setattr(launch, "sync_directory", sync_directory)
    monkeypatch.setattr(httpx, "HTTPTransport", transport)
    assert study.live(*local_activation[:3])["passes"] == {"low": 16, "medium": 16}
    launch.private(launch.STATE, directory=True)
    assert (launch.CLAIM / "manifest.sha256").read_text() == local_activation[2]["fingerprint"] + "\n"
