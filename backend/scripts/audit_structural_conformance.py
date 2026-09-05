#!/usr/bin/env python3
"""Print the offline V2 structural-grounding audit; never persists results."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.evaluation.structural_conformance import (
    Compatibility,
    Coverage,
    StructuralConformanceReport,
    build_v2_structural_conformance_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit frozen V2 structural contracts against current grounding offline.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_v2_structural_conformance_report()
    payload = report.as_safe_dict()
    if args.json_output:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    else:
        _print_text(report, payload)
    return 0


def _print_text(
    report: StructuralConformanceReport,
    payload: dict[str, Any],
) -> None:
    print(f"Report: {report.report_version}")
    print(
        "Dataset: "
        f"{report.dataset_id} v{report.dataset_version} {report.dataset_digest}"
    )
    for name, summary in payload["summaries"].items():
        print(
            f"{name}: cases={summary['case_count']} "
            f"compatibility={_compact(summary['compatibility'])} "
            f"required={_compact(summary['required_coverage'])} "
            f"suggested={_compact(summary['suggested_coverage'])} "
            f"unavailable={_compact(summary['unavailable_dimensions'])}"
        )
    print("Capability matrix (free-query answerable):")
    for item in report.capability_matrix:
        print(
            f"  {item.capability.value}: total={item.total_applicable_cases} "
            f"required={_compact(item.required_coverage)} "
            f"conflicts={item.required_conflicts} "
            f"suggested={_compact(item.suggested_coverage)} "
            f"unavailable={_compact(item.unavailable_dimensions)}"
        )
    conflicts = [
        case.case_id
        for case in report.cases
        if case.compatibility is Compatibility.CONFLICT
    ]
    zero_required = [
        case.case_id
        for case in report.cases
        if case.answerable and case.required.coverage is Coverage.NONE
    ]
    suggested_only = [
        case.case_id
        for case in report.cases
        if case.answerable
        and case.required.coverage is Coverage.NONE
        and case.suggested.coverage in {Coverage.PARTIAL, Coverage.COMPLETE}
    ]
    print(f"Required conflicts: {','.join(conflicts) or 'none'}")
    print(f"Zero required coverage: {','.join(zero_required) or 'none'}")
    print(
        f"Suggested coverage absent from required: {','.join(suggested_only) or 'none'}"
    )


def _compact(values: Mapping[str, int]) -> str:
    return ",".join(f"{key}:{value}" for key, value in values.items()) or "none"


if __name__ == "__main__":
    raise SystemExit(run_cli())
