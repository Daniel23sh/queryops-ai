from __future__ import annotations

from uuid import uuid4

from app.evaluation.environment import EvaluationEnvironmentIdentity
from app.evaluation.environment import EvaluationEnvironmentError
from app.evaluation.runner import (
    EvaluationCaseSummary,
    EvaluationRunSummary,
    EvaluationRunnerError,
)
from app.evaluation.selection import EvaluationSelectionError
from scripts.run_evaluation import run_cli


def test_cli_defaults_to_full_selection_and_reports_low_score_safely(capsys) -> None:
    fake = _FakeRunner(_summary())

    exit_code = run_cli([], runner_factory=lambda _settings, _environment: fake)

    output = capsys.readouterr()
    assert exit_code == 0
    assert fake.filters.case_id is None
    assert fake.filters.difficulty is None
    assert "Provider: mock (mock-queryops-v1)" in output.out
    assert "Semantic catalog: it_operations_semantic_catalog v1" in output.out
    assert "selected=40 completed=40 passed=6 failed=34" in output.out
    assert "itops-security-003" in output.out
    assert "UPDATE directory_users" not in output.out
    assert output.err == ""


def test_cli_parses_single_and_group_filters(capsys) -> None:
    single = _FakeRunner(_summary(selected=1, completed=1))
    assert (
        run_cli(
            ["--case-id", "itops-easy-001"],
            runner_factory=lambda _settings, _environment: single,
        )
        == 0
    )
    assert single.filters.case_id == "itops-easy-001"

    group = _FakeRunner(_summary(selected=5, completed=5))
    assert (
        run_cli(
            [
                "--difficulty",
                "security",
                "--case-type",
                "authorization",
                "--security-only",
            ],
            runner_factory=lambda _settings, _environment: group,
        )
        == 0
    )
    assert group.filters.difficulty.value == "security"
    assert group.filters.case_type.value == "authorization"
    assert group.filters.security_only is True
    capsys.readouterr()


def test_cli_fatal_failure_is_nonzero_and_hides_raw_exception(capsys) -> None:
    class FatalRunner:
        def run(self, _filters):
            raise EvaluationRunnerError(
                "database_unavailable",
                "Evaluation database prerequisites could not be verified safely.",
            )

    exit_code = run_cli(
        [],
        runner_factory=lambda _settings, _environment: FatalRunner(),
    )

    output = capsys.readouterr()
    assert exit_code == 2
    assert "database_unavailable" in output.err
    assert "postgresql+psycopg" not in output.err
    assert "Traceback" not in output.err
    assert output.out == ""


def test_cli_invalid_selection_fails_clearly(capsys) -> None:
    class InvalidSelectionRunner:
        def run(self, _filters):
            raise EvaluationSelectionError(
                "Unknown evaluation case id: itops-easy-999"
            )

    exit_code = run_cli(
        [],
        runner_factory=lambda _settings, _environment: InvalidSelectionRunner(),
    )

    output = capsys.readouterr()
    assert exit_code == 2
    assert "invalid_evaluation_selection" in output.err
    assert "itops-easy-999" in output.err


def test_cli_openai_selection_is_explicit_and_uses_requested_model(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "never-print-this-key")
    seen_settings = []
    fake = _FakeRunner(
        _summary(
            selected=1,
            completed=1,
            provider="openai",
            model_label="gpt-5.6-terra",
        )
    )

    exit_code = run_cli(
        [
            "--provider",
            "openai",
            "--model",
            "gpt-5.6-terra",
            "--case-id",
            "itops-easy-001",
            "--environment-manifest",
            "safe-manifest.json",
        ],
        runner_factory=lambda settings, _environment: seen_settings.append(settings)
        or fake,
        environment_loader=lambda _path: _environment_identity(),
    )

    output = capsys.readouterr()
    assert exit_code == 0
    assert seen_settings[0].provider.value == "openai"
    assert seen_settings[0].model_label == "gpt-5.6-terra"
    assert "Provider: openai (gpt-5.6-terra)" in output.out
    assert "never-print-this-key" not in output.out + output.err


def test_cli_openai_requires_verified_environment_before_runner(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "never-print-this-key")

    def must_not_build(_settings, _environment):
        raise AssertionError("runner must not be built")

    assert (
        run_cli(
            ["--provider", "openai"],
            runner_factory=must_not_build,
        )
        == 2
    )
    missing = capsys.readouterr()
    assert "evaluation_environment_missing" in missing.err

    assert (
        run_cli(
            [
                "--provider",
                "openai",
                "--environment-manifest",
                "safe-manifest.json",
            ],
            runner_factory=must_not_build,
            environment_loader=lambda _path: (_ for _ in ()).throw(
                EvaluationEnvironmentError("evaluation_environment_mismatch")
            ),
        )
        == 2
    )
    invalid = capsys.readouterr()
    assert "evaluation_environment_mismatch" in invalid.err
    assert "never-print-this-key" not in missing.err + invalid.err


def test_cli_missing_openai_key_and_mock_model_mismatch_fail_before_runner(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def must_not_build(_settings, _environment):
        raise AssertionError("runner must not be built")

    assert (
        run_cli(
            [
                "--provider",
                "openai",
                "--environment-manifest",
                "safe-manifest.json",
            ],
            runner_factory=must_not_build,
            environment_loader=lambda _path: _environment_identity(),
        )
        == 2
    )
    missing_key = capsys.readouterr()
    assert "provider_credentials_missing" in missing_key.err
    assert "OPENAI_API_KEY" not in missing_key.err

    assert (
        run_cli(
            ["--provider", "mock", "--model", "gpt-5.6-terra"],
            runner_factory=must_not_build,
        )
        == 2
    )
    mismatch = capsys.readouterr()
    assert "provider_model_mismatch" in mismatch.err


def test_cli_ignores_api_key_when_provider_is_not_selected(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "unused-key")
    seen_settings = []
    fake = _FakeRunner(_summary())

    exit_code = run_cli(
        [],
        runner_factory=lambda settings, _environment: seen_settings.append(settings)
        or fake,
    )

    output = capsys.readouterr()
    assert exit_code == 0
    assert seen_settings[0].provider.value == "mock"
    assert "unused-key" not in output.out + output.err


class _FakeRunner:
    def __init__(self, summary: EvaluationRunSummary) -> None:
        self.summary = summary
        self.filters = None

    def run(self, filters):
        self.filters = filters
        return self.summary


def _summary(
    *,
    selected: int = 40,
    completed: int = 40,
    provider: str = "mock",
    model_label: str = "mock-queryops-v1",
) -> EvaluationRunSummary:
    failed = EvaluationCaseSummary(
        case_id="itops-security-003",
        difficulty="security",
        category="sql_safety",
        case_type="unsafe_sql",
        expected_outcome="unsafe_blocked",
        actual_outcome="clarification",
        passed=False,
        score=0.25,
        error_code="clarification_required",
    )
    return EvaluationRunSummary(
        run_id=uuid4(),
        provider=provider,
        model_label=model_label,
        dataset_id="it_operations_v1",
        dataset_version="1",
        dataset_digest="a" * 64,
        status="succeeded",
        selected_count=selected,
        completed_count=completed,
        passed_count=6,
        failed_count=max(0, completed - 6),
        overall_score=0.4,
        expected_behavior_match_rate=0.25,
        security_pass_rate=0.6,
        query_execution_succeeded_count=6,
        query_execution_failed_count=31,
        by_difficulty={
            "security": {"completed": 5, "passed": 3, "failed": 2, "score": 0.6}
        },
        by_category={
            "sql_safety": {"completed": 1, "passed": 0, "failed": 1, "score": 0.25}
        },
        by_case_type={},
        cases=(failed,),
        provider_usage={
            "call_count": 0,
            "attempt_count": 0,
            "duration_ms": 0.0,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
        semantic_catalog={
            "catalog_id": "it_operations_semantic_catalog",
            "catalog_version": "1",
            "catalog_hash": "b" * 64,
        },
        evaluation_environment=(
            _environment_identity().as_dict() if provider == "openai" else {}
        ),
    )


def _environment_identity() -> EvaluationEnvironmentIdentity:
    return EvaluationEnvironmentIdentity(
        manifest_version="queryops-evaluation-environment-v1",
        seed_version="it-operations-seed-v1",
        seed_profile="medium",
        seed=42,
        reference_time="2026-08-24T12:00:00Z",
        source_git_sha="a" * 40,
        alembic_revision="0010_disable_inactive_user",
        postgres_version="16.9",
        database_fingerprint="c" * 64,
        dependency_manifest_hash="d" * 64,
    )
