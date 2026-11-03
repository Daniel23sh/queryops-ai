"""Version/approval isolation and adversarial six-dispatch boundary, all fake HTTP."""
import copy
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
import pytest

from scripts import w6c_live as v2, w6c_v3 as v3
from scripts.w6c_dispatch import DiagnosticStop, DispatchGuard, digest


def contracts():
    return [{"case_id": i, "body_sha256": digest({"model": "gpt-6.1-terra", "case": i})}
            for i in v3.CASE_IDS]


def request(index=0):
    return httpx.Request("POST", "https://api.openai.com/v1/responses",
        headers={"authorization": "Bearer synthetic"},
        json={"model": "gpt-6.1-terra", "case": v3.CASE_IDS[index]})


def guard_at(path, handler=None, before=None):
    calls = []
    def dispatch(req):
        calls.append(req)
        events = [json.loads(line) for line in path.read_text().splitlines()]
        assert events[-1]["event"] == "dispatch_reserved"
        return handler(req) if handler else httpx.Response(200, json=v3.fake_response(None))
    return v3.V3DispatchGuard(httpx.MockTransport(dispatch), path, "f" * 64,
                             contracts(), "synthetic", before_dispatch=before), calls


def approval_for(manifest):
    return {"schema": "queryops-w6c-operator-approval-v3", "approved": True,
        "fingerprint": manifest["fingerprint"], "source_git_sha": manifest["source_git_sha"],
        "model": "gpt-6.1-terra", "max_logical_calls": 6, "max_physical_dispatches": 6,
        "max_dispatches_per_question": 1, "no_retry_no_resume": True}


def test_exact_selection_bytes_frozen_contract_and_v2_unchanged():
    config, lock, cases, _ = v3.frozen_inputs()
    assert tuple(c["id"] for c in cases) == v3.CASE_IDS
    assert config["settings"] == v2.frozen_inputs()[0]["settings"]
    assert config["execution_authorized"] is False
    assert DispatchGuard.max_calls == 12 and v3.V3DispatchGuard.max_calls == 6
    assert v3.STATE != v2.STATE and v3.STATE.parent == v2.STATE.parent
    for case, row in zip(cases, config["cases"], strict=True):
        assert hashlib.sha256(case["question"].encode()).hexdigest() == row["question_sha256"]
        assert case in json.loads((v2.ARTIFACTS / "heldout-v1.json").read_text())["cases"]
    assert lock == v2.frozen_inputs()[1]


@pytest.mark.parametrize("mutation", ["order", "budget", "settings", "approval", "hash", "acceptance"])
def test_v3_config_drift_fails_before_artifact_execution_or_database(tmp_path, monkeypatch, mutation):
    config = copy.deepcopy(v3.frozen_inputs()[0])
    if mutation == "order":
        config["cases"].reverse()
    elif mutation == "budget":
        config["max_physical_dispatches"] = 12
    elif mutation == "settings":
        config["settings"]["OPENAI_MAX_RETRIES"] = "1"
    elif mutation == "approval":
        config["execution_authorized"] = True
    elif mutation == "hash":
        config["cases"][0]["question_sha256"] = "f" * 64
    else:
        config["acceptance"]["other_cases"] = "weaker"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    monkeypatch.setattr(v3, "CONFIG", path)
    monkeypatch.setattr(v3, "source_identity", lambda: "a" * 40)
    monkeypatch.setattr(v3, "initialize", lambda *_: pytest.fail("initialization reached"))
    with pytest.raises(DiagnosticStop, match="v3_contract_invalid"):
        v3.prepare(datetime.now(UTC).isoformat(), initialize_database=True)


def test_six_calls_then_budget_exhaustion(tmp_path):
    guard, calls = guard_at(tmp_path / "journal")
    try:
        for index, case in enumerate(v3.CASE_IDS):
            guard.begin(case)
            guard.handle_request(request(index))
            guard.finish()
        with pytest.raises(DiagnosticStop):
            guard.begin(v3.CASE_IDS[0])
        assert len(calls) == guard.logical_calls == guard.physical_dispatches == 6
        assert os.stat(tmp_path / "journal").st_mode & 0o777 == 0o600
    finally:
        guard.close()


@pytest.mark.parametrize("stage", ["started", "logical", "dispatched", "completed", "failed"])
def test_every_restart_is_rejected_even_with_new_fingerprint(tmp_path, stage):
    guard, calls = guard_at(tmp_path / "journal")
    if stage != "started":
        guard.begin(v3.CASE_IDS[0])
    if stage in {"dispatched", "completed"}:
        guard.handle_request(request())
    if stage == "completed":
        guard.finish()
    if stage == "failed":
        with pytest.raises(DiagnosticStop):
            guard.stop("physical_budget_exhausted")
    guard.close()
    with pytest.raises(FileExistsError):
        v3.V3DispatchGuard(httpx.MockTransport(lambda _: pytest.fail("resumed")),
                          tmp_path / "journal", "new-fingerprint", contracts(), "synthetic")
    assert len(calls) <= 1


@pytest.mark.parametrize("failure", ["timeout", "interrupt", "missing_usage", "malformed", "auth", "redirect"])
def test_first_failure_is_terminal_and_does_not_expose_details(tmp_path, failure):
    def handler(req):
        if failure == "timeout":
            raise httpx.ReadTimeout("private", request=req)
        if failure == "interrupt":
            raise KeyboardInterrupt("private")
        if failure == "malformed":
            return httpx.Response(200, text="private")
        data = v3.fake_response(None)
        if failure == "missing_usage":
            data.pop("usage")
        return httpx.Response({"auth": 401, "redirect": 307}.get(failure, 200), json=data)
    guard, calls = guard_at(tmp_path / "journal", handler)
    try:
        guard.begin(v3.CASE_IDS[0])
        with pytest.raises(BaseException):
            guard.handle_request(request())
        with pytest.raises(DiagnosticStop):
            guard.begin(v3.CASE_IDS[1])
        with pytest.raises(DiagnosticStop):
            guard.handle_request(request())
        assert len(calls) == guard.physical_dispatches == 1
        assert "private" not in (tmp_path / "journal").read_text()
        if failure in {"timeout", "interrupt", "missing_usage", "malformed"}:
            assert guard.records[0]["usage_complete"] is False
            assert guard.records[0]["input_tokens"] is None
    finally:
        guard.close()


def test_concurrent_duplicate_dispatch_is_reserved_only_once(tmp_path):
    guard, calls = guard_at(tmp_path / "journal")
    guard.begin(v3.CASE_IDS[0])
    def attempt(_):
        try:
            guard.handle_request(request())
        except DiagnosticStop:
            pass
    try:
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(attempt, range(2)))
        assert len(calls) == guard.physical_dispatches == 1
    finally:
        guard.close()


@pytest.mark.parametrize("change", ["body", "credential", "authorization", "write", "fsync"])
def test_checks_and_durable_reservation_precede_physical_transport(tmp_path, monkeypatch, change):
    def before(_):
        if change == "authorization":
            raise DiagnosticStop("authorization_changed")
    guard, calls = guard_at(tmp_path / "journal", before=before)
    try:
        guard.begin(v3.CASE_IDS[0])
        req = request()
        if change == "body":
            req = request(1)
        if change == "credential":
            req.headers["authorization"] = "Bearer other"
        if change == "write":
            monkeypatch.setattr(os, "write", lambda *_: 0)
        if change == "fsync":
            monkeypatch.setattr(os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("private")))
        with pytest.raises(BaseException):
            guard.handle_request(req)
        assert not calls and guard.stopped
    finally:
        guard.close()


@pytest.mark.parametrize("mutation", ["v2", "absent", "fingerprint", "budget", "source", "model", "extra", "bool"])
def test_exact_separate_approval_required(mutation):
    manifest = {"fingerprint": "f" * 64, "source_git_sha": "a" * 40,
                "settings": {"OPENAI_MODEL": "gpt-6.1-terra"}}
    approval = approval_for(manifest)
    v3.verify_approval(approval, manifest)
    if mutation == "v2":
        from tests.test_w6c_live import approval_for as historical_approval
        approval = historical_approval(manifest)
    elif mutation == "absent":
        approval = None
    elif mutation == "extra":
        approval["extra"] = True
    elif mutation == "bool":
        approval["approved"] = 1
    else:
        key = {"fingerprint": "fingerprint", "budget": "max_physical_dispatches",
               "source": "source_git_sha", "model": "model"}[mutation]
        approval[key] = "different"
    with pytest.raises(DiagnosticStop):
        v3.verify_approval(approval, manifest)


@pytest.mark.parametrize("version", [v2, v3])
@pytest.mark.parametrize("mode", ["--live", "--dry-run", "--initialize"])
def test_cli_artifacts_cannot_create_or_read_either_live_journal(version, mode, tmp_path, monkeypatch):
    monkeypatch.setattr(v3.httpx, "HTTPTransport", lambda **_: pytest.fail("network reached"))
    monkeypatch.setattr(v3, "prepare", lambda *_a, **_k: pytest.fail("preparation reached"))
    for args in ([mode, "--out", str(version.STATE / "dispatch.jsonl")],
                 [mode, "--manifest", str(version.STATE / "dispatch.jsonl"), "--out", str(tmp_path / "out")]):
        assert v3.main(args) == 2


@pytest.mark.parametrize("database", ["queryops_w6c_v2_test", "queryops", "queryops_w6c_v3_test?host=remote"])
def test_v3_db_cannot_alias_v2_or_application(monkeypatch, database):
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_DISPOSABLE", "1")
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1/" + database)
    with pytest.raises(DiagnosticStop):
        v3.disposable_url()


def test_approval_must_be_private_owned_regular_file(tmp_path):
    path = tmp_path / "approval"
    path.write_text('{}')
    path.chmod(0o644)
    with pytest.raises(DiagnosticStop):
        v3.read_approval(path)
    path.chmod(0o600)
    assert v3.read_approval(path) == {}
    link = tmp_path / "symlink"
    link.symlink_to(path)
    with pytest.raises(DiagnosticStop):
        v3.read_approval(link)


def test_version_guard_cannot_accept_other_version_selection(tmp_path):
    from tests.test_w6c_dispatch import contracts as v2_contracts
    with pytest.raises(DiagnosticStop):
        DispatchGuard(httpx.MockTransport(lambda _: None), tmp_path / "v2", "f", contracts(), "synthetic")
    with pytest.raises(DiagnosticStop):
        v3.V3DispatchGuard(httpx.MockTransport(lambda _: None), tmp_path / "v3", "f", v2_contracts(), "synthetic")
    assert not (tmp_path / "v2").exists() and not (tmp_path / "v3").exists()


@pytest.mark.parametrize("mutation", ["none", "symlink", "ancestor_symlink", "writable", "mode", "owner"])
def test_owned_journal_directory_validation_and_creation_fsync(monkeypatch, mutation):
    import stat
    import tempfile
    from pathlib import Path
    # A safe repository-owned temporary hierarchy avoids accepting /tmp's
    # world-writable parent and never touches the actual per-account state.
    with tempfile.TemporaryDirectory(prefix=".w6c-journal-test-", dir=v3.ROOT) as raw:
        base = Path(raw)
        state = base / "private" / "v3"
        monkeypatch.setattr(v3, "STATE", state)
        if mutation != "none":
            state.mkdir(mode=0o700, parents=True)
        if mutation == "symlink":
            state.rmdir()
            state.symlink_to(base, target_is_directory=True)
        elif mutation == "ancestor_symlink":
            state.rmdir()
            state.parent.rmdir()
            state.parent.symlink_to(base, target_is_directory=True)
        elif mutation == "writable":
            state.parent.chmod(0o777)
        elif mutation == "mode":
            state.chmod(0o755)
        elif mutation == "owner":
            original = Path.lstat
            def lstat(path):
                info = original(path)
                if path == state:
                    fields = list(info)
                    fields[4] = os.getuid() + 1000
                    return os.stat_result(fields)
                return info
            monkeypatch.setattr(Path, "lstat", lstat)
        synced = []
        original_fsync = os.fsync
        def fsync(fd):
            assert stat.S_ISDIR(os.fstat(fd).st_mode)
            synced.append(fd)
            original_fsync(fd)
        monkeypatch.setattr(os, "fsync", fsync)
        if mutation == "none":
            assert v3.live_journal() == state / "dispatch.jsonl"
            assert len(synced) == 2
            assert stat.S_IMODE(state.stat().st_mode) == 0o700
            assert not (state / "dispatch.jsonl").exists()
        else:
            with pytest.raises(DiagnosticStop):
                v3.live_journal()
        assert not v2.STATE.is_relative_to(base)


def test_state_comes_from_os_account_not_environment_home(monkeypatch):
    import pwd
    from pathlib import Path
    monkeypatch.setenv("HOME", "/untrusted-home")
    expected = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/queryops/w6c-live-v3"
    assert v3.STATE == expected
