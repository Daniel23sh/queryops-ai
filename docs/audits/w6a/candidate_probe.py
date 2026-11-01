"""Exploratory, provider-free candidate recall probe; run from backend/.

PYTHONPATH=. .venv/bin/python ../docs/audits/w6a/candidate_probe.py
No connection or database writes. Resource metadata uses seed specifications;
only the resource-loading seam is replaced, leaving schema projection and access
policy real. This is not persisted-resource, PostgreSQL, or RLS verification.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app.auth.access_context import AccessScopeContext, UserAccessContext
from app.domains.it_operations.seed import DATA_RESOURCE_SPECS
from app.models.product import DataResource
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.schema_context import build_schema_context
from app.query_engine.semantic_catalog import (
    MAX_SEMANTIC_PROJECTION_BYTES,
    SemanticCatalogProjection,
    build_semantic_catalog_projection,
    expand_semantic_concept_ids,
)
from app.query_engine.semantic_grounding import (
    _concept_is_authorized,
    _project_concept,
    _project_entity,
    _project_metric,
    _project_relationship,
    _relationship_is_authorized,
)
from app.query_engine.service import _user_generation_context


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = "b1f03a4790c7569f7da0ef8d9be57ddd6da023c5"
KINDS = ("entities", "concepts", "metrics", "rules", "relationships")


def schema_fixture(mode: str) -> tuple[dict, dict]:
    """Real schema and permission projection over unpersisted seed metadata."""
    scope = AccessScopeContext(
        id=uuid.UUID(int=1), type="global", key="global", display_name="Synthetic",
        access_level="read", is_default=True, department_id=None,
    )
    access = UserAccessContext(
        user_id=uuid.UUID(int=2), role=None,
        permissions=frozenset({"can_query_scoped_data"}), scopes=(scope,),
        default_scope=scope, has_global_scope=True, subject_attributes={},
    )
    if mode == "no_permission":
        access = replace(access, permissions=frozenset())
    if mode == "no_scope":
        access = replace(access, scopes=(), default_scope=None, has_global_scope=False)
    resources = {}
    for spec in DATA_RESOURCE_SPECS:
        table, display, sensitivity, scope_type, scope_column, queryable, exportable, exposure = spec
        resources[table] = DataResource(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"w6a:resource:{table}"),
            resource_type="table", domain="it_operations", schema_name="public",
            table_name=table, column_name=None, display_name=display,
            sensitivity_level=sensitivity, scope_type=scope_type,
            scope_column=scope_column, is_queryable=queryable,
            is_exportable=exportable, llm_exposure_level=exposure,
            resource_metadata=None,
        )
    if mode == "device_not_queryable":
        resources["devices"].is_queryable = False
    with patch("app.query_engine.schema_context._load_data_resources_by_table", return_value=resources):
        schema = build_schema_context(None, access)  # type: ignore[arg-type]
    # These two controls isolate candidate closure after authorized projection.
    # Production schema_context exposes domain-pack columns, so these are injected
    # negative contexts rather than claims of a persisted field-level ACL.
    removed_column = {
        "missing_compliance_column": "compliance_status",
        "missing_assignee_column": "assigned_user_id",
    }.get(mode)
    if removed_column:
        schema["allowed_columns"]["devices"].remove(removed_column)
    return schema, _user_generation_context(access)


def catalog_sets(catalog) -> dict[str, set[str]]:
    return {
        "entities": {x.id for x in catalog.entities},
        "concepts": {x.id for x in catalog.concepts},
        "metrics": {x.id for x in catalog.metrics},
        "rules": {x.id for x in catalog.composition_rules},
        "relationships": {x.id for x in catalog.relationships},
    }


def authorized_sets(catalog, schema: dict) -> dict[str, set[str]]:
    tables = frozenset(schema["allowed_tables"])
    columns = {table: frozenset(values) for table, values in schema["allowed_columns"].items()}
    entities = {x.id for x in catalog.entities if x.table in tables}
    concepts = {
        x.id for x in catalog.concepts
        if x.entity_id in entities and _concept_is_authorized(x, catalog, columns)
    }
    return {
        "entities": entities,
        "concepts": concepts,
        "metrics": {
            x.id for x in catalog.metrics if x.entity_id in entities
            and set(expand_semantic_concept_ids(catalog, x.required_concept_ids)) <= concepts
        },
        "rules": {
            x.id for x in catalog.composition_rules
            if set((*x.all_of_concept_ids, *x.or_concept_ids)) <= concepts
        },
        "relationships": {
            x.id for x in catalog.relationships
            if _relationship_is_authorized(x, catalog.entities_by_id, tables, columns)
        },
    }


def summarize(results: list[dict]) -> dict:
    positive = [x for x in results if x["kind"] != "control"]
    summary = {
        "case_count": len(results), "positive_case_count": len(positive),
        "control_case_count": len(results) - len(positive),
        "stage_counts": dict(sorted(Counter(x["stage"] for x in results).items())),
        "controls_passed": sum(x["control_pass"] is True for x in results),
        "positive_cases_fully_projected": sum(x["all_expected_projected"] for x in positive),
    }
    for kind in KINDS:
        expected = sum(len(x["coverage"][kind]["expected"]) for x in positive)
        present = sum(len(x["coverage"][kind]["catalog_present"]) for x in positive)
        authorized = sum(len(x["coverage"][kind]["authorized"]) for x in positive)
        projected = sum(len(x["coverage"][kind]["projected"]) for x in positive)
        summary[kind] = {
            "expected_items": expected, "catalog_present_items": present,
            "authorized_items": authorized, "projected_items": projected,
            "projected_over_authorized": projected / authorized if authorized else None,
        }
    return summary


def projection_bytes(projection: SemanticCatalogProjection) -> int:
    return len(json.dumps(projection.as_prompt_dict(), sort_keys=True, separators=(",", ":")).encode())


def complete_projection(catalog, schema: dict, user: dict) -> SemanticCatalogProjection:
    """Offline size inventory, not a proposed production retrieval path."""
    authorized = authorized_sets(catalog, schema)
    return SemanticCatalogProjection(
        catalog_id=catalog.id, catalog_version=catalog.version, catalog_hash=catalog.digest,
        entities=tuple(_project_entity(x, frozenset(schema["allowed_columns"][x.table])) for x in catalog.entities if x.id in authorized["entities"]),
        relationships=tuple(_project_relationship(x) for x in catalog.relationships if x.id in authorized["relationships"]),
        concepts=tuple(_project_concept(x, catalog.entities_by_id[x.entity_id]) for x in catalog.concepts if x.id in authorized["concepts"]),
        metrics=tuple(_project_metric(x) for x in catalog.metrics if x.id in authorized["metrics"]),
        composition_rules=tuple({
            "id": x.id, "description": x.description,
            "all_of_concept_ids": list(x.all_of_concept_ids), "or_concept_ids": list(x.or_concept_ids),
        } for x in catalog.composition_rules if x.id in authorized["rules"]),
        authorization_guidance=tuple({
            "scope_type": x.scope_type, "possessive_references": list(x.possessive_references),
            "enforcement": x.enforcement, "description": x.description,
            "scope_reference_resolved": user["scope_reference_resolved"],
        } for x in catalog.authorization_guidance if x.scope_type == user["scope_type"]),
        examples=(), candidate_signals=(), authoritative_business_terms=(),
    )


def alternative_summary(cases: list[dict], catalog, schema: dict, user: dict) -> dict:
    """Post-first-run mechanism inventory; excluded from primary corpus scores.

    Every alternative copies authorized production projections in memory only.
    No compression, cap increase, trimming, prompt, or runtime change is tested.
    """
    full = complete_projection(catalog, schema, user)
    variants = {"all_authorized_facts_minimal": [], "all_entities_and_relationships": [], "selected_entity_definition_closure": []}
    for case in cases:
        if case["kind"] == "control":
            continue
        current = build_semantic_catalog_projection(catalog, case["question"], schema, user)
        selected_entities = {x["id"] for x in current.entities}
        closure_concepts = tuple(x for x in full.concepts if x["entity_id"] in selected_entities)
        closure_concept_ids = {x["id"] for x in closure_concepts}
        alternatives = {
            "all_authorized_facts_minimal": full,
            "all_entities_and_relationships": replace(current, entities=full.entities, relationships=full.relationships),
            "selected_entity_definition_closure": replace(
                current, concepts=closure_concepts,
                metrics=tuple(x for x in full.metrics if x["entity_id"] in selected_entities),
                composition_rules=tuple(x for x in full.composition_rules if set(x["all_of_concept_ids"] + x["or_concept_ids"]) <= closure_concept_ids),
            ),
        }
        for name, alternative in alternatives.items():
            selected = {
                "entities": {x["id"] for x in alternative.entities},
                "concepts": {x["id"] for x in alternative.concepts},
                "metrics": {x["id"] for x in alternative.metrics},
                "rules": {x["id"] for x in alternative.composition_rules},
                "relationships": {x["id"] for x in alternative.relationships},
            }
            size = projection_bytes(alternative)
            covered = all(set(case["expected"][kind]) <= selected[kind] for kind in KINDS)
            variants[name].append({"id": case["id"], "projection_bytes": size,
                                   "within_cap": size <= MAX_SEMANTIC_PROJECTION_BYTES,
                                   "all_expected_ids_present": covered})
    return {
        "classification": "post_first_run_offline_alternative_inventory_not_independent_validation",
        "cap_bytes": MAX_SEMANTIC_PROJECTION_BYTES,
        "full_authorized_cardinality": {kind: len(ids) for kind, ids in authorized_sets(catalog, schema).items()},
        "full_facts_minimal_bytes": projection_bytes(full),
        "full_facts_omits": ["examples", "candidate_signals", "suggested_result_intent"],
        "alternatives": {name: {
            "cases": len(items),
            "all_expected_ids_present": sum(x["all_expected_ids_present"] for x in items),
            "within_cap": sum(x["within_cap"] for x in items),
            "covered_and_within_cap": sum(x["all_expected_ids_present"] and x["within_cap"] for x in items),
            "min_bytes": min(x["projection_bytes"] for x in items),
            "max_bytes": max(x["projection_bytes"] for x in items),
            "over_cap_ids": [x["id"] for x in items if not x["within_cap"]],
            "missing_expected_ids_case_ids": [x["id"] for x in items if not x["all_expected_ids_present"]],
        } for name, items in variants.items()},
        "limits": [
            "Copy-only availability/byte inventory: lexical signals are preserved rather than reranked for copied definitions.",
            "All-positive corpus targets are present in the full authorized catalog by construction; 100 percent unbounded availability is tautological.",
            "No alternative is a complete implementation or measured model improvement. Items above the cap are unusable under the current contract.",
            "Broadening can add ambiguous/irrelevant choices; false selection, latency, cost, prompt interaction and deployment safety are unmeasured.",
        ],
    }


def main() -> None:
    source_check = subprocess.run(
        ["git", "diff", "--quiet", SOURCE, "--", "backend/app", "backend/scripts", "backend/tests"],
        cwd=ROOT, check=False,
    )
    assert source_check.returncode == 0, "Production/test baseline differs; freeze a new investigation first"
    raw_cases = (HERE / "candidate-cases.json").read_bytes()
    corpus = json.loads(raw_cases)
    assert corpus["classification"] == "exploratory_not_blinded_holdout"
    assert corpus["baseline_source"] == SOURCE
    cases = corpus["cases"]
    assert len(cases) == len({x["id"] for x in cases})
    pack = load_it_operations_domain_pack()
    catalog = pack.semantic_catalog
    baseline = json.loads((HERE / "baseline.json").read_text())
    assert baseline["source_commit"] == SOURCE
    assert baseline["catalog"]["catalog_hash"] == catalog.digest
    available = catalog_sets(catalog)
    contexts = {mode: schema_fixture(mode) for mode in sorted({x["context"] for x in cases})}
    results = []
    for case in cases:
        schema, user = contexts[case["context"]]
        authorized = authorized_sets(catalog, schema)
        projection = build_semantic_catalog_projection(catalog, case["question"], schema, user)
        prompt = projection.as_prompt_dict()
        # Self-checks verify probe invariants without converting a retrieval miss
        # into a failing test or a claim about provider/final-answer correctness.
        assert prompt == build_semantic_catalog_projection(catalog, case["question"], schema, user).as_prompt_dict()
        assert projection.grounded_result_intent is None
        size = projection_bytes(projection)
        assert size <= MAX_SEMANTIC_PROJECTION_BYTES
        selected = {
            "entities": {x["id"] for x in projection.entities},
            "concepts": {x["id"] for x in projection.concepts},
            "metrics": {x["id"] for x in projection.metrics},
            "rules": {x["id"] for x in projection.composition_rules},
            "relationships": {x["id"] for x in projection.relationships},
        }
        assert all(selected[kind] <= authorized[kind] for kind in KINDS)
        lexical_raw = projection.lexical_evidence()
        lexical = {
            kind: set(lexical_raw.get(f"{'entity' if kind == 'entities' else kind[:-1]}_ids", []))
            for kind in KINDS
        }
        if case["id"] == "devices-canonical":
            assert lexical["entities"] == {"devices"}
        coverage = {}
        for kind in KINDS:
            expected = set(case["expected"][kind])
            coverage[kind] = {
                "expected": sorted(expected),
                "catalog_present": sorted(expected & available[kind]),
                "authorized": sorted(expected & authorized[kind]),
                "projected": sorted(expected & selected[kind]),
                "missing_from_catalog": sorted(expected - available[kind]),
                "authorization_excluded": sorted((expected & available[kind]) - authorized[kind]),
                "missing_from_projection": sorted((expected & authorized[kind]) - selected[kind]),
            }
        fully_projected = all(not (set(case["expected"][kind]) - selected[kind]) for kind in KINDS)
        control_pass = None
        if case["kind"] == "control":
            control_pass = fully_projected
            if case.get("expect_empty_entities"):
                control_pass &= not selected["entities"]
            control_pass &= all(not (set(ids) & selected[kind]) for kind, ids in case.get("forbidden", {}).items())
            control_pass &= all(not (set(ids) & lexical[kind]) for kind, ids in case.get("forbidden_lexical", {}).items())
            stage = "control_satisfied" if control_pass else "control_failed"
        elif any(x["missing_from_catalog"] for x in coverage.values()):
            stage = "catalog_absent"
        elif any(x["authorization_excluded"] for x in coverage.values()):
            stage = "authorization_excluded"
        elif coverage["entities"]["missing_from_projection"]:
            stage = "entity_retrieval_miss"
        elif coverage["relationships"]["missing_from_projection"]:
            stage = "relationship_context_miss"
        elif not fully_projected:
            stage = "definition_context_miss"
        else:
            stage = "covered"
        results.append({
            "id": case["id"], "family": case["family"], "kind": case["kind"],
            "context": case["context"], "stage": stage,
            "all_expected_projected": fully_projected, "control_pass": control_pass,
            "coverage": coverage,
            "selected": {kind: sorted(ids) for kind, ids in selected.items()},
            "lexical": {kind: sorted(ids) for kind, ids in lexical.items()},
            "projection_bytes": size,
            "misleading_entity_only": bool(
                set(case.get("misleading_if_only", [])) & selected["entities"]
                and not set(case["expected"]["entities"]) & selected["entities"]
            ),
            "decoy_ids_present": {
                kind: sorted(set(ids) & selected[kind])
                for kind, ids in case.get("decoy_ids", {}).items()
            },
            "provider_selection": "not_measured", "final_correctness": "not_measured",
        })
    grouped = {}
    for kind in sorted({x["kind"] for x in results}):
        grouped[kind] = summarize([x for x in results if x["kind"] == kind])
    vocab = [x for x in results if x["kind"] == "vocabulary"]
    vocab_families = sorted({x["family"] for x in vocab})
    output = {
        "schema_version": 1, "classification": corpus["classification"],
        "baseline_source": SOURCE,
        "source_paths_unchanged": ["backend/app", "backend/scripts", "backend/tests"],
        "corpus_sha256": hashlib.sha256(raw_cases).hexdigest(),
        "catalog_id": catalog.id, "catalog_version": catalog.version,
        "catalog_hash": catalog.digest,
        "schema_method": "production_schema_context_and_access_policy_with_unpersisted_seed_metadata_loader_fixture",
        "context_table_counts": {mode: len(schema["allowed_tables"]) for mode, (schema, _) in contexts.items()},
        "catalog_ids": {kind: sorted(ids) for kind, ids in available.items()},
        "global_authorized_ids": {kind: sorted(ids) for kind, ids in authorized_sets(catalog, contexts["global"][0]).items()},
        "context_authorization_excluded_from_global": {
            mode: {
                kind: sorted(authorized_sets(catalog, contexts["global"][0])[kind] - authorized_sets(catalog, schema)[kind])
                for kind in KINDS
                if authorized_sets(catalog, contexts["global"][0])[kind] - authorized_sets(catalog, schema)[kind]
            }
            for mode, (schema, _) in contexts.items() if mode != "global"
        },
        "summary": summarize(results), "by_kind": grouped,
        "offline_alternative_inventory": alternative_summary(cases, catalog, *contexts["global"]),
        "vocabulary_families": {
            "count": len(vocab_families),
            "with_entity_miss": [family for family in vocab_families if any(x["family"] == family and x["stage"] == "entity_retrieval_miss" for x in vocab)],
            "fully_covered": [family for family in vocab_families if all(x["all_expected_projected"] for x in vocab if x["family"] == family)],
        },
        "warnings": [
            "Exploratory researcher-authored corpus; not population recall, blinded holdout, release evidence, or a model benchmark.",
            "Policy and schema functions run unchanged; persisted metadata/effective permission resolution, PostgreSQL, RLS, and API execution are not tested.",
            "Missing-column modes inject negative post-projection contexts; production schema builder exposes domain-pack columns.",
            "Expected IDs measure availability only; laptop subtype filters, chosen definition, grain, Boolean meaning and final correctness are not scored.",
            "Extra candidates and absent lexical matches are not errors by themselves; provider selection is not measured.",
            "A missing rule/metric can sometimes be expressed by other supported forms; an absent required entity cannot be selected in a valid plan.",
            "No provider invoked, SQL rendered/executed, row read, database connected, or database write performed.",
        ],
    }
    compact_results = []
    for row in results:
        compact = {
            "id": row["id"], "stage": row["stage"], "selected": row["selected"],
            "lexical": {kind: ids for kind, ids in row["lexical"].items() if ids},
            "projection_bytes": row["projection_bytes"],
            "missing": {
                kind: values["missing_from_projection"] for kind, values in row["coverage"].items()
                if values["missing_from_projection"]
            },
        }
        for field in ("missing_from_catalog", "authorization_excluded"):
            missing = {kind: values[field] for kind, values in row["coverage"].items() if values[field]}
            if missing:
                compact[field] = missing
        if row["control_pass"] is not None:
            compact["control_pass"] = row["control_pass"]
        if row["misleading_entity_only"]:
            compact["misleading_entity_only"] = True
        if row["decoy_ids_present"]:
            compact["decoy_ids_present"] = row["decoy_ids_present"]
        compact_results.append(compact)
    # One case per line keeps repeated graph IDs auditable without thousands of
    # redundant lines. Expected IDs remain in the separately hashed corpus.
    encoded = json.dumps(output, indent=2, sort_keys=True)[:-2]
    encoded += ',\n  "results": [\n'
    encoded += ",\n".join("    " + json.dumps(row, sort_keys=True, separators=(",", ":")) for row in compact_results)
    encoded += "\n  ]\n}\n"
    (HERE / "candidate-results.json").write_text(encoded)
    print(json.dumps({"summary": output["summary"], "by_kind": grouped,
                      "vocabulary_families": output["vocabulary_families"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
