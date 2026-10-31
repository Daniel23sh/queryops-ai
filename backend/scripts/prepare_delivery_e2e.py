"""Deterministic delivery sources, guarded to an explicitly disposable database."""
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

VENDOR = "Synthetic delivery fixture"
BASE_SQL = (
    "SELECT product_name, monthly_cost_usd FROM licenses "
    f"WHERE vendor = '{VENDOR}'"
)
SOURCES = {
    "below_cap": (f"{BASE_SQL} AND monthly_cost_usd <= 99 ORDER BY product_name", False),
    "at_cap": (f"{BASE_SQL} AND monthly_cost_usd <= 100 ORDER BY product_name", False),
    "above_cap": (f"{BASE_SQL} ORDER BY product_name", False),
    "top_100": (f"{BASE_SQL} ORDER BY product_name LIMIT 100", False),
    "top_500": (f"{BASE_SQL} ORDER BY product_name LIMIT 500", False),
    "clamped": (f"{BASE_SQL} ORDER BY product_name LIMIT 600", False),
    "table_11": (f"{BASE_SQL} ORDER BY product_name LIMIT 11", False),
    "table_24": (f"{BASE_SQL} ORDER BY product_name LIMIT 24", False),
    "legacy": (f"{BASE_SQL} ORDER BY product_name LIMIT 100", True),
}


def prepare_delivery_state(db: Session) -> dict:
    seed_database(db, profile_name="small", reset=True)
    db.add_all([
        License(product_name=f"Delivery {index:04d}", vendor=VENDOR, monthly_cost_usd=index)
        for index in range(1, 621)
    ])
    db.commit()
    analyst = db.scalar(select(AppUser).where(AppUser.email == "demo.analyst@queryops.local"))
    assert analyst is not None
    access = build_user_access_context(analyst, db)
    context = build_schema_context(db, access)
    dashboard = Dashboard(
        owner_user_id=analyst.id, title="Result delivery checks", visibility_scope="personal",
    )
    db.add(dashboard)
    db.flush()
    result = {"dashboard_id": str(dashboard.id), "query_runs": {}}
    for name, (sql, legacy) in SOURCES.items():
        validation = validate_sql(sql, context)
        assert validation.valid and validation.sanitized_sql
        execution = execute_validated_sql(db, access, validation)
        assert execution.status == "succeeded"
        metadata = {
            "referenced_tables": validation.referenced_tables,
            "execution": {
                "status": "succeeded", "row_count": execution.row_count,
                "truncated": execution.truncated,
                "delivery_completeness": execution.execution_metadata["delivery_completeness"],
            },
        }
        if not legacy:
            metadata["validation"] = bound_metadata(validation)
        else:
            metadata["execution"].pop("delivery_completeness")
        now = datetime.now(UTC)
        run = QueryRun(
            user_id=analyst.id, status="succeeded", natural_language_question=f"Delivery {name}",
            executed_sql=validation.sanitized_sql, row_count=execution.row_count,
            duration_ms=max(0, round(execution.duration_ms)), query_metadata=metadata,
            started_at=now, completed_at=now,
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
                result = prepare_delivery_state(db)
            print(json.dumps(result))
        finally:
            engine.dispose()
    except (UnsafeE2EDatabaseError, SQLAlchemyError):
        print("Delivery fixture failed safely.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
