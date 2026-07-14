from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Protocol

from sqlalchemy import Engine, func, or_, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.auth.access_context import UserAccessContext
from app.auth.access_policy import authorize_resource_access
from app.core.rls import build_rls_context, set_rls_context
from app.dashboards.policy import dashboard_is_visible
from app.domains.it_operations.models import (
    AccountStatus,
    AccountType,
    AssignmentStatus,
    ComplianceStatus,
    Device,
    DirectoryUser,
    EmployeeStatus,
    License,
    LicenseAssignment,
    SecurityEvent,
    SupportTicket,
    TicketStatus,
)
from app.models.product import (
    AppAuditLog,
    AppUser,
    Dashboard,
    DashboardCard,
    DataResource,
    QueryRun,
    RequestStatus,
    RoleUpgradeRequest,
    RunStatus,
    UserStatus,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.runtime_role import QUERY_RUNTIME_ROLE, set_query_runtime_role


HomeMode = Literal["personal", "scoped", "global"]
ScopeType = Literal["personal", "department", "global"]

OPERATIONAL_METRIC_DEPENDENCIES: dict[str, frozenset[str]] = {
    "active_human_users": frozenset({"directory_users"}),
    "device_compliance": frozenset({"devices"}),
    "monthly_license_cost_usd": frozenset({"license_assignments", "licenses"}),
    "unused_license_assignments": frozenset({"license_assignments"}),
    "open_support_tickets": frozenset({"support_tickets"}),
    "security_events_last_30_days": frozenset({"security_events"}),
}
OPERATIONAL_RESOURCE_NAMES = frozenset(
    table_name
    for dependencies in OPERATIONAL_METRIC_DEPENDENCIES.values()
    for table_name in dependencies
)
ADMIN_PERMISSION_KEYS = frozenset(
    {"can_manage_users", "can_approve_role_requests", "can_view_global_audit"}
)


@dataclass(frozen=True)
class HomeScope:
    type: ScopeType
    display_name: str
    scope_count: int


@dataclass(frozen=True)
class PersonalSummary:
    owned_dashboard_count: int
    shared_dashboard_count: int
    owned_card_count: int
    successful_queries_last_30_days: int
    pending_own_role_requests: int


@dataclass(frozen=True)
class OperationalMetrics:
    active_human_users: int | None = None
    device_total: int | None = None
    compliant_device_count: int | None = None
    device_compliance_rate: Decimal | None = None
    monthly_license_cost_usd: Decimal | None = None
    unused_license_assignments: int | None = None
    open_support_tickets: int | None = None
    security_events_last_30_days: int | None = None


@dataclass(frozen=True)
class OperationalMetricsRead:
    metrics: OperationalMetrics
    runtime_role: str
    transaction_read_only: bool
    row_security_enabled: bool


@dataclass(frozen=True)
class AdminMetrics:
    active_app_users: int | None
    pending_role_requests: int | None
    app_audit_events_last_7_days: int | None


@dataclass(frozen=True)
class HomeOverview:
    mode: HomeMode
    scope: HomeScope
    personal_summary: PersonalSummary
    operational_metrics: OperationalMetrics | None
    admin_metrics: AdminMetrics | None


class OperationalMetricsReader(Protocol):
    def __call__(
        self,
        db: Session,
        access_context: UserAccessContext,
        metric_names: frozenset[str],
        now: datetime,
    ) -> OperationalMetricsRead:
        raise NotImplementedError


def get_operational_metrics_reader() -> OperationalMetricsReader:
    return read_operational_metrics


def build_home_overview(
    db: Session,
    *,
    current_user: AppUser,
    access_context: UserAccessContext,
    operational_metrics_reader: OperationalMetricsReader,
    now: datetime | None = None,
) -> HomeOverview:
    current_time = now or datetime.now(UTC)
    mode = _home_mode(access_context)
    operational_metrics: OperationalMetrics | None = None

    if mode != "personal":
        allowed_metric_names = _allowed_operational_metric_names(
            db,
            access_context,
            mode,
        )
        operational_metrics = operational_metrics_reader(
            db,
            access_context,
            allowed_metric_names,
            current_time,
        ).metrics

    return HomeOverview(
        mode=mode,
        scope=_home_scope(access_context),
        personal_summary=_personal_summary(
            db,
            current_user=current_user,
            access_context=access_context,
            now=current_time,
        ),
        operational_metrics=operational_metrics,
        admin_metrics=_admin_metrics(db, access_context, current_time),
    )


def read_operational_metrics(
    db: Session,
    access_context: UserAccessContext,
    metric_names: frozenset[str],
    now: datetime,
) -> OperationalMetricsRead:
    engine = _engine_from_session(db)
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Home operational metrics require PostgreSQL.")

    values: dict[str, int | Decimal | None] = {}
    with engine.connect() as connection:
        with connection.begin():
            # This must remain the first statement in the aggregate transaction.
            connection.execute(text("SET TRANSACTION READ ONLY"))
            set_query_runtime_role(connection)
            set_rls_context(connection, build_rls_context(access_context))

            runtime_role = str(connection.execute(text("SELECT current_user")).scalar_one())
            transaction_read_only = (
                str(connection.execute(text("SHOW transaction_read_only")).scalar_one())
                == "on"
            )
            row_security_enabled = (
                str(connection.execute(text("SHOW row_security")).scalar_one()) == "on"
            )
            _require_operational_boundary(
                runtime_role=runtime_role,
                transaction_read_only=transaction_read_only,
                row_security_enabled=row_security_enabled,
            )
            _read_allowed_metrics(connection, metric_names, now, values)

    device_total = _optional_int(values.get("device_total"))
    compliant_device_count = _optional_int(values.get("compliant_device_count"))
    return OperationalMetricsRead(
        metrics=OperationalMetrics(
            active_human_users=_optional_int(values.get("active_human_users")),
            device_total=device_total,
            compliant_device_count=compliant_device_count,
            device_compliance_rate=_compliance_rate(
                device_total,
                compliant_device_count,
            ),
            monthly_license_cost_usd=_optional_decimal(
                values.get("monthly_license_cost_usd")
            ),
            unused_license_assignments=_optional_int(
                values.get("unused_license_assignments")
            ),
            open_support_tickets=_optional_int(values.get("open_support_tickets")),
            security_events_last_30_days=_optional_int(
                values.get("security_events_last_30_days")
            ),
        ),
        runtime_role=runtime_role,
        transaction_read_only=transaction_read_only,
        row_security_enabled=row_security_enabled,
    )


def _read_allowed_metrics(
    connection: Connection,
    metric_names: frozenset[str],
    now: datetime,
    values: dict[str, int | Decimal | None],
) -> None:
    if "active_human_users" in metric_names:
        values["active_human_users"] = connection.scalar(
            select(func.count(DirectoryUser.id)).where(
                DirectoryUser.account_type == AccountType.HUMAN.value,
                DirectoryUser.employee_status == EmployeeStatus.ACTIVE.value,
                DirectoryUser.account_status == AccountStatus.ACTIVE.value,
            )
        )

    if "device_compliance" in metric_names:
        device_totals = connection.execute(
            select(
                func.count(Device.id),
                func.count(Device.id).filter(
                    Device.compliance_status == ComplianceStatus.COMPLIANT.value
                ),
            )
        ).one()
        values["device_total"] = device_totals[0]
        values["compliant_device_count"] = device_totals[1]

    if "monthly_license_cost_usd" in metric_names:
        values["monthly_license_cost_usd"] = connection.scalar(
            select(func.coalesce(func.sum(License.monthly_cost_usd), Decimal("0.00")))
            .select_from(LicenseAssignment)
            .join(License, License.id == LicenseAssignment.license_id)
            .where(LicenseAssignment.status == AssignmentStatus.ACTIVE.value)
        )

    if "unused_license_assignments" in metric_names:
        unused_cutoff = now - timedelta(days=_unused_license_default_days())
        values["unused_license_assignments"] = connection.scalar(
            select(func.count(LicenseAssignment.id)).where(
                LicenseAssignment.status == AssignmentStatus.ACTIVE.value,
                LicenseAssignment.is_mandatory.is_(False),
                or_(
                    LicenseAssignment.last_used_at.is_(None),
                    LicenseAssignment.last_used_at < unused_cutoff,
                ),
            )
        )

    if "open_support_tickets" in metric_names:
        values["open_support_tickets"] = connection.scalar(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.status.in_(
                    [TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value]
                )
            )
        )

    if "security_events_last_30_days" in metric_names:
        security_cutoff = now - timedelta(days=30)
        values["security_events_last_30_days"] = connection.scalar(
            select(func.count(SecurityEvent.id)).where(
                SecurityEvent.occurred_at >= security_cutoff
            )
        )


def _personal_summary(
    db: Session,
    *,
    current_user: AppUser,
    access_context: UserAccessContext,
    now: datetime,
) -> PersonalSummary:
    dashboards = db.scalars(
        select(Dashboard)
        .where(Dashboard.is_archived.is_(False))
        .order_by(Dashboard.id)
    ).all()
    owned_dashboards = [
        dashboard
        for dashboard in dashboards
        if dashboard.owner_user_id == current_user.id
    ]
    shared_dashboards = [
        dashboard
        for dashboard in dashboards
        if dashboard.owner_user_id != current_user.id
        and dashboard_is_visible(dashboard, current_user, access_context)
    ]
    owned_dashboard_ids = [dashboard.id for dashboard in owned_dashboards]
    owned_card_count = 0
    if owned_dashboard_ids:
        owned_card_count = int(
            db.scalar(
                select(func.count(DashboardCard.id)).where(
                    DashboardCard.dashboard_id.in_(owned_dashboard_ids)
                )
            )
            or 0
        )

    query_cutoff = now - timedelta(days=30)
    successful_queries = int(
        db.scalar(
            select(func.count(QueryRun.id)).where(
                QueryRun.user_id == current_user.id,
                QueryRun.status == RunStatus.SUCCEEDED.value,
                QueryRun.created_at >= query_cutoff,
            )
        )
        or 0
    )
    pending_role_requests = int(
        db.scalar(
            select(func.count(RoleUpgradeRequest.id)).where(
                RoleUpgradeRequest.requester_user_id == current_user.id,
                RoleUpgradeRequest.status == RequestStatus.PENDING.value,
            )
        )
        or 0
    )

    return PersonalSummary(
        owned_dashboard_count=len(owned_dashboards),
        shared_dashboard_count=len(shared_dashboards),
        owned_card_count=owned_card_count,
        successful_queries_last_30_days=successful_queries,
        pending_own_role_requests=pending_role_requests,
    )


def _admin_metrics(
    db: Session,
    access_context: UserAccessContext,
    now: datetime,
) -> AdminMetrics | None:
    if not ADMIN_PERMISSION_KEYS.intersection(access_context.permissions):
        return None

    active_app_users = None
    if access_context.has_permission("can_manage_users"):
        active_app_users = int(
            db.scalar(
                select(func.count(AppUser.id)).where(
                    AppUser.status == UserStatus.ACTIVE.value
                )
            )
            or 0
        )

    pending_role_requests = None
    if access_context.has_permission("can_approve_role_requests"):
        pending_role_requests = int(
            db.scalar(
                select(func.count(RoleUpgradeRequest.id)).where(
                    RoleUpgradeRequest.status == RequestStatus.PENDING.value
                )
            )
            or 0
        )

    recent_audit_events = None
    if access_context.has_permission("can_view_global_audit"):
        audit_cutoff = now - timedelta(days=7)
        recent_audit_events = int(
            db.scalar(
                select(func.count(AppAuditLog.id)).where(
                    AppAuditLog.created_at >= audit_cutoff
                )
            )
            or 0
        )

    return AdminMetrics(
        active_app_users=active_app_users,
        pending_role_requests=pending_role_requests,
        app_audit_events_last_7_days=recent_audit_events,
    )


def _home_mode(access_context: UserAccessContext) -> HomeMode:
    if access_context.has_global_scope and access_context.has_permission(
        "can_view_global_data"
    ):
        return "global"
    if access_context.has_permission("can_view_scoped_data") and any(
        scope.type == "department" and scope.department_id is not None
        for scope in access_context.scopes
    ):
        return "scoped"
    return "personal"


def _home_scope(access_context: UserAccessContext) -> HomeScope:
    if access_context.has_global_scope:
        global_scope = next(
            (scope for scope in access_context.scopes if scope.type == "global"),
            None,
        )
        return HomeScope(
            type="global",
            display_name=(global_scope.display_name if global_scope else "Global"),
            scope_count=1,
        )

    department_scopes = [
        scope
        for scope in access_context.scopes
        if scope.type == "department" and scope.department_id is not None
    ]
    if len(department_scopes) == 1:
        return HomeScope(
            type="department",
            display_name=department_scopes[0].display_name,
            scope_count=1,
        )
    if len(department_scopes) > 1:
        return HomeScope(
            type="department",
            display_name=f"{len(department_scopes)} assigned scopes",
            scope_count=len(department_scopes),
        )
    return HomeScope(type="personal", display_name="Personal", scope_count=0)


def _allowed_operational_metric_names(
    db: Session,
    access_context: UserAccessContext,
    mode: HomeMode,
) -> frozenset[str]:
    resources = db.scalars(
        select(DataResource).where(
            DataResource.resource_type == "table",
            DataResource.table_name.in_(OPERATIONAL_RESOURCE_NAMES),
        )
    ).all()
    resources_by_name = {resource.table_name: resource for resource in resources}
    action = "view:global_data" if mode == "global" else "view:scoped_data"
    allowed_resources: set[str] = set()

    for table_name in OPERATIONAL_RESOURCE_NAMES:
        resource = resources_by_name.get(table_name)
        if resource is None or resource.is_queryable is not True:
            continue
        decision = authorize_resource_access(
            access_context,
            action,
            resource,
            _resource_runtime_context(access_context, resource),
        )
        if decision.allowed:
            allowed_resources.add(table_name)

    return frozenset(
        metric_name
        for metric_name, dependencies in OPERATIONAL_METRIC_DEPENDENCIES.items()
        if dependencies.issubset(allowed_resources)
    )


def _resource_runtime_context(
    access_context: UserAccessContext,
    resource: DataResource,
) -> dict[str, str]:
    if not resource.scope_type:
        return {}
    if access_context.has_global_scope:
        return {"scope_type": resource.scope_type, "scope_key": "global"}

    default_scope = access_context.default_scope
    if default_scope is not None and default_scope.type == resource.scope_type:
        return {
            "scope_type": resource.scope_type,
            "scope_key": default_scope.key,
        }
    matching_scope = next(
        (scope for scope in access_context.scopes if scope.type == resource.scope_type),
        None,
    )
    if matching_scope is None:
        return {"scope_type": resource.scope_type}
    return {"scope_type": resource.scope_type, "scope_key": matching_scope.key}


def _unused_license_default_days() -> int:
    domain_pack = load_it_operations_domain_pack()
    template = domain_pack.templates_by_id.get("unused_licenses_by_department")
    if template is None:
        raise RuntimeError("Approved unused-license template is unavailable.")
    parameter = next(
        (item for item in template.parameters if item.name == "unused_days"),
        None,
    )
    if parameter is None or isinstance(parameter.default, bool):
        raise RuntimeError("Approved unused-license threshold is unavailable.")
    try:
        days = int(parameter.default)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Approved unused-license threshold is invalid.") from exc
    if days <= 0:
        raise RuntimeError("Approved unused-license threshold is invalid.")
    return days


def _engine_from_session(db: Session) -> Engine:
    bind = db.get_bind()
    if isinstance(bind, Engine):
        return bind
    if isinstance(bind, Connection):
        return bind.engine
    raise TypeError("Home operational metrics require a SQLAlchemy Engine.")


def _require_operational_boundary(
    *,
    runtime_role: str,
    transaction_read_only: bool,
    row_security_enabled: bool,
) -> None:
    if runtime_role != QUERY_RUNTIME_ROLE:
        raise RuntimeError("Home operational runtime role is not active.")
    if not transaction_read_only:
        raise RuntimeError("Home operational transaction is not read-only.")
    if not row_security_enabled:
        raise RuntimeError("Home operational row security is not active.")


def _compliance_rate(
    device_total: int | None,
    compliant_device_count: int | None,
) -> Decimal | None:
    if not device_total or compliant_device_count is None:
        return None
    return (
        (Decimal(compliant_device_count) * Decimal("100")) / Decimal(device_total)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _optional_int(value: int | Decimal | None) -> int | None:
    return int(value) if value is not None else None


def _optional_decimal(value: int | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
