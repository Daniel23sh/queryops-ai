"""Pre-execution manual witnesses and independent SQL oracles, never V2 inputs."""


def field(entity, column="id"):
    return {"entity_id": entity, "column": column}


def plan(entities, concepts=(), rules=(), fields=(), relationships=(), distinct=False,
         literals=(), aggregations=()):
    return dict(entity_ids=list(entities), concept_ids=list(concepts),
                composition_rule_ids=list(rules), metric_id=None, distinct=distinct,
                output_fields=[field(*f) for f in fields],
                relationships=[dict(relationship_id=r, join_type=j) for r, j in relationships],
                literal_filters=list(literals), aggregations=list(aggregations),
                group_by=[], having=[], order_by=[], limit=None)


def literal(entity, column, operator, value):
    return dict(field=field(entity, column), operator=operator, value=value)


def contrast(name, expected_result="incorrect", **changes):
    return dict(id=name, changes=changes, expected_result=expected_result)


def witnesses():
    values = []

    def add(number, supplied, sql, contrasts=()):
        values.append(dict(case_id=f"W6C-{number:03}", plan=supplied,
                           oracle_sql=sql, contrasts=list(contrasts)))

    add(1, plan(["devices"], ["stale_device"], fields=[("devices", "id")]),
        "SELECT id FROM devices WHERE last_seen_at IS NULL OR last_seen_at < CURRENT_TIMESTAMP - INTERVAL '30 days'",
        [contrast("missing_staleness", concept_ids=[])])
    add(4, plan(["directory_users"], fields=[("directory_users", "id")],
                literals=[literal("directory_users", "account_status", "not_equals", "locked")]),
        "SELECT id FROM directory_users WHERE account_status <> 'locked'",
        [contrast("excess_active_human", concept_ids=["active_human_directory_user"])])
    add(5, plan(["directory_users", "license_assignments"],
                ["inactive_human_directory_user", "active_mandatory_license_assignment"],
                fields=[("directory_users", "id")],
                relationships=[("license_assignment_user", "inner")], distinct=True),
        "SELECT DISTINCT du.id FROM directory_users du JOIN license_assignments la ON la.user_id=du.id WHERE du.account_type='human' AND du.account_status='active' AND (du.last_login_at IS NULL OR du.last_login_at < CURRENT_TIMESTAMP - INTERVAL '90 days') AND la.status='active' AND la.is_mandatory=TRUE",
        [contrast("assignment_fanout", distinct=False),
         contrast("excess_exception_exclusion", literal_filters=[literal("license_assignments", "is_exception", "equals", False)])])
    posture = "(compliance_status='non_compliant' OR antivirus_status IN ('missing','outdated') OR encryption_enabled=FALSE)"
    add(6, plan(["devices"], ["stale_device"], ["non_compliant_device_posture"], [("devices", "id")]),
        "SELECT id FROM devices WHERE (last_seen_at IS NULL OR last_seen_at < CURRENT_TIMESTAMP - INTERVAL '30 days') AND " + posture,
        [contrast("missing_or_rule", composition_rule_ids=[]),
         contrast("excess_status_arm", concept_ids=["stale_device", "non_compliant_device"]),
         contrast("collapsed_all_arms", expected_result="rejected", concept_ids=["stale_device", "non_compliant_device", "antivirus_attention_device", "unencrypted_device"])])
    left = [("user_group_membership_user", "left"), ("user_group_membership_group", "left"), ("security_event_user", "left")]
    add(7, plan(["directory_users", "user_group_memberships", "groups", "security_events"],
                ["inactive_human_directory_user"], ["disablement_policy_review"], [("directory_users", "id")],
                left, True, [literal("directory_users", "employee_status", "equals", "on_leave")]),
        "SELECT DISTINCT du.id FROM directory_users du LEFT JOIN user_group_memberships ugm ON ugm.user_id=du.id LEFT JOIN groups g ON g.id=ugm.group_id LEFT JOIN security_events se ON se.user_id=du.id WHERE du.account_type='human' AND du.account_status='active' AND (du.last_login_at IS NULL OR du.last_login_at < CURRENT_TIMESTAMP - INTERVAL '90 days') AND du.employee_status='on_leave' AND (g.is_privileged=TRUE OR (se.severity='critical' AND se.status IN ('open','investigating')))",
        [contrast("inner_both_branches", relationships=[dict(relationship_id=r, join_type="inner") for r, _ in left])])
    add(8, plan(["devices", "software_installs"], ["high_risk_unsupported_software_install"],
                fields=[("devices", "id")], relationships=[("software_install_device", "inner")], distinct=True),
        "SELECT DISTINCT d.id FROM devices d JOIN software_installs si ON si.device_id=d.id WHERE si.is_unsupported=TRUE AND si.risk_level='high'",
        [contrast("install_fanout", distinct=False),
         contrast("excess_outdated", concept_ids=["high_risk_unsupported_software_install", "outdated_software_install"])])
    count = dict(id="endpoint_count", function="count", field=field("devices"), distinct=True)
    add(9, plan(["devices", "software_installs", "security_events"],
                ["outdated_software_install", "unresolved_critical_security_event"],
                relationships=[("software_install_device", "inner"), ("security_event_device", "inner")],
                aggregations=[count]),
        "SELECT COUNT(DISTINCT d.id) AS endpoint_count FROM devices d JOIN software_installs si ON si.device_id=d.id JOIN security_events se ON se.device_id=d.id WHERE si.is_outdated=TRUE AND se.severity='critical' AND se.status IN ('open','investigating')",
        [contrast("count_joined_rows", aggregations=[{**count, "distinct": False}])])
    add(10, plan(["devices", "software_installs"], ["unencrypted_device", "unsupported_software_install"],
                 fields=[("devices", "id"), ("software_installs", "id")],
                 relationships=[("software_install_device", "inner")]),
        "SELECT d.id AS endpoint_key, si.id AS installation_key FROM devices d JOIN software_installs si ON si.device_id=d.id WHERE d.encryption_enabled=FALSE AND si.is_unsupported=TRUE",
        [contrast("missing_install_identity", output_fields=[field("devices")])])
    add(11, plan(["license_assignments"], ["high_confidence_unused_license_assignment"],
                 fields=[("license_assignments", "id")]),
        "SELECT id FROM license_assignments WHERE status='active' AND is_mandatory=FALSE AND is_exception=FALSE AND (last_used_at IS NULL OR last_used_at < CURRENT_TIMESTAMP - INTERVAL '90 days')",
        [contrast("weaker_sixty_day_definition", concept_ids=["unused_license_assignment"])])
    add(12, plan(["license_assignments"], ["active_license_assignment"], fields=[("license_assignments", "id")]),
        "SELECT id FROM license_assignments WHERE status='active'",
        [contrast("excess_unused", concept_ids=["unused_license_assignment"])])
    add(13, plan(["user_group_memberships"], ["recent_privileged_group_membership"],
                 fields=[("user_group_memberships", "user_id"), ("user_group_memberships", "group_id"), ("user_group_memberships", "added_at")]),
        "SELECT user_id, group_id, added_at FROM user_group_memberships WHERE added_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'")
    add(14, plan(["directory_users", "devices", "software_installs", "login_events", "license_assignments", "licenses", "user_group_memberships", "groups"],
                 ["inactive_human_directory_user", "stale_device", "high_risk_unsupported_software_install", "failed_login_within_30_days", "active_exception_license_assignment", "recent_privileged_group_membership", "privileged_group"],
                 fields=[("directory_users", "id"), ("licenses", "product_name")],
                 relationships=[(r, "inner") for r in ("device_assignee", "software_install_device", "login_event_user", "license_assignment_user", "license_assignment_license", "user_group_membership_user", "user_group_membership_group")], distinct=True),
        "SELECT DISTINCT du.id, l.product_name FROM directory_users du JOIN devices d ON d.assigned_user_id=du.id JOIN software_installs si ON si.device_id=d.id JOIN login_events le ON le.user_id=du.id JOIN license_assignments la ON la.user_id=du.id JOIN licenses l ON l.id=la.license_id JOIN user_group_memberships ugm ON ugm.user_id=du.id JOIN groups g ON g.id=ugm.group_id WHERE du.account_type='human' AND du.account_status='active' AND (du.last_login_at IS NULL OR du.last_login_at < CURRENT_TIMESTAMP - INTERVAL '90 days') AND (d.last_seen_at IS NULL OR d.last_seen_at < CURRENT_TIMESTAMP - INTERVAL '30 days') AND si.is_unsupported=TRUE AND si.risk_level='high' AND le.event_type='failed' AND le.occurred_at >= CURRENT_TIMESTAMP - INTERVAL '30 days' AND la.status='active' AND la.is_exception=TRUE AND ugm.added_at >= CURRENT_TIMESTAMP - INTERVAL '30 days' AND g.is_privileged=TRUE")
    add(15, plan(["support_tickets"], ["open_support_ticket_older_than_30_days"], fields=[("support_tickets", "id")]),
        "SELECT id FROM support_tickets WHERE status IN ('open','in_progress') AND opened_at < CURRENT_TIMESTAMP - INTERVAL '30 days'",
        [contrast("missing_age", concept_ids=["open_support_ticket"])])
    add(20, plan(["devices"], ["unencrypted_device"], ["non_compliant_device_posture"], [("devices", "id")]),
        "SELECT id FROM devices WHERE encryption_enabled=FALSE",
        [contrast("missing_explicit_narrowing", concept_ids=[])])
    return values
