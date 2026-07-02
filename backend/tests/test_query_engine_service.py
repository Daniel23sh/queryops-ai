from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.access_context import UserAccessContext, build_user_access_context
from app.db.base import Base
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser, QueryRun
from app.query_engine.llm_provider import SQLGenerationResult
from app.query_engine.result_formatter import format_query_result
from app.query_engine.service import (
    QueryEngineRequest,
    QueryEngineService,
    QueryEngineServiceResult,
)
from app.query_engine.sql_executor import SQLExecutionResult
from app.query_engine.sql_validator import SQLValidationResult


def test_successful_template_query_creates_succeeded_query_run(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(
            question="How many open support tickets exist in my department by priority?",
            template_id="open_support_tickets_by_department",
        ),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert result.query_run_id == str(query_run.id)
    assert query_run.status == "succeeded"
    assert query_run.generated_sql is not None
    assert query_run.generated_sql.startswith("SELECT priority, status")
    assert query_run.executed_sql == executor.seen_sql[0]
    assert query_run.row_count == 1
    assert query_run.error_message is None
    assert query_run.query_metadata["template_id"] == "open_support_tickets_by_department"
    assert query_run.query_metadata["provider"] == "domain_pack_template"
    assert query_run.query_metadata["validation"]["valid"] is True
    assert query_run.query_metadata["execution"]["status"] == "succeeded"


def test_successful_known_mock_free_text_query_creates_succeeded_query_run(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show non-compliant devices in my department."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "succeeded"
    assert query_run.status == "succeeded"
    assert query_run.generated_sql is not None
    assert "FROM devices" in query_run.generated_sql
    assert query_run.executed_sql == executor.seen_sql[0]
    assert query_run.query_metadata["provider"] == "mock"
    assert query_run.query_metadata["model"] == "mock-queryops-v1"


def test_unsupported_question_creates_clarification_query_run_without_execution(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Can you forecast next year's laptop budget?"),
    )

    query_run = only_query_run(db_session)
    assert result.status == "clarification_required"
    assert result.clarification_required is True
    assert query_run.status == "failed"
    assert query_run.generated_sql is None
    assert query_run.executed_sql is None
    assert query_run.error_message == "I could not map that question to a supported query."
    assert query_run.query_metadata["clarification_required"] is True
    assert query_run.query_metadata["unsupported_reason"] == "unsupported_question"
    assert executor.seen_sql == []


def test_validation_failure_creates_failed_query_run_with_sanitized_error(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(
        executor=executor,
        validator=lambda _sql, _schema_context: SQLValidationResult(
            valid=False,
            sanitized_sql=None,
            referenced_tables=[],
            error_code="table_not_allowed",
            reason="internal parser detail for sensitive_table",
            public_error="SQL is not allowed for safe read-only querying.",
        ),
    )
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(
            question="Show non-compliant devices in my department.",
        ),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "validation_failed"
    assert query_run.status == "failed"
    assert query_run.error_message == "SQL is not allowed for safe read-only querying."
    assert "sensitive_table" not in query_run.error_message
    assert query_run.executed_sql is None
    assert query_run.query_metadata["validation"]["error_code"] == "table_not_allowed"
    assert executor.seen_sql == []


def test_execution_failure_creates_failed_query_run_with_sanitized_error(
    db_session: Session,
) -> None:
    executor = FakeExecutor(
        result=SQLExecutionResult(
            status="failed",
            columns=[],
            rows=[],
            row_count=0,
            duration_ms=4.2,
            truncated=False,
            execution_metadata={"internal_error_type": "UndefinedColumn"},
            referenced_tables=["devices"],
            error_code="database_error",
            public_error="Query execution failed safely.",
        )
    )
    service = QueryEngineService(executor=executor)
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show non-compliant devices in my department."),
    )

    query_run = only_query_run(db_session)
    assert result.status == "failed"
    assert result.error_code == "database_error"
    assert query_run.status == "failed"
    assert query_run.executed_sql == executor.seen_sql[0]
    assert query_run.error_message == "Query execution failed safely."
    assert "UndefinedColumn" not in query_run.error_message
    assert "missing_column" not in query_run.error_message


def test_generated_and_executed_sql_follow_security_storage_expectations(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(
        executor=executor,
        validator=lambda sql, _schema_context: SQLValidationResult(
            valid=True,
            sanitized_sql="SELECT id, hostname FROM devices LIMIT 25",
            referenced_tables=["devices"],
        ),
    )
    user = user_by_email(db_session, "demo.analyst@queryops.local")

    service.run(
        db_session,
        user,
        QueryEngineRequest(question="Show non-compliant devices in my department."),
    )

    query_run = only_query_run(db_session)
    assert query_run.generated_sql is not None
    assert "ORDER BY hostname" in query_run.generated_sql
    assert query_run.executed_sql == "SELECT id, hostname FROM devices LIMIT 25"
    assert executor.seen_sql == ["SELECT id, hostname FROM devices LIMIT 25"]


def test_service_never_executes_unsupported_provider_output(
    db_session: Session,
) -> None:
    executor = FakeExecutor()
    service = QueryEngineService(
        provider=UnsupportedSqlProvider(),
        executor=executor,
    )
    user = user_by_email(db_session, "demo.manager@queryops.local")

    result = service.run(
        db_session,
        user,
        QueryEngineRequest(question="Try something unsafe."),
    )

    query_run = only_query_run(db_session)
    assert result.clarification_required is True
    assert query_run.generated_sql is None
    assert query_run.executed_sql is None
    assert executor.seen_sql == []


def test_result_formatter_is_deterministic() -> None:
    execution_result = SQLExecutionResult(
        status="succeeded",
        columns=["name"],
        rows=[{"name": "Finance"}],
        row_count=1,
        duration_ms=3.6,
        truncated=False,
        execution_metadata={"runtime_role": "queryops_query_runtime"},
        referenced_tables=["departments"],
    )

    first = format_query_result(
        status="succeeded",
        query_run_id="run-1",
        execution_result=execution_result,
        warnings=["beta", "alpha"],
    )
    second = format_query_result(
        status="succeeded",
        query_run_id="run-1",
        execution_result=execution_result,
        warnings=["beta", "alpha"],
    )

    assert isinstance(first, QueryEngineServiceResult)
    assert first == second
    assert first.message == "Query completed successfully."
    assert first.warnings == ["alpha", "beta"]


class FakeExecutor:
    def __init__(self, result: SQLExecutionResult | None = None) -> None:
        self.result = result or SQLExecutionResult(
            status="succeeded",
            columns=["status", "ticket_count"],
            rows=[{"status": "open", "ticket_count": 2}],
            row_count=1,
            duration_ms=2.4,
            truncated=False,
            execution_metadata={"runtime_role": "queryops_query_runtime"},
            referenced_tables=["support_tickets"],
        )
        self.seen_sql: list[str] = []

    def __call__(
        self,
        _db: Session,
        _access_context: UserAccessContext,
        validation_result: SQLValidationResult,
        *,
        options: Any = None,
    ) -> SQLExecutionResult:
        assert options is not None
        self.seen_sql.append(validation_result.sanitized_sql or "")
        return self.result


class UnsupportedSqlProvider:
    provider_name = "unsupported-test-provider"
    model_name = "unsupported-test-model"

    def generate_sql(
        self,
        _question: str,
        _schema_context: dict[str, Any],
        _user_context: dict[str, Any],
        _options: dict[str, Any],
    ) -> SQLGenerationResult:
        return SQLGenerationResult(
            generated_sql="DROP TABLE directory_users",
            provider_name=self.provider_name,
            model_name=self.model_name,
            generation_metadata={"source": "test"},
            clarification_required=True,
            unsupported_reason="unsupported_question",
            safe_error="I could not map that question to a supported query.",
        )


def only_query_run(session: Session) -> QueryRun:
    query_runs = session.scalars(select(QueryRun)).all()
    assert len(query_runs) == 1
    return query_runs[0]


def user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


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
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("GROQ_API_KEY", None)

    try:
        yield session
    finally:
        session.close()
        engine.dispose()
