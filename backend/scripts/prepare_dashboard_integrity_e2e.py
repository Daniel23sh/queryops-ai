"""Deterministic dashboard measures, restricted to an explicitly disposable DB."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.access_context import build_user_access_context
from app.domains.it_operations.models import License
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser, Dashboard, QueryRun
from app.query_engine.delivery import bound_metadata
from app.query_engine.schema_context import build_schema_context
from app.query_engine.sql_executor import execute_validated_sql
from app.query_engine.sql_validator import validate_sql
from scripts.prepare_m8_e2e import UnsafeE2EDatabaseError, validated_e2e_database_url

VENDOR = "Synthetic dashboard integrity fixture"
PREDICATE = f"FROM licenses WHERE vendor = '{VENDOR}'"
SOURCES = {
    "total_licenses": f"SELECT COUNT(*) AS total_licenses {PREDICATE}",
    "max_cost": f"SELECT MAX(monthly_cost_usd) AS max_cost {PREDICATE}",
    "target_count": f"SELECT COUNT(*) AS target_count {PREDICATE}",
    "gauge": f"SELECT COUNT(*) AS current_count, SUM(monthly_cost_usd) AS target_count {PREDICATE}",
    "chart": f"SELECT product_name, monthly_cost_usd AS total_cost {PREDICATE} ORDER BY product_name LIMIT 2",
}


def prepare_dashboard_integrity_state(db: Session) -> dict:
    seed_database(db, profile_name="small", reset=True)
    db.add_all([
        License(product_name=f"Integrity {index:02d}", vendor=VENDOR, monthly_cost_usd=index)
        for index in range(1, 43)
    ])
    db.commit()
    analyst = db.scalar(select(AppUser).where(AppUser.email == "demo.analyst@queryops.local"))
    assert analyst is not None
    access = build_user_access_context(analyst, db)
    context = build_schema_context(db, access)
    dashboard = Dashboard(owner_user_id=analyst.id, title="Dashboard integrity checks", visibility_scope="personal")
    db.add(dashboard)
    db.flush()
    result = {"dashboard_id": str(dashboard.id), "query_runs": {}}
    for name, sql in SOURCES.items():
        validation = validate_sql(sql, context)
        assert validation.valid and validation.sanitized_sql, name
        execution = execute_validated_sql(db, access, validation)
        assert execution.status == "succeeded", name
        if name in {"total_licenses", "max_cost", "target_count"}:
            assert execution.rows == [{name: 42}], name
        now = datetime.now(UTC)
        run = QueryRun(
            user_id=analyst.id, status="succeeded", natural_language_question=f"Integrity {name}",
            executed_sql=validation.sanitized_sql, row_count=execution.row_count,
            duration_ms=max(0, round(execution.duration_ms)), started_at=now, completed_at=now,
            query_metadata={
                "referenced_tables": validation.referenced_tables,
                "validation": bound_metadata(validation),
                "execution": {
                    "status": "succeeded", "row_count": execution.row_count,
                    "truncated": execution.truncated,
                    "delivery_completeness": execution.execution_metadata["delivery_completeness"],
                },
            },
        )
        db.add(run)
        db.flush()
        result["query_runs"][name] = str(run.id)
    db.commit()
    return result


def main() -> int:
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
                result = prepare_dashboard_integrity_state(db)
            print(json.dumps(result))
        finally:
            engine.dispose()
    except (UnsafeE2EDatabaseError, SQLAlchemyError):
        print("Dashboard integrity fixture failed safely.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
