from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.action_engine.base import ActionTargetInput, ActionTargetReference
from app.action_engine.registry import (
    UnknownActionTypeError,
    build_default_action_registry,
)
from app.auth.access_context import UserAccessContext, build_user_access_context
from app.db.base import Base
from app.domains.it_operations.actions.reclaim_unused_license import (
    ELIGIBLE_NO_USAGE,
    ELIGIBLE_UNUSED,
    OVER_THRESHOLD,
    OVERRIDE_EXCEPTION,
    OVERRIDE_MANDATORY,
    OVERRIDE_SERVICE_ACCOUNT,
    SKIP_INVALID,
    SKIP_RECENT,
    SKIP_RECLAIMED,
    SKIP_SUSPENDED,
    ActionExecutionUnavailableError,
    ReclaimActionPreview,
    ReclaimCandidateRead,
    ReclaimCandidateRow,
    ReclaimUnusedLicenseHandler,
)
from app.domains.it_operations.seed import seed_database
from app.models.product import AccessScope, AppUser, SupportedActionType


NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


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


def test_exactly_sixty_days_is_not_older_than_the_boundary(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    row = _row(finance_scope, last_used_at=NOW - timedelta(days=60))

    preview = _preview(db_session, context, finance_scope, [row])

    assert preview.eligible_records == ()
    assert [record.reason_code for record in preview.skipped_records] == [SKIP_RECENT]


def test_older_than_sixty_days_is_eligible(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, last_used_at=NOW - timedelta(days=60, seconds=1))],
    )

    assert len(preview.eligible_records) == 1
    assert preview.eligible_records[0].reason_code == ELIGIBLE_UNUSED


def test_recent_use_is_skipped(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, last_used_at=NOW - timedelta(days=30))],
    )

    assert preview.skipped_records[0].reason_code == SKIP_RECENT


def test_null_last_used_is_eligible_and_high_confidence(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, last_used_at=None)],
    )

    record = preview.eligible_records[0]
    assert record.reason_code == ELIGIBLE_NO_USAGE
    assert record.high_confidence is True
    assert preview.high_confidence_count == 1


def test_older_than_ninety_days_is_high_confidence(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, last_used_at=NOW - timedelta(days=90, seconds=1))],
    )

    assert preview.eligible_records[0].high_confidence is True


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        ("reclaimed", SKIP_RECLAIMED),
        ("suspended", SKIP_SUSPENDED),
    ],
)
def test_non_active_assignment_is_hard_skipped(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
    status: str,
    reason_code: str,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, assignment_status=status)],
    )

    assert preview.skipped_records[0].reason_code == reason_code
    assert preview.admin_override_records == ()


@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"is_mandatory": True}, OVERRIDE_MANDATORY),
        ({"is_exception": True}, OVERRIDE_EXCEPTION),
        ({"account_type": "service"}, OVERRIDE_SERVICE_ACCOUNT),
    ],
)
def test_locked_policy_conditions_are_admin_override_records(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
    updates: dict,
    reason_code: str,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, **updates)],
    )

    assert preview.eligible_records == ()
    assert preview.skipped_records == ()
    assert reason_code in preview.admin_override_records[0].override_reason_codes
    assert preview.requires_admin is True


def test_normal_human_assignment_is_eligible(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(db_session, context, finance_scope, [_row(finance_scope)])

    assert len(preview.eligible_records) == 1
    assert preview.admin_override_records == ()
    assert preview.skipped_records == ()


def test_negative_monthly_cost_is_structurally_invalid_and_not_exposed(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [_row(finance_scope, monthly_cost_usd=Decimal("-1.00"))],
    )

    assert preview.eligible_records == ()
    assert preview.admin_override_records == ()
    assert preview.skipped_records[0].reason_code == SKIP_INVALID
    assert preview.skipped_records[0].monthly_cost_usd is None


def test_estimated_savings_uses_decimal_without_float_rounding(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [
            _row(finance_scope, monthly_cost_usd=Decimal("0.10")),
            _row(finance_scope, monthly_cost_usd=Decimal("0.20")),
            _row(
                finance_scope,
                monthly_cost_usd=Decimal("0.335"),
                is_mandatory=True,
            ),
        ],
    )

    assert preview.estimated_monthly_savings == Decimal("0.30")
    assert preview.override_estimated_monthly_savings == Decimal("0.34")


def test_candidate_costs_use_the_same_half_up_precision_as_the_aggregate(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    preview = _preview(
        db_session,
        context,
        finance_scope,
        [
            _row(finance_scope, monthly_cost_usd=Decimal("0.335")),
            _row(finance_scope, monthly_cost_usd=Decimal("0.335")),
        ],
    )

    assert [record.monthly_cost_usd for record in preview.eligible_records] == [
        Decimal("0.34"),
        Decimal("0.34"),
    ]
    assert preview.estimated_monthly_savings == Decimal("0.68")


def test_duplicated_requested_ids_do_not_duplicate_preview_rows(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    row = _row(finance_scope)
    reference = ActionTargetReference(
        record_type="license_assignment",
        record_id=row.assignment_id,
    )

    preview = _preview(
        db_session,
        context,
        finance_scope,
        [row],
        targets=(reference, reference),
    )

    assert [record.record_id for record in preview.eligible_records] == [
        row.assignment_id
    ]


def test_over_twenty_is_a_request_level_admin_flag_without_reclassification(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    rows = [_row(finance_scope) for _ in range(21)]

    preview = _preview(db_session, context, finance_scope, rows)

    assert len(preview.eligible_records) == 21
    assert preview.admin_override_records == ()
    assert OVER_THRESHOLD in {flag.code for flag in preview.policy_flags}
    assert preview.requires_admin is True


def test_every_examined_record_has_exactly_one_classification(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    rows = [
        _row(finance_scope),
        _row(finance_scope, last_used_at=NOW - timedelta(days=1)),
        _row(finance_scope, is_exception=True),
    ]

    preview = _preview(db_session, context, finance_scope, rows)
    groups = [
        {record.record_id for record in preview.eligible_records},
        {record.record_id for record in preview.skipped_records},
        {record.record_id for record in preview.admin_override_records},
    ]

    assert len(set.union(*groups)) == 3
    assert groups[0].isdisjoint(groups[1])
    assert groups[0].isdisjoint(groups[2])
    assert groups[1].isdisjoint(groups[2])


def test_default_registry_registers_only_reclaim_and_unknown_types_fail_closed() -> None:
    registry = build_default_action_registry()

    assert registry.registered_action_types == (
        SupportedActionType.RECLAIM_UNUSED_LICENSE,
    )
    with pytest.raises(UnknownActionTypeError, match="No handler is registered"):
        registry.get(SupportedActionType.DISABLE_INACTIVE_USER)


def test_revalidation_and_execution_fail_closed_in_pr2(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
) -> None:
    handler = ReclaimUnusedLicenseHandler(
        candidate_reader=_reader([_row(finance_scope)])
    )
    preview = handler.build_preview(
        db=db_session,
        target=_target(finance_scope),
        requester=context,
        now=NOW,
    )

    with pytest.raises(ActionExecutionUnavailableError, match="Revalidation"):
        handler.revalidate(
            db=db_session,
            preview=preview,
            approver=context,
            now=NOW,
        )

    with pytest.raises(ActionExecutionUnavailableError, match="Execution"):
        handler.execute(
            db=db_session,
            action_request_id=uuid.uuid4(),
            approved_by_app_user_id=uuid.uuid4(),
            revalidation=None,  # type: ignore[arg-type]
            idempotency_key="not-executable-in-pr2",
            now=NOW,
        )


def _preview(
    db_session: Session,
    context: UserAccessContext,
    finance_scope: AccessScope,
    rows: list[ReclaimCandidateRow],
    *,
    targets: tuple[ActionTargetReference, ...] = (),
) -> ReclaimActionPreview:
    return ReclaimUnusedLicenseHandler(candidate_reader=_reader(rows)).build_preview(
        db=db_session,
        target=_target(finance_scope, targets=targets),
        requester=context,
        now=NOW,
    )


def _target(
    scope: AccessScope,
    *,
    targets: tuple[ActionTargetReference, ...] = (),
) -> ActionTargetInput:
    assert scope.department_id is not None
    return ActionTargetInput(
        action_type=SupportedActionType.RECLAIM_UNUSED_LICENSE,
        scope_type=scope.scope_type,
        scope_key=scope.scope_key,
        scope_id=scope.id,
        department_id=scope.department_id,
        targets=targets,
        reason="Deterministic reclaim preview",
    )


def _reader(rows: list[ReclaimCandidateRow]):
    deduplicated = {
        row.assignment_id: row
        for row in rows
    }

    def read(_db, _target, _requester):
        return ReclaimCandidateRead(
            records=tuple(deduplicated.values()),
            runtime_role="queryops_query_runtime",
            transaction_read_only=True,
            row_security_enabled=True,
        )

    return read


def _row(
    scope: AccessScope,
    *,
    assignment_status: str = "active",
    last_used_at: datetime | None = NOW - timedelta(days=61),
    is_mandatory: bool = False,
    is_exception: bool = False,
    account_type: str = "human",
    monthly_cost_usd: Decimal = Decimal("17.25"),
) -> ReclaimCandidateRow:
    assert scope.department_id is not None
    user_id = uuid.uuid4()
    return ReclaimCandidateRow(
        assignment_id=uuid.uuid4(),
        assignment_user_id=user_id,
        assignment_department_id=scope.department_id,
        assignment_status=assignment_status,
        last_used_at=last_used_at,
        is_mandatory=is_mandatory,
        is_exception=is_exception,
        directory_user_id=user_id,
        directory_user_department_id=scope.department_id,
        user_display_label=f"User {str(user_id)[:8]}",
        account_type=account_type,
        license_id=uuid.uuid4(),
        license_product="QueryOps Test Suite",
        license_vendor="QueryOps",
        monthly_cost_usd=monthly_cost_usd,
    )
