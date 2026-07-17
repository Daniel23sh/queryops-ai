from __future__ import annotations

import ipaddress
import json
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.routes import actions as actions_routes
from app.core.rls import build_rls_context, set_rls_context
from app.db.session import get_db
from app.domains.it_operations.models import (
    Department,
    DirectoryUser,
    License,
    LicenseAssignment,
)
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AccessScope,
    ActionRequest,
    AppUser,
    DataResource,
)
from app.query_engine.runtime_role import set_query_runtime_role
from app.auth.access_context import build_user_access_context


REFERENCE_NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
REQUIRED_RESOURCES = (
    "directory_users",
    "license_assignments",
    "licenses",
)


@pytest.mark.parametrize(
    ("email", "scope_key"),
    [
        ("demo.manager@queryops.local", "finance"),
        ("demo.analyst@queryops.local", "it"),
    ],
)
def test_scoped_previews_contain_only_current_viewer_rls_rows(
    client: TestClient,
    postgres_engine: Engine,
    email: str,
    scope_key: str,
) -> None:
    csrf_token = _login(client, email)

    response = _preview(client, postgres_engine, csrf_token, scope_key)

    assert response.status_code == 201, response.json()
    preview = response.json()["data"]["preview"]
    records = _all_preview_records(preview)
    assert records
    assert {record["scope"]["key"] for record in records} == {scope_key}
    assert "@" not in json.dumps(records)


def test_foreign_selector_is_indistinguishable_and_leaks_no_domain_details(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        foreign = session.execute(
            select(LicenseAssignment, DirectoryUser, License)
            .join(DirectoryUser, DirectoryUser.id == LicenseAssignment.user_id)
            .join(License, License.id == LicenseAssignment.license_id)
            .join(Department, Department.id == LicenseAssignment.department_id)
            .where(Department.name == "Sales")
            .order_by(LicenseAssignment.id)
        ).first()
        assert foreign is not None
        assignment, directory_user, license_record = foreign

    csrf_token = _login(client, "demo.manager@queryops.local")
    foreign_response = _preview(
        client,
        postgres_engine,
        csrf_token,
        "finance",
        license_assignment_ids=[assignment.id],
    )
    missing_id = uuid.uuid4()
    missing_response = _preview(
        client,
        postgres_engine,
        csrf_token,
        "finance",
        license_assignment_ids=[missing_id],
    )

    assert foreign_response.status_code == missing_response.status_code == 201
    foreign_preview = foreign_response.json()["data"]["preview"]
    missing_preview = missing_response.json()["data"]["preview"]
    assert foreign_preview["eligible_records"] == []
    assert foreign_preview["override_required_records"] == []
    assert len(foreign_preview["skipped_records"]) == 1
    assert len(missing_preview["skipped_records"]) == 1
    foreign_skip = foreign_preview["skipped_records"][0]
    missing_skip = missing_preview["skipped_records"][0]
    assert foreign_skip["reason_code"] == missing_skip["reason_code"]
    assert foreign_skip["reason_code"] == "record_not_found_or_not_authorized"
    assert foreign_skip["user_display_label"] is None
    assert foreign_skip["license_product"] is None
    assert foreign_skip["license_vendor"] is None
    serialized = json.dumps(foreign_response.json())
    assert directory_user.full_name not in serialized
    assert directory_user.email not in serialized
    assert license_record.product_name not in serialized


def test_admin_global_preview_marks_cross_scope_and_secure_read_boundary(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    csrf_token = _login(client, "demo.admin@queryops.local")

    response = _preview(client, postgres_engine, csrf_token, "global")

    assert response.status_code == 201, response.json()
    data = response.json()["data"]
    preview = data["preview"]
    assert data["requires_admin"] is True
    assert preview["eligible_records"] == []
    assert preview["override_required_records"]
    assert len(
        {
            record["scope"]["key"]
            for record in preview["override_required_records"]
        }
    ) > 1
    flag_codes = {flag["code"] for flag in preview["policy_flags"]}
    assert {"cross_scope_target", "global_scope_request"}.issubset(flag_codes)

    with Session(postgres_engine) as session:
        action_request = session.get(ActionRequest, uuid.UUID(data["id"]))
        assert action_request is not None
        decision = action_request.access_decision_snapshot_json
        assert decision["read_boundary"] == {
            "runtime_role": "queryops_query_runtime",
            "transaction_read_only": True,
            "row_security_enabled": True,
        }
        assert [item["table_name"] for item in decision["resource_decisions"]] == [
            "directory_users",
            "license_assignments",
            "licenses",
        ]
        assert all(item["allowed"] for item in decision["resource_decisions"])


@pytest.mark.parametrize("table_name", REQUIRED_RESOURCES)
def test_each_required_data_resource_is_authorized_independently(
    client: TestClient,
    postgres_engine: Engine,
    table_name: str,
) -> None:
    csrf_token = _login(client, "demo.manager@queryops.local")
    with Session(postgres_engine) as session:
        resource = session.scalar(
            select(DataResource).where(DataResource.table_name == table_name)
        )
        assert resource is not None
        original = resource.is_queryable
        resource.is_queryable = False
        session.commit()

    try:
        response = _preview(client, postgres_engine, csrf_token, "finance")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
        assert response.json()["error"]["message"] == (
            "You are not authorized to perform this action."
        )
    finally:
        with Session(postgres_engine) as session:
            resource = session.scalar(
                select(DataResource).where(DataResource.table_name == table_name)
            )
            assert resource is not None
            resource.is_queryable = original
            session.commit()


def test_action_persistence_preserves_domain_rls_and_context_is_transaction_local(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        manager = _user(session, "demo.manager@queryops.local")
        access_context = build_user_access_context(manager, session)
    before_ids = _runtime_assignment_ids(postgres_engine, access_context)
    assert before_ids

    csrf_token = _login(client, "demo.manager@queryops.local")
    response = _preview(client, postgres_engine, csrf_token, "finance")

    assert response.status_code == 201, response.json()
    after_ids = _runtime_assignment_ids(postgres_engine, access_context)
    assert after_ids == before_ids
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT current_user")) == "queryops"
        assert connection.scalar(
            text("SELECT current_setting('app.current_scope_keys', true)")
        ) in {None, ""}
        assert connection.scalar(
            text("SELECT current_setting('app.has_global_scope', true)")
        ) in {None, ""}


def test_matching_app_and_directory_email_does_not_infer_identity(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        manager = _user(session, "demo.manager@queryops.local")
        finance = session.scalar(
            select(Department).where(Department.name == "Finance")
        )
        assert finance is not None
        assert session.scalar(
            select(DirectoryUser).where(DirectoryUser.email == manager.email)
        ) is None
        directory_user = DirectoryUser(
            employee_number="IDENTITY-HEURISTIC-GUARD",
            email=manager.email,
            full_name="Identity Heuristic Sentinel",
            department_id=finance.id,
        )
        session.add(directory_user)
        session.commit()
        directory_user_id = directory_user.id
        manager_id = manager.id
        assert directory_user_id != manager_id

    csrf_token = _login(client, "demo.manager@queryops.local")
    response = _preview(
        client,
        postgres_engine,
        csrf_token,
        "finance",
        target_user_ids=[directory_user_id],
    )

    assert response.status_code == 201, response.json()
    data = response.json()["data"]
    skipped = data["preview"]["skipped_records"]
    assert skipped == [
        {
            "record_type": "directory_user",
            "record_id": str(directory_user_id),
            "license_assignment_id": None,
            "scope": {
                "id": None,
                "type": "department",
                "key": "finance",
            },
            "user_display_label": None,
            "license_product": None,
            "license_vendor": None,
            "last_used_at": None,
            "monthly_cost_usd": None,
            "reason_code": "record_not_found_or_not_authorized",
            "reason": "The selected record is unavailable.",
            "high_confidence": False,
        }
    ]
    assert "Identity Heuristic Sentinel" not in json.dumps(response.json())
    with Session(postgres_engine) as session:
        action_request = session.get(ActionRequest, uuid.UUID(data["id"]))
        assert action_request is not None
        assert action_request.requested_by_app_user_id == manager_id
        assert action_request.requested_by_app_user_id != directory_user_id


def _runtime_assignment_ids(
    engine: Engine,
    access_context,
) -> tuple[uuid.UUID, ...]:
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            set_query_runtime_role(connection)
            set_rls_context(connection, build_rls_context(access_context))
            return tuple(
                connection.scalars(
                    select(LicenseAssignment.id).order_by(LicenseAssignment.id)
                ).all()
            )


def _all_preview_records(preview: dict) -> list[dict]:
    return [
        *preview["eligible_records"],
        *preview["skipped_records"],
        *preview["override_required_records"],
    ]


def _preview(
    client: TestClient,
    engine: Engine,
    csrf_token: str,
    scope_key: str,
    *,
    license_assignment_ids: list[uuid.UUID] | None = None,
    target_user_ids: list[uuid.UUID] | None = None,
):
    with Session(engine) as session:
        scope = session.scalar(
            select(AccessScope).where(
                AccessScope.scope_key == scope_key,
                AccessScope.scope_type == (
                    "global" if scope_key == "global" else "department"
                ),
            )
        )
        assert scope is not None
        payload = {
            "action_type": "reclaim_unused_license",
            "scope_id": str(scope.id),
            "department_id": (
                str(scope.department_id) if scope.department_id else None
            ),
            "reason": "Verify deterministic PostgreSQL action preview.",
        }
    if license_assignment_ids is not None:
        payload["license_assignment_ids"] = [
            str(record_id) for record_id in license_assignment_ids
        ]
    if target_user_ids is not None:
        payload["target_user_ids"] = [str(record_id) for record_id in target_user_ids]
    return client.post(
        "/api/v1/actions/preview",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


def _user(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


@pytest.fixture
def client(postgres_engine: Engine) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with Session(postgres_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[actions_routes.get_action_clock] = lambda: (
        lambda: REFERENCE_NOW
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(actions_routes.get_action_clock, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = _postgres_test_database_url()
    if database_url is None:
        pytest.skip(
            "Action preview PostgreSQL tests require POSTGRES_TEST_DATABASE_URL "
            "pointing to a disposable database."
        )

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    _run_alembic_upgrade(database_url)
    with Session(engine) as session:
        seed_database(session, profile_name="small", reset=True)
        session.commit()
    try:
        yield engine
    finally:
        engine.dispose()


def _postgres_test_database_url() -> str | None:
    explicit_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if explicit_url:
        return _validated_disposable_url(explicit_url)
    return None


def _validated_disposable_url(database_url: str) -> str:
    if os.environ.get("POSTGRES_TEST_DATABASE_DISPOSABLE") != "1":
        pytest.fail(
            "Set POSTGRES_TEST_DATABASE_DISPOSABLE=1 to permit destructive action tests."
        )
    parsed_url = make_url(database_url)
    database_name = parsed_url.database
    application_database_name = os.environ.get("POSTGRES_DB", "queryops")
    if parsed_url.get_backend_name() != "postgresql" or not database_name:
        pytest.fail("Action preview tests require an explicit PostgreSQL database.")
    application_url = os.environ.get("DATABASE_URL")
    if application_url and _database_identity(make_url(application_url)) == _database_identity(
        parsed_url
    ):
        pytest.fail("Refusing to use DATABASE_URL for destructive action tests.")
    if database_name == application_database_name:
        pytest.fail("Refusing to use the configured application database for destructive tests.")
    if "test" not in database_name.lower() and "dev" not in database_name.lower():
        pytest.fail("The destructive test database name must identify it as test or dev.")
    return database_url


def _database_identity(database_url) -> tuple[str | None, int, str | None]:
    host = (database_url.host or "localhost").rstrip(".").lower()
    if not host:
        pytest.fail("Could not determine the destructive test database endpoint.")
    try:
        if ipaddress.ip_address(host).is_loopback:
            host = "localhost"
    except ValueError:
        pass
    return host, database_url.port or 5432, database_url.database


def test_validated_disposable_url_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("POSTGRES_TEST_DATABASE_DISPOSABLE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(pytest.fail.Exception, match="POSTGRES_TEST_DATABASE_DISPOSABLE=1"):
        _validated_disposable_url(
            "postgresql+psycopg://queryops:queryops@localhost:5432/queryops_test"
        )


@pytest.mark.parametrize(
    ("database_url", "expected_message"),
    [
        ("sqlite:///queryops_test.db", "explicit PostgreSQL database"),
        (
            "postgresql+psycopg://queryops:queryops@localhost:5432",
            "explicit PostgreSQL database",
        ),
        (
            "postgresql+psycopg://queryops:queryops@localhost:5432/queryops_ci",
            "must identify it as test or dev",
        ),
    ],
)
def test_validated_disposable_url_rejects_unsafe_targets(
    monkeypatch,
    database_url: str,
    expected_message: str,
) -> None:
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_DISPOSABLE", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)

    with pytest.raises(pytest.fail.Exception, match=expected_message):
        _validated_disposable_url(database_url)


def test_validated_disposable_url_rejects_postgres_db(monkeypatch) -> None:
    database_url = (
        "postgresql+psycopg://queryops:queryops@localhost:5432/queryops_test"
    )
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_DISPOSABLE", "1")
    monkeypatch.setenv("POSTGRES_DB", "queryops_test")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(pytest.fail.Exception, match="configured application database"):
        _validated_disposable_url(database_url)


@pytest.mark.parametrize("application_host", ["127.0.0.1", "localhost."])
def test_validated_disposable_url_rejects_database_url_identity(
    monkeypatch,
    application_host: str,
) -> None:
    database_url = (
        "postgresql+psycopg://queryops:queryops@localhost:5432/queryops_test"
    )
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_DISPOSABLE", "1")
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql+psycopg://other:secret@{application_host}:5432/queryops_test",
    )

    with pytest.raises(pytest.fail.Exception, match="Refusing to use DATABASE_URL"):
        _validated_disposable_url(database_url)


@pytest.mark.parametrize("database_name", ["queryops_test", "queryops_m8_dev"])
def test_validated_disposable_url_accepts_test_and_dev_names(
    monkeypatch,
    database_name: str,
) -> None:
    database_url = (
        "postgresql+psycopg://queryops:queryops@localhost:5432/" + database_name
    )
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_DISPOSABLE", "1")
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert _validated_disposable_url(database_url) == database_url


def _run_alembic_upgrade(database_url: str) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(alembic_config, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
