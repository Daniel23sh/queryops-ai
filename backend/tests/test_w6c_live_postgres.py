"""Full no-external-network diagnostic preparation on a newly created test DB."""
import json
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text

from scripts import w6c_live as live
from scripts.w6c_dispatch import DiagnosticStop
from tests.action_postgres_test_db import validated_disposable_database_url
from tests.test_query_api_postgres import run_alembic_upgrade
from sqlalchemy.orm import Session


@pytest.fixture(scope="module")
def disposable_diagnostic_url():
    raw = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit disposable PostgreSQL required")
    return validated_disposable_database_url(raw)


@pytest.fixture(scope="module")
def prepared(disposable_diagnostic_url):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("POSTGRES_TEST_DATABASE_URL", disposable_diagnostic_url)
        patch.setattr(live, "disposable_url", lambda: disposable_diagnostic_url)
        patch.delenv("OPENAI_API_KEY", raising=False)
        patch.setattr(live, "source_identity", lambda **_: "a" * 40)
        patch.setattr(live.httpx, "HTTPTransport", lambda **_: pytest.fail("external network transport reached"))
        reference = datetime.now(UTC).replace(microsecond=0).isoformat()
        # Shared CI test database is already migrated. Migrations intentionally
        # refuse to recreate cluster-wide action roles in a second fresh DB.
        run_alembic_upgrade(disposable_diagnostic_url)
        engine = create_engine(disposable_diagnostic_url)
        try:
            with Session(engine) as db:
                live.seed_database(db, profile_name="small", reset=True, reference_now=datetime.fromisoformat(reference))
                live.add_fresh_contrasts(db, datetime.fromisoformat(reference))
                db.commit()
        finally:
            engine.dispose()
        manifest = live.prepare(reference)
        yield manifest


def test_full_preflight_without_credentials_checks_ten_read_only_oracles(prepared):
    manifest = prepared
    assert manifest["logical_calls"] == manifest["physical_dispatches"] == 0
    assert len(manifest["cases"]) == 12
    assert sum(c.get("oracle_equal") is True for c in manifest["cases"]) == 10
    assert all(c["output_contract_match"] is True and c["result_multiset_match"] is True
               for c in manifest["cases"] if "oracle_equal" in c)
    assert all(c.get("oracle_complete") is True for c in manifest["cases"] if "oracle_equal" in c)
    encoded = json.dumps(manifest)
    for forbidden in ("Bearer", "api_key", "oracle_sql", "rows", "scope_keys", "demo.analyst@"):
        assert forbidden not in encoded


def test_real_sdk_full_dry_run_dispatches_exactly_twelve_and_preserves_reverse_or(prepared):
    result = live.execute(prepared)
    assert result["mode"] == "in_process_manual_witnesses"
    assert result["provider_interpretation"] == "unmeasured"
    assert result["logical_calls"] == result["physical_dispatches"] == 12
    assert len(result["measurements"]) == 12
    assert all(c.get("oracle_equal", c.get("semantic_match")) is True for c in result["cases"])
    assert next(c for c in result["cases"] if c["case_id"] == "W6C-007")["left_reverse_selected"] is True


def test_initialize_refuses_to_reset_prepared_database(prepared):
    with pytest.raises(DiagnosticStop, match="database_not_empty"):
        live.prepare(prepared["reference_time"], initialize_database=True)


def test_source_fingerprint_drift_prevents_client_creation(prepared, monkeypatch):
    monkeypatch.setattr(live, "source_identity", lambda **_: "b" * 40)
    with pytest.raises(DiagnosticStop, match="preflight_identity_changed"):
        live.execute(prepared)


def test_reference_must_match_actual_seed_not_just_a_fresh_timestamp(prepared):
    from datetime import timedelta
    changed = datetime.fromisoformat(prepared["reference_time"]) + timedelta(seconds=1)
    with pytest.raises(DiagnosticStop, match="seed_reference_mismatch"):
        live.prepare(changed.isoformat())


def test_preflight_rechecks_authorization_and_database_identity(prepared):
    engine = create_engine(live.disposable_url())
    try:
        with engine.begin() as db:
            db.execute(text("UPDATE data_resources SET is_queryable=FALSE WHERE table_name='devices'"))
        with pytest.raises(DiagnosticStop):
            live.execute(prepared)
    finally:
        with engine.begin() as db:
            db.execute(text("UPDATE data_resources SET is_queryable=TRUE WHERE table_name='devices'"))
        engine.dispose()


def test_same_reference_reproduces_entire_database_fingerprint(prepared):
    engine = create_engine(live.disposable_url())
    try:
        reference = datetime.fromisoformat(prepared["reference_time"])
        with Session(engine) as db:
            live.seed_database(db, profile_name="small", reset=True, reference_now=reference)
            live.add_fresh_contrasts(db, reference)
            db.commit()
        assert live.prepare(prepared["reference_time"])["database_fingerprint"] == prepared["database_fingerprint"]
    finally:
        engine.dispose()


@pytest.mark.parametrize("case_id,mutation,expected", [
    ("W6C-009", "aggregate_alias", True), ("W6C-001", "unrequested_limit", False),
    ("W6C-007", "missing_independent_filter", False),
])
def test_oracle_contract_distinguishes_semantics_from_incidental_fixture_equality(prepared, case_id, mutation, expected):
    from app.query_engine.semantic_plan import SemanticPlan
    _, _, cases, pack = live.frozen_inputs()
    case = next(c for c in cases if c["id"] == case_id)
    witness = live.witnesses_by_id()[case_id]
    supplied = json.loads(json.dumps(witness["plan"]))
    if mutation == "aggregate_alias":
        supplied["aggregations"][0]["id"] = "different_endpoint_count"
    elif mutation == "unrequested_limit":
        supplied["limit"] = 500
    else:
        supplied["literal_filters"] = []
    engine = create_engine(live.disposable_url())
    try:
        with Session(engine) as db:
            access, schema, _, projection, _ = live.context(db, case, pack)
        with live.query_runtime_transaction(engine, access, isolation_level="repeatable_read", timezone_name="UTC") as runtime:
            result = live.oracle_comparison(runtime, access, schema, SemanticPlan.model_validate_json(json.dumps(supplied)),
                                            witness, pack, projection)
        accepted = result["oracle_equal"] and result.get("independent_where_restriction", True)
        assert accepted is expected
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure", ["refusal", "malformed", "partial_usage", "http_auth", "interrupt_after_response"])
def test_sequence_failure_never_starts_a_second_question(prepared, monkeypatch, failure):
    instances = []
    original_guard = live.DispatchGuard
    class RecordingGuard(original_guard):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)
    monkeypatch.setattr(live, "DispatchGuard", RecordingGuard)
    original_response = live.fake_response
    def response(plan):
        data = original_response(plan)
        if failure == "refusal":
            data["output"][0]["content"] = [{"type": "refusal", "refusal": "private"}]
        elif failure == "malformed":
            data["output"][0]["content"][0]["text"] = "private-invalid-json"
        elif failure == "partial_usage":
            data.pop("usage")
        elif failure == "http_auth":
            data["error"] = {"code": "invalid_api_key"}
        return data
    monkeypatch.setattr(live, "fake_response", response)
    if failure == "interrupt_after_response":
        original_generate = live.OpenAIProvider.generate_plan
        def interrupted(self, *args, **kwargs):
            original_generate(self, *args, **kwargs)
            raise KeyboardInterrupt()
        monkeypatch.setattr(live.OpenAIProvider, "generate_plan", interrupted)
    with pytest.raises(BaseException):
        live.execute(prepared)
    assert len(instances) == 1
    assert instances[0].logical_calls == instances[0].physical_dispatches == 1
    assert instances[0].stopped


@pytest.mark.parametrize("gate", ["approval", "not_merged", "environment"])
def test_live_gates_fail_before_constructing_network_transport(prepared, monkeypatch, gate):
    from tests.test_w6c_live import approval_for
    config, _, _, _ = live.frozen_inputs()
    for key, value in {**config["settings"], "LLM_PROVIDER": "openai", "OPENAI_API_KEY": "synthetic"}.items():
        monkeypatch.setenv(key, value)
    approval = approval_for(prepared)
    if gate == "approval":
        approval["approved"] = False
    if gate == "environment":
        monkeypatch.setenv("OPENAI_MAX_RETRIES", "2")
    if gate == "not_merged":
        def source(*, merged=False):
            if merged:
                raise DiagnosticStop("merged_candidate_required")
            return "a" * 40
        monkeypatch.setattr(live, "source_identity", source)
    with pytest.raises(DiagnosticStop):
        live.execute(prepared, approval=approval, dry_run=False)


def test_second_question_failure_preserves_first_semantic_result_in_durable_journal(prepared, monkeypatch):
    import httpx
    journals = []
    original_guard = live.DispatchGuard
    class RecordingGuard(original_guard):
        def __init__(self, transport, journal, *args, **kwargs):
            self.journal = journal
            super().__init__(transport, journal, *args, **kwargs)
        def close(self):
            journals.append([json.loads(line) for line in self.journal.read_text().splitlines()])
            super().close()
    monkeypatch.setattr(live, "DispatchGuard", RecordingGuard)
    original_response = live.fake_response
    calls = []
    def response(plan):
        calls.append(True)
        if len(calls) == 2:
            raise httpx.ReadTimeout("private-second-call")
        return original_response(plan)
    monkeypatch.setattr(live, "fake_response", response)
    with pytest.raises(Exception):
        live.execute(prepared)
    assert len(calls) == 2
    events = journals[-1]
    completed = [e for e in events if e["event"] == "case_result"]
    assert completed == [{"event": "case_result", "case_id": "W6C-001", "outcome": "plan",
                          "output_contract_match": True, "result_multiset_match": True,
                          "oracle_equal": True, "oracle_complete": True, "same_read_only_snapshot": True}]
    assert len([e for e in events if e["event"] == "dispatch_reserved"]) == 2
    assert events[-1]["event"] == "sequence_failed"
    failed = [e for e in events if e["event"] == "dispatch_result"][-1]
    assert failed["transport_failure_category"] == "timeout"
    assert failed["input_tokens"] is None and failed["usage_complete"] is False
    assert "private" not in json.dumps(events)


@pytest.mark.parametrize("mutation,contract_match,multiset_match", [
    ("unchanged", True, True), ("limit", False, True),
    ("restriction", True, False), ("field_identity", False, "not_evaluated"),
    ("distinct_fanout", False, False), ("aggregate_target", False, "not_evaluated"),
])
def test_independent_contract_and_result_measurements(prepared, mutation, contract_match, multiset_match):
    from app.query_engine.semantic_plan import SemanticPlan
    # Synthetic mutations of independently authored witnesses, not recovered
    # provider outputs or an inferred explanation of the historical failure.
    case_id = "W6C-009" if mutation == "aggregate_target" else "W6C-008"
    _, _, cases, pack = live.frozen_inputs()
    case = next(c for c in cases if c["id"] == case_id)
    witness = live.witnesses_by_id()[case_id]
    supplied = json.loads(json.dumps(witness["plan"]))
    if mutation == "limit":
        supplied["limit"] = 500
    elif mutation == "restriction":
        supplied["literal_filters"] = [{"field": {"entity_id": "devices", "column": "os"},
                                        "operator": "equals", "value": "no-such-synthetic-os"}]
    elif mutation == "field_identity":
        supplied["output_fields"] = [{"entity_id": "devices", "column": "hostname"}]
    elif mutation == "distinct_fanout":
        supplied["distinct"] = False
    elif mutation == "aggregate_target":
        supplied["aggregations"][0]["field"] = {"entity_id": "software_installs", "column": "id"}
    engine = create_engine(live.disposable_url())
    try:
        with Session(engine) as db:
            access, schema, _, projection, _ = live.context(db, case, pack)
        with live.query_runtime_transaction(engine, access, isolation_level="repeatable_read", timezone_name="UTC") as runtime:
            result = live.oracle_comparison(runtime, access, schema, SemanticPlan.model_validate_json(json.dumps(supplied)),
                                            witness, pack, projection)
        assert result["output_contract_match"] is contract_match
        assert result["result_multiset_match"] == multiset_match
        assert result["oracle_equal"] is (contract_match and multiset_match is True)
        assert result["oracle_complete"] is True and result["same_read_only_snapshot"] is True
    finally:
        engine.dispose()
