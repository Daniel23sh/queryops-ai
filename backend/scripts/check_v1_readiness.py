#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.db.session import SessionLocal
from app.evaluation.readiness import ReadinessAssessment, ReadinessVerdict
from app.evaluation.readiness_service import assessment_for_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check one persisted run against the QueryOps V1 readiness policy.",
    )
    parser.add_argument("--run-id", required=True, type=UUID)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with SessionLocal() as db:
            assessment = assessment_for_run(db, args.run_id)
        payload = _payload(assessment)
        if args.json_output:
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        else:
            _print_text(payload)
    except Exception:
        print(
            "V1 readiness check failed: internal_safe_failure",
            file=sys.stderr,
        )
        return 2
    if assessment.verdict is ReadinessVerdict.READY:
        return 0
    if assessment.verdict is ReadinessVerdict.NOT_READY:
        return 1
    return 2


def _payload(assessment: ReadinessAssessment) -> dict[str, Any]:
    usage = assessment.usage
    return {
        "policy_id": assessment.policy_id,
        "verdict": assessment.verdict.value,
        "run_id": str(assessment.run_id) if assessment.run_id else None,
        "provider": assessment.provider,
        "model_label": assessment.model_label,
        "dataset": {
            "id": assessment.dataset_id,
            "version": assessment.dataset_version,
            "digest": assessment.dataset_digest,
        },
        "counts": {
            "selected": assessment.selected_count,
            "completed": assessment.completed_count,
        },
        "average_latency_ms": assessment.average_latency_ms,
        "usage": (
            {
                "call_count": usage.call_count,
                "attempt_count": usage.attempt_count,
                "duration_ms": usage.duration_ms,
                "input_tokens": usage.input_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            }
            if usage
            else None
        ),
        "gates": [
            {
                "code": gate.code,
                "label": gate.label,
                "status": gate.status.value,
                "threshold": gate.threshold,
                "actual": gate.actual,
                "reason_code": gate.reason_code,
            }
            for gate in assessment.gates
        ],
    }


def _print_text(payload: dict[str, Any]) -> None:
    dataset = payload["dataset"]
    counts = payload["counts"]
    print(f"Policy: {payload['policy_id']}")
    print(f"Verdict: {payload['verdict']}")
    print(f"Run ID: {payload['run_id'] or 'none'}")
    print(
        "Evidence: "
        f"provider={payload['provider'] or 'none'} "
        f"model={payload['model_label'] or 'none'}"
    )
    print(
        "Dataset: "
        f"{dataset['id']} v{dataset['version']} ({dataset['digest']})"
    )
    print(
        "Cases: "
        f"selected={counts['selected']} completed={counts['completed']}"
    )
    for gate in payload["gates"]:
        detail = ""
        if gate["actual"] is not None:
            detail += f" actual={gate['actual']:.6f}"
        if gate["threshold"] is not None:
            detail += f" threshold={gate['threshold']:.6f}"
        if gate["reason_code"]:
            detail += f" reason={gate['reason_code']}"
        print(f"Gate {gate['code']}: {gate['status']}{detail}")


if __name__ == "__main__":
    raise SystemExit(run_cli())
