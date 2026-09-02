from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.domains.it_operations.seed import SeedSummary, expected_seed_table_counts
from app.evaluation import environment
from app.db.base import Base
from app.domains.it_operations.seed import seed_database
from app.evaluation.environment import (
    EvaluationEnvironmentIdentity,
    EvaluationEnvironmentError,
    build_evaluation_environment_manifest,
    evaluation_database_fingerprint,
    reference_time_is_eligible,
    validate_evaluation_environment_manifest,
    validate_persisted_environment_identity,
)
from app.evaluation.loader import (
    load_it_operations_evaluation_set,
    load_it_operations_evaluation_v2_set,
)
from app.evaluation.selection import evaluation_dataset_digest
from app.models.product import Permission, Role, RolePermission


REFERENCE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def test_release_environment_manifest_builds_and_validates_exact_v2_identity(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_release_environment(monkeypatch)
    manifest = build_evaluation_environment_manifest(
        object(),  # type: ignore[arg-type]
        _release_seed_summary(),
        source_git_sha="a" * 40,
    )
    evaluation_set = load_it_operations_evaluation_v2_set()

    assert manifest["dataset"] == {
        "id": "it_operations_v2",
        "version": "2",
        "digest": evaluation_dataset_digest(evaluation_set),
    }

    path = tmp_path / "evaluation-environment.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    identity = validate_evaluation_environment_manifest(
        object(),  # type: ignore[arg-type]
        path,
        now=REFERENCE_TIME,
        source_git_sha="a" * 40,
    )
    assert identity.source_git_sha == "a" * 40


def test_release_environment_manifest_rejects_historical_v1_identity(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_release_environment(monkeypatch)
    manifest = build_evaluation_environment_manifest(
        object(),  # type: ignore[arg-type]
        _release_seed_summary(),
        source_git_sha="a" * 40,
    )
    historical = load_it_operations_evaluation_set()
    manifest["dataset"] = {
        "id": historical.dataset_id,
        "version": historical.version,
        "digest": evaluation_dataset_digest(historical),
    }
    path = tmp_path / "evaluation-environment-v1.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(EvaluationEnvironmentError) as exc_info:
        validate_evaluation_environment_manifest(
            object(),  # type: ignore[arg-type]
            path,
            now=REFERENCE_TIME,
            source_git_sha="a" * 40,
        )

    assert exc_info.value.code == "evaluation_dataset_identity_mismatch"


def test_evaluation_database_fingerprint_is_deterministic_for_seed_inputs() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(
            db,
            profile_name="small",
            reset=True,
            reference_now=REFERENCE_TIME,
        )
        seeded_identity_timestamps = [
            *db.scalars(select(Role.created_at)),
            *db.scalars(select(Role.updated_at)),
            *db.scalars(select(Permission.created_at)),
            *db.scalars(select(Permission.updated_at)),
            *db.scalars(select(RolePermission.created_at)),
        ]
        assert seeded_identity_timestamps
        assert all(
            _as_utc(value) == REFERENCE_TIME for value in seeded_identity_timestamps
        )
        first_digest, first_counts = evaluation_database_fingerprint(db)
        seed_database(
            db,
            profile_name="small",
            reset=True,
            reference_now=REFERENCE_TIME,
        )
        second_digest, second_counts = evaluation_database_fingerprint(db)

    engine.dispose()
    assert first_digest == second_digest
    assert first_counts == second_counts
    assert len(first_digest) == 64


def test_evaluation_database_fingerprint_changes_with_reference_time() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(
            db,
            profile_name="small",
            reset=True,
            reference_now=REFERENCE_TIME,
        )
        first_digest, _ = evaluation_database_fingerprint(db)
        seed_database(
            db,
            profile_name="small",
            reset=True,
            reference_now=REFERENCE_TIME + timedelta(days=1),
        )
        second_digest, _ = evaluation_database_fingerprint(db)

    engine.dispose()
    assert first_digest != second_digest


def test_persisted_environment_identity_is_strict_and_time_bounded() -> None:
    identity = _identity()

    assert validate_persisted_environment_identity(identity.as_dict()) == identity
    assert validate_persisted_environment_identity(
        {**identity.as_dict(), "raw_rows": []}
    ) is None
    assert validate_persisted_environment_identity(
        {**identity.as_dict(), "database_fingerprint": "invalid"}
    ) is None
    assert reference_time_is_eligible(identity, REFERENCE_TIME + timedelta(hours=24))
    assert not reference_time_is_eligible(
        identity,
        REFERENCE_TIME + timedelta(hours=24, seconds=1),
    )


def _identity() -> EvaluationEnvironmentIdentity:
    return EvaluationEnvironmentIdentity(
        manifest_version="queryops-evaluation-environment-v1",
        seed_version="it-operations-seed-v1",
        seed_profile="medium",
        seed=42,
        reference_time="2026-08-24T12:00:00Z",
        source_git_sha="a" * 40,
        alembic_revision="0010_disable_inactive_user",
        postgres_version="16.9",
        database_fingerprint="b" * 64,
        dependency_manifest_hash="c" * 64,
    )


def _release_seed_summary() -> SeedSummary:
    return SeedSummary(
        profile_name="medium",
        seed=42,
        reference_now=REFERENCE_TIME,
        table_counts=expected_seed_table_counts("medium"),
        anomaly_counts={"reviewed_fixture": 1},
    )


def _stub_release_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(environment, "_require_release_database", lambda _db: None)
    monkeypatch.setattr(
        environment,
        "evaluation_database_fingerprint",
        lambda _db: ("b" * 64, {"departments": 6}),
    )
    monkeypatch.setattr(
        environment,
        "_alembic_revision",
        lambda _db: "0010_disable_inactive_user",
    )
    monkeypatch.setattr(environment, "_postgres_version", lambda _db: "16.9")
    monkeypatch.setattr(environment, "_dependency_manifest_hash", lambda: "c" * 64)
    monkeypatch.setattr(environment, "_runtime_versions", lambda: {"runtime": "test"})


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
