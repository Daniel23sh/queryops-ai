from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domains.it_operations.seed import seed_database
from app.evaluation.environment import (
    EvaluationEnvironmentIdentity,
    evaluation_database_fingerprint,
    reference_time_is_eligible,
    validate_persisted_environment_identity,
)


REFERENCE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


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
