from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.seed import seed_database
from app.evaluation.contracts import ExpectedOutcome
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.selection import evaluation_dataset_digest
from app.main import app
from app.models.product import (
    AccessScope,
    AppUser,
    EvaluationResult,
    EvaluationRun,
    Permission,
    Role,
    RolePermission,
    RunStatus,
    UserAccessScope,
)


ENDPOINTS = (
    "/api/v1/evaluation/overview",
    "/api/v1/evaluation/queries",
    "/api/v1/evaluation/actions",
    "/api/v1/evaluation/security",
    "/api/v1/evaluation/dashboards",
    "/api/v1/evaluation/readiness",
)
LEAK_SENTINELS = (
    "SELECT secret FROM private_table",
    "row-secret@example.invalid",
    "provider-secret-payload",
    "postgresql://secret-connection",
    "Traceback (most recent call last)",
)


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
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def complete_run(db_session: Session) -> EvaluationRun:
    return _create_run(db_session)


@pytest.mark.parametrize("path", ENDPOINTS)
def test_evaluation_endpoints_require_authentication(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("path", ENDPOINTS)
def test_user_is_forbidden_from_all_evaluation_endpoints(client: TestClient, path: str) -> None:
    _login(client, "demo.user@queryops.local")
    response = client.get(path)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_overview_recomputes_full_metrics_and_honest_coverage(
    client: TestClient,
    complete_run: EvaluationRun,
) -> None:
    _login(client, "demo.admin@queryops.local")
    response = client.get("/api/v1/evaluation/overview")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["run"]["id"] == str(complete_run.id)
    assert data["metrics"] == {
        "availability": "measured",
        "eligible_count": 40,
        "selected_count": 40,
        "completed_count": 40,
        "passed_count": 40,
        "failed_count": 0,
        "overall_score": 1.0,
        "expected_behavior_match_rate": 1.0,
        "security_pass_rate": 1.0,
        "query_execution_succeeded_count": 35,
        "query_execution_failed_count": 0,
    }
    coverage = {item["capability"]: item for item in data["coverage"]}
    assert coverage["queries"]["availability"] == "measured"
    assert coverage["security"]["measured_case_count"] == 5
    assert coverage["actions"] == {
        "capability": "actions",
        "availability": "not_measured",
        "measured_case_count": 0,
        "score": None,
    }
    assert coverage["dashboards"]["availability"] == "not_measured"


def test_scoped_roles_receive_only_visible_recomputed_totals(
    client: TestClient,
    complete_run: EvaluationRun,
) -> None:
    evaluation_set = load_it_operations_evaluation_set()

    _login(client, "demo.manager@queryops.local")
    manager = client.get("/api/v1/evaluation/overview").json()["data"]["metrics"]
    manager_expected = sum(
        case.requesting_role.value == "manager" for case in evaluation_set.cases
    )
    assert manager["eligible_count"] == manager_expected
    assert manager["selected_count"] == manager_expected
    assert manager["eligible_count"] < 40

    _login(client, "demo.analyst@queryops.local")
    analyst = client.get("/api/v1/evaluation/overview").json()["data"]["metrics"]
    analyst_expected = sum(
        case.requesting_role.value == "analyst" for case in evaluation_set.cases
    )
    assert analyst["eligible_count"] == analyst_expected
    assert analyst["selected_count"] == analyst_expected
    assert analyst["eligible_count"] < 40


def test_client_scope_parameters_cannot_widen_manager_visibility(
    client: TestClient,
    complete_run: EvaluationRun,
) -> None:
    _login(client, "demo.manager@queryops.local")
    baseline = client.get("/api/v1/evaluation/overview").json()["data"]
    attempted = client.get(
        "/api/v1/evaluation/overview?scope_type=global&scope_key=global"
    ).json()["data"]
    assert attempted == baseline


def test_manager_business_projection_omits_technical_details_even_with_sql_permission(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    _add_role_permission(db_session, "manager", "can_view_sql")
    _login(client, "demo.manager@queryops.local")
    response = client.get("/api/v1/evaluation/queries?limit=100")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert items
    assert all(item["technical"] is None for item in items)


def test_analyst_technical_projection_is_safe_and_sql_permission_gates_resources(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    _login(client, "demo.analyst@queryops.local")
    response = client.get("/api/v1/evaluation/queries?limit=100")
    assert response.status_code == 200
    technical = response.json()["data"]["items"][0]["technical"]
    assert technical is not None
    assert technical["referenced_tables"] is not None

    _remove_role_permission(db_session, "analyst", "can_view_sql")
    response = client.get("/api/v1/evaluation/queries?limit=100")
    assert response.status_code == 200
    technical = response.json()["data"]["items"][0]["technical"]
    assert technical is not None
    assert technical["referenced_tables"] is None


def test_protected_resource_name_is_not_returned_as_sql_adjacent_metadata(
    client: TestClient,
    complete_run: EvaluationRun,
) -> None:
    _login(client, "demo.analyst@queryops.local")
    items = client.get("/api/v1/evaluation/queries?limit=100").json()["data"]["items"]
    protected = next(item for item in items if item["case_id"] == "itops-security-004")
    assert protected["technical"]["referenced_tables"] == []
    assert "it_audit_events" not in json.dumps(protected)


def test_missing_role_permission_or_scope_fails_closed(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    _login(client, "demo.manager@queryops.local")
    _remove_role_permission(db_session, "manager", "can_view_department_evaluation")
    response = client.get("/api/v1/evaluation/overview")
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("email", "role", "permission"),
    [
        ("demo.analyst@queryops.local", "analyst", "can_view_scope_evaluation"),
        ("demo.admin@queryops.local", "admin", "can_view_global_evaluation"),
    ],
)
def test_each_role_requires_its_exact_evaluation_permission(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
    email: str,
    role: str,
    permission: str,
) -> None:
    _remove_role_permission(db_session, role, permission)
    _login(client, email)
    response = client.get("/api/v1/evaluation/overview")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_sql_permission_alone_never_grants_user_evaluation_access(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    _add_role_permission(db_session, "user", "can_view_sql")
    _login(client, "demo.user@queryops.local")
    assert client.get("/api/v1/evaluation/overview").status_code == 403


def test_admin_without_global_scope_fails_closed(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    admin = db_session.scalar(
        select(AppUser).where(AppUser.email == "demo.admin@queryops.local")
    )
    assert admin is not None
    links = db_session.scalars(
        select(UserAccessScope)
        .join(AccessScope, AccessScope.id == UserAccessScope.scope_id)
        .where(
            UserAccessScope.user_id == admin.id,
            AccessScope.scope_type == "global",
        )
    ).all()
    assert links
    for link in links:
        db_session.delete(link)
    db_session.commit()
    _login(client, "demo.admin@queryops.local")
    assert client.get("/api/v1/evaluation/overview").status_code == 403


@pytest.mark.parametrize(
    "email",
    ["demo.manager@queryops.local", "demo.analyst@queryops.local"],
)
def test_scoped_viewer_without_assigned_scope_fails_closed(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
    email: str,
) -> None:
    user = db_session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    links = db_session.scalars(
        select(UserAccessScope).where(UserAccessScope.user_id == user.id)
    ).all()
    assert links
    for link in links:
        db_session.delete(link)
    db_session.commit()
    _login(client, email)
    assert client.get("/api/v1/evaluation/overview").status_code == 403


def test_inactive_authenticated_user_is_rejected(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    _login(client, "demo.manager@queryops.local")
    user = db_session.scalar(
        select(AppUser).where(AppUser.email == "demo.manager@queryops.local")
    )
    assert user is not None
    user.status = "disabled"
    db_session.commit()
    response = client.get("/api/v1/evaluation/overview")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_missing_evaluation_actor_attribution_returns_safe_unavailable(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    actor = db_session.scalar(
        select(AppUser).where(AppUser.email == "demo.user@queryops.local")
    )
    assert actor is not None
    actor.status = "disabled"
    db_session.commit()
    _login(client, "demo.admin@queryops.local")
    response = client.get("/api/v1/evaluation/overview")
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "EVALUATION_SCOPE_ATTRIBUTION_UNAVAILABLE",
        "message": "Evaluation metrics are unavailable.",
        "details": {},
        "request_id": response.json()["error"]["request_id"],
    }


def test_no_eligible_run_uses_unavailable_and_null_scores(client: TestClient) -> None:
    _login(client, "demo.admin@queryops.local")
    overview = client.get("/api/v1/evaluation/overview").json()["data"]
    assert overview["run"] is None
    assert overview["metrics"]["availability"] == "unavailable"
    assert overview["metrics"]["overall_score"] is None
    actions = client.get("/api/v1/evaluation/actions").json()["data"]
    assert actions["run"] is None
    assert actions["availability"] == "unavailable"
    assert actions["score"] is None


def test_no_openai_run_returns_incomplete_readiness(client: TestClient) -> None:
    _login(client, "demo.admin@queryops.local")
    data = client.get("/api/v1/evaluation/readiness").json()["data"]
    assert data["verdict"] == "incomplete"
    assert data["provider"] is None
    assert data["technical"] is None
    assert data["gates"][0]["reason_code"] == "qualifying_run_missing"


def test_readiness_selects_latest_qualifying_openai_and_ignores_newer_ineligible_runs(
    client: TestClient,
    db_session: Session,
) -> None:
    qualifying = _create_run(
        db_session,
        provider="openai",
        completed_at=datetime.now(UTC) - timedelta(hours=2),
    )
    _create_run(db_session, provider="mock", completed_at=datetime.now(UTC))
    filtered = _create_run(
        db_session,
        provider="openai",
        completed_at=datetime.now(UTC) - timedelta(hours=1),
    )
    filtered.summary = {
        **filtered.summary,
        "filters": {**filtered.summary["filters"], "category": "licenses"},
    }
    _create_run(db_session, provider="openai", status=RunStatus.FAILED.value)
    _create_run(
        db_session,
        provider="openai",
        status=RunStatus.RUNNING.value,
        completed_at=None,
    )
    db_session.commit()
    _login(client, "demo.admin@queryops.local")

    data = client.get("/api/v1/evaluation/readiness").json()["data"]

    assert data["verdict"] == "ready"
    assert data["provider"] == "openai"
    assert data["model_label"] == "gpt-5.6-terra"
    assert data["completed_count"] == 40
    assert data["technical"]["run_id"] == str(qualifying.id)


def test_readiness_role_projections_remain_bounded(
    client: TestClient,
    db_session: Session,
) -> None:
    _create_run(db_session, provider="openai")
    _login(client, "demo.manager@queryops.local")
    manager = client.get("/api/v1/evaluation/readiness").json()["data"]
    assert manager["technical"] is None
    assert all(gate["actual"] is None for gate in manager["gates"])
    assert all(gate["threshold"] is None for gate in manager["gates"])

    _login(client, "demo.analyst@queryops.local")
    analyst = client.get("/api/v1/evaluation/readiness").json()["data"]
    assert analyst["technical"] is None

    _login(client, "demo.admin@queryops.local")
    admin = client.get("/api/v1/evaluation/readiness").json()["data"]
    assert admin["technical"]["selected_count"] == 40
    assert admin["technical"]["usage"]["call_count"] == 40
    assert next(
        gate for gate in admin["gates"] if gate["code"] == "result_accuracy"
    )["actual"] == 1.0


def test_unknown_and_inaccessible_runs_share_safe_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    admin_only = _create_run(db_session, case_ids={"itops-medium-006"})
    _login(client, "demo.manager@queryops.local")
    inaccessible = client.get(f"/api/v1/evaluation/overview?run_id={admin_only.id}")
    unknown = client.get(f"/api/v1/evaluation/overview?run_id={uuid4()}")
    assert inaccessible.status_code == unknown.status_code == 404
    assert inaccessible.json()["error"]["code"] == unknown.json()["error"]["code"]
    assert inaccessible.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_latest_default_ignores_running_and_uses_stable_completed_order(
    client: TestClient,
    db_session: Session,
) -> None:
    older = _create_run(db_session, completed_at=datetime.now(UTC) - timedelta(hours=1))
    newer = _create_run(db_session, completed_at=datetime.now(UTC))
    running = _create_run(db_session, status=RunStatus.RUNNING.value, completed_at=None)
    _login(client, "demo.admin@queryops.local")
    response = client.get("/api/v1/evaluation/overview")
    assert response.json()["data"]["run"]["id"] == str(newer.id)
    assert response.json()["data"]["run"]["id"] not in {str(older.id), str(running.id)}


@pytest.mark.parametrize(
    ("older_provider", "newer_provider"),
    [("mock", "openai"), ("openai", "mock")],
)
def test_latest_default_selects_newest_supported_provider_run(
    client: TestClient,
    db_session: Session,
    older_provider: str,
    newer_provider: str,
) -> None:
    _create_run(
        db_session,
        completed_at=datetime.now(UTC) - timedelta(hours=1),
        provider=older_provider,
    )
    newer = _create_run(
        db_session,
        completed_at=datetime.now(UTC),
        provider=newer_provider,
    )
    _login(client, "demo.admin@queryops.local")

    run = client.get("/api/v1/evaluation/overview").json()["data"]["run"]

    assert run["id"] == str(newer.id)
    assert run["provider"] == newer_provider
    assert run["model_label"] == (
        "gpt-5.6-terra" if newer_provider == "openai" else "mock-queryops-v1"
    )


def test_explicit_openai_run_serializes_validated_identity(
    client: TestClient,
    db_session: Session,
) -> None:
    run = _create_run(db_session, provider="openai", model_label="gpt-5.6-terra")
    _login(client, "demo.admin@queryops.local")

    response = client.get(f"/api/v1/evaluation/overview?run_id={run.id}")

    assert response.status_code == 200
    assert response.json()["data"]["run"]["provider"] == "openai"
    assert response.json()["data"]["run"]["model_label"] == "gpt-5.6-terra"


@pytest.mark.parametrize(
    ("provider", "model_label"),
    [
        ("anthropic", "claude"),
        ("openai", ""),
        ("openai", "bad model with spaces"),
        ("openai", "x" * 129),
        ("mock", "not-the-mock-model"),
    ],
)
def test_malformed_or_unknown_persisted_provider_identity_is_rejected(
    client: TestClient,
    db_session: Session,
    provider: str,
    model_label: str,
) -> None:
    run = _create_run(db_session)
    run.summary = {
        **run.summary,
        "provider": provider,
        "model_label": model_label,
    }
    db_session.commit()
    _login(client, "demo.admin@queryops.local")

    explicit = client.get(f"/api/v1/evaluation/overview?run_id={run.id}")
    default = client.get("/api/v1/evaluation/overview")

    assert explicit.status_code == 404
    assert default.status_code == 200
    assert default.json()["data"]["run"] is None


def test_default_and_explicit_selection_reject_stale_dataset_identity(
    client: TestClient,
    db_session: Session,
) -> None:
    valid = _create_run(db_session, completed_at=datetime.now(UTC) - timedelta(hours=1))
    stale = _create_run(db_session, completed_at=datetime.now(UTC))
    stale.summary = {**stale.summary, "dataset_digest": "0" * 64}
    db_session.commit()
    _login(client, "demo.admin@queryops.local")
    default = client.get("/api/v1/evaluation/overview")
    explicit = client.get(f"/api/v1/evaluation/overview?run_id={stale.id}")
    assert default.json()["data"]["run"]["id"] == str(valid.id)
    assert explicit.status_code == 404


def test_explicit_running_run_is_clearly_partial(
    client: TestClient,
    db_session: Session,
) -> None:
    running = _create_run(
        db_session,
        case_ids={"itops-easy-001"},
        status=RunStatus.RUNNING.value,
        completed_at=None,
    )
    _login(client, "demo.admin@queryops.local")
    data = client.get(
        f"/api/v1/evaluation/overview?run_id={running.id}"
    ).json()["data"]
    assert data["run"]["status"] == "running"
    assert data["metrics"]["availability"] == "partially_measured"


def test_query_filters_pagination_and_invalid_category_are_strict(
    client: TestClient,
    complete_run: EvaluationRun,
) -> None:
    _login(client, "demo.admin@queryops.local")
    response = client.get(
        "/api/v1/evaluation/queries?difficulty=security&passed=true&limit=2&offset=1"
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pagination"] == {"limit": 2, "offset": 1, "returned": 2, "total": 5}
    assert all(item["difficulty"] == "security" for item in data["items"])
    assert data["by_difficulty"] == [
        {
            "key": "security",
            "eligible_count": 5,
            "completed_count": 5,
            "passed_count": 5,
            "failed_count": 0,
            "score": 1.0,
        }
    ]

    invalid = client.get("/api/v1/evaluation/queries?category=not-a-category")
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_EVALUATION_FILTER"


@pytest.mark.parametrize(
    "query",
    [
        "run_id=not-a-uuid",
        "difficulty=impossible",
        "case_type=impossible",
        "outcome=impossible",
        "limit=101",
        "limit=0",
        "offset=-1",
        f"category={'x' * 65}",
    ],
)
def test_query_parameter_contracts_fail_validation(
    client: TestClient,
    complete_run: EvaluationRun,
    query: str,
) -> None:
    _login(client, "demo.admin@queryops.local")
    response = client.get(f"/api/v1/evaluation/queries?{query}")
    assert response.status_code == 422


def test_security_endpoint_uses_only_five_security_cases(
    client: TestClient,
    complete_run: EvaluationRun,
) -> None:
    _login(client, "demo.admin@queryops.local")
    data = client.get("/api/v1/evaluation/security").json()["data"]
    assert data["metrics"]["eligible_count"] == 5
    assert data["metrics"]["completed_count"] == 5
    assert data["metrics"]["security_pass_rate"] == 1.0
    assert {item["key"] for item in data["by_expected_behavior"]} == {
        "authorization_denial",
        "scope_denial",
        "unsafe_query_block",
        "protected_resource_denial",
        "clarification",
    }
    assert [item["case_id"] for item in data["items"]] == [
        f"itops-security-{index:03d}" for index in range(1, 6)
    ]


@pytest.mark.parametrize("capability", ["actions", "dashboards"])
def test_unmeasured_capabilities_are_not_fabricated(
    client: TestClient,
    complete_run: EvaluationRun,
    capability: str,
) -> None:
    _login(client, "demo.admin@queryops.local")
    data = client.get(f"/api/v1/evaluation/{capability}").json()["data"]
    assert data["availability"] == "not_measured"
    assert data["measured_cases"] == 0
    assert data["score"] is None
    assert data["reason_code"] == f"{capability[:-1]}_evaluation_not_available"


def test_api_ignores_untrusted_json_and_never_leaks_sensitive_fields(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    result = db_session.scalar(
        select(EvaluationResult).where(
            EvaluationResult.evaluation_run_id == complete_run.id
        ).limit(1)
    )
    assert result is not None
    result.error_message = LEAK_SENTINELS[4]
    result.expected_output = {
        **result.expected_output,
        "sql": LEAK_SENTINELS[0],
        "rows": [LEAK_SENTINELS[1]],
    }
    result.actual_output = {**result.actual_output, "provider_payload": LEAK_SENTINELS[2]}
    result.metrics = {**result.metrics, "database_url": LEAK_SENTINELS[3]}
    db_session.commit()

    _login(client, "demo.admin@queryops.local")
    for path in ENDPOINTS:
        serialized = json.dumps(client.get(path).json())
        for sentinel in LEAK_SENTINELS:
            assert sentinel not in serialized


def test_reads_do_not_write_evaluation_records(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    before = (
        db_session.scalar(select(func.count()).select_from(EvaluationRun)),
        db_session.scalar(select(func.count()).select_from(EvaluationResult)),
    )
    _login(client, "demo.admin@queryops.local")
    for path in ENDPOINTS:
        assert client.get(path).status_code == 200
    after = (
        db_session.scalar(select(func.count()).select_from(EvaluationRun)),
        db_session.scalar(select(func.count()).select_from(EvaluationResult)),
    )
    assert after == before


def test_reads_never_invoke_runner_query_engine_or_baseline(
    client: TestClient,
    complete_run: EvaluationRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("execution boundary must not be invoked by metrics reads")

    monkeypatch.setattr("app.evaluation.runner.EvaluationRunner.run", forbidden)
    monkeypatch.setattr("app.query_engine.service.QueryEngineService.run", forbidden)
    monkeypatch.setattr("app.evaluation.baseline.execute_evaluation_baseline", forbidden)
    _login(client, "demo.admin@queryops.local")
    for path in ENDPOINTS:
        assert client.get(path).status_code == 200


def test_full_read_fetches_evaluation_results_in_one_bounded_query(
    client: TestClient,
    db_session: Session,
    complete_run: EvaluationRun,
) -> None:
    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    _login(client, "demo.admin@queryops.local")
    event.listen(db_session.bind, "before_cursor_execute", capture)
    try:
        response = client.get("/api/v1/evaluation/overview")
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture)
    assert response.status_code == 200
    result_selects = [
        statement for statement in statements if "FROM evaluation_results" in statement
    ]
    assert len(result_selects) == 1
    assert len(statements) < 30
    serialized_statements = "\n".join(statements).lower()
    for forbidden_table in (
        "query_runs",
        "action_requests",
        "approval_requests",
        "dashboards",
        "it_audit_events",
    ):
        assert forbidden_table not in serialized_statements


def test_internal_database_failure_returns_controlled_error_without_raw_detail(
    client: TestClient,
    complete_run: EvaluationRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import OperationalError

    def fail_read(*_args, **_kwargs):
        raise OperationalError(
            "SELECT secret",
            {"password": "raw-secret"},
            RuntimeError("raw-driver-error"),
        )

    monkeypatch.setattr(
        "app.evaluation.read_service.EvaluationReadService.overview",
        fail_read,
    )
    _login(client, "demo.admin@queryops.local")
    response = client.get("/api/v1/evaluation/overview")
    assert response.status_code == 503
    serialized = json.dumps(response.json())
    assert response.json()["error"]["code"] == "EVALUATION_METRICS_UNAVAILABLE"
    for sentinel in ("SELECT secret", "raw-secret", "raw-driver-error"):
        assert sentinel not in serialized


def test_malformed_and_duplicate_case_rows_are_partial_not_double_counted(
    client: TestClient,
    db_session: Session,
) -> None:
    run = _create_run(db_session, case_ids={"itops-easy-001"})
    original = db_session.scalar(
        select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run.id)
    )
    assert original is not None
    db_session.add(
        EvaluationResult(
            evaluation_run_id=run.id,
            case_name=original.case_name,
            status=original.status,
            score=original.score,
            expected_output=original.expected_output,
            actual_output=original.actual_output,
            metrics=original.metrics,
            error_message=None,
        )
    )
    db_session.commit()
    _login(client, "demo.admin@queryops.local")
    metrics = client.get(
        f"/api/v1/evaluation/overview?run_id={run.id}"
    ).json()["data"]["metrics"]
    assert metrics["selected_count"] == 1
    assert metrics["completed_count"] == 0
    assert metrics["availability"] == "partially_measured"


def test_duplicate_security_result_is_partial_not_unavailable_or_double_counted(
    client: TestClient,
    db_session: Session,
) -> None:
    run = _create_run(db_session, case_ids={"itops-security-003"})
    original = db_session.scalar(
        select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run.id)
    )
    assert original is not None
    db_session.add(
        EvaluationResult(
            evaluation_run_id=run.id,
            case_name=original.case_name,
            status=original.status,
            score=original.score,
            expected_output=original.expected_output,
            actual_output=original.actual_output,
            metrics=original.metrics,
            error_message=None,
        )
    )
    db_session.commit()
    _login(client, "demo.admin@queryops.local")
    metrics = client.get(
        f"/api/v1/evaluation/security?run_id={run.id}"
    ).json()["data"]["metrics"]
    assert metrics["selected_count"] == 1
    assert metrics["completed_count"] == 0
    assert metrics["availability"] == "partially_measured"


def test_openapi_documents_exactly_the_six_read_only_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    evaluation_paths = {
        path: operations
        for path, operations in paths.items()
        if path.startswith("/api/v1/evaluation")
    }
    assert set(evaluation_paths) == set(ENDPOINTS)
    assert all(set(operations) == {"get"} for operations in evaluation_paths.values())
    assert all(
        "200" in operations["get"]["responses"]
        for operations in evaluation_paths.values()
    )
    assert all(
        {"200", "401", "403", "404", "422", "503"}
        <= set(operations["get"]["responses"])
        for operations in evaluation_paths.values()
    )


def _create_run(
    db: Session,
    *,
    case_ids: set[str] | None = None,
    status: str = RunStatus.SUCCEEDED.value,
    completed_at: datetime | None = None,
    provider: str = "mock",
    model_label: str | None = None,
) -> EvaluationRun:
    evaluation_set = load_it_operations_evaluation_set()
    selected = tuple(
        case for case in evaluation_set.cases if case_ids is None or case.id in case_ids
    )
    now = datetime.now(UTC)
    run = EvaluationRun(
        requested_by_user_id=None,
        name=f"{evaluation_set.dataset_id}:{provider}",
        run_type="manual_evaluation",
        status=status,
        started_at=now - timedelta(seconds=1),
        completed_at=(
            now
            if completed_at is None and status == RunStatus.SUCCEEDED.value
            else completed_at
        ),
        summary={
            "provider": provider,
            "model_label": model_label
            or ("gpt-5.6-terra" if provider == "openai" else "mock-queryops-v1"),
            "dataset_id": evaluation_set.dataset_id,
            "dataset_version": evaluation_set.version,
            "dataset_digest": evaluation_dataset_digest(evaluation_set),
            "selected_count": len(selected),
            "completed_count": len(selected),
            "filters": {
                "case_id": None,
                "difficulty": None,
                "category": None,
                "case_type": None,
                "security_only": False,
            },
            "provider_usage": {
                "call_count": len(selected) if provider == "openai" else 0,
                "attempt_count": len(selected) if provider == "openai" else 0,
                "duration_ms": round(1.25 * len(selected), 3) if provider == "openai" else 0.0,
                "input_tokens": len(selected) if provider == "openai" else 0,
                "cached_input_tokens": 0,
                "output_tokens": len(selected) if provider == "openai" else 0,
                "total_tokens": 2 * len(selected) if provider == "openai" else 0,
            },
            "failure_code": None,
            "raw_prompt": LEAK_SENTINELS[2],
        },
    )
    db.add(run)
    db.flush()
    for case in selected:
        success = case.expected_outcome is ExpectedOutcome.SUCCESS
        db.add(
            EvaluationResult(
                evaluation_run_id=run.id,
                case_name=case.id,
                status="succeeded",
                score=1.0,
                expected_output={
                    "outcome": case.expected_outcome.value,
                    "referenced_tables": list(case.expected_tables),
                },
                actual_output={
                    "outcome": case.expected_outcome.value,
                    "referenced_tables": list(case.expected_tables),
                    "execution_succeeded": success,
                    "error_code": None if success else _expected_error_code(case.expected_outcome),
                },
                metrics={
                    "score": 1.0,
                    "passed": True,
                    "outcome_correct": True,
                    "execution_correct": True,
                    "tables_correct": True,
                    "result_correct": True if success else None,
                    "expected_row_count": 0,
                    "actual_row_count": 0,
                    "failure_reasons": [],
                    "difficulty": case.difficulty.value,
                    "category": case.category,
                    "case_type": case.case_type.value,
                    "security_sensitive": case.security_sensitive,
                    "duration_ms": 1.25,
                    "missing_row_count": 0,
                    "extra_row_count": 0,
                    "query_invoked": case.requesting_role.value != "user",
                    "query_execution_attempted": success,
                    **(
                        {
                            "provider_measurement": {
                                "provider": "openai",
                                "model_label": model_label or "gpt-5.6-terra",
                                "duration_ms": 1.25,
                                "attempt_count": 1,
                                "input_tokens": 1,
                                "cached_input_tokens": 0,
                                "output_tokens": 1,
                                "total_tokens": 2,
                            }
                        }
                        if provider == "openai"
                        else {}
                    ),
                },
                error_message=None,
            )
        )
    db.commit()
    db.refresh(run)
    return run


def _expected_error_code(outcome: ExpectedOutcome) -> str:
    return {
        ExpectedOutcome.DENIED: "access_denied",
        ExpectedOutcome.CLARIFICATION: "clarification_required",
        ExpectedOutcome.UNSAFE_BLOCKED: "unsafe_sql_blocked",
    }[outcome]


def _remove_role_permission(db: Session, role_name: str, permission_key: str) -> None:
    row = db.scalar(
        select(RolePermission)
        .join(Role, Role.id == RolePermission.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Role.name == role_name, Permission.key == permission_key)
    )
    assert row is not None
    db.delete(row)
    db.commit()


def _add_role_permission(db: Session, role_name: str, permission_key: str) -> None:
    role = db.scalar(select(Role).where(Role.name == role_name))
    permission = db.scalar(select(Permission).where(Permission.key == permission_key))
    assert role is not None and permission is not None
    existing = db.scalar(
        select(RolePermission).where(
            RolePermission.role_id == role.id,
            RolePermission.permission_id == permission.id,
        )
    )
    if existing is None:
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        db.commit()


def _login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
