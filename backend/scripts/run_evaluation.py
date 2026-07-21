#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from app.db.session import SessionLocal
from app.evaluation.contracts import CaseType, EvaluationDifficulty
from app.evaluation.loader import EvaluationDatasetValidationError
from app.evaluation.runner import EvaluationRunSummary, EvaluationRunner, EvaluationRunnerError
from app.evaluation.selection import EvaluationFilters, EvaluationSelectionError


RunnerFactory = Callable[[], EvaluationRunner]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the deterministic IT Operations evaluation with MockLLM.",
    )
    parser.add_argument("--case-id", help="Run one stable evaluation case ID.")
    parser.add_argument(
        "--difficulty",
        choices=[item.value for item in EvaluationDifficulty],
        help="Run one difficulty group.",
    )
    parser.add_argument("--category", help="Run one exact dataset category.")
    parser.add_argument(
        "--case-type",
        choices=[item.value for item in CaseType],
        help="Run one case classification.",
    )
    parser.add_argument(
        "--security-only",
        action="store_true",
        help="Run only cases marked security-sensitive.",
    )
    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    runner_factory: RunnerFactory | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    filters = EvaluationFilters(
        case_id=args.case_id,
        difficulty=(
            EvaluationDifficulty(args.difficulty) if args.difficulty else None
        ),
        category=args.category,
        case_type=CaseType(args.case_type) if args.case_type else None,
        security_only=args.security_only,
    )
    factory = runner_factory or (lambda: EvaluationRunner(SessionLocal))
    try:
        summary = factory().run(filters)
    except (
        EvaluationDatasetValidationError,
        EvaluationSelectionError,
        EvaluationRunnerError,
    ) as exc:
        code = getattr(exc, "code", "evaluation_configuration_error")
        message = getattr(
            exc,
            "safe_message",
            "Evaluation configuration is invalid.",
        )
        print(f"Evaluation failed: {code}: {message}", file=sys.stderr)
        return 2
    except Exception:
        print(
            "Evaluation failed: internal_error: Evaluation could not start safely.",
            file=sys.stderr,
        )
        return 2

    _print_summary(summary)
    return 0


def _print_summary(summary: EvaluationRunSummary) -> None:
    print(f"Run ID: {summary.run_id}")
    print(f"Provider: {summary.provider} ({summary.model_label})")
    print(
        "Dataset: "
        f"{summary.dataset_id} v{summary.dataset_version} "
        f"({summary.dataset_digest})"
    )
    print(
        "Cases: "
        f"selected={summary.selected_count} completed={summary.completed_count} "
        f"passed={summary.passed_count} failed={summary.failed_count}"
    )
    print(
        f"Overall semantic score: {summary.overall_score:.3f}; "
        "expected-behavior match rate: "
        f"{summary.expected_behavior_match_rate:.3f}"
    )
    if summary.security_pass_rate is not None:
        print(f"Security-case pass rate: {summary.security_pass_rate:.3f}")
    print(
        "Query execution: "
        f"succeeded={summary.query_execution_succeeded_count} "
        f"failed_or_blocked={summary.query_execution_failed_count}"
    )
    _print_breakdown("Difficulty", summary.by_difficulty)
    _print_breakdown("Category", summary.by_category)
    failures = [case for case in summary.cases if not case.passed]
    if failures:
        print("Failed cases:")
        for case in failures:
            code = case.error_code or "semantic_mismatch"
            print(
                f"  {case.case_id}: expected={case.expected_outcome} "
                f"actual={case.actual_outcome} code={code}"
            )


def _print_breakdown(
    label: str,
    values: dict[str, dict[str, int | float]],
) -> None:
    print(f"{label} breakdown:")
    for name, metrics in values.items():
        print(
            f"  {name}: completed={metrics['completed']} "
            f"passed={metrics['passed']} score={float(metrics['score']):.3f}"
        )


if __name__ == "__main__":
    raise SystemExit(run_cli())
