from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domains.it_operations.models import DirectoryUser, LicenseAssignment
from app.domains.it_operations.seed import REFERENCE_NOW, seed_database
from app.models.product import AccessScope, AppUser, UserAccessScope
from scripts.inspect_m8_e2e import inspect_action_state
from scripts.prepare_m8_e2e import (
    UnsafeE2EDatabaseError,
    prepare_e2e_state,
    validated_e2e_database_url,
)


TARGET = "postgresql+psycopg://queryops:queryops@127.0.0.1:5432/queryops_e2e_test"
APPLICATION = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"


@pytest.mark.parametrize(
    ("target", "opt_in", "application", "application_name", "message"),
    [
        (TARGET, None, APPLICATION, "queryops", "M8_E2E_DATABASE_DISPOSABLE"),
        ("sqlite:///queryops_e2e_test.db", "1", APPLICATION, "queryops", "PostgreSQL"),
        (
            "postgresql+psycopg://queryops:queryops@db.example.com/queryops_e2e_test",
            "1",
            APPLICATION,
            "queryops",
            "loopback",
        ),
        (
            f"{TARGET}?host=localhost",
            "1",
            APPLICATION,
            "queryops",
            "query parameters",
        ),
        (
            "postgresql+psycopg://queryops:queryops@localhost/queryops_release",
            "1",
            APPLICATION,
            "queryops",
            "test, dev, or e2e",
        ),
        (
            "postgresql+psycopg://queryops:queryops@localhost/queryops",
            "1",
            None,
            "queryops",
            "normal application database",
        ),
        (
            TARGET,
            "1",
            "postgresql+psycopg://queryops:queryops@localhost:5432/queryops_e2e_test",
            "queryops",
            "normal application database",
        ),
        (
            TARGET,
            "1",
            f"{APPLICATION}?hostaddr=127.0.0.1",
            "queryops",
            "endpoint query overrides",
        ),
        (f" {TARGET}", "1", APPLICATION, "queryops", "unambiguous"),
    ],
)
def test_e2e_database_guard_rejects_unsafe_targets(
    target: str,
    opt_in: str | None,
    application: str | None,
    application_name: str,
    message: str,
) -> None:
    with pytest.raises(UnsafeE2EDatabaseError, match=message):
        validated_e2e_database_url(
            target,
            disposable_opt_in=opt_in,
            application_url=application,
            application_database_name=application_name,
        )


@pytest.mark.parametrize(
    "target",
    [
        TARGET,
        "postgresql+psycopg://queryops:queryops@localhost:5432/queryops-test",
        "postgresql+psycopg://queryops:queryops@localhost:5432/dev_queryops",
    ],
)
def test_e2e_database_guard_accepts_explicit_disposable_local_targets(
    target: str,
) -> None:
    assert validated_e2e_database_url(
        target,
        disposable_opt_in="1",
        application_url=APPLICATION,
        application_database_name="queryops",
    ) == target


def test_e2e_preparation_is_idempotent_and_keeps_it_default(
    seeded_session: Session,
) -> None:
    now = REFERENCE_NOW + timedelta(days=22)
    first = prepare_e2e_state(seeded_session, now=now)
    second = prepare_e2e_state(seeded_session, now=now)

    analyst = seeded_session.scalar(
        select(AppUser).where(AppUser.email == "demo.analyst@queryops.local")
    )
    finance = seeded_session.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == "department",
            AccessScope.scope_key == "finance",
        )
    )
    assert analyst is not None and finance is not None
    assignments = seeded_session.scalars(
        select(UserAccessScope).where(UserAccessScope.user_id == analyst.id)
    ).all()
    assert first.created is True
    assert second.created is False
    assert first.stabilized_service_assignments == 1
    assert second.stabilized_service_assignments == 0
    assert len(assignments) == 2
    assert sum(assignment.is_default for assignment in assignments) == 1
    assert next(
        assignment for assignment in assignments if assignment.scope_id == finance.id
    ).access_level == "manage"
    assert seeded_session.scalar(
        select(func.count()).select_from(UserAccessScope).where(
            UserAccessScope.user_id == analyst.id,
            UserAccessScope.scope_id == finance.id,
        )
    ) == 1
    assert seeded_session.scalar(
        select(func.count())
        .select_from(LicenseAssignment)
        .join(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
        .where(
            LicenseAssignment.department_id == finance.department_id,
            LicenseAssignment.status == "active",
            LicenseAssignment.is_mandatory.is_(False),
            DirectoryUser.account_type == "service",
            LicenseAssignment.last_used_at < now - timedelta(days=60),
        )
    ) == 0


def test_e2e_action_state_inspection_tracks_only_action_lifecycle_rows(
    seeded_session: Session,
) -> None:
    state = inspect_action_state(seeded_session)

    assert state.action_requests == 0
    assert state.approval_requests == 0
    assert state.action_audit_events == 0
    assert state.action_notifications == 0


@pytest.fixture
def seeded_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, profile_name="small")
        session.commit()
        yield session
    engine.dispose()
