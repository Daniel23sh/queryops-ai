"""Synthetic fixtures for the guarded Access & Workflow Integrity browser lane."""
from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domains.it_operations.seed import seed_database
from app.models.product import (
    AccessScope, AppAuditLog, AppUser, Dashboard, RoleUpgradeRequest, UserAccessScope,
)
from scripts.prepare_m8_e2e import UnsafeE2EDatabaseError, validated_e2e_database_url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=(
        "setup", "reset", "revoke-analyst", "assign-finance", "assign-global",
        "revoke-user", "inspect-user",
    ))
    operation = parser.parse_args().operation
    try:
        target = validated_e2e_database_url(
            os.environ.get("M8_E2E_DATABASE_URL", ""),
            disposable_opt_in=os.environ.get("M8_E2E_DATABASE_DISPOSABLE"),
            application_url=os.environ.get("DATABASE_URL"),
            application_database_name=os.environ.get("POSTGRES_DB", "queryops"),
        )
        engine = create_engine(target)
        try:
            with Session(engine) as db:
                if operation in {"setup", "reset"}:
                    seed_database(db, profile_name="small", reset=True)
                analyst = _user(db, "demo.analyst@queryops.local")
                user = _user(db, "demo.user@queryops.local")
                result = {}
                if operation == "setup":
                    admin = _user(db, "demo.admin@queryops.local")
                    for key in ("it", "finance", "sales"):
                        scope = _scope(db, "department", key)
                        dashboard = Dashboard(
                            owner_user_id=admin.id, title=f"Access integrity {key}",
                            visibility_scope="department", department_id=scope.department_id,
                        )
                        db.add(dashboard)
                        db.flush()
                        result[key] = str(dashboard.id)
                    dashboard = Dashboard(owner_user_id=admin.id, title="Access integrity global", visibility_scope="global")
                    db.add(dashboard)
                    db.flush()
                    result["global"] = str(dashboard.id)
                elif operation in {"revoke-analyst", "revoke-user"}:
                    actor = analyst if operation == "revoke-analyst" else user
                    db.execute(delete(UserAccessScope).where(UserAccessScope.user_id == actor.id))
                elif operation in {"assign-finance", "assign-global"}:
                    scope = _scope(db, "department", "finance") if operation == "assign-finance" else _scope(db, "global", "global")
                    db.add(UserAccessScope(user_id=analyst.id, scope_id=scope.id, access_level="manage", is_default=False))
                elif operation == "inspect-user":
                    result = {
                        "role": user.role.name,
                        "scopes": [str(item) for item in db.scalars(select(UserAccessScope.scope_id).where(UserAccessScope.user_id == user.id))],
                        "decision_audits": db.scalar(select(func.count()).select_from(AppAuditLog).where(
                            AppAuditLog.entity_id.in_(select(RoleUpgradeRequest.id).where(RoleUpgradeRequest.requester_user_id == user.id)),
                            AppAuditLog.event_type.in_(["role_request.approved", "role_request.rejected"]),
                        )),
                    }
                db.commit()
                print(json.dumps(result))
        finally:
            engine.dispose()
    except (UnsafeE2EDatabaseError, SQLAlchemyError):
        print("Access integrity fixture failed safely.")
        return 2
    return 0


def _user(db: Session, email: str) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None, "Synthetic actor missing."
    return user


def _scope(db: Session, scope_type: str, key: str) -> AccessScope:
    scope = db.scalar(select(AccessScope).where(AccessScope.scope_type == scope_type, AccessScope.scope_key == key))
    assert scope is not None, "Synthetic scope missing."
    return scope


if __name__ == "__main__":
    raise SystemExit(main())
