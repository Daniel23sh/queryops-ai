from __future__ import annotations

import json
from contextlib import nullcontext
from uuid import UUID, uuid4

import pytest

from app.evaluation.readiness import (
    GateStatus,
    ReadinessAssessment,
    ReadinessGate,
    ReadinessUsage,
    ReadinessVerdict,
)
from scripts import check_v1_readiness


@pytest.mark.parametrize(
    ("verdict", "expected_exit"),
    [
        (ReadinessVerdict.READY, 0),
        (ReadinessVerdict.NOT_READY, 1),
        (ReadinessVerdict.INCOMPLETE, 2),
    ],
)
def test_readiness_cli_exit_codes(monkeypatch, capsys, verdict, expected_exit) -> None:
    _install(monkeypatch, _assessment(verdict))
    run_id = uuid4()

    exit_code = check_v1_readiness.run_cli(["--run-id", str(run_id)])

    output = capsys.readouterr()
    assert exit_code == expected_exit
    assert f"Verdict: {verdict.value}" in output.out
    assert output.err == ""


def test_readiness_cli_requires_explicit_run_id() -> None:
    with pytest.raises(SystemExit) as error:
        check_v1_readiness.run_cli([])
    assert error.value.code == 2


def test_readiness_cli_json_is_fixed_bounded_and_sanitized(monkeypatch, capsys) -> None:
    _install(monkeypatch, _assessment(ReadinessVerdict.READY))

    assert check_v1_readiness.run_cli(["--run-id", str(uuid4()), "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert set(payload) == {
        "policy_id",
        "verdict",
        "run_id",
        "provider",
        "model_label",
        "dataset",
        "counts",
        "average_latency_ms",
        "usage",
        "gates",
    }
    assert set(payload["usage"]) == {
        "call_count",
        "attempt_count",
        "duration_ms",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
    }
    serialized = output.out + output.err
    for sentinel in (
        "SELECT secret",
        "raw-row@example.invalid",
        "provider-payload",
        "OPENAI_API_KEY",
        "postgresql://",
        "Traceback",
    ):
        assert sentinel not in serialized


def test_readiness_cli_never_calls_provider_and_safe_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "app.query_engine.openai_provider.OpenAIProvider.generate_sql",
        lambda *_args, **_kwargs: pytest.fail("readiness must not call OpenAI"),
    )
    monkeypatch.setattr(check_v1_readiness, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(
        check_v1_readiness,
        "assessment_for_run",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("postgresql://secret")),
    )

    assert check_v1_readiness.run_cli(["--run-id", str(uuid4())]) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert "internal_safe_failure" in output.err
    assert "postgresql://secret" not in output.err
    assert "Traceback" not in output.err


def _install(monkeypatch, assessment: ReadinessAssessment) -> None:
    monkeypatch.setattr(check_v1_readiness, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(
        check_v1_readiness,
        "assessment_for_run",
        lambda _db, _run_id: assessment,
    )


def _assessment(verdict: ReadinessVerdict) -> ReadinessAssessment:
    status = {
        ReadinessVerdict.READY: GateStatus.PASSED,
        ReadinessVerdict.NOT_READY: GateStatus.FAILED,
        ReadinessVerdict.INCOMPLETE: GateStatus.INCOMPLETE,
    }[verdict]
    reason = {
        ReadinessVerdict.READY: None,
        ReadinessVerdict.NOT_READY: "result_accuracy_below_threshold",
        ReadinessVerdict.INCOMPLETE: "qualifying_run_missing",
    }[verdict]
    run_id = UUID("00000000-0000-4000-8000-000000009999")
    return ReadinessAssessment(
        policy_id="queryops-v1-readiness-v1",
        verdict=verdict,
        run_id=run_id,
        provider="openai",
        model_label="gpt-5.6-terra",
        dataset_id="it_operations_v1",
        dataset_version="1",
        dataset_digest="a" * 64,
        selected_count=40,
        completed_count=40,
        average_latency_ms=123.5,
        usage=ReadinessUsage(
            call_count=34,
            attempt_count=35,
            duration_ms=4567.0,
            input_tokens=1000,
            cached_input_tokens=100,
            output_tokens=500,
            total_tokens=1500,
        ),
        gates=(
            ReadinessGate(
                code="result_accuracy",
                label="Result accuracy",
                status=status,
                threshold=0.75,
                actual=0.75 if verdict is not ReadinessVerdict.INCOMPLETE else None,
                reason_code=reason,
            ),
        ),
    )
