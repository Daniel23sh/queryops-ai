#!/usr/bin/env python3
"""Print PR53 offline evidence to stdout; no SQL, provider, DB or persistence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from typing import Any

from scripts.semantic_ownership import authority_inventory, compare_fixture
from scripts.semantic_ownership_fixtures import architecture_fixtures, fixture_packs, offline_schema


def build_report() -> dict[str, Any]:
    packs = fixture_packs()
    context = {"scope_type": "global", "scope_reference_resolved": True}
    cases = []
    for fixture in architecture_fixtures():
        pack = packs[fixture.domain_id]
        for index, question in enumerate(fixture.questions):
            cases.append({"paraphrase": index, **compare_fixture(
                fixture, question, pack, offline_schema(pack), context,
            )})
    return {
        "version": "semantic-ownership-shadow-v1",
        "scope": "Remove only question-derived grounded_result_intent; retain lexical mandates and candidate graph. Validation acceptance is not execution or answer correctness.",
        "inventory": authority_inventory(),
        "cases": cases,
    }


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report()
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    print(report["version"])
    print(report["scope"])
    print("Authority inventory:")
    for item in report["inventory"]:
        print(f"  {item['id']}: {item['authority'].value} -> {item['disposition'].value}; {item['effect']}")
    print("Shadow evidence (first rejection only; PR52 mismatches do not apply SQL equivalence):")
    outcomes: Counter[str] = Counter()
    for case in report["cases"]:
        legacy, proposed = case["legacy"], case["proposed"]
        outcome = f"{'accept' if legacy['accepted'] else 'reject'}/{'accept' if proposed['accepted'] else 'reject'}"
        outcomes[outcome] += 1
        print(f"  {case['fixture_id']}[{case['paraphrase']}]: {outcome}; "
              f"legacy={legacy['first_rejection']}; proposed={proposed['first_rejection']}; "
              f"difference={case['difference']}; fixture_structure_matches={case['fixture_structure_matches']}")
        print("    " + case["evidence"])
        print("    Owners: " + "; ".join(case["future_owners"]))
    print("Observed outcomes (not scores): " + json.dumps(dict(sorted(outcomes.items()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
