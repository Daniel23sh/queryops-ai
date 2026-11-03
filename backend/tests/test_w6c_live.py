"""Preparation and approval regressions, never real OpenAI requests."""
import copy
import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts import w6c_live as live
from scripts.w6c_dispatch import DiagnosticStop, digest


def test_versioned_selection_preserves_original_bytes_and_oracles():
    config, _, cases, _ = live.frozen_inputs()
    assert [c["id"] for c in cases] == ["W6C-001", "W6C-002", "W6C-003", "W6C-004",
        "W6C-006", "W6C-008", "W6C-009", "W6C-007", "W6C-011", "W6C-012", "W6C-013", "W6C-020"]
    assert config["execution_authorized"] is False
    frozen = live.artifact_module("witnesses").witnesses()
    old = next(w for w in frozen if w["case_id"] == "W6C-007")
    new = live.witnesses_by_id()["W6C-007"]
    assert new["oracle_sql"] == old["oracle_sql"]
    assert [r["join_type"] for r in new["plan"]["relationships"]] == ["left_reverse", "left", "left_reverse"]
    assert old["plan"]["relationships"][0]["join_type"] == "left"


@pytest.mark.parametrize("name", ["heldout-v1.json", "fixture.py", "witnesses.py", "freeze.json", "live-experiment-proposal.md"])
def test_changed_frozen_bytes_fail_before_artifact_import_or_database(monkeypatch, name):
    original = live.file_hash
    monkeypatch.setattr(live, "file_hash", lambda p: "0" * 64 if p.name == name else original(p))
    monkeypatch.setattr(live, "artifact_module", lambda _: pytest.fail("artifact imported"))
    monkeypatch.setattr(live, "create_engine", lambda _: pytest.fail("database opened"))
    monkeypatch.setattr(live, "source_identity", lambda: "a" * 40)
    with pytest.raises(DiagnosticStop):
        live.prepare(datetime.now(UTC).isoformat(), initialize_database=True)


def test_preflight_settings_need_no_key_and_do_not_change_normal_defaults(monkeypatch):
    from app.query_engine.provider_config import OpenAIProviderSettings
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "2")
    config, _, _, _ = live.frozen_inputs()
    settings = live.diagnostic_settings(config)
    assert settings.openai.max_retries == 0
    assert OpenAIProviderSettings(api_key="synthetic").max_retries == 2
    assert settings.openai.model == "gpt-6.1-terra"


@pytest.mark.parametrize("setting", ["LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_TIMEOUT_SECONDS",
    "OPENAI_MAX_RETRIES", "OPENAI_REASONING_EFFORT", "OPENAI_MAX_OUTPUT_TOKENS"])
def test_live_requires_explicit_exact_environment_and_credentials(monkeypatch, setting):
    config, _, _, _ = live.frozen_inputs()
    for key, value in {**config["settings"], "LLM_PROVIDER": "openai", "OPENAI_API_KEY": "synthetic"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(setting, raising=False)
    with pytest.raises(Exception):
        live.diagnostic_settings(config, live=True)


@pytest.mark.parametrize("age", [timedelta(hours=25), timedelta(minutes=-6)])
def test_reference_must_be_fresh(age):
    with pytest.raises(DiagnosticStop):
        live.fresh_reference((datetime.now(UTC) - age).isoformat())


def approval_for(manifest):
    return {"schema": "queryops-w6c-operator-approval-v2", "approved": True,
        "fingerprint": manifest["fingerprint"], "source_git_sha": manifest["source_git_sha"],
        "model": "gpt-6.1-terra", "max_logical_calls": 12, "max_physical_dispatches": 12,
        "max_dispatches_per_question": 1, "no_retry_no_resume": True}


@pytest.mark.parametrize("mutation", ["absent", "budget", "fingerprint", "model", "source", "extra", "numeric_approval"])
def test_approval_is_exact_and_bound_to_entire_preflight(mutation):
    manifest = {"fingerprint": "f" * 64, "source_git_sha": "a" * 40,
                "settings": {"OPENAI_MODEL": "gpt-6.1-terra"}}
    approval = approval_for(manifest)
    live.verify_approval(approval, manifest)
    if mutation == "absent":
        approval = None
    elif mutation == "extra":
        approval["secret"] = "must-not-appear"
    elif mutation == "numeric_approval":
        approval["approved"] = 1
    else:
        key = {"budget": "max_physical_dispatches", "model": "model", "source": "source_git_sha",
               "fingerprint": "fingerprint"}[mutation]
        approval[key] = "changed"
    with pytest.raises(DiagnosticStop):
        live.verify_approval(approval, manifest)


def test_live_cli_has_no_implicit_approval_or_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr(live.httpx, "HTTPTransport", lambda **_: pytest.fail("network transport constructed"))
    assert live.main(["--live", "--out", str(tmp_path / "new.json")]) == 2
    assert not (tmp_path / "new.json").exists()


def test_manifest_changes_fail_before_http_client(tmp_path, monkeypatch):
    old = {"reference_time": datetime.now(UTC).isoformat(), "fingerprint": "a" * 64}
    monkeypatch.setattr(live, "prepare", lambda _: {**old, "fingerprint": "b" * 64})
    monkeypatch.setattr(live.httpx, "HTTPTransport", lambda **_: pytest.fail("network reached"))
    with pytest.raises(DiagnosticStop):
        live.execute(old, dry_run=False)


@pytest.mark.parametrize("change", ["app_db", "host", "query", "name", "flag"])
def test_disposable_database_guard_precedes_connection(monkeypatch, change):
    url = "postgresql+psycopg://user:synthetic@127.0.0.1:55471/queryops_w6c_v2_test"
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_DISPOSABLE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/queryops")
    if change == "app_db":
        monkeypatch.setenv("DATABASE_URL", url)
    if change == "host":
        url = url.replace("127.0.0.1", "remote.test")
    if change == "query":
        url += "?host=remote.test"
    if change == "name":
        url = url.replace("queryops_w6c_v2_test", "queryops")
    if change == "flag":
        monkeypatch.delenv("POSTGRES_TEST_DATABASE_DISPOSABLE")
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_URL", url)
    with pytest.raises(DiagnosticStop):
        live.disposable_url()


def test_config_changes_are_in_manifest_fingerprint():
    config, _, _, _ = live.frozen_inputs()
    changed = copy.deepcopy(config)
    changed["settings"]["OPENAI_MAX_RETRIES"] = "1"
    assert digest(config) != digest(changed)
    with pytest.raises(DiagnosticStop):
        live.diagnostic_settings(changed)
