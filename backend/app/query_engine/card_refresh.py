from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext
from app.models.product import AppUser, DashboardCard, QueryRun, RunStatus
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.schema_context import SchemaContextOptions, build_schema_context
from app.query_engine.sql_executor import (
    SQLExecutionOptions,
    SQLExecutionResult,
    execute_validated_sql,
)
from app.query_engine.sql_validator import SQLValidationResult, validate_sql


CARD_REFRESH_QUERY_ACTION = "query:scoped_data"
CARD_REFRESH_ROW_LIMIT = 100
SAFE_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CardRefreshSQLExecutor(Protocol):
    def __call__(
        self,
        db: Session,
        access_context: UserAccessContext,
        validation_result: SQLValidationResult,
        *,
        options: SQLExecutionOptions | None = None,
    ) -> SQLExecutionResult:
        raise NotImplementedError


def get_card_refresh_sql_executor() -> CardRefreshSQLExecutor:
    return execute_validated_sql


@dataclass(frozen=True)
class CardRefreshError(Exception):
    code: str
    message: str
    status_code: int


def refresh_dashboard_card(
    db: Session,
    *,
    card: DashboardCard,
    current_user: AppUser,
    access_context: UserAccessContext,
    sql_executor: CardRefreshSQLExecutor,
) -> dict[str, Any]:
    if card.saved_query_id is None or card.saved_query is None:
        raise _not_refreshable()
    if not access_context.has_permission("can_query_scoped_data"):
        raise _not_allowed()

    source_run = _latest_successful_query_run(db, card.saved_query_id)
    if source_run is None:
        raise _not_refreshable()
    if (
        not isinstance(source_run.executed_sql, str)
        or not source_run.executed_sql.strip()
    ):
        raise _not_refreshable()

    referenced_tables = _trusted_referenced_tables(source_run)
    if referenced_tables is None:
        raise _not_refreshable()

    validation_result = _validate_refresh_sql(
        db,
        access_context,
        source_run.executed_sql,
    )
    if not validation_result.valid or validation_result.sanitized_sql is None:
        if not _tables_are_accessible(db, access_context, referenced_tables):
            raise _not_allowed()
        raise _not_refreshable()
    if sorted(validation_result.referenced_tables) != referenced_tables:
        raise _not_refreshable()

    started_at = datetime.now(UTC)
    execution_result = sql_executor(
        db,
        access_context,
        validation_result,
        options=SQLExecutionOptions(
            row_limit=CARD_REFRESH_ROW_LIMIT,
            query_action=CARD_REFRESH_QUERY_ACTION,
        ),
    )
    if execution_result.status != "succeeded":
        if execution_result.error_code == "access_denied":
            raise _not_allowed()
        raise CardRefreshError(
            code="CARD_REFRESH_FAILED",
            message="Dashboard card refresh failed safely.",
            status_code=500,
        )

    completed_at = datetime.now(UTC)
    duration_ms = max(0, int(round(execution_result.duration_ms)))
    refresh_run = QueryRun(
        user_id=current_user.id,
        saved_query_id=card.saved_query_id,
        status=RunStatus.SUCCEEDED.value,
        natural_language_question=card.saved_query.natural_language_question,
        generated_sql=None,
        executed_sql=validation_result.sanitized_sql,
        row_count=execution_result.row_count,
        duration_ms=duration_ms,
        error_message=None,
        started_at=started_at,
        completed_at=completed_at,
        query_metadata={
            "source": "dashboard_card_refresh",
            "card_id": str(card.id),
            "dashboard_id": str(card.dashboard_id),
            "saved_query_id": str(card.saved_query_id),
            "refreshed_from_query_run_id": str(source_run.id),
            "referenced_tables": referenced_tables,
            "validation": {"valid": True, "error_code": None},
            "execution": {
                "status": "succeeded",
                "error_code": None,
                "row_count": execution_result.row_count,
                "duration_ms": duration_ms,
                "truncated": execution_result.truncated,
                "row_limit": CARD_REFRESH_ROW_LIMIT,
            },
        },
    )
    db.add(refresh_run)
    db.commit()
    db.refresh(refresh_run)

    return {
        "card_id": str(card.id),
        "dashboard_id": str(card.dashboard_id),
        "saved_query_id": str(card.saved_query_id),
        "query_run_id": str(refresh_run.id),
        "status": RunStatus.SUCCEEDED.value,
        "columns": execution_result.columns,
        "rows": execution_result.rows,
        "row_count": execution_result.row_count,
        "duration_ms": duration_ms,
        "truncated": execution_result.truncated,
        "refreshed_at": completed_at,
        "message": "Dashboard card refreshed successfully.",
        "warnings": [],
    }


def _latest_successful_query_run(
    db: Session,
    saved_query_id: UUID,
) -> QueryRun | None:
    return db.scalar(
        select(QueryRun)
        .where(
            QueryRun.saved_query_id == saved_query_id,
            QueryRun.status == RunStatus.SUCCEEDED.value,
        )
        .order_by(
            QueryRun.completed_at.desc().nulls_last(),
            QueryRun.created_at.desc(),
            QueryRun.id.desc(),
        )
        .limit(1)
    )


def _trusted_referenced_tables(query_run: QueryRun) -> list[str] | None:
    metadata = query_run.query_metadata
    if not isinstance(metadata, dict):
        return None
    raw_tables = metadata.get("referenced_tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        return None

    tables: set[str] = set()
    for raw_table in raw_tables:
        if not isinstance(raw_table, str):
            return None
        table_name = raw_table.strip().lower()
        if not table_name or SAFE_TABLE_NAME_RE.fullmatch(table_name) is None:
            return None
        tables.add(table_name)
    return sorted(tables) if tables else None


def _validate_refresh_sql(
    db: Session,
    access_context: UserAccessContext,
    executed_sql: str,
) -> SQLValidationResult:
    return validate_sql(executed_sql, _refresh_schema_context(db, access_context))


def _tables_are_accessible(
    db: Session,
    access_context: UserAccessContext,
    referenced_tables: list[str],
) -> bool:
    schema_context = _refresh_schema_context(db, access_context)
    return set(referenced_tables).issubset(set(schema_context["allowed_tables"]))


def _refresh_schema_context(
    db: Session,
    access_context: UserAccessContext,
) -> dict[str, Any]:
    return build_schema_context(
        db,
        access_context,
        domain_pack=load_it_operations_domain_pack(),
        options=SchemaContextOptions(query_action=CARD_REFRESH_QUERY_ACTION),
    )


def _not_refreshable() -> CardRefreshError:
    return CardRefreshError(
        code="CARD_NOT_REFRESHABLE",
        message="Dashboard card cannot be refreshed.",
        status_code=400,
    )


def _not_allowed() -> CardRefreshError:
    return CardRefreshError(
        code="CARD_REFRESH_NOT_ALLOWED",
        message="Dashboard card cannot be refreshed with your current permissions.",
        status_code=403,
    )
