from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.domains.it_operations.seed import seed_database
from app.evaluation.environment import (
    EvaluationEnvironmentError,
    build_evaluation_environment_manifest,
    validate_evaluation_environment_manifest,
    validate_persisted_environment_identity,
)
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.runner import EvaluationRunner
from app.evaluation.selection import EvaluationFilters
from app.models.product import EvaluationResult, EvaluationRun
from app.query_engine.llm_provider import LLMProviderFailure
from app.query_engine.provider_config import (
    OpenAIProviderSettings,
    ProviderId,
    ProviderSettings,
    provider_descriptor,
)
from tests.action_postgres_test_db import validated_disposable_database_url


def test_frozen_provider_identity_and_failed_usage_round_trip_in_postgres(tmp_path):
    url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Provider integrity requires disposable PostgreSQL.")
    engine = create_engine(validated_disposable_database_url(url), pool_pre_ping=True)
    settings = ProviderSettings(ProviderId.OPENAI, OpenAIProviderSettings(api_key="synthetic-never-network"))
    reference = datetime.now(UTC).replace(microsecond=0)
    try:
        with Session(engine) as db:
            summary = seed_database(db, profile_name="medium", reset=True, reference_now=reference)
            manifest = build_evaluation_environment_manifest(db, summary, source_git_sha="a" * 40, provider_settings=settings)
            db.commit()
        path = tmp_path / "frozen.json"
        path.write_text(json.dumps(manifest))
        with Session(engine) as db:
            identity = validate_evaluation_environment_manifest(db, path, source_git_sha="a" * 40, provider_settings=settings)
            with pytest.raises(EvaluationEnvironmentError) as caught:
                validate_evaluation_environment_manifest(
                    db, path, source_git_sha="a" * 40,
                    provider_settings=replace(settings, openai=replace(settings.openai, reasoning_effort="medium")),
                )
            assert caught.value.code == "evaluation_provider_runtime_mismatch"

        class FailedProvider:
            provider_name = "openai"
            model_name = settings.model_label

            def generate_plan(self, *_args, **_kwargs):
                raise LLMProviderFailure("provider_response_invalid", measurement={
                    "provider": "openai", "model_label": self.model_name,
                    "call_count": 1, "attempt_count": None, "usage_complete": False,
                    "duration_ms": 12.5, "input_tokens": 25,
                    "private_payload": "must-not-persist",
                })

        run = EvaluationRunner(
            sessionmaker(engine, expire_on_commit=False),
            dataset_loader=load_it_operations_evaluation_v2_set,
            provider_descriptor=provider_descriptor(settings),
            provider_factory=lambda _pack: FailedProvider(),
            evaluation_environment=identity,
        ).run(EvaluationFilters(case_id="itops-easy-005"))
        with Session(engine) as db:
            persisted = db.get(EvaluationRun, run.run_id)
            result = db.scalar(select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run.run_id))
            assert persisted is not None and result is not None
            assert persisted.summary["evaluation_environment"] == identity.as_dict()
            assert validate_persisted_environment_identity(persisted.summary["evaluation_environment"]) == identity
            measurement = result.metrics["provider_measurement"]
            assert measurement["call_count"] == 1
            assert measurement["attempt_count"] is None
            assert measurement["input_tokens"] == 25
            assert measurement["usage_complete"] is False
            assert result.actual_output["error_code"] == "provider_response_invalid"
            assert persisted.summary["provider_usage"] == {
                "call_count": 1, "attempt_count": None, "duration_ms": 12.5,
                "input_tokens": None, "cached_input_tokens": None,
                "output_tokens": None, "total_tokens": None,
            }
            assert "must-not-persist" not in repr([persisted.summary, result.metrics, result.actual_output])
            assert "synthetic-never-network" not in path.read_text()
    finally:
        engine.dispose()
