"""Adversarial physical-boundary tests; every request stays in process."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from openai import OpenAI

from scripts.w6c_dispatch import DiagnosticStop, DispatchGuard, digest
from scripts.w6c_live import fake_response


def contracts():
    return [{"case_id": f"case-{i}", "body_sha256": digest({"model": "gpt-6.1-terra", "question": i})}
            for i in range(12)]


def request(index=0, **changes):
    body = {"model": "gpt-6.1-terra", "question": index}
    body.update(changes)
    return httpx.Request("POST", "https://api.openai.com/v1/responses",
                         headers={"authorization": "Bearer synthetic"}, json=body)


def guarded(tmp_path, handler=None, before=None):
    calls = []
    def dispatch(req):
        calls.append(req)
        return handler(req) if handler else httpx.Response(200, json=fake_response(None))
    guard = DispatchGuard(httpx.MockTransport(dispatch), tmp_path / "journal", "f" * 64,
                          contracts(), "synthetic", before_dispatch=before)
    return guard, calls


def test_twelve_calls_dispatch_exactly_once_and_thirteenth_cannot_dispatch(tmp_path):
    guard, calls = guarded(tmp_path)
    try:
        for i in range(12):
            guard.begin(f"case-{i}")
            guard.handle_request(request(i))
            guard.finish()
        with pytest.raises(DiagnosticStop):
            guard.begin("case-12")
        assert len(calls) == guard.logical_calls == guard.physical_dispatches == 12
        assert all(r["usage_complete"] and r["latency_ms"] >= 0 for r in guard.records)
    finally:
        guard.close()


@pytest.mark.parametrize("error", ["timeout", "connect", "interrupt", "redirect", "auth", "server",
                                   "missing_usage", "partial_usage", "invalid_usage", "model", "incomplete", "stream"])
def test_first_transport_or_telemetry_failure_is_terminal_and_usage_is_honest(tmp_path, error):
    class InterruptedStream(httpx.SyncByteStream):
        def __iter__(self):
            raise httpx.ReadTimeout("private-stream")
            yield b""

    def handler(req):
        if error == "timeout":
            raise httpx.ReadTimeout("private-timeout", request=req)
        if error == "connect":
            raise httpx.ConnectError("private-host", request=req)
        if error == "interrupt":
            raise KeyboardInterrupt()
        if error == "stream":
            return httpx.Response(200, stream=InterruptedStream())
        data = fake_response(None)
        status = {"redirect": 307, "auth": 401, "server": 500}.get(error, 200)
        if error == "missing_usage":
            data.pop("usage")
        if error == "partial_usage":
            data["usage"].pop("output_tokens")
        if error == "invalid_usage":
            data["usage"]["total_tokens"] = 100
        if error == "model":
            data["model"] = "gpt-5.6-terra"
        if error == "incomplete":
            data["status"] = "incomplete"
        return httpx.Response(status, json=data, headers={"location": "https://api.openai.com/v1/responses"})

    guard, calls = guarded(tmp_path, handler)
    try:
        guard.begin("case-0")
        with pytest.raises(BaseException):
            guard.handle_request(request())
        with pytest.raises(DiagnosticStop):
            guard.handle_request(request())
        with pytest.raises(DiagnosticStop):
            guard.begin("case-1")
        assert guard.physical_dispatches == len(calls) == 1
        if error in {"timeout", "connect", "interrupt", "stream", "missing_usage"}:
            assert guard.records[0]["usage_complete"] is False
            assert guard.records[0]["input_tokens"] is None
        if error == "partial_usage":
            assert guard.records[0]["output_tokens"] is None
        journal = (tmp_path / "journal").read_text()
        assert "private" not in journal and "Bearer" not in journal
    finally:
        guard.close()


@pytest.mark.parametrize("mutate", ["model", "url", "method", "key", "body"])
def test_request_identity_checked_before_any_dispatch(tmp_path, mutate):
    guard, calls = guarded(tmp_path)
    req = request()
    if mutate == "model":
        req = request(model="gpt-5.6-terra")
    if mutate == "url":
        req.url = httpx.URL("https://example.test/v1/responses")
    if mutate == "method":
        req.method = "GET"
    if mutate == "key":
        req.headers["authorization"] = "Bearer other"
    if mutate == "body":
        req = request(stream=True)
    try:
        guard.begin("case-0")
        with pytest.raises(DiagnosticStop):
            guard.handle_request(req)
        assert calls == [] and guard.physical_dispatches == 0
    finally:
        guard.close()


def test_reauthorization_at_transport_boundary_fails_before_reserving(tmp_path):
    def revoked(_):
        raise DiagnosticStop("authorization_changed")
    guard, calls = guarded(tmp_path, before=revoked)
    try:
        guard.begin("case-0")
        with pytest.raises(DiagnosticStop):
            guard.handle_request(request())
        assert calls == [] and guard.physical_dispatches == 0 and guard.stopped
    finally:
        guard.close()


@pytest.mark.parametrize("stage", ["started", "logical", "dispatch", "completed"])
def test_restart_never_resets_budget_even_after_interruption(tmp_path, stage):
    guard, calls = guarded(tmp_path)
    if stage != "started":
        guard.begin("case-0")
    if stage in {"dispatch", "completed"}:
        guard.handle_request(request())
    if stage == "completed":
        guard.finish()
    guard.close()
    with pytest.raises(FileExistsError):
        guarded(tmp_path)
    assert len(calls) <= 1


def test_reservation_is_durable_before_underlying_dispatch(tmp_path):
    def handler(_):
        events = [json.loads(line) for line in (tmp_path / "journal").read_text().splitlines()]
        assert events[-1]["event"] == "dispatch_reserved"
        assert events[-1]["physical_dispatch"] == 1
        return httpx.Response(200, json=fake_response(None))
    guard, _ = guarded(tmp_path, handler)
    try:
        guard.begin("case-0")
        guard.handle_request(request())
    finally:
        guard.close()


def test_journal_failure_prevents_dispatch_and_is_terminal(tmp_path, monkeypatch):
    guard, calls = guarded(tmp_path)
    guard.begin("case-0")
    monkeypatch.setattr(guard, "_write", lambda _: (_ for _ in ()).throw(OSError("disk full")))
    try:
        with pytest.raises(OSError):
            guard.handle_request(request())
        assert calls == [] and guard.stopped
    finally:
        guard.close()


def test_concurrent_duplicate_execution_cannot_dispatch_twice(tmp_path):
    guard, calls = guarded(tmp_path)
    guard.begin("case-0")
    def attempt(_):
        try:
            guard.handle_request(request())
        except DiagnosticStop:
            pass
    try:
        with ThreadPoolExecutor(2) as executor:
            list(executor.map(attempt, range(2)))
        assert len(calls) == guard.physical_dispatches == 1
    finally:
        guard.close()


@pytest.mark.parametrize("mode", ["retry", "redirect", "duplicate_success"])
def test_real_sdk_cannot_retry_redirect_or_repeat_a_question(tmp_path, monkeypatch, mode):
    calls = []
    body = {"model": "gpt-6.1-terra", "input": "test", "store": False}
    selected = copy.deepcopy(contracts())
    selected[0]["body_sha256"] = digest(body)
    def handler(_):
        calls.append(True)
        status = {"retry": 500, "redirect": 307, "duplicate_success": 200}[mode]
        return httpx.Response(status, json=fake_response(None),
                              headers={"location": "https://api.openai.com/v1/responses"})
    guard = DispatchGuard(httpx.MockTransport(handler), tmp_path / "journal", "f" * 64, selected, "synthetic")
    client = OpenAI(api_key="synthetic", base_url="https://api.openai.com/v1", max_retries=2,
                    http_client=httpx.Client(transport=guard, follow_redirects=True))
    monkeypatch.setattr("openai._base_client.time.sleep", lambda _: None)
    try:
        guard.begin("case-0")
        if mode == "duplicate_success":
            client.responses.create(**body)
        with pytest.raises(Exception):
            client.responses.create(**body)
        assert len(calls) == guard.physical_dispatches == 1
    finally:
        client.close()
