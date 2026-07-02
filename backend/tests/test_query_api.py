from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.queries import get_query_engine_service
from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import AppUser, Permission, PermissionEffect, QueryRun, UserPermission
from app.query_engine.result_formatter import QueryEngineServiceResult


SAFE_METADATA = {
    "provider": "mock",
    "model": "mock-queryops-v1",
    "template_id": "open_support_tickets_by_department",
    "referenced_tables": ["support_tickets"],
    "scope_type": "department",
    "clarification_required": False,
    "validation": {
        "valid": True,
        "error_code": None,
        "reason": "internal parser detail",
    },
    "execution": {
        "status": "succeeded",
        "error_code": None,
        "row_count": 1,
        "duration_ms": 2.4,
        "truncated": False,
        "runtime_role": "queryops_query_runtime",
    },
    "internal_policy_reason": "secret policy detail",
    "generated_sql": "SELECT hidden",
    "session_cookie": "qo_session=secret",
}


def test_query_run_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/queries/run", json={"question": "hello"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_query_clarify_requires_authentication(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/queries/{uuid.uuid4()}/clarify",
        json={"question": "hello"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_query_run_requires_csrf_for_authenticated_post(client: TestClient) -> None:
    _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        json={
            "question": "How many open support tickets exist in my department by priority?",
            "template_id": "open_support_tickets_by_department",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"


def test_allowed_template_query_runs_with_csrf(
    client: TestClient,
    fake_service: FakeQueryEngineService,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "question": "How many open support tickets exist in my department by priority?",
            "template_id": "open_support_tickets_by_department",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["query_run_id"]
    assert data["row_count"] == 1
    assert data["rows"] == [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "opened_at": "2026-07-02T09:00:00Z",
            "monthly_cost_usd": "12.50",
            "encrypted": True,
        }
    ]
    assert len(fake_service.calls) == 1
    assert fake_service.calls[0].template_id == "open_support_tickets_by_department"


def test_user_without_free_query_permission_is_denied(client: TestClient) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Show non-compliant devices in my department."},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_user_without_scoped_query_permission_cannot_run_hidden_template(
    client: TestClient,
    fake_service: FakeQueryEngineService,
) -> None:
    csrf_token = _login(client, "demo.user@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "question": "How many open support tickets exist in my department by priority?",
            "template_id": "open_support_tickets_by_department",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUERY_TEMPLATE_NOT_FOUND"
    assert fake_service.calls == []


def test_manager_template_response_hides_sql(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = _post_template_run(client, csrf_token)

    assert response.status_code == 200
    data = response.json()["data"]
    assert "generated_sql" not in data
    assert "executed_sql" not in data
    assert "SELECT" not in json.dumps(data)


def test_analyst_template_and_free_text_response_includes_sql(
    client: TestClient,
) -> None:
    csrf_token = _login(client, "demo.analyst@queryops.local")

    template_response = _post_template_run(client, csrf_token)
    free_text_response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Show non-compliant devices in my department."},
    )

    assert template_response.status_code == 200
    assert free_text_response.status_code == 200
    for response in (template_response, free_text_response):
        data = response.json()["data"]
        assert data["generated_sql"].startswith("SELECT")
        assert data["executed_sql"].startswith("SELECT")


def test_admin_response_includes_sql(client: TestClient) -> None:
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = _post_template_run(client, csrf_token)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["generated_sql"].startswith("SELECT")
    assert data["executed_sql"].startswith("SELECT")


def test_unsupported_free_text_returns_safe_clarification_and_persists(
    client: TestClient,
    db_session: Session,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Can you forecast next year's laptop budget?"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "clarification_required"
    assert data["clarification_required"] is True
    assert data["message"] == "I could not map that question to a supported query."
    query_run = db_session.get(QueryRun, uuid.UUID(data["query_run_id"]))
    assert query_run is not None
    assert query_run.status == "failed"
    assert query_run.error_message == "I could not map that question to a supported query."


def test_non_empty_parameters_are_rejected_without_invoking_service(
    client: TestClient,
    fake_service: FakeQueryEngineService,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "question": "How many open support tickets exist in my department by priority?",
            "template_id": "open_support_tickets_by_department",
            "parameters": {"priority": "high"},
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "QUERY_PARAMETERS_NOT_SUPPORTED"
    assert body["error"]["message"] == "Query template parameters are not supported yet."
    assert fake_service.calls == []


@pytest.mark.parametrize(
    "field_name",
    [
        "saved_query_id",
        "scope_id",
        "scope_key",
        "execution_options",
        "provider",
        "model",
        "raw_sql",
        "unknown_field",
    ],
)
def test_unsafe_or_unknown_execution_fields_are_rejected(
    client: TestClient,
    fake_service: FakeQueryEngineService,
    field_name: str,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "hello", field_name: "unsafe"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_QUERY_REQUEST"
    assert fake_service.calls == []


def test_history_returns_only_current_user_records_newest_first_and_hides_sql(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    old_run = _add_query_run(db_session, manager, "old manager run", minute=1)
    new_run = _add_query_run(db_session, manager, "new manager run", minute=2)
    _add_query_run(db_session, analyst, "other user run", minute=3)
    _login(client, manager.email)

    response = client.get("/api/v1/queries/history")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert [row["id"] for row in rows] == [str(new_run.id), str(old_run.id)]
    assert [row["natural_language_question"] for row in rows] == [
        "new manager run",
        "old manager run",
    ]
    assert "generated_sql" not in rows[0]
    assert "executed_sql" not in rows[0]
    assert "other user run" not in json.dumps(rows)


def test_history_includes_sql_for_analyst(client: TestClient, db_session: Session) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    _add_query_run(db_session, analyst, "analyst run", minute=1)
    _login(client, analyst.email)

    response = client.get("/api/v1/queries/history")

    assert response.status_code == 200
    row = response.json()["data"][0]
    assert row["generated_sql"] == "SELECT generated"
    assert row["executed_sql"] == "SELECT executed"


def test_detail_returns_only_current_user_query_run(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    query_run = _add_query_run(db_session, manager, "manager run", minute=1)
    _login(client, manager.email)

    response = client.get(f"/api/v1/queries/{query_run.id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(query_run.id)
    assert data["natural_language_question"] == "manager run"
    assert "generated_sql" not in data
    assert "executed_sql" not in data


def test_unknown_query_run_detail_returns_safe_404(client: TestClient) -> None:
    _login(client, "demo.manager@queryops.local")

    response = client.get(f"/api/v1/queries/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_FOUND"


def test_another_users_query_run_detail_returns_safe_404(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    other_run = _add_query_run(db_session, analyst, "analyst run", minute=1)
    _login(client, "demo.manager@queryops.local")

    response = client.get(f"/api/v1/queries/{other_run.id}")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "QUERY_RUN_NOT_FOUND"
    assert "analyst run" not in body["error"]["message"]


def test_user_can_clarify_own_query_run_and_new_run_links_metadata(
    client: TestClient,
    db_session: Session,
    fake_service: FakeQueryEngineService,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    original_run = _add_query_run(db_session, manager, "ambiguous manager run", minute=1)
    csrf_token = _login(client, manager.email)

    response = client.post(
        f"/api/v1/queries/{original_run.id}/clarify",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Show non-compliant devices in my department."},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["query_run_id"] != str(original_run.id)
    assert "generated_sql" not in data
    assert "executed_sql" not in data

    clarified_run = db_session.get(QueryRun, uuid.UUID(data["query_run_id"]))
    assert clarified_run is not None
    assert clarified_run.user_id == manager.id
    assert clarified_run.natural_language_question == "Show non-compliant devices in my department."
    assert clarified_run.query_metadata["clarified_from_query_run_id"] == str(original_run.id)
    assert fake_service.calls[-1].question == "Show non-compliant devices in my department."
    assert fake_service.calls[-1].metadata == {
        "clarified_from_query_run_id": str(original_run.id)
    }


def test_clarify_requires_csrf_for_authenticated_post(
    client: TestClient,
    db_session: Session,
    fake_service: FakeQueryEngineService,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    original_run = _add_query_run(db_session, manager, "ambiguous manager run", minute=1)
    _login(client, manager.email)

    response = client.post(
        f"/api/v1/queries/{original_run.id}/clarify",
        json={"question": "Show non-compliant devices in my department."},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert fake_service.calls == []


def test_unknown_query_run_clarify_returns_safe_404(
    client: TestClient,
    fake_service: FakeQueryEngineService,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        f"/api/v1/queries/{uuid.uuid4()}/clarify",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Show non-compliant devices in my department."},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_FOUND"
    assert fake_service.calls == []


def test_user_cannot_clarify_another_users_query_run(
    client: TestClient,
    db_session: Session,
    fake_service: FakeQueryEngineService,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    other_run = _add_query_run(db_session, analyst, "analyst run", minute=1)
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        f"/api/v1/queries/{other_run.id}/clarify",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Show non-compliant devices in my department."},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUERY_RUN_NOT_FOUND"
    assert fake_service.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"question": ""},
        {"question": "   "},
        {"question": "Show devices.", "template_id": "non_compliant_devices_by_department"},
        {"question": "Show devices.", "unknown": "field"},
    ],
)
def test_invalid_clarify_payload_is_rejected(
    client: TestClient,
    db_session: Session,
    fake_service: FakeQueryEngineService,
    payload: Any,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    original_run = _add_query_run(db_session, manager, "ambiguous manager run", minute=1)
    csrf_token = _login(client, manager.email)

    response = client.post(
        f"/api/v1/queries/{original_run.id}/clarify",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_QUERY_REQUEST"
    assert fake_service.calls == []


def test_clarify_response_includes_sql_only_for_can_view_sql(
    client: TestClient,
    db_session: Session,
) -> None:
    analyst = _user_by_email(db_session, "demo.analyst@queryops.local")
    original_run = _add_query_run(db_session, analyst, "ambiguous analyst run", minute=1)
    csrf_token = _login(client, analyst.email)

    response = client.post(
        f"/api/v1/queries/{original_run.id}/clarify",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "Show non-compliant devices in my department."},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["generated_sql"] == "SELECT generated"
    assert data["executed_sql"] == "SELECT executed"


def test_response_metadata_is_whitelisted_and_safe(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = _post_template_run(client, csrf_token)

    assert response.status_code == 200
    metadata = response.json()["data"]["metadata"]
    assert metadata == {
        "provider": "mock",
        "model": "mock-queryops-v1",
        "template_id": "open_support_tickets_by_department",
        "referenced_tables": ["support_tickets"],
        "scope_type": "department",
        "clarification_required": False,
        "validation": {"valid": True, "error_code": None},
        "execution": {
            "status": "succeeded",
            "error_code": None,
            "row_count": 1,
            "duration_ms": 2.4,
            "truncated": False,
        },
    }
    serialized = json.dumps(response.json())
    assert "internal parser detail" not in serialized
    assert "runtime_role" not in serialized
    assert "secret" not in serialized


def test_sensitive_errors_do_not_leak(client: TestClient) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")

    response = client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={"question": "return a db error"},
    )

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "missing_column" not in serialized
    assert "UndefinedColumn" not in serialized
    assert "stack" not in serialized
    assert response.json()["data"]["message"] == "Query execution failed safely."


class FakeQueryEngineService:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def run(
        self,
        db: Session,
        user: AppUser,
        request: Any,
    ) -> QueryEngineServiceResult:
        self.calls.append(request)
        request_metadata = getattr(request, "metadata", {})
        if "forecast" in request.question:
            return self._persist_and_result(
                db,
                user,
                request.question,
                status="clarification_required",
                query_run_status="failed",
                generated_sql=None,
                executed_sql=None,
                error_message="I could not map that question to a supported query.",
                error_code="unsupported_question",
                clarification_required=True,
                metadata={
                    **SAFE_METADATA,
                    **request_metadata,
                    "clarification_required": True,
                    "unsupported_reason": "unsupported_question",
                },
            )
        if "db error" in request.question:
            return self._persist_and_result(
                db,
                user,
                request.question,
                status="failed",
                query_run_status="failed",
                generated_sql="SELECT generated",
                executed_sql="SELECT executed",
                error_message="Query execution failed safely.",
                error_code="database_error",
                metadata={
                    **SAFE_METADATA,
                    **request_metadata,
                    "execution": {
                        **SAFE_METADATA["execution"],
                        "status": "failed",
                        "error_code": "database_error",
                        "internal_error_type": "UndefinedColumn missing_column",
                    },
                },
            )
        return self._persist_and_result(
            db,
            user,
            request.question,
            status="succeeded",
            query_run_status="succeeded",
            generated_sql="SELECT generated",
            executed_sql="SELECT executed",
            error_message=None,
            error_code=None,
            metadata={**SAFE_METADATA, **request_metadata},
        )

    def _persist_and_result(
        self,
        db: Session,
        user: AppUser,
        question: str,
        *,
        status: str,
        query_run_status: str,
        generated_sql: str | None,
        executed_sql: str | None,
        error_message: str | None,
        error_code: str | None,
        metadata: dict[str, Any],
        clarification_required: bool = False,
    ) -> QueryEngineServiceResult:
        query_run = QueryRun(
            user_id=user.id,
            status=query_run_status,
            natural_language_question=question,
            generated_sql=generated_sql,
            executed_sql=executed_sql,
            row_count=0 if status != "succeeded" else 1,
            duration_ms=2,
            error_message=error_message,
            query_metadata=metadata,
            started_at=datetime(2026, 7, 2, 9, 0, tzinfo=UTC),
            completed_at=datetime(2026, 7, 2, 9, 0, 1, tzinfo=UTC),
        )
        db.add(query_run)
        db.commit()
        db.refresh(query_run)
        return QueryEngineServiceResult(
            status=status,
            query_run_id=str(query_run.id),
            columns=["id", "opened_at", "monthly_cost_usd", "encrypted"]
            if status == "succeeded"
            else [],
            rows=[
                {
                    "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
                    "opened_at": datetime(2026, 7, 2, 9, 0, tzinfo=UTC),
                    "monthly_cost_usd": Decimal("12.50"),
                    "encrypted": True,
                }
            ]
            if status == "succeeded"
            else [],
            row_count=0 if status != "succeeded" else 1,
            duration_ms=2.4,
            truncated=False,
            message=error_message or "Query completed successfully.",
            warnings=[],
            clarification_required=clarification_required,
            error_code=error_code,
            public_error=error_message,
            metadata=metadata,
        )


def _post_template_run(client: TestClient, csrf_token: str):
    return client.post(
        "/api/v1/queries/run",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "question": "How many open support tickets exist in my department by priority?",
            "template_id": "open_support_tickets_by_department",
        },
    )


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return response.json()["data"]["csrf_token"]


def _user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _permission_by_key(session: Session, key: str) -> Permission:
    permission = session.scalar(select(Permission).where(Permission.key == key))
    assert permission is not None
    return permission


def _add_query_run(
    session: Session,
    user: AppUser,
    question: str,
    *,
    minute: int,
) -> QueryRun:
    timestamp = datetime(2026, 7, 2, 9, minute, tzinfo=UTC)
    query_run = QueryRun(
        user_id=user.id,
        status="succeeded",
        natural_language_question=question,
        generated_sql="SELECT generated",
        executed_sql="SELECT executed",
        row_count=1,
        duration_ms=7,
        error_message=None,
        query_metadata=SAFE_METADATA,
        created_at=timestamp,
        started_at=timestamp,
        completed_at=timestamp,
    )
    session.add(query_run)
    session.commit()
    session.refresh(query_run)
    return query_run


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
def fake_service() -> FakeQueryEngineService:
    return FakeQueryEngineService()


@pytest.fixture
def client(
    db_session: Session,
    fake_service: FakeQueryEngineService,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_query_engine_service] = lambda: fake_service
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_query_engine_service, None)
