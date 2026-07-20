from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.product import (
    ActionRequest,
    AppAuditLog,
    ApprovalRequest,
    Notification,
)
if __package__:
    from .prepare_m8_e2e import validated_e2e_database_url
else:
    from prepare_m8_e2e import validated_e2e_database_url


@dataclass(frozen=True)
class E2EActionState:
    action_requests: int
    approval_requests: int
    action_audit_events: int
    action_notifications: int


def inspect_action_state(session: Session) -> E2EActionState:
    return E2EActionState(
        action_requests=_count(session, select(func.count()).select_from(ActionRequest)),
        approval_requests=_count(
            session,
            select(func.count())
            .select_from(ApprovalRequest)
            .where(ApprovalRequest.action_request_id.is_not(None)),
        ),
        action_audit_events=_count(
            session,
            select(func.count())
            .select_from(AppAuditLog)
            .where(AppAuditLog.action_request_id.is_not(None)),
        ),
        action_notifications=_count(
            session,
            select(func.count())
            .select_from(Notification)
            .where(Notification.related_resource_type == "action_request"),
        ),
    )


def _count(session: Session, statement) -> int:
    return int(session.scalar(statement) or 0)


def main() -> None:
    target_url = validated_e2e_database_url(
        os.environ.get("M8_E2E_DATABASE_URL", ""),
        disposable_opt_in=os.environ.get("M8_E2E_DATABASE_DISPOSABLE"),
        application_url=os.environ.get("DATABASE_URL"),
        application_database_name=os.environ.get("POSTGRES_DB", "queryops"),
    )
    engine = create_engine(target_url)
    try:
        with Session(engine) as session:
            state = inspect_action_state(session)
    finally:
        engine.dispose()
    print(json.dumps(asdict(state), sort_keys=True))


if __name__ == "__main__":
    main()
