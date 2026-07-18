from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.action_engine.base import ActionTargetInput, ActionTargetReference
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.db.base import Base
from app.domains.it_operations.actions.disable_inactive_user import (
    ELIGIBLE_INACTIVE,
    OVER_THRESHOLD,
    OVERRIDE_CROSS_SCOPE,
    OVERRIDE_OPEN_CRITICAL_EVENT,
    OVERRIDE_PRIVILEGED,
    SKIP_ALREADY_DISABLED,
    SKIP_RECENT_LOGIN,
    SKIP_SERVICE_ACCOUNT,
    SKIP_UNAVAILABLE,
    DisableCandidateRead,
    DisableCandidateRow,
    DisableInactiveUserHandler,
)
from app.domains.it_operations.seed import seed_database
from app.models.product import AccessScope, AppUser, SupportedActionType


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_database(session, profile_name="small", reset=True)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def context(db_session: Session) -> UserAccessContext:
    manager = db_session.query(AppUser).filter_by(
        email="demo.manager@queryops.local"
    ).one()
    return build_user_access_context(manager, db_session)


@pytest.fixture
def finance_scope(db_session: Session) -> AccessScope:
    return db_session.query(AccessScope).filter_by(
        scope_type="department",
        scope_key="finance",
    ).one()


def test_inactive_human_is_eligible(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(db_session, context, finance_scope, [_row(finance_scope)])

    assert len(preview.eligible_records) == 1
    assert preview.eligible_records[0].reason_code == ELIGIBLE_INACTIVE
    assert preview.requires_admin is False


def test_exactly_ninety_days_is_eligible(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, latest_login=NOW - timedelta(days=90))],
    )

    assert len(preview.eligible_records) == 1


def test_recent_successful_login_is_skipped(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, latest_login=NOW - timedelta(days=89, hours=23))],
    )

    assert preview.skipped_records[0].reason_code == SKIP_RECENT_LOGIN
    assert preview.recent_login_skipped_count == 1


def test_no_successful_login_history_is_eligible(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, latest_login=None)],
    )

    assert len(preview.eligible_records) == 1


def test_already_disabled_user_is_skipped(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, account_status="disabled")],
    )

    assert preview.skipped_records[0].reason_code == SKIP_ALREADY_DISABLED


def test_service_account_is_hard_skipped_and_never_override_executable(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [
            _row(
                finance_scope,
                account_type="service",
                is_privileged=True,
                has_open_critical_security_event=True,
            )
        ],
    )

    assert preview.skipped_records[0].reason_code == SKIP_SERVICE_ACCOUNT
    assert preview.admin_override_records == ()
    assert preview.service_accounts_excluded_count == 1


def test_missing_user_is_a_nondisclosing_skip(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    target_id = uuid.uuid4()
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [],
        target_ids=(target_id,),
    )

    assert preview.skipped_records[0].record_id == target_id
    assert preview.skipped_records[0].reason_code == SKIP_UNAVAILABLE


def test_duplicate_target_ids_do_not_duplicate_preview_rows(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    row = _row(finance_scope)
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [row, row],
        target_ids=(row.directory_user_id, row.directory_user_id),
    )

    assert [record.record_id for record in preview.eligible_records] == [
        row.directory_user_id
    ]


def test_privileged_human_requires_admin_override(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, is_privileged=True)],
    )

    assert OVERRIDE_PRIVILEGED in (
        preview.admin_override_records[0].override_reason_codes
    )
    assert preview.privileged_users_count == 1


def test_open_critical_security_event_requires_admin_override(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, has_open_critical_security_event=True)],
    )

    assert OVERRIDE_OPEN_CRITICAL_EVENT in (
        preview.admin_override_records[0].override_reason_codes
    )
    assert preview.open_security_events_count == 1


def test_cross_scope_human_requires_admin_override(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    other_scope = db_session.query(AccessScope).filter_by(
        scope_type="department",
        scope_key="it",
    ).one()
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(other_scope)],
    )

    assert OVERRIDE_CROSS_SCOPE in (
        preview.admin_override_records[0].override_reason_codes
    )
    assert preview.crosses_scopes is True


def test_over_twenty_is_request_level_only(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope) for _ in range(21)],
    )

    assert len(preview.eligible_records) == 21
    assert preview.admin_override_records == ()
    assert OVER_THRESHOLD in {flag.code for flag in preview.policy_flags}


def _preview(
    db: Session,
    context: UserAccessContext,
    scope: AccessScope,
    rows: list[DisableCandidateRow],
    *,
    target_ids: tuple[uuid.UUID, ...] | None = None,
):
    deduplicated = {row.directory_user_id: row for row in rows}

    def reader(_db, _target, _requester):
        return DisableCandidateRead(
            records=tuple(deduplicated.values()),
            runtime_role="queryops_query_runtime",
            transaction_read_only=True,
            row_security_enabled=True,
        )

    selected = target_ids or tuple(deduplicated)
    target = ActionTargetInput(
        action_type=SupportedActionType.DISABLE_INACTIVE_USER,
        scope_type=scope.scope_type,
        scope_key=scope.scope_key,
        scope_id=scope.id,
        department_id=scope.department_id,
        targets=tuple(
            ActionTargetReference(record_type="directory_user", record_id=record_id)
            for record_id in selected
        ),
        reason="Disable inactive users",
    )
    return DisableInactiveUserHandler(candidate_reader=reader).build_preview(
        db=db,
        target=target,
        requester=context,
        now=NOW,
    )


def _row(
    scope: AccessScope,
    *,
    account_type: str = "human",
    account_status: str = "active",
    latest_login: datetime | None = NOW - timedelta(days=91),
    is_privileged: bool = False,
    has_open_critical_security_event: bool = False,
) -> DisableCandidateRow:
    assert scope.department_id is not None
    user_id = uuid.uuid4()
    return DisableCandidateRow(
        directory_user_id=user_id,
        department_id=scope.department_id,
        account_type=account_type,
        account_status=account_status,
        user_display_label=f"User {str(user_id)[:8]}",
        latest_successful_login_at=latest_login,
        is_privileged=is_privileged,
        has_open_critical_security_event=has_open_critical_security_event,
    )
