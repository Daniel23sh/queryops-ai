from __future__ import annotations

import json
import re
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Any, Literal, Protocol

from sqlalchemy import Engine, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext
from app.auth.access_policy import QUERY_ACTIONS, authorize_resource_access
from app.core.rls import build_rls_context, set_rls_context
from app.models.product import DataResource
from app.query_engine.runtime_role import set_query_runtime_role
from app.query_engine.sql_validator import SQLValidationResult


QUERY_EXECUTION_PUBLIC_ERROR = "Query execution failed safely."
QUERY_EXECUTION_AUTHORIZATION_ERROR = "You are not authorized to access this resource."
QUERY_ACTION = "query:scoped_data"
DEFAULT_STATEMENT_TIMEOUT_MS = 5_000
DEFAULT_ROW_LIMIT = 500
MAX_STATEMENT_TIMEOUT_MS = 30_000
MAX_ROW_LIMIT = 1_000
PROHIBITED_SQL_KEYWORDS = frozenset(
    {
        "alter",
        "call",
        "copy",
        "create",
        "delete",
        "do",
        "drop",
        "execute",
        "grant",
        "insert",
        "merge",
        "reset",
        "revoke",
        "set",
        "truncate",
        "update",
        "upsert",
    }
)


class ValidationLike(Protocol):
    valid: bool
    sanitized_sql: str | None
    referenced_tables: list[str]
    referenced_columns: dict[str, list[str]]
    error_code: str | None
    reason: str | None
    public_error: str | None


@dataclass(frozen=True)
class SQLExecutionOptions:
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS
    row_limit: int = DEFAULT_ROW_LIMIT
    query_action: str = QUERY_ACTION
    max_payload_bytes: int | None = None
    acquisition_deadline: float | None = None


@dataclass(frozen=True)
class SQLExecutionResult:
    status: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: float
    truncated: bool
    execution_metadata: dict[str, Any] = field(default_factory=dict)
    referenced_tables: list[str] = field(default_factory=list)
    error_code: str | None = None
    public_error: str | None = None


def execute_validated_sql(
    db: Session | Engine | Connection,
    access_context: UserAccessContext,
    validation_result: SQLValidationResult | ValidationLike,
    *,
    options: SQLExecutionOptions | None = None,
) -> SQLExecutionResult:
    started_at = perf_counter()
    execution_options = _normalize_options(options)
    referenced_tables = sorted(set(getattr(validation_result, "referenced_tables", [])))

    if not getattr(validation_result, "valid", False):
        return _failure(
            started_at,
            "invalid_sql",
            validation_result.public_error or QUERY_EXECUTION_PUBLIC_ERROR,
            referenced_tables,
        )

    sanitized_sql = getattr(validation_result, "sanitized_sql", None)
    if not sanitized_sql:
        return _failure(
            started_at,
            "invalid_sql",
            QUERY_EXECUTION_PUBLIC_ERROR,
            referenced_tables,
        )
    if not _sanitized_sql_is_read_only(sanitized_sql):
        return _failure(
            started_at,
            "unsafe_sql",
            QUERY_EXECUTION_PUBLIC_ERROR,
            referenced_tables,
        )
    if not referenced_tables:
        return _failure(
            started_at,
            "missing_referenced_tables",
            QUERY_EXECUTION_PUBLIC_ERROR,
            referenced_tables,
        )

    engine = _engine_from_db(db)
    if engine.dialect.name != "postgresql":
        return _failure(
            started_at,
            "postgres_required",
            QUERY_EXECUTION_PUBLIC_ERROR,
            referenced_tables,
        )

    resources = _load_data_resources_for_execution(db, referenced_tables)
    resource_error = _validate_and_authorize_resources(
        resources,
        referenced_tables,
        access_context,
        execution_options.query_action,
    )
    if resource_error is not None:
        return _failure(
            started_at,
            resource_error,
            (
                QUERY_EXECUTION_AUTHORIZATION_ERROR
                if resource_error == "access_denied"
                else QUERY_EXECUTION_PUBLIC_ERROR
            ),
            referenced_tables,
        )

    try:
        if isinstance(db, Connection):
            result = _execute_on_runtime_connection(
                db,
                access_context,
                sanitized_sql,
                referenced_tables,
                execution_options,
                started_at,
            )
        else:
            result = _execute_in_read_only_runtime_role(
                engine,
                access_context,
                sanitized_sql,
                referenced_tables,
                execution_options,
                started_at,
            )
        if result.status != "succeeded":
            return replace(
                result,
                execution_metadata={
                    **result.execution_metadata,
                    "delivery_completeness": "unknown",
                },
            )
        safety_bound_reached = (
            getattr(validation_result, "limit_source", None)
            in {"safety_added", "safety_clamped"}
            and getattr(validation_result, "effective_limit", None) is not None
            and result.row_count >= validation_result.effective_limit
        )
        return replace(
            result,
            execution_metadata={
                **result.execution_metadata,
                "delivery_completeness": (
                    "unknown"
                    if result.execution_metadata.get("payload_limited") is True
                    or result.execution_metadata.get("timeout") is True
                    else "safety_limited"
                    if safety_bound_reached or result.truncated
                    else "unknown"
                    if getattr(validation_result, "limit_source", None) is None
                    else "complete"
                ),
            },
        )
    except SQLAlchemyError as exc:
        original = getattr(exc, "orig", None)
        return _failure(
            started_at,
            "database_error",
            QUERY_EXECUTION_PUBLIC_ERROR,
            referenced_tables,
            execution_metadata={
                "internal_error_type": type(exc).__name__,
                "timeout": getattr(original, "sqlstate", None) == "57014",
            },
        )


@contextmanager
def query_runtime_transaction(
    db: Session | Engine | Connection,
    access_context: UserAccessContext,
    *,
    isolation_level: Literal["read_committed", "repeatable_read"] = "read_committed",
    timezone_name: Literal["UTC"] | None = None,
) -> Generator[Connection, None, None]:
    """Open one governed read-only query-runtime transaction."""
    engine = _engine_from_db(db)
    if engine.dialect.name != "postgresql":
        raise TypeError("Query runtime transactions require PostgreSQL.")
    with engine.connect() as connection:
        with connection.begin():
            isolation = (
                " ISOLATION LEVEL REPEATABLE READ"
                if isolation_level == "repeatable_read"
                else ""
            )
            # This must be the first statement in the transaction.
            connection.execute(text(f"SET TRANSACTION{isolation} READ ONLY"))
            resources = connection.execute(
                select(DataResource).where(DataResource.resource_type == "table")
            ).mappings().all()
            set_query_runtime_role(connection)
            if timezone_name is not None:
                connection.execute(text(f"SET LOCAL TIME ZONE '{timezone_name}'"))
            set_rls_context(connection, build_rls_context(access_context))
            connection.info["queryops_runtime_context"] = _context_identity(
                access_context
            )
            connection.info["queryops_runtime_resources"] = {
                row["table_name"]: DataResource(**dict(row)) for row in resources
            }
            try:
                yield connection
            finally:
                connection.info.pop("queryops_runtime_context", None)
                connection.info.pop("queryops_runtime_resources", None)


def _normalize_options(options: SQLExecutionOptions | None) -> SQLExecutionOptions:
    raw_options = options or SQLExecutionOptions()
    statement_timeout_ms = max(
        1,
        min(int(raw_options.statement_timeout_ms), MAX_STATEMENT_TIMEOUT_MS),
    )
    row_limit = max(1, min(int(raw_options.row_limit), MAX_ROW_LIMIT))
    return SQLExecutionOptions(
        statement_timeout_ms=statement_timeout_ms,
        row_limit=row_limit,
        query_action=(
            raw_options.query_action
            if raw_options.query_action in QUERY_ACTIONS
            else QUERY_ACTION
        ),
        max_payload_bytes=(
            max(1, int(raw_options.max_payload_bytes))
            if raw_options.max_payload_bytes is not None
            else None
        ),
        acquisition_deadline=raw_options.acquisition_deadline,
    )


def _engine_from_db(db: Session | Engine | Connection) -> Engine:
    if isinstance(db, Engine):
        return db
    if isinstance(db, Connection):
        return db.engine
    bind = db.get_bind()
    if isinstance(bind, Engine):
        return bind
    if isinstance(bind, Connection):
        return bind.engine
    raise TypeError("SQL executor requires a SQLAlchemy Session, Engine, or Connection.")


def _load_data_resources(
    engine: Engine,
    table_names: list[str],
) -> dict[str, DataResource]:
    with Session(engine) as session:
        resources = session.scalars(
            select(DataResource)
            .where(
                DataResource.resource_type == "table",
                DataResource.table_name.in_(table_names),
            )
            .order_by(DataResource.table_name)
        ).all()
        return {resource.table_name: resource for resource in resources}


def _load_data_resources_for_execution(
    db: Session | Engine | Connection,
    table_names: list[str],
) -> dict[str, DataResource]:
    if not isinstance(db, Connection):
        return _load_data_resources(_engine_from_db(db), table_names)
    cache = db.info.get("queryops_runtime_resources")
    if not isinstance(cache, dict):
        return {}
    return {name: cache[name] for name in table_names if name in cache}


def _validate_and_authorize_resources(
    resources_by_table: dict[str, DataResource],
    referenced_tables: list[str],
    access_context: UserAccessContext,
    query_action: str,
) -> str | None:
    for table_name in referenced_tables:
        resource = resources_by_table.get(table_name)
        if resource is None:
            return "resource_not_found"
        if resource.is_queryable is not True or table_name == "it_audit_events":
            return "resource_not_queryable"

        decision = authorize_resource_access(
            access_context,
            query_action,
            resource,
            _runtime_context_for_resource(access_context, resource),
        )
        if not decision.allowed:
            return "access_denied"

    return None


def _runtime_context_for_resource(
    access_context: UserAccessContext,
    resource: DataResource,
) -> dict[str, str]:
    if not resource.scope_type:
        return {}

    scope_key = _scope_key_for_resource(access_context, resource.scope_type)
    runtime_context = {"scope_type": resource.scope_type}
    if scope_key is not None:
        runtime_context["scope_key"] = scope_key
    return runtime_context


def _scope_key_for_resource(
    access_context: UserAccessContext,
    scope_type: str,
) -> str | None:
    if access_context.has_global_scope:
        return "global"

    default_scope = access_context.default_scope
    if default_scope is not None and default_scope.type == scope_type:
        return default_scope.key

    matching_keys = sorted(
        scope.key for scope in access_context.scopes if scope.type == scope_type
    )
    return matching_keys[0] if matching_keys else None


def _execute_in_read_only_runtime_role(
    engine: Engine,
    access_context: UserAccessContext,
    sanitized_sql: str,
    referenced_tables: list[str],
    options: SQLExecutionOptions,
    started_at: float,
) -> SQLExecutionResult:
    with query_runtime_transaction(engine, access_context) as connection:
        return _execute_on_runtime_connection(
            connection,
            access_context,
            sanitized_sql,
            referenced_tables,
            options,
            started_at,
        )


def _execute_on_runtime_connection(
    connection: Connection,
    access_context: UserAccessContext,
    sanitized_sql: str,
    referenced_tables: list[str],
    options: SQLExecutionOptions,
    started_at: float,
) -> SQLExecutionResult:
    connection.execute(
        text(f"SET LOCAL statement_timeout = {options.statement_timeout_ms}")
    )
    runtime_role = connection.execute(text("SELECT current_user")).scalar_one()
    transaction_read_only = connection.execute(text("SHOW transaction_read_only")).scalar_one()
    transaction_isolation = connection.execute(text("SHOW transaction_isolation")).scalar_one()
    if (
        runtime_role != "queryops_query_runtime"
        or transaction_read_only != "on"
        or connection.info.get("queryops_runtime_context")
        != _context_identity(access_context)
    ):
        raise SQLAlchemyError("Query runtime connection is not governed.")
    result = connection.execute(
        text(sanitized_sql),
        execution_options=(
            {"stream_results": True, "max_row_buffer": 1}
            if options.max_payload_bytes is not None
            else None
        ),
    )
    try:
        columns = list(result.keys())
        if len(columns) != len(set(columns)):
            return _failure(
                started_at, "ambiguous_output_columns", QUERY_EXECUTION_PUBLIC_ERROR,
                referenced_tables,
            )
        rows: list[dict[str, Any]] = []
        payload_bytes = 2 if options.max_payload_bytes is not None else 0
        payload_limited = False
        acquisition_timed_out = False
        truncated = False
        for row in result.mappings():
            if (
                options.acquisition_deadline is not None
                and perf_counter() >= options.acquisition_deadline
            ):
                acquisition_timed_out = True
                break
            if (
                options.max_payload_bytes is not None
                and payload_bytes > options.max_payload_bytes
            ):
                payload_limited = True
                break
            if len(rows) == options.row_limit:
                truncated = True
                break
            mapped = dict(row)
            if options.max_payload_bytes is not None:
                encoded_size = normalized_json_size(
                    mapped,
                    maximum=options.max_payload_bytes - payload_bytes,
                )
                if rows:
                    encoded_size += 1
                if payload_bytes + encoded_size > options.max_payload_bytes:
                    payload_limited = True
                    break
                payload_bytes += encoded_size
            rows.append(mapped)
            if (
                options.acquisition_deadline is not None
                and perf_counter() >= options.acquisition_deadline
            ):
                acquisition_timed_out = True
                break
    finally:
        result.close()
    return SQLExecutionResult(
        status="succeeded",
        columns=columns,
        rows=rows,
        row_count=len(rows),
        duration_ms=_duration_ms(started_at),
        truncated=truncated,
        execution_metadata={
            "runtime_role": runtime_role,
            "transaction_read_only": transaction_read_only,
            "transaction_isolation": transaction_isolation,
            "statement_timeout_ms": options.statement_timeout_ms,
            "row_limit": options.row_limit,
            "payload_bytes": payload_bytes,
            "payload_limited": payload_limited,
            "timeout": acquisition_timed_out,
        },
        referenced_tables=referenced_tables,
        error_code=None,
        public_error=None,
    )


def normalized_json_size(value: Any, *, maximum: int | None = None) -> int:
    size = 0
    for chunk in json.JSONEncoder(
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    ).iterencode(value):
        size += len(chunk.encode("utf-8"))
        if maximum is not None and size > maximum:
            return maximum + 1
    return size


def _sanitized_sql_is_read_only(sanitized_sql: str) -> bool:
    if ";" in sanitized_sql:
        return False

    masked_sql = _mask_string_literals(sanitized_sql)
    lowered = masked_sql.strip().lower()
    if not (lowered.startswith("select ") or lowered.startswith("with ")):
        return False

    return not any(
        re.search(rf"\b{re.escape(keyword)}\b", lowered)
        for keyword in PROHIBITED_SQL_KEYWORDS
    )


def _context_identity(access_context: UserAccessContext) -> tuple[Any, ...]:
    return (
        str(access_context.user_id),
        access_context.role,
        tuple(sorted(access_context.permissions)),
        access_context.has_global_scope,
        tuple(
            sorted(
                (
                    str(scope.id),
                    scope.type,
                    scope.key,
                    scope.access_level,
                    scope.is_default,
                    str(scope.department_id) if scope.department_id else None,
                )
                for scope in access_context.scopes
            )
        ),
        str(access_context.default_scope.id) if access_context.default_scope else None,
        json.dumps(
            access_context.subject_attributes,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _mask_string_literals(sql: str) -> str:
    chars = list(sql)
    index = 0
    while index < len(chars):
        if chars[index] != "'":
            index += 1
            continue

        index += 1
        while index < len(chars):
            if chars[index] == "'":
                if index + 1 < len(chars) and chars[index + 1] == "'":
                    chars[index] = " "
                    chars[index + 1] = " "
                    index += 2
                    continue
                index += 1
                break
            chars[index] = " "
            index += 1
    return "".join(chars)


def _failure(
    started_at: float,
    error_code: str,
    public_error: str,
    referenced_tables: list[str],
    *,
    execution_metadata: dict[str, Any] | None = None,
) -> SQLExecutionResult:
    return SQLExecutionResult(
        status="failed",
        columns=[],
        rows=[],
        row_count=0,
        duration_ms=_duration_ms(started_at),
        truncated=False,
        execution_metadata={
            "delivery_completeness": "unknown",
            **(execution_metadata or {}),
        },
        referenced_tables=referenced_tables,
        error_code=error_code,
        public_error=public_error,
    )


def _duration_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)
