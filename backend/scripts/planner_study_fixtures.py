"""Preregistered IT Operations diagnostics and their tiny synthetic witness set."""
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.domains.it_operations.models import (
    Department, Device, DirectoryUser, Group, SupportTicket, UserGroupMembership,
)
from app.domains.it_operations.seed import (
    ROLE_PERMISSION_KEYS, _seed_data_resources, get_seed_profile,
)
from app.models.product import (
    AccessScope, AppUser, Permission, Role, RolePermission, UserAccessScope,
)
from scripts.semantic_ownership_fixtures import count, field, plan
from app.query_engine.semantic_plan import (
    SemanticLiteralFilter, SemanticPlan, SemanticRelationshipIntent,
)


@dataclass(frozen=True)
class StudyCase:
    id: str
    family: str
    question: str
    plans: tuple[SemanticPlan, ...]
    rows: tuple[tuple[str | int, ...], ...]
    hint_sensitive: bool = False


def relation(name: str) -> SemanticRelationshipIntent:
    return SemanticRelationshipIntent(relationship_id=name, join_type="inner")


def equals(entity: str, column: str, value: str) -> SemanticLiteralFilter:
    return SemanticLiteralFilter(field=field(entity, column), operator="equals", value=value)


HOST = field("devices", "hostname")
DEVICE_TYPE = field("devices", "device_type")
DEVICE_ID = field("devices", "id")
DEPARTMENT = field("departments", "name")
TICKET_ID = field("support_tickets", "id")
GROUP_ID = field("groups", "id")
LAPTOP = equals("devices", "device_type", "laptop")
STATUS = equals("devices", "compliance_status", "non_compliant")
OUTDATED = equals("devices", "antivirus_status", "outdated")
DISTRIBUTION = equals("groups", "group_type", "distribution")
CRITICAL = equals("support_tickets", "priority", "critical")

CASES = (
    StudyCase("composition-posture", "composition",
              "Return the hostnames of laptops covered by the non-compliant posture policy.",
              (plan(entity_ids=("devices",), composition_rule_ids=("non_compliant_device_posture",),
                    literal_filters=(LAPTOP,), output_fields=(HOST,)),),
              (("study-antivirus",), ("study-encryption",), ("study-missing",), ("study-status",))),
    StudyCase("composition-status", "composition",
              "List laptop hostnames whose recorded compliance status is non-compliant, regardless of antivirus or encryption.",
              (plan(entity_ids=("devices",), concept_ids=("non_compliant_device",), literal_filters=(LAPTOP,),
                    output_fields=(HOST,)),
               plan(entity_ids=("devices",), literal_filters=(LAPTOP, STATUS), output_fields=(HOST,))),
              (("study-status",),)),
    StudyCase("grain-type", "grain", "Show counts of managed devices broken down by device type.",
              tuple(plan(entity_ids=("devices",), output_fields=(DEVICE_TYPE,), group_by=(DEVICE_TYPE,),
                         aggregations=(agg,)) for agg in (count(), count(DEVICE_ID), count(DEVICE_ID, distinct=True))),
              (("desktop", 1), ("laptop", 5))),
    StudyCase("grain-memberships", "grain", "How many distribution groups have at least one directory user as a member?",
              (plan(entity_ids=("directory_users", "groups", "user_group_memberships"),
                    literal_filters=(DISTRIBUTION,), relationships=(relation("user_group_membership_user"),
                    relation("user_group_membership_group")), aggregations=(count(GROUP_ID, distinct=True),)),),
              ((1,),), hint_sensitive=True),
    StudyCase("clarify-urgent", "clarification", "How many support tickets are urgent?", (), ()),
    StudyCase("clarify-critical", "clarification", "How many support tickets have critical priority?",
              tuple(plan(entity_ids=("support_tickets",), literal_filters=(CRITICAL,), aggregations=(agg,))
                    for agg in (count(), count(TICKET_ID), count(TICKET_ID, distinct=True))), ((1,),)),
    StudyCase("relationship-device", "relationship",
              "For devices with outdated antivirus, give each hostname and the device's own department name.",
              (plan(entity_ids=("devices", "departments"), literal_filters=(OUTDATED,),
                    relationships=(relation("device_department"),), output_fields=(HOST, DEPARTMENT)),),
              (("study-antivirus", "IT"),)),
    StudyCase("relationship-assignee", "relationship",
              "For devices with outdated antivirus and an assigned user, give each hostname and the assigned user's department name.",
              (plan(entity_ids=("devices", "directory_users", "departments"), literal_filters=(OUTDATED,),
                    relationships=(relation("device_assignee"), relation("directory_user_department")),
                    output_fields=(HOST, DEPARTMENT)),), (("study-antivirus", "Finance"),)),
)

ACTOR = "study.analyst@queryops.invalid"
DENIED_ACTOR = "study.reader@queryops.invalid"


def key(label: str):
    return uuid5(NAMESPACE_URL, f"queryops/planner-reliability-study/v1/{label}")


def add_witnesses(db: Session, reference: datetime) -> None:
    """Insert only into a separately verified, empty, migrated study database."""
    dates = {"created_at": reference, "updated_at": reference}
    departments = {name: key(name) for name in ("IT", "Finance", "Sales")}
    db.add_all(Department(id=id_, name=name, **dates) for name, id_ in departments.items())
    db.flush()
    scopes = {}
    for name, id_ in departments.items():
        scopes[name] = AccessScope(id=key("scope-" + name), scope_type="department", scope_key=name.lower(),
                                   department_id=id_, domain="it_operations", display_name=name, **dates)
    db.add_all(scopes.values())
    state = SimpleNamespace(profile=get_seed_profile("small"), reference_now=reference)
    _seed_data_resources(db, state)
    permissions = ("can_run_free_query", "can_query_scoped_data")
    db.add_all(Permission(id=key(name), key=name, category="query", description=name, **dates)
               for name in permissions)
    for email, role_name, allowed_scopes in ((ACTOR, "analyst", ("IT", "Finance")),
                                            (DENIED_ACTOR, "user", ("IT",))):
        role = Role(id=key(role_name), name=role_name, description=role_name, **dates)
        db.add(role)
        db.flush()
        user = AppUser(id=key(email), email=email, full_name=role_name, auth_provider="demo",
                       provider_user_id=email, role_id=role.id, department_id=departments["IT"],
                       status="active", **dates)
        db.add(user)
        db.flush()
        db.add_all(RolePermission(role_id=role.id, permission_id=key(name), created_at=reference)
                   for name in permissions if name in ROLE_PERMISSION_KEYS[role_name])
        db.add_all(UserAccessScope(user_id=user.id, scope_id=scopes[name].id,
                                  access_level="manage", is_default=i == 0, created_at=reference)
                   for i, name in enumerate(allowed_scopes))
    for name, department in (("assigned", "Finance"), ("member", "IT"), ("ordinary", "IT")):
        db.add(DirectoryUser(id=key(name), employee_number=name, email=f"{name}@queryops.invalid",
                             full_name=name, department_id=departments[department], **dates))
    for name, kind in (("populated", "distribution"), ("empty", "distribution"), ("ordinary", "security")):
        db.add(Group(id=key("group-" + name), name=name, department_id=departments["IT"],
                     group_type=kind, **dates))
    db.flush()
    for user, group in (("member", "populated"), ("ordinary", "populated"), ("ordinary", "ordinary")):
        db.add(UserGroupMembership(user_id=key(user), group_id=key("group-" + group),
                                   department_id=departments["IT"], added_at=reference))
    for name, department, kind, status, antivirus, encrypted in (
        ("status", "IT", "laptop", "non_compliant", "healthy", True),
        ("antivirus", "IT", "laptop", "compliant", "outdated", True),
        ("missing", "IT", "laptop", "compliant", "missing", True),
        ("encryption", "IT", "laptop", "compliant", "healthy", False),
        ("healthy", "IT", "laptop", "compliant", "healthy", True),
        ("non-laptop", "IT", "desktop", "non_compliant", "healthy", True),
        ("hidden", "Sales", "laptop", "non_compliant", "outdated", True),
    ):
        db.add(Device(id=key("device-" + name), department_id=departments[department],
                      assigned_user_id=key("assigned") if name in {"antivirus", "hidden"} else None,
                      hostname=f"study-{name}", os="Study OS", os_version="1", device_type=kind,
                      compliance_status=status, antivirus_status=antivirus, encryption_enabled=encrypted, **dates))
    for i, (category, priority, department) in enumerate((
        ("hardware", "critical", "IT"), ("hardware", "high", "IT"),
        ("network", "low", "Finance"), ("hidden", "critical", "Sales"),
    )):
        db.add(SupportTicket(id=key(f"ticket-{i}"), department_id=departments[department],
                             title=f"Study ticket {i}", category=category, priority=priority,
                             opened_at=reference, **dates))
