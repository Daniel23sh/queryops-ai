"""Freeze secret-free W6a identities; run from backend with PYTHONPATH=."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path

from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.selection import (
    EvaluationSuite,
    evaluation_dataset_digest,
    select_evaluation_suite,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.provider_config import (
    OFFICIAL_OPENAI_BASE_URL,
    ProviderSettings,
    installed_runtime_versions,
    load_provider_settings,
    provider_runtime_identity,
)
from app.query_engine.semantic_catalog import semantic_catalog_identity


SOURCE = "b1f03a4790c7569f7da0ef8d9be57ddd6da023c5"
ROOT = Path(__file__).resolve().parents[3]
INPUTS = ("backend", "frontend", "AGENTS.md", "docs/evaluation")


def main() -> None:
    subprocess.run(
        ["git", "diff", "--exit-code", SOURCE, "--", *INPUTS],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    tree = subprocess.check_output(
        ["git", "ls-tree", "-r", SOURCE, "--", *INPUTS], cwd=ROOT
    )
    dataset = load_it_operations_evaluation_v2_set()
    suite = select_evaluation_suite(dataset, EvaluationSuite.CANARY)
    # Identity only: no credential lookup, client construction or request.
    settings = load_provider_settings(
        {**os.environ, "OPENAI_API_KEY": "identity-only"}, provider_override="openai"
    )
    configured = settings.openai
    assert configured is not None
    result = {
        "diagnostic_only": True,
        "source_commit": SOURCE,
        "source_tree_sha256": hashlib.sha256(tree).hexdigest(),
        "source_tree_paths": list(INPUTS),
        "dataset": {
            "id": dataset.dataset_id,
            "version": dataset.version,
            "digest": evaluation_dataset_digest(dataset),
            "case_count": len(dataset.cases),
        },
        "catalog": semantic_catalog_identity(
            load_it_operations_domain_pack().semantic_catalog
        ),
        "canary_identity_only_not_executed": suite.as_safe_dict(),
        "seed": {
            "profile": "medium",
            "seed": 42,
            "reference_time_utc": "2026-11-01T09:20:36+00:00",
            "clock_note": "SQL transaction time is real; probes record it separately.",
        },
        "python": platform.python_version(),
        "postgres_image": {
            "tag": "postgres:16.14",
            "local_image_id": "sha256:95206741a5b214807675e14165369d05b93a9cf692223b616d07cca227e74b0b",
        },
        "packages": installed_runtime_versions(),
        "default_mock_identity_not_quality_evidence": provider_runtime_identity(
            ProviderSettings()
        ),
        "configured_openai_not_invoked": {
            "configuration_source": "shell environment plus code defaults; no dotenv file loaded",
            "provider": settings.provider.value,
            "model": settings.model_label,
            "endpoint": OFFICIAL_OPENAI_BASE_URL,
            "reasoning_effort": configured.reasoning_effort,
            "max_output_tokens": configured.max_output_tokens,
            "timeout_seconds": configured.timeout_seconds,
            "max_retries": configured.max_retries,
            "runtime_identity": provider_runtime_identity(settings),
            "credential_checked": False,
            "provider_calls": 0,
        },
        "probe_contract": {
            "plans": "handwritten downstream isolation, not provider output",
            "new_cases": "exploratory contrasts, not blinded held-out validation",
            "qualifies_release": False,
        },
    }
    assert result["dataset"]["digest"] == (
        "6ac164ab6c58c0b008a65afc01cd26aa434fecd3eaa402b5bdad9c89e6f6540f"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
