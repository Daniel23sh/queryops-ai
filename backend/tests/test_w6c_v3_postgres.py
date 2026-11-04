"""Six frozen read-only witnesses through actual PostgreSQL and SDK parsing."""
import copy
import json
import os
import socket
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from scripts import w6c_v3 as live
from scripts.w6c_dispatch import DiagnosticStop
from tests.action_postgres_test_db import validated_disposable_database_url
from tests.test_query_api_postgres import run_alembic_upgrade
from tests.test_w6c_v3 import approval_for


@pytest.fixture(scope="module")
def prepared():
    raw = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit disposable PostgreSQL required")
    url = validated_disposable_database_url(raw)
    with pytest.MonkeyPatch.context() as patch:
        # CI owns one already guarded DB. The real CLI separately enforces its v3
        # name and empty initialization; never recreate cluster-global roles here.
        patch.setattr(live, "disposable_url", lambda: url)
        patch.setattr(live, "source_identity", lambda **_: "a" * 40)
        patch.setattr(live.httpx, "HTTPTransport", lambda **_: pytest.fail("real HTTP transport reached"))
        patch.setattr(live, "live_journal", lambda: pytest.fail("live journal reached"))
        patch.setattr(socket.socket, "connect", lambda *_: pytest.fail("Python network socket reached"))
        patch.delenv("OPENAI_API_KEY", raising=False)
        reference = datetime.now(UTC).replace(microsecond=0)
        run_alembic_upgrade(url)
        engine = create_engine(url)
        try:
            with Session(engine) as db:
                live.v2.seed_database(db, profile_name="small", reset=True, reference_now=reference)
                live.v2.add_fresh_contrasts(db, reference)
                db.commit()
        finally:
            engine.dispose()
        yield live.prepare(reference.isoformat())


def test_six_independent_witnesses_and_complete_sdk_sequence(prepared):
    assert prepared["schema"] == "queryops-w6c-preflight-v3"
    assert prepared["logical_calls"] == prepared["physical_dispatches"] == 0
    assert tuple(c["case_id"] for c in prepared["cases"]) == live.CASE_IDS
    assert all(c["output_contract_match"] is c["result_multiset_match"] is True for c in prepared["cases"])
    result = live.execute(prepared)
    assert result["schema"] == "queryops-w6c-diagnostic-result-v3"
    assert result["logical_calls"] == result["physical_dispatches"] == len(result["cases"]) == 6
    assert all(c["oracle_equal"] for c in result["cases"])
    assert result["cases"][-1]["both_optional_arms_preserved"] is True
    assert all(c["usage_complete"] for c in result["measurements"])
    for forbidden in ("Bearer", "api_key", "oracle_sql", '"rows"', "scope_keys", "demo.analyst@"):
        assert forbidden not in json.dumps([prepared, result])


def capture_journal(monkeypatch):
    journals = []
    original = live.V3DispatchGuard
    class RecordingGuard(original):
        def __init__(self, transport, journal, *args, **kwargs):
            self.journal = journal
            super().__init__(transport, journal, *args, **kwargs)
        def close(self):
            journals.append([json.loads(line) for line in self.journal.read_text().splitlines()])
            super().close()
    monkeypatch.setattr(live, "V3DispatchGuard", RecordingGuard)
    return journals


@pytest.mark.parametrize("failure,stage", [("timeout", "http_boundary"), ("missing_usage", "http_boundary"),
    ("malformed", "sdk_parse"), ("refusal", "sdk_parse"), ("interrupt", "sdk_parse"),
    ("safety", "plan_safety"), ("oracle", "oracle_comparison"), ("authorization", "dispatch_revalidation")])
def test_second_case_fatal_failure_retains_first_and_never_retries(prepared, monkeypatch, failure, stage):
    journals = capture_journal(monkeypatch)
    original_response = live.fake_response
    calls = []
    def response(plan):
        calls.append(True)
        data = original_response(plan)
        if len(calls) == 2:
            if failure == "timeout":
                raise httpx.ReadTimeout("private")
            if failure == "missing_usage":
                data.pop("usage")
            if failure == "malformed":
                data["output"][0]["content"][0]["text"] = "private-invalid-json"
            if failure == "refusal":
                data["output"][0]["content"] = [{"type": "refusal", "refusal": "private"}]
        return data
    monkeypatch.setattr(live, "fake_response", response)
    original_generate = live.OpenAIProvider.generate_plan
    def generate(self, *args, **kwargs):
        value = original_generate(self, *args, **kwargs)
        if len(calls) == 2 and failure == "interrupt":
            raise KeyboardInterrupt("private")
        return value
    monkeypatch.setattr(live.OpenAIProvider, "generate_plan", generate)
    if failure in {"safety", "oracle"}:
        name = "checked_sql" if failure == "safety" else "oracle_comparison"
        original = getattr(live, name)
        def checked(*args, **kwargs):
            if len(calls) == 2:
                raise RuntimeError("private SQL rows provider content")
            return original(*args, **kwargs)
        monkeypatch.setattr(live, name, checked)
    if failure == "authorization":
        original_context = live.context
        def context(db, case, *args):
            # Fail at the second transport recheck, after logical reservation.
            if case["id"] == live.CASE_IDS[1] and journals == [] and len(calls) == 1:
                contexts.append(True)
                if len(contexts) == 2:
                    raise DiagnosticStop("private-untrusted-code")
            return original_context(db, case, *args)
        contexts = []
        monkeypatch.setattr(live, "context", context)
    with pytest.raises(BaseException):
        live.execute(prepared)
    events = journals[-1]
    completed = [e for e in events if e["event"] == "case_result"]
    assert len(completed) == 1 and completed[0]["case_id"] == live.CASE_IDS[0]
    assert events[-1]["event"] == "sequence_failed" and events[-1]["failure_stage"] == stage
    assert events[-1]["logical_calls"] == 2
    assert events[-1]["physical_dispatches"] == (1 if failure == "authorization" else 2)
    assert "private" not in json.dumps(events)


@pytest.mark.parametrize("gate", ["approval", "v2_approval", "source", "environment", "manifest"])
def test_live_rejected_before_journal_or_http_transport(prepared, monkeypatch, gate):
    for key, value in {**prepared["settings"], "LLM_PROVIDER": "openai", "OPENAI_API_KEY": "synthetic"}.items():
        monkeypatch.setenv(key, value)
    approval = approval_for(prepared)
    supplied = copy.deepcopy(prepared)
    if gate == "approval":
        approval["approved"] = False
    elif gate == "v2_approval":
        approval["schema"] = "queryops-w6c-operator-approval-v2"
    elif gate == "source":
        def source(*, merged=False):
            if merged:
                raise DiagnosticStop("merged_candidate_required")
            return "a" * 40
        monkeypatch.setattr(live, "source_identity", source)
    elif gate == "environment":
        monkeypatch.setenv("OPENAI_MAX_RETRIES", "1")
    else:
        supplied["schema"] = "queryops-w6c-preflight-v2"
    with pytest.raises(DiagnosticStop):
        live.execute(supplied, approval=approval, dry_run=False)


@pytest.mark.parametrize("drift", ["data", "rls", "grants", "query_role", "action_role", "authorization", "column_grants", "schema_grants"])
def test_security_or_identity_drift_rejected_before_client(prepared, drift):
    changes = {
        "column_grants": ("GRANT UPDATE (hostname) ON devices TO queryops_action_runtime", "REVOKE UPDATE (hostname) ON devices FROM queryops_action_runtime"),
        "schema_grants": ("GRANT CREATE ON SCHEMA public TO queryops_action_runtime", "REVOKE CREATE ON SCHEMA public FROM queryops_action_runtime"),
        "data": ("UPDATE devices SET os='synthetic-drift'", None),
        "rls": ("ALTER TABLE devices DISABLE ROW LEVEL SECURITY", None),
        "grants": ("GRANT UPDATE ON devices TO queryops_query_runtime", "REVOKE UPDATE ON devices FROM queryops_query_runtime"),
        "query_role": ("ALTER ROLE queryops_query_runtime BYPASSRLS", "ALTER ROLE queryops_query_runtime NOBYPASSRLS"),
        "action_role": ("ALTER ROLE queryops_action_runtime LOGIN", "ALTER ROLE queryops_action_runtime NOLOGIN"),
        "authorization": ("UPDATE data_resources SET is_queryable=FALSE WHERE table_name='devices'", None),
    }
    engine = create_engine(live.disposable_url())
    command, undo = changes[drift]
    try:
        with engine.connect() as db:
            transaction = db.begin()
            db.execute(text(command))
            # Commit so the separate preflight connection observes the mutation.
            transaction.commit()
        with pytest.raises(DiagnosticStop):
            live.execute(prepared)
    finally:
        if undo:
            with engine.begin() as db:
                db.execute(text(undo))
        else:
            with engine.begin() as db:
                if drift == "rls":
                    db.execute(text("ALTER TABLE devices ENABLE ROW LEVEL SECURITY"))
                elif drift == "authorization":
                    db.execute(text("UPDATE data_resources SET is_queryable=TRUE WHERE table_name='devices'"))
                elif drift == "data":
                    reference = datetime.fromisoformat(prepared["reference_time"])
                    with Session(bind=db) as session:
                        live.v2.seed_database(session, profile_name="small", reset=True, reference_now=reference)
                        live.v2.add_fresh_contrasts(session, reference)
                        session.commit()
        engine.dispose()


@pytest.mark.parametrize("mutation,contract,multiset", [("limit", False, True), ("restriction", True, False),
                                                     ("identity", False, "not_evaluated")])
def test_safe_semantic_mismatch_continues_and_keeps_independent_measurements(prepared, monkeypatch, mutation, contract, multiset):
    original = live.fake_response
    calls = []
    def response(plan):
        plan = copy.deepcopy(plan)
        calls.append(True)
        if len(calls) == 1:
            if mutation == "limit":
                plan["limit"] = 500
            elif mutation == "identity":
                plan["output_fields"] = [{"entity_id": "devices", "column": "hostname"}]
            else:
                plan["literal_filters"] = [{"field": {"entity_id": "devices", "column": "os"},
                                            "operator": "equals", "value": "synthetic-no-match"}]
        return original(plan)
    monkeypatch.setattr(live, "fake_response", response)
    result = live.execute(prepared)
    assert result["physical_dispatches"] == len(calls) == 6
    assert result["cases"][0]["output_contract_match"] is contract
    assert result["cases"][0]["result_multiset_match"] == multiset


def test_simulated_live_failure_burns_persistent_budget_across_second_execute(prepared, monkeypatch, tmp_path):
    # Exact approval exists only in memory for a synthetic test. Both journal
    # location and HTTP transport are replaced; no real live state is accessed.
    for key, value in {**prepared["settings"], "LLM_PROVIDER": "openai", "OPENAI_API_KEY": "synthetic"}.items():
        monkeypatch.setenv(key, value)
    journal = tmp_path / "synthetic-dispatch"
    monkeypatch.setattr(live, "live_journal", lambda: journal)
    calls = []
    def handler(request):
        calls.append(True)
        raise httpx.ReadTimeout("private", request=request)
    monkeypatch.setattr(live.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(handler))
    approval = approval_for(prepared)
    with pytest.raises(Exception):
        live.execute(prepared, approval=approval, dry_run=False)
    events = journal.read_bytes()
    with pytest.raises(FileExistsError):
        live.execute(prepared, approval=approval, dry_run=False)
    assert journal.read_bytes() == events
    assert len(calls) == 1
