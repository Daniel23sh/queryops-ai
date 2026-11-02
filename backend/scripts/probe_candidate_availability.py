#!/usr/bin/env python3
"""Offline W6b diagnostics; no provider, database or SQL execution.

From backend: PYTHONPATH=. .venv/bin/python scripts/probe_candidate_availability.py
load_corpus(), measure_current() and build_report() do not write artifacts.
measure_current() needs no Git history; build_report() locally replays the baseline.
"""
from __future__ import annotations

import hashlib
import json
import platform
import runpy
import subprocess
import types
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.selection import evaluation_dataset_digest
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.provider_config import installed_runtime_versions
from app.query_engine.semantic_catalog import MAX_SEMANTIC_PROJECTION_BYTES, build_semantic_catalog_projection
from app.query_engine.semantic_grounding import _validate_projection_concept_dependency_closure

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "docs/audits/w6a"
OUTPUT = ROOT / "docs/audits/2026-11-01-candidate-availability-results.json"
BASELINE = "722e6a092b53dd58b7f9779393273ed13cc70c33"
W6A = "b1f03a4790c7569f7da0ef8d9be57ddd6da023c5"
CORPUS_SHA256 = "203afe0e190bbcf4d569a596697a414c552496efae967577613ae51c5f9253e9"
CATALOG_HASH = "918df0c63288b7ed7ce700f8442c82bc1ffa3f51e1f4eaa63fd66012af82adb4"
KINDS = ("entities", "concepts", "metrics", "rules", "relationships")
ATTRS = {kind: "composition_rules" if kind == "rules" else kind for kind in KINDS}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_corpus() -> list[dict]:
    raw = (HERE / "candidate-cases.json").read_bytes()
    assert digest(raw) == CORPUS_SHA256
    corpus = json.loads(raw)
    assert corpus["classification"] == "exploratory_not_blinded_holdout"
    cases = corpus["cases"]
    assert len(cases) == len({case["id"] for case in cases}) == 79
    return cases


def selected(projection) -> dict[str, set[str]]:
    return {kind: {item["id"] for item in getattr(projection, attr)} for kind, attr in ATTRS.items()}


def projection_bytes(projection) -> int:
    return len(json.dumps(projection.as_prompt_dict(), sort_keys=True, separators=(",", ":")).encode())


def observe(case: dict, projection) -> dict:
    ids = selected(projection)
    raw_lexical = projection.lexical_evidence()
    lexical = {
        "entities": set(raw_lexical["entity_ids"]), "concepts": set(raw_lexical["concept_ids"]),
        "metrics": set(raw_lexical["metric_ids"]), "rules": set(raw_lexical["rule_ids"]),
        "relationships": set(),
    }
    missing = {kind: sorted(set(case["expected"][kind]) - ids[kind]) for kind in KINDS}
    forbidden_absent = all(not set(values) & ids[kind] for kind, values in case.get("forbidden", {}).items())
    forbidden_lexical_absent = all(not set(values) & lexical[kind] for kind, values in case.get("forbidden_lexical", {}).items())
    covered = not any(missing.values())
    empty_pass = not case.get("expect_empty_entities") or not ids["entities"]
    size = projection_bytes(projection)
    return {
        "all_expected_projected": covered,
        "selected": {kind: sorted(values) for kind, values in ids.items()},
        "missing": {kind: values for kind, values in missing.items() if values},
        "projection_bytes": size, "within_cap": size <= MAX_SEMANTIC_PROJECTION_BYTES,
        "legacy_control_pass": (covered and empty_pass and forbidden_absent and forbidden_lexical_absent) if case["kind"] == "control" else None,
        "empty_entity_expectation_pass": empty_pass,
        "forbidden_ids_absent": forbidden_absent,
        "forbidden_lexical_ids_absent": forbidden_lexical_absent,
        "decoy_ids_present": {kind: sorted(set(values) & ids[kind]) for kind, values in case.get("decoy_ids", {}).items()},
    }


def summary(cases: list[dict], rows: list[dict]) -> dict:
    paired = list(zip(cases, rows, strict=True))
    positive = [(case, row) for case, row in paired if case["kind"] != "control"]
    return {
        "positive_cases": len(positive), "controls": len(paired) - len(positive),
        "positive_cases_fully_projected": sum(row["all_expected_projected"] for _, row in positive),
        "positive_cases_covered_within_cap": sum(row["all_expected_projected"] and row["within_cap"] for _, row in positive),
        "components": {kind: {
            "expected_occurrences": sum(len(case["expected"][kind]) for case, _ in positive),
            "projected_occurrences": sum(len(set(case["expected"][kind]) & set(row["selected"][kind])) for case, row in positive),
        } for kind in KINDS},
        "legacy_controls_passed": sum(row["legacy_control_pass"] is True for _, row in paired),
        "legacy_control_failures": [case["id"] for case, row in paired if row["legacy_control_pass"] is False],
        "over_cap_ids": [case["id"] for case, row in paired if not row["within_cap"]],
        "projection_bytes_range": [min(row["projection_bytes"] for _, row in paired), max(row["projection_bytes"] for _, row in paired)],
    }


def check_projection(projection, authorized: dict[str, set[str]]) -> None:
    ids = selected(projection)
    assert all(ids[kind] <= authorized[kind] for kind in KINDS)
    assert projection_bytes(projection) <= MAX_SEMANTIC_PROJECTION_BYTES
    assert projection.grounded_result_intent is None
    _validate_projection_concept_dependency_closure(projection)
    assert all(concept["entity_id"] in ids["entities"] for concept in projection.concepts)
    for metric in projection.metrics:
        assert metric["entity_id"] in ids["entities"] and set(metric["required_concept_ids"]) <= ids["concepts"]
    assert all(set(rule["all_of_concept_ids"] + rule["or_concept_ids"]) <= ids["concepts"] for rule in projection.composition_rules)
    assert all({rel["from_entity"], rel["to_entity"]} <= ids["entities"] for rel in projection.relationships)


def measure_current() -> dict[str, Any]:
    """Measure current authorized availability without requiring historical Git objects."""
    cases = load_corpus()
    helpers = runpy.run_path(str(HERE / "candidate_probe.py"), run_name="frozen_w6a_helpers")
    catalog = load_it_operations_domain_pack().semantic_catalog
    assert catalog.digest == CATALOG_HASH
    contexts = {mode: helpers["schema_fixture"](mode) for mode in sorted({case["context"] for case in cases})}
    rows, results = [], []
    for case in cases:
        schema, user = contexts[case["context"]]
        projection = build_semantic_catalog_projection(catalog, case["question"], schema, user)
        check_projection(projection, helpers["authorized_sets"](catalog, schema))
        assert projection.as_prompt_dict() == build_semantic_catalog_projection(catalog, case["question"], schema, user).as_prompt_dict()
        row = observe(case, projection)
        assert row["forbidden_ids_absent"] and row["forbidden_lexical_ids_absent"]
        rows.append(row)
        results.append({"id": case["id"], "kind": case["kind"], "family": case["family"], "context": case["context"], **row})
    return {
        "summary": summary(cases, rows), "results": results,
        "authorization_and_closure_checks": {
            "all_cases": 79, "all_projected_ids_authorized": True,
            "forbidden_selection_and_lexical_ids_absent": True,
            "all_entity_relationship_concept_metric_rule_dependencies_closed": True,
            "no_required_result_intent_added": True, "deterministic": True, "all_within_cap": True,
        },
    }


def build_report() -> dict[str, Any]:
    cases = load_corpus()
    helpers = runpy.run_path(str(HERE / "candidate_probe.py"), run_name="frozen_w6a_helpers")
    grounding_path = "backend/app/query_engine/semantic_grounding.py"
    baseline_code = git("show", f"{BASELINE}:{grounding_path}")
    assert baseline_code == git("show", f"{W6A}:{grounding_path}")
    baseline_module = types.ModuleType("frozen_w6b_baseline_grounding")
    exec(compile(baseline_code, f"{BASELINE}:{grounding_path}", "exec"), baseline_module.__dict__)
    baseline_builder = baseline_module.build_semantic_grounding_projection
    # The isolated historical inventory must not delegate to today's augmentation.
    helpers["alternative_summary"].__globals__["build_semantic_catalog_projection"] = baseline_builder
    frozen_artifacts = {
        "candidate_probe.py": "2098903300bce284fa43e25021ec6ba1c1af184552eb23f416ba6001dcc9eef8",
        "candidate-results.json": "9ccf58114f1a37d25cadb43e9fd391616738e249115f681881c9955960227af8",
    }
    for name, expected_hash in frozen_artifacts.items():
        assert digest((HERE / name).read_bytes()) == expected_hash, name
    historical_rows = {row["id"]: row for row in json.loads((HERE / "candidate-results.json").read_text())["results"]}
    shared_paths = (
        "backend/app/query_engine/semantic_catalog.py", "backend/app/query_engine/schema_context.py",
        "backend/app/query_engine/semantic_catalog_loader.py",
        "backend/app/domains/it_operations/domain_pack/semantic_catalog.yaml",
    )
    for path in shared_paths:
        assert (ROOT / path).read_bytes() == git("show", f"{BASELINE}:{path}"), path
    catalog = load_it_operations_domain_pack().semantic_catalog
    assert catalog.digest == CATALOG_HASH
    contexts = {mode: helpers["schema_fixture"](mode) for mode in sorted({case["context"] for case in cases})}
    before_rows, after_rows, results = [], [], []
    alternatives: dict[str, list[dict]] = {"authorized_entity_relationship_graph": [], "narrow_catalog_vocabulary": []}
    vocabulary_additions = {
        "devices": ("computer", "computers", "laptop", "laptops", "desktop", "desktops", "server", "servers"),
        "directory_users": ("staff", "personnel"),
        "login_events": ("sign in", "sign ins", "sign-in", "sign-ins", "authentication attempt", "authentication attempts"),
        "support_tickets": ("helpdesk request", "helpdesk requests", "helpdesk case", "helpdesk cases"),
    }
    vocabulary_catalog = replace(catalog, entities=tuple(replace(entity, natural_language_references=(*entity.natural_language_references, *vocabulary_additions.get(entity.id, ()))) for entity in catalog.entities))
    for case in cases:
        schema, user = contexts[case["context"]]
        authorized = helpers["authorized_sets"](catalog, schema)
        before = baseline_builder(catalog, case["question"], schema, user)
        after = build_semantic_catalog_projection(catalog, case["question"], schema, user)
        assert after.as_prompt_dict() == build_semantic_catalog_projection(catalog, case["question"], schema, user).as_prompt_dict()
        check_projection(before, authorized)
        check_projection(after, authorized)
        for attr in ATTRS.values():
            retained = {item["id"]: item for item in getattr(after, attr)}
            assert all(retained.get(item["id"]) == item for item in getattr(before, attr)), case["id"]
        for attr in ("candidate_signals", "examples", "authoritative_business_terms", "grounded_result_intent", "suggested_result_intent"):
            assert getattr(before, attr) == getattr(after, attr), (case["id"], attr)
        assert before.lexical_evidence() == after.lexical_evidence()
        before_row, after_row = observe(case, before), observe(case, after)
        assert before_row["selected"] == historical_rows[case["id"]]["selected"]
        assert before_row["projection_bytes"] == historical_rows[case["id"]]["projection_bytes"]
        assert after_row["forbidden_ids_absent"] and after_row["forbidden_lexical_ids_absent"]
        before_rows.append(before_row)
        after_rows.append(after_row)
        results.append({
            "id": case["id"], "kind": case["kind"], "family": case["family"], "context": case["context"],
            "before": before_row, "after": after_row,
            "added_authorized_ids": {kind: sorted(selected(after)[kind] - selected(before)[kind]) for kind in KINDS},
            "lexical_evidence_unchanged": True, "existing_core_unchanged": True,
        })
        full = helpers["complete_projection"](catalog, schema, user)
        alternatives["authorized_entity_relationship_graph"].append(observe(case, replace(before, entities=full.entities, relationships=full.relationships)))
        alternatives["narrow_catalog_vocabulary"].append(observe(case, baseline_builder(vocabulary_catalog, case["question"], schema, user)))
    before_summary, after_summary = summary(cases, before_rows), summary(cases, after_rows)
    assert before_summary["positive_cases_fully_projected"] == 40 and before_summary["legacy_controls_passed"] == 10
    dataset = load_it_operations_evaluation_v2_set()
    dataset_digest = evaluation_dataset_digest(dataset)
    assert dataset_digest == "6ac164ab6c58c0b008a65afc01cd26aa434fecd3eaa402b5bdad9c89e6f6540f"
    return {
        "schema_version": 1, "classification": "known_w6a_regression_corpus_not_unseen_holdout_or_model_quality",
        "baseline_source": BASELINE, "w6a_grounding_source": W6A,
        "current_head": git("rev-parse", "HEAD").decode().strip(),
        "source_identity": {path: digest((ROOT / path).read_bytes()) for path in (grounding_path, "backend/app/query_engine/mock_llm_provider.py", *shared_paths, "backend/scripts/probe_candidate_availability.py", "docs/audits/w6a/candidate_probe.py")},
        "corpus_sha256": CORPUS_SHA256, "frozen_w6a_artifacts_sha256": frozen_artifacts,
        "catalog": {"id": catalog.id, "version": catalog.version, "hash": catalog.digest},
        "dataset_identity_only": {"id": dataset.dataset_id, "version": dataset.version, "digest": dataset_digest, "cases": len(dataset.cases)},
        "runtime": {"python": platform.python_version(), "packages": installed_runtime_versions()},
        "budget_bytes": MAX_SEMANTIC_PROJECTION_BYTES,
        "before": before_summary, "after": after_summary,
        "by_kind": {kind: {phase: summary([case for case in cases if case["kind"] == kind], [row for case, row in zip(cases, rows, strict=True) if case["kind"] == kind]) for phase, rows in (("before", before_rows), ("after", after_rows))} for kind in sorted({case["kind"] for case in cases})},
        "regressions": [case["id"] for case, before, after in zip(cases, before_rows, after_rows, strict=True) if before["all_expected_projected"] and not after["all_expected_projected"]],
        "improved_positive_ids": [case["id"] for case, before, after in zip(cases, before_rows, after_rows, strict=True) if case["kind"] != "control" and not before["all_expected_projected"] and after["all_expected_projected"]],
        "authorization_and_closure_checks": {
            "all_cases": 79, "all_projected_ids_authorized": True,
            "forbidden_selection_and_lexical_ids_absent": True,
            "all_entity_relationship_concept_metric_rule_dependencies_closed": True,
            "existing_core_preserved": True, "lexical_evidence_unchanged": True,
            "no_required_result_intent_added": True, "deterministic": True, "all_within_cap": True,
        },
        "alternatives": {
            "classification": "illustrative_offline_mechanisms_not_independent_validation_or_model_experiments",
            "narrow_vocabulary_additions": vocabulary_additions,
            "summary": {name: summary(cases, rows) for name, rows in alternatives.items()},
            "full_and_selected_definition_inventory": helpers["alternative_summary"](cases, catalog, *contexts["global"]),
        },
        "limits": [
            "Availability does not measure provider selection, semantic interpretation, SQL correctness or final answers.",
            "The immutable W6a corpus was known during design; this is not independent W6c or release qualification.",
            "Legacy empty-entity controls are scored literally. Authorized availability adds options without asserting question meaning, permission, scope, lexical authority or required intent.",
            "Extra candidates and service-account decoys are options, not measured false selections; negated lexical evidence remains unchanged.",
            "Vocabulary alternative is illustrative and hand selected, including laptop subtype caveats; no catalog changes were made.",
            "Original unpersisted synthetic resource metadata fixture exercises schema/access functions. Persisted permissions, API, PostgreSQL and RLS are verified separately.",
            "Missing-column controls inject post-schema contexts; no field-level ACL capability is claimed.",
            "No provider call/client, database connection, SQL render/execution, row read or database write occurs in this probe.",
        ],
        "results": results,
    }


def main() -> None:
    report = build_report()
    rows = report.pop("results")
    encoded = json.dumps(report, indent=2, sort_keys=True)[:-2]
    encoded += ',\n  "results": [\n'
    encoded += ",\n".join("    " + json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
    OUTPUT.write_text(encoded + "\n  ]\n}\n")
    print(json.dumps({"before": report["before"], "after": report["after"], "output": str(OUTPUT)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
