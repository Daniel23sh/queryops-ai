"""Destructive-operation ownership and evidence integrity of the local adapter."""
import importlib.util
import json
import linecache
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


local = load("local_validation", "scripts/validate_local.py")
gate = load("local_validation_gate", "scripts/validation/gate.py")


@pytest.mark.parametrize("key", ["DATABASE_URL", "POSTGRES_TEST_DATABASE_URL", "M8_E2E_DATABASE_URL",
                                      "OPENAI_API_KEY", "AUTH_MODE", "LLM_PROVIDER", "DOCKER_HOST",
                                      "COMPOSE_PROJECT_NAME", "HTTP_PROXY", "PGSERVICE", "PGHOST"])
def test_existing_targets_and_secrets_are_never_forwarded(monkeypatch, key):
    monkeypatch.setenv(key, "protected-user-resource")
    assert key not in local.clean_environment()


def test_conflicting_container_is_not_adopted_or_deleted(tmp_path):
    run = local.Run(tmp_path)
    with patch.object(local, "command", return_value="existing") as command:
        with pytest.raises(local.ValidationError, match="conflict"):
            run.create("backend", "image")
        assert command.call_count == 1
    assert run.containers == []


def test_client_config_proxies_are_explicitly_cleared(tmp_path):
    run = local.Run(tmp_path)
    with patch.object(local, "command", side_effect=["", "a" * 64]) as command:
        run.create("backend", "image")
    arguments = command.call_args.args
    for key in local.PROXY_KEYS:
        assert key + "=" in arguments


def test_cleanup_refuses_foreign_owner(tmp_path):
    run = local.Run(tmp_path)
    run.containers.append("a" * 64)
    with patch.object(local, "command", return_value="someone-else") as command:
        run.cleanup()
    assert not any(call.args[1:3] == ("rm", "-f") for call in command.call_args_list)
    assert run.summary["cleanup"] != "complete"
    assert run.summary["status"] == "failed"


def test_partial_create_is_registered_and_cleaned_only_by_owned_id(tmp_path):
    run = local.Run(tmp_path)
    def command(*args, **kwargs):
        if args[1] == "ps":
            return "" if not run.containers else "a" * 64
        if args[1] == "create":
            raise local.ValidationError("interrupted create")
        if args[1] == "inspect":
            return "a" * 64 + " " + run.token
        return ""
    with patch.object(local, "command", side_effect=command) as mocked:
        with pytest.raises(local.ValidationError):
            run.create("partial", "image")
        assert len(run.containers) == 1
        run.cleanup()
        mocked.assert_any_call("docker", "rm", "-f", "-v", "a" * 64)
    assert run.summary["cleanup"] == "complete"


def test_interruption_during_name_to_id_transition_retains_ownership(tmp_path):
    run = local.Run(tmp_path)
    def interrupt(frame, event, arg):
        if event == "line" and frame.f_code is local.Run.create.__code__:
            line = linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()
            if line.startswith("self.containers[self.containers.index(name)]") or line == "self.containers.append(identifier)":
                sys.settrace(None)
                raise KeyboardInterrupt
        return interrupt
    with patch.object(local, "command", side_effect=["", "a" * 64]):
        try:
            sys.settrace(interrupt)
            with pytest.raises(KeyboardInterrupt):
                run.create("interrupted", "image")
        finally:
            sys.settrace(None)
    assert len(run.containers) == 1


def test_failed_build_does_not_delete_preexisting_image(tmp_path):
    run = local.Run(tmp_path)
    with patch.object(local, "command", return_value="protected-image") as command:
        with pytest.raises(local.ValidationError, match="conflict"):
            run.build(tmp_path, "Dockerfile", "runner")
        assert command.call_count == 1
    assert run.images == []


def test_dirty_checkout_rejected_before_docker(tmp_path):
    run = local.Run(tmp_path)
    with patch.object(local, "command", return_value=" M user-file") as command:
        with pytest.raises(local.ValidationError, match="clean"):
            run.execute()
    assert command.call_count == 1


def test_snapshot_pins_the_recorded_revision_even_if_head_moves(tmp_path):
    run = local.Run(tmp_path)
    revision = "b" * 40
    def command(*args, **kwargs):
        if args[:3] == ("git", "rev-parse", "HEAD"):
            return revision
        if args[:2] == ("git", "archive"):
            assert args[-1] == revision
            raise local.ValidationError("snapshot pinned")
        if args[:3] == ("docker", "context", "inspect"):
            return "unix:///local-docker.sock"
        return ""
    with patch.object(local, "command", side_effect=command):
        with pytest.raises(local.ValidationError, match="snapshot pinned"):
            run.execute()


@pytest.mark.parametrize("xml,expected", [
    ('<testsuites><testsuite><testcase/><testcase><skipped/></testcase><testcase><failure>secret</failure></testcase></testsuite></testsuites>',
     {"executed": 2, "passed": 1, "failed": 1, "skipped": 1}),
    ('<testsuite/>', {"executed": 0, "passed": 0, "failed": 0, "skipped": 0}),
])
def test_counts_distinguish_collected_and_executed_without_diagnostics(tmp_path, xml, expected):
    source = tmp_path / "report.xml"
    source.write_text(xml)
    assert gate.junit_counts(source) == expected
    assert "secret" not in json.dumps(gate.junit_counts(source))


@pytest.mark.parametrize("xml", ['<testsuite/>', '<testsuite><testcase><skipped/></testcase></testsuite>',
                                  '<testsuite><testcase><failure/></testcase></testsuite>'])
def test_required_suites_cannot_silently_skip_or_be_empty(tmp_path, xml, monkeypatch):
    runner = gate.Gate.__new__(gate.Gate)
    runner.report = {"suites": {}}
    monkeypatch.setattr(runner, "save", lambda: None)
    source = tmp_path / "report.xml"
    source.write_text(xml)
    with pytest.raises(RuntimeError):
        runner.collect("postgres-security", source, zero_skips=True)


def test_cleanup_continues_after_one_failure(tmp_path):
    run = local.Run(tmp_path)
    run.containers = ["first", "second"]
    with patch.object(run, "remove", side_effect=[local.ValidationError("fail"), None]) as remove:
        run.cleanup()
    assert remove.call_count == 2
    assert run.summary["cleanup"] != "complete"
