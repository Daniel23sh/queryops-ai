from __future__ import annotations

from uuid import uuid4

from app.evaluation.runner import (
    EvaluationCaseSummary,
    EvaluationRunSummary,
    EvaluationRunnerError,
)
from app.evaluation.selection import EvaluationSelectionError
from scripts.run_evaluation import run_cli


def test_cli_defaults_to_full_selection_and_reports_low_score_safely(capsys) -> None:
    fake = _FakeRunner(_summary())

    exit_code = run_cli([], runner_factory=lambda: fake)

    output = capsys.readouterr()
    assert exit_code == 0
    assert fake.filters.case_id is None
    assert fake.filters.difficulty is None
    assert "Provider: mock (mock-queryops-v1)" in output.out
    assert "selected=40 completed=40 passed=6 failed=34" in output.out
    assert "itops-security-003" in output.out
    assert "UPDATE directory_users" not in output.out
    assert output.err == ""


def test_cli_parses_single_and_group_filters(capsys) -> None:
    single = _FakeRunner(_summary(selected=1, completed=1))
    assert (
        run_cli(
            ["--case-id", "itops-easy-001"],
            runner_factory=lambda: single,
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
            runner_factory=lambda: group,
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

    exit_code = run_cli([], runner_factory=FatalRunner)

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

    exit_code = run_cli([], runner_factory=InvalidSelectionRunner)

    output = capsys.readouterr()
    assert exit_code == 2
    assert "invalid_evaluation_selection" in output.err
    assert "itops-easy-999" in output.err


class _FakeRunner:
    def __init__(self, summary: EvaluationRunSummary) -> None:
        self.summary = summary
        self.filters = None

    def run(self, filters):
        self.filters = filters
        return self.summary


def _summary(*, selected: int = 40, completed: int = 40) -> EvaluationRunSummary:
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
        provider="mock",
        model_label="mock-queryops-v1",
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
    )
