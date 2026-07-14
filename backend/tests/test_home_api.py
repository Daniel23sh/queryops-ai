from __future__ import annotations

import json
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.domains.it_operations.seed import seed_database
from app.main import app
from app.models.product import (
    AccessScope,
    AppAuditLog,
    AppUser,
    Dashboard,
    DashboardCard,
    DataResource,
    Permission,
    PermissionEffect,
    QueryRun,
    RequestStatus,
    Role,
    RoleUpgradeRequest,
    RunStatus,
    UserAccessScope,
    UserPermission,
)
from app.services.home_overview import (
    OperationalMetrics,
    OperationalMetricsRead,
    get_operational_metrics_reader,
)


@dataclass
class StubOperationalMetricsReader:
    calls: list[frozenset[str]] = field(default_factory=list)

    def __call__(self, _db, _access_context, metric_names, _now):
        self.calls.append(metric_names)
        return OperationalMetricsRead(
            metrics=OperationalMetrics(
                active_human_users=84 if "active_human_users" in metric_names else None,
                device_total=117 if "device_compliance" in metric_names else None,
                compliant_device_count=(
                    109 if "device_compliance" in metric_names else None
                ),
                device_compliance_rate=(
                    Decimal("93.16") if "device_compliance" in metric_names else None
                ),
                monthly_license_cost_usd=(
                    Decimal("18432.50")
                    if "monthly_license_cost_usd" in metric_names
                    else None
                ),
                unused_license_assignments=(
                    18 if "unused_license_assignments" in metric_names else None
                ),
                open_support_tickets=(
                    11 if "open_support_tickets" in metric_names else None
                ),
                security_events_last_30_days=(
                    7 if "security_events_last_30_days" in metric_names else None
                ),
            ),
            runtime_role="queryops_query_runtime",
            transaction_read_only=True,
            row_security_enabled=True,
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
def operational_reader() -> StubOperationalMetricsReader:
    return StubOperationalMetricsReader()


@pytest.fixture
def client(
    db_session: Session,
    operational_reader: StubOperationalMetricsReader,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_operational_metrics_reader] = (
        lambda: operational_reader
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_operational_metrics_reader, None)
        app.dependency_overrides.pop(get_db, None)


def test_home_overview_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/home/overview")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_user_receives_personal_summary_without_domain_or_admin_metrics(
    client: TestClient,
    db_session: Session,
    operational_reader: StubOperationalMetricsReader,
) -> None:
    user = _user_by_email(db_session, "demo.user@queryops.local")
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    user_role = _role_by_name(db_session, "user")
    now = datetime.now(UTC)

    owned = Dashboard(owner_user_id=user.id, title="Owned", visibility_scope="personal")
    shared = Dashboard(
        owner_user_id=manager.id,
        title="Shared global",
        visibility_scope="global",
    )
    archived = Dashboard(
        owner_user_id=user.id,
        title="Archived",
        visibility_scope="personal",
        is_archived=True,
    )
    foreign_personal = Dashboard(
        owner_user_id=manager.id,
        title="Private",
        visibility_scope="personal",
    )
    db_session.add_all([owned, shared, archived, foreign_personal])
    db_session.flush()
    db_session.add_all(
        [
            DashboardCard(dashboard_id=owned.id, title="One", position=0),
            DashboardCard(dashboard_id=owned.id, title="Two", position=1),
            QueryRun(
                user_id=user.id,
                status=RunStatus.SUCCEEDED.value,
                created_at=now - timedelta(days=1),
            ),
            QueryRun(
                user_id=user.id,
                status=RunStatus.SUCCEEDED.value,
                created_at=now - timedelta(days=31),
            ),
            QueryRun(
                user_id=user.id,
                status=RunStatus.FAILED.value,
                created_at=now - timedelta(days=1),
            ),
            QueryRun(
                user_id=manager.id,
                status=RunStatus.SUCCEEDED.value,
                created_at=now - timedelta(days=1),
            ),
            RoleUpgradeRequest(
                requester_user_id=user.id,
                requested_role_id=user_role.id,
                status=RequestStatus.PENDING.value,
                reason="Pending",
            ),
            RoleUpgradeRequest(
                requester_user_id=user.id,
                requested_role_id=user_role.id,
                status=RequestStatus.REJECTED.value,
                reason="Resolved",
            ),
        ]
    )
    db_session.commit()
    _login(client, user.email)

    response = client.get("/api/v1/home/overview")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "personal"
    assert data["scope"] == {
        "type": "department",
        "display_name": "Sales",
        "scope_count": 1,
    }
    assert data["personal_summary"] == {
        "owned_dashboard_count": 1,
        "shared_dashboard_count": 0,
        "owned_card_count": 2,
        "successful_queries_last_30_days": 1,
        "pending_own_role_requests": 1,
    }
    assert data["operational_metrics"] is None
    assert data["admin_metrics"] is None
    assert operational_reader.calls == []
    _assert_safe_aggregate_payload(response.json())


@pytest.mark.parametrize(
    ("email", "expected_scope"),
    [
        ("demo.manager@queryops.local", "Finance"),
        ("demo.analyst@queryops.local", "IT"),
    ],
)
def test_scoped_roles_receive_operational_metrics_without_admin_metrics(
    client: TestClient,
    operational_reader: StubOperationalMetricsReader,
    email: str,
    expected_scope: str,
) -> None:
    _login(client, email)

    response = client.get("/api/v1/home/overview")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "scoped"
    assert data["scope"] == {
        "type": "department",
        "display_name": expected_scope,
        "scope_count": 1,
    }
    assert data["operational_metrics"]["active_human_users"] == 84
    assert data["operational_metrics"]["device_compliance_rate"] == 93.16
    assert data["operational_metrics"]["monthly_license_cost_usd"] == 18432.5
    assert data["admin_metrics"] is None
    assert len(operational_reader.calls) == 1
    _assert_safe_aggregate_payload(response.json())


def test_multiple_department_scopes_are_aggregated_without_a_scope_selector(
    client: TestClient,
    db_session: Session,
) -> None:
    manager = _user_by_email(db_session, "demo.manager@queryops.local")
    sales_scope = _scope_by_type_key(db_session, "department", "sales")
    db_session.add(
        UserAccessScope(
            user_id=manager.id,
            scope_id=sales_scope.id,
            access_level="read",
            is_default=False,
        )
    )
    db_session.commit()
    _login(client, manager.email)

    response = client.get("/api/v1/home/overview")

    assert response.status_code == 200
    assert response.json()["data"]["scope"] == {
        "type": "department",
        "display_name": "2 assigned scopes",
        "scope_count": 2,
    }


def test_resource_denial_nulls_only_dependent_operational_metrics(
    client: TestClient,
    db_session: Session,
    operational_reader: StubOperationalMetricsReader,
) -> None:
    devices = db_session.scalar(
        select(DataResource).where(DataResource.table_name == "devices")
    )
    assert devices is not None
    devices.is_queryable = False
    db_session.commit()
    _login(client, "demo.manager@queryops.local")

    response = client.get("/api/v1/home/overview")

    assert response.status_code == 200
    metrics = response.json()["data"]["operational_metrics"]
    assert metrics["device_total"] is None
    assert metrics["compliant_device_count"] is None
    assert metrics["device_compliance_rate"] is None
    assert metrics["active_human_users"] == 84
    assert "device_compliance" not in operational_reader.calls[0]


def test_admin_metrics_are_global_and_independently_permission_gated(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _user_by_email(db_session, "demo.admin@queryops.local")
    user = _user_by_email(db_session, "demo.user@queryops.local")
    role = _role_by_name(db_session, "manager")
    db_session.add_all(
        [
            AppAuditLog(
                actor_user_id=admin.id,
                event_type="home.test",
                created_at=datetime.now(UTC) - timedelta(days=1),
            ),
            RoleUpgradeRequest(
                requester_user_id=user.id,
                requested_role_id=role.id,
                status=RequestStatus.PENDING.value,
                reason="Test",
            ),
        ]
    )
    manage_users = _permission_by_key(db_session, "can_manage_users")
    db_session.add(
        UserPermission(
            user_id=admin.id,
            permission_id=manage_users.id,
            effect=PermissionEffect.DENY.value,
            reason="Home direct-deny regression",
        )
    )
    db_session.commit()
    _login(client, admin.email)

    response = client.get("/api/v1/home/overview")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "global"
    assert data["scope"] == {
        "type": "global",
        "display_name": "Global",
        "scope_count": 1,
    }
    assert data["operational_metrics"] is not None
    assert data["admin_metrics"]["active_app_users"] is None
    assert data["admin_metrics"]["pending_role_requests"] == 1
    assert data["admin_metrics"]["app_audit_events_last_7_days"] == 1
    _assert_safe_aggregate_payload(response.json())


def _login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/demo/login", json={"email": email})
    assert response.status_code == 200


def _user_by_email(db_session: Session, email: str) -> AppUser:
    user = db_session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


def _role_by_name(db_session: Session, name: str) -> Role:
    role = db_session.scalar(select(Role).where(Role.name == name))
    assert role is not None
    return role


def _permission_by_key(db_session: Session, key: str) -> Permission:
    permission = db_session.scalar(select(Permission).where(Permission.key == key))
    assert permission is not None
    return permission


def _scope_by_type_key(
    db_session: Session,
    scope_type: str,
    scope_key: str,
) -> AccessScope:
    scope = db_session.scalar(
        select(AccessScope).where(
            AccessScope.scope_type == scope_type,
            AccessScope.scope_key == scope_key,
        )
    )
    assert scope is not None
    return scope


def _assert_safe_aggregate_payload(payload: object) -> None:
    serialized = json.dumps(payload).lower()
    assert "generated_sql" not in serialized
    assert "executed_sql" not in serialized
    assert "source_ip" not in serialized
    assert "directory_user" not in serialized
    assert "select " not in serialized
