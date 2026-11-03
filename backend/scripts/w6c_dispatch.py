"""Single-use W6c HTTP boundary. Never imported by the product provider factory."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, NoReturn

import httpx

from app.query_engine.openai_provider import _usage_counts


class DiagnosticStop(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def transport_failure_category(exc: BaseException) -> str | None:
    """Classify only available types/codes; never serialize exception text."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, (httpx.NetworkError, httpx.ProxyError)):
        return "connection_failure"
    if isinstance(exc, (httpx.ProtocolError, httpx.UnsupportedProtocol)):
        return "protocol_failure"
    if isinstance(exc, DiagnosticStop):
        return {"http_failure": "http_failure", "unexpected_redirect": "redirect"}.get(exc.code)
    return "unknown_interruption"


class DispatchGuard(httpx.BaseTransport):
    """Reserve durably BEFORE touching the underlying transport; never resume."""

    def __init__(self, transport: httpx.BaseTransport, journal: Path,
                 fingerprint: str, requests: list[dict[str, Any]], api_key: str,
                 before_dispatch=None):
        if len(requests) != 12 or len({r["case_id"] for r in requests}) != 12 or not api_key.strip():
            raise DiagnosticStop("invalid_dispatch_contract")
        self.transport = transport
        self.requests = requests
        self.api_key = api_key
        self.before_dispatch = before_dispatch
        self.lock = threading.RLock()
        self.logical_calls = 0
        self.physical_dispatches = 0
        self.stopped = False
        self.active: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = []
        # O_EXCL rejects concurrent starts and every restart, including a crash
        # after reservation but before the operating system sends any bytes.
        self.fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            self._write({"event": "started", "fingerprint": fingerprint})
            parent = os.open(journal.parent, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        except BaseException:
            os.close(self.fd)
            raise

    def _write(self, record: dict[str, Any]) -> None:
        raw = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        # A short/failed write is terminal, never permission to dispatch.
        if os.write(self.fd, raw) != len(raw):
            raise DiagnosticStop("journal_write_failed")
        os.fsync(self.fd)

    def begin(self, case_id: str) -> None:
        with self.lock:
            if (self.stopped or self.active is not None or self.logical_calls >= 12
                    or self.requests[self.logical_calls]["case_id"] != case_id):
                self.stop("logical_budget_or_order_invalid")
            self.active = self.requests[self.logical_calls]
            self.logical_calls += 1
            try:
                self._write({"event": "logical_call", "case_id": case_id,
                             "logical_call": self.logical_calls})
            except BaseException:
                self.stopped = True
                raise

    def stop(self, code: str) -> NoReturn:
        self.stopped = True
        self._write({"event": "stopped", "code": code})
        raise DiagnosticStop(code)

    def finish(self, record: dict[str, Any] | None = None) -> None:
        with self.lock:
            if self.stopped or self.active is None or not self.active.get("dispatched"):
                self.stop("missing_or_failed_dispatch")
            if record is not None:
                allowed = {"case_id", "outcome", "oracle_equal", "oracle_complete",
                    "same_read_only_snapshot", "semantic_match", "both_optional_arms_preserved",
                    "left_reverse_selected", "independent_where_restriction", "optional_or_rule_selected",
                    "output_contract_match", "result_multiset_match"}
                if (set(record) - allowed or record.get("case_id") != self.active["case_id"]
                        or record.get("outcome") not in {"plan", "clarification", "unsafe_request"}
                        or any(type(value) is not bool and not (
                                   key == "result_multiset_match" and type(value) is str
                                   and value == "not_evaluated")
                               for key, value in record.items() if key not in {"case_id", "outcome"})):
                    self.stop("case_evidence_invalid")
                try:
                    self._write({"event": "case_result", **record})
                except BaseException:
                    self.stopped = True
                    raise
            self.active = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            active = self.active
            if self.stopped or active is None or active.get("dispatched") or self.physical_dispatches >= 12:
                self.stop("physical_budget_exhausted")
            try:
                body = json.loads(request.content)
            except (ValueError, UnicodeError):
                self.stop("invalid_request")
            if (request.method != "POST" or str(request.url) != "https://api.openai.com/v1/responses"
                    or request.headers.get("authorization") != "Bearer " + self.api_key
                    or digest(body) != active["body_sha256"]):
                self.stop("request_identity_mismatch")
            if self.before_dispatch is not None:
                try:
                    self.before_dispatch(active["case_id"])
                except BaseException:
                    self.stopped = True
                    raise
            active["dispatched"] = True
            self.physical_dispatches += 1
            record: dict[str, Any] = {"case_id": active["case_id"],
                "physical_dispatch": self.physical_dispatches, "usage_complete": False,
                "input_tokens": None, "cached_input_tokens": None,
                "output_tokens": None, "total_tokens": None, "latency_ms": None,
                "failure": None, "transport_failure_category": None}
            self.records.append(record)
            started = time.perf_counter()
            try:
                self._write({"event": "dispatch_reserved", **record})
                response = self.transport.handle_request(request)
                # Read at this boundary: stream timeouts/interruptions cannot be
                # hidden by SDK parsing or a redirect/retry above the transport.
                response.read()
                try:
                    data = response.json() if len(response.content) <= 1_000_000 else {}
                except (ValueError, UnicodeError):
                    # A non-JSON HTTP error/redirect still has a known category.
                    # Successful malformed responses remain a fatal shape error.
                    if 200 <= response.status_code < 300:
                        raise DiagnosticStop("response_invalid") from None
                    data = {}
                usage = _usage_counts(data.get("usage")) if isinstance(data, dict) else {}
                record.update(usage)
                record["usage_complete"] = (len(usage) == 4
                    and usage["cached_input_tokens"] <= usage["input_tokens"]
                    and usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"])
                if 300 <= response.status_code < 400:
                    raise DiagnosticStop("unexpected_redirect")
                if not 200 <= response.status_code < 300:
                    raise DiagnosticStop("http_failure")
                if len(response.content) > 1_000_000:
                    raise DiagnosticStop("response_too_large")
                if not record["usage_complete"]:
                    raise DiagnosticStop("incomplete_usage")
                if (data.get("status") != "completed" or data.get("model") != body["model"]
                        or data.get("error") or data.get("incomplete_details")):
                    raise DiagnosticStop("response_identity_or_status_invalid")
                return response
            except BaseException as exc:
                self.stopped = True
                record["failure"] = exc.code if isinstance(exc, DiagnosticStop) else "transport_or_interruption"
                record["transport_failure_category"] = transport_failure_category(exc)
                raise
            finally:
                record["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
                try:
                    self._write({"event": "dispatch_result", **record})
                except BaseException:
                    self.stopped = True
                    raise

    def close(self) -> None:
        if self.fd >= 0:
            try:
                self.transport.close()
            finally:
                os.close(self.fd)
                self.fd = -1
