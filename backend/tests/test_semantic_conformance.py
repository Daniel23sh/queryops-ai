from __future__ import annotations

import pytest

from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_conformance import (
    SemanticConformanceReason,
    check_semantic_conformance,
)
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticHavingIntent,
    SemanticLiteralFilter,
    SemanticOrderIntent,
    SemanticPlan,
    SemanticRelationshipIntent,
    validate_semantic_plan,
)
from app.query_engine.sql_validator import SQLValidationResult


def test_active_metric_requires_every_business_predicate_and_ignores_alias() -> None:
    sql = (
        "SELECT COUNT(*) AS active_human_user_count FROM directory_users "
        "WHERE account_type = 'human' AND employee_status = 'active' "
        "AND account_status = 'active'"
    )
    result = _check(_active_metric_plan(), sql, ("directory_users",))

    assert result.valid is True
    assert result.reason_code is None
    assert result.checked_predicate_count == 3

    missing = _check(
        _active_metric_plan(),
        "SELECT COUNT(*) AS active_user_count FROM directory_users "
        "WHERE account_type = 'human' AND account_status = 'active'",
        ("directory_users",),
    )
    assert missing.valid is False
    assert missing.reason_code is SemanticConformanceReason.PREDICATE_MISSING


def test_literal_not_disabled_does_not_require_active_user_metric() -> None:
    plan = SemanticPlan(
        entity_ids=("directory_users",),
        concept_ids=(),
        composition_rule_ids=(),
        metric_id=None,
        distinct=False,
        literal_filters=(
            SemanticLiteralFilter(
                field=SemanticFieldRef(
                    entity_id="directory_users",
                    column="account_status",
                ),
                operator="not_equals",
                value="disabled",
            ),
        ),
        relationships=(),
        output_fields=(),
        aggregations=(
            SemanticAggregationIntent(
                id="row_count",
                function="count",
                field=None,
                distinct=False,
            ),
        ),
        group_by=(),
        having=(),
        order_by=(),
        limit=None,
    )

    assert _check(
        plan,
        "SELECT COUNT(*) FROM directory_users WHERE account_status <> 'disabled'",
        ("directory_users",),
    ).valid
    extra = _check(
        plan,
        "SELECT COUNT(*) FROM directory_users WHERE account_status <> 'disabled' "
        "AND employee_status = 'active'",
        ("directory_users",),
    )
    assert extra.reason_code is SemanticConformanceReason.EXTRA_FILTER


def test_relationship_endpoint_and_join_type_are_enforced() -> None:
    plan = SemanticPlan(
        entity_ids=("devices", "directory_users"),
        concept_ids=("active_employee",),
        composition_rule_ids=("non_compliant_device_posture",),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(
            SemanticRelationshipIntent(
                relationship_id="device_assignee",
                join_type="left",
            ),
        ),
        output_fields=(
            SemanticFieldRef(entity_id="devices", column="hostname"),
            SemanticFieldRef(entity_id="directory_users", column="full_name"),
        ),
        aggregations=(),
        group_by=(),
        having=(),
        order_by=(),
        limit=None,
    )
    sql = (
        "SELECT d.hostname, u.full_name FROM devices d LEFT JOIN directory_users u "
        "ON d.assigned_user_id = u.id WHERE "
        "(d.compliance_status = 'non_compliant' "
        "OR d.antivirus_status IN ('outdated', 'missing') "
        "OR d.encryption_enabled = false) "
        "AND u.employee_status = 'active'"
    )
    assert _check(plan, sql, ("devices", "directory_users")).valid

    wrong_join = sql.replace("LEFT JOIN", "JOIN")
    result = _check(plan, wrong_join, ("devices", "directory_users"))
    assert result.reason_code is SemanticConformanceReason.RELATIONSHIP_MISMATCH

    reversed_left = (
        "SELECT d.hostname, u.full_name FROM directory_users u "
        "LEFT JOIN devices d ON u.id = d.assigned_user_id WHERE "
        "(d.compliance_status = 'non_compliant' "
        "OR d.antivirus_status IN ('outdated', 'missing') "
        "OR d.encryption_enabled = false) "
        "AND u.employee_status = 'active'"
    )
    reversed_result = _check(
        plan,
        reversed_left,
        ("devices", "directory_users"),
    )
    assert (
        reversed_result.reason_code
        is SemanticConformanceReason.RELATIONSHIP_MISMATCH
    )

    inner_plan = plan.model_copy(
        update={
            "relationships": (
                SemanticRelationshipIntent(
                    relationship_id="device_assignee",
                    join_type="inner",
                ),
            )
        }
    )
    reordered_inner = reversed_left.replace("LEFT JOIN", "JOIN")
    assert _check(
        inner_plan,
        reordered_inner,
        ("directory_users", "devices"),
    ).valid


def test_missing_wrong_and_extra_relationships_fail_closed() -> None:
    plan = SemanticPlan(
        entity_ids=("devices", "directory_users"),
        concept_ids=(),
        composition_rule_ids=(),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(
            SemanticRelationshipIntent(
                relationship_id="device_assignee",
                join_type="inner",
            ),
        ),
        output_fields=(
            SemanticFieldRef(entity_id="devices", column="hostname"),
            SemanticFieldRef(entity_id="directory_users", column="full_name"),
        ),
        aggregations=(),
        group_by=(),
        having=(),
        order_by=(),
        limit=None,
    )

    missing = _check(
        plan,
        "SELECT d.hostname, u.full_name FROM devices d JOIN directory_users u "
        "ON d.hostname = 'unrelated'",
        ("devices", "directory_users"),
    )
    assert missing.reason_code is SemanticConformanceReason.RELATIONSHIP_MISSING

    wrong_endpoint = _check(
        plan,
        "SELECT d.hostname, u.full_name FROM devices d JOIN directory_users u "
        "ON d.department_id = u.department_id",
        ("devices", "directory_users"),
    )
    assert (
        wrong_endpoint.reason_code
        is SemanticConformanceReason.RELATIONSHIP_MISMATCH
    )

    extra_table = _check(
        plan,
        "SELECT d.hostname, u.full_name FROM devices d JOIN directory_users u "
        "ON d.assigned_user_id = u.id JOIN departments p "
        "ON d.department_id = p.id",
        ("devices", "directory_users", "departments"),
    )
    assert extra_table.reason_code is SemanticConformanceReason.TABLE_MISMATCH


def test_unsupported_sql_shape_fails_closed() -> None:
    result = _check(
        _active_metric_plan(),
        "WITH users AS (SELECT * FROM directory_users) SELECT COUNT(*) FROM users",
        ("directory_users",),
    )
    assert result.valid is False
    assert result.reason_code is SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED


@pytest.mark.parametrize(
    "predicate_sql",
    [
        "account_status <> 'disabled'",
        "account_status != 'disabled'",
        "NOT (account_status = 'disabled')",
        "account_status NOT IN ('disabled')",
    ],
)
def test_not_equals_equivalent_forms(predicate_sql: str) -> None:
    plan = _literal_plan("not_equals", "disabled")
    assert _check(
        plan,
        f"SELECT COUNT(*) FROM directory_users WHERE {predicate_sql}",
        ("directory_users",),
    ).valid


def test_reversed_equality_and_in_or_equivalence() -> None:
    active = SemanticPlan(
        **{
            **_output_plan("directory_users", "id").model_dump(),
            "concept_ids": ("active_directory_account",),
        }
    )
    assert _check(
        active,
        "SELECT id FROM directory_users WHERE 'active' = account_status",
        ("directory_users",),
    ).valid

    open_tickets = SemanticPlan(
        **{
            **_output_plan("support_tickets", "id").model_dump(),
            "concept_ids": ("open_support_ticket",),
        }
    )
    assert _check(
        open_tickets,
        "SELECT id FROM support_tickets WHERE status = 'open' "
        "OR status = 'in_progress'",
        ("support_tickets",),
    ).valid
    narrowed = _check(
        open_tickets,
        "SELECT id FROM support_tickets WHERE status IN ('open')",
        ("support_tickets",),
    )
    assert narrowed.reason_code is SemanticConformanceReason.PREDICATE_CONFLICT


def test_non_compliant_posture_requires_every_or_branch() -> None:
    plan = SemanticPlan(
        **{
            **_output_plan("devices", "hostname").model_dump(),
            "composition_rule_ids": ("non_compliant_device_posture",),
        }
    )
    valid_sql = (
        "SELECT hostname FROM devices WHERE compliance_status = 'non_compliant' "
        "OR antivirus_status IN ('missing', 'outdated') "
        "OR encryption_enabled = false"
    )
    assert _check(plan, valid_sql, ("devices",)).valid

    missing = _check(
        plan,
        "SELECT hostname FROM devices WHERE compliance_status = 'non_compliant' "
        "OR antivirus_status IN ('missing', 'outdated')",
        ("devices",),
    )
    assert missing.reason_code is SemanticConformanceReason.OR_STRUCTURE_MISMATCH
    wrong_and = _check(
        plan,
        "SELECT hostname FROM devices WHERE compliance_status = 'non_compliant' "
        "AND antivirus_status IN ('missing', 'outdated') "
        "AND encryption_enabled = false",
        ("devices",),
    )
    assert wrong_and.reason_code is SemanticConformanceReason.OR_STRUCTURE_MISMATCH


def test_output_alias_is_harmless_but_missing_output_fails() -> None:
    plan = _output_plan("devices", "hostname")
    assert _check(
        plan,
        "SELECT hostname AS device_name FROM devices",
        ("devices",),
    ).valid
    result = _check(plan, "SELECT id FROM devices", ("devices",))
    assert result.reason_code is SemanticConformanceReason.OUTPUT_MISMATCH


def test_count_distinct_sum_grouping_having_and_ordering() -> None:
    plan = SemanticPlan(
        entity_ids=("licenses", "license_assignments"),
        concept_ids=(),
        composition_rule_ids=(),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(
            SemanticRelationshipIntent(
                relationship_id="license_assignment_license",
                join_type="inner",
            ),
        ),
        output_fields=(SemanticFieldRef(entity_id="licenses", column="vendor"),),
        aggregations=(
            SemanticAggregationIntent(
                id="assignment_count",
                function="count",
                field=SemanticFieldRef(
                    entity_id="license_assignments", column="user_id"
                ),
                distinct=True,
            ),
            SemanticAggregationIntent(
                id="monthly_total",
                function="sum",
                field=SemanticFieldRef(
                    entity_id="licenses", column="monthly_cost_usd"
                ),
                distinct=False,
            ),
        ),
        group_by=(SemanticFieldRef(entity_id="licenses", column="vendor"),),
        having=(
            SemanticHavingIntent(
                aggregation_id="assignment_count",
                operator="greater_than",
                value=1,
            ),
        ),
        order_by=(
            SemanticOrderIntent(
                target_kind="aggregation",
                field=None,
                aggregation_id="monthly_total",
                direction="desc",
            ),
            SemanticOrderIntent(
                target_kind="field",
                field=SemanticFieldRef(entity_id="licenses", column="vendor"),
                aggregation_id=None,
                direction="asc",
            ),
        ),
        limit=None,
    )
    sql = (
        "SELECT l.vendor, COUNT(DISTINCT a.user_id) AS assignment_count, "
        "SUM(l.monthly_cost_usd) AS monthly_total "
        "FROM license_assignments a JOIN licenses l ON a.license_id = l.id "
        "GROUP BY l.vendor HAVING COUNT(DISTINCT a.user_id) > 1 "
        "ORDER BY monthly_total DESC, l.vendor ASC"
    )
    assert _check(plan, sql, ("license_assignments", "licenses")).valid

    wrong_order = _check(
        plan,
        sql.replace(
            "ORDER BY monthly_total DESC, l.vendor ASC",
            "ORDER BY l.vendor ASC, monthly_total DESC",
        ),
        ("license_assignments", "licenses"),
    )
    assert wrong_order.reason_code is SemanticConformanceReason.ORDER_BY_MISMATCH
    missing_group = _check(
        plan,
        sql.replace("GROUP BY l.vendor ", ""),
        ("license_assignments", "licenses"),
    )
    assert missing_group.reason_code is SemanticConformanceReason.GROUP_BY_MISMATCH
    missing_having = _check(
        plan,
        sql.replace("HAVING COUNT(DISTINCT a.user_id) > 1 ", ""),
        ("license_assignments", "licenses"),
    )
    assert missing_having.reason_code is SemanticConformanceReason.HAVING_MISMATCH

    wrong_having_operator = _check(
        plan,
        sql.replace(
            "HAVING COUNT(DISTINCT a.user_id) > 1",
            "HAVING COUNT(DISTINCT a.user_id) >= 1",
        ),
        ("license_assignments", "licenses"),
    )
    assert (
        wrong_having_operator.reason_code
        is SemanticConformanceReason.HAVING_MISMATCH
    )
    wrong_direction = _check(
        plan,
        sql.replace("monthly_total DESC", "monthly_total ASC"),
        ("license_assignments", "licenses"),
    )
    assert wrong_direction.reason_code is SemanticConformanceReason.ORDER_BY_MISMATCH
    extra_group = _check(
        plan,
        sql.replace("GROUP BY l.vendor", "GROUP BY l.vendor, l.product_name"),
        ("license_assignments", "licenses"),
    )
    assert extra_group.reason_code is SemanticConformanceReason.GROUP_BY_MISMATCH


def test_aggregation_function_target_distinctness_and_metric_nullability() -> None:
    metric = _active_metric_plan()
    predicates = (
        "account_type = 'human' AND employee_status = 'active' "
        "AND account_status = 'active'"
    )
    unproven_non_nullable_count = _check(
        metric,
        f"SELECT COUNT(id) FROM directory_users WHERE {predicates}",
        ("directory_users",),
    )
    assert (
        unproven_non_nullable_count.reason_code
        is SemanticConformanceReason.AGGREGATION_MISMATCH
    )

    nullable_count = _check(
        metric,
        f"SELECT COUNT(last_login_at) FROM directory_users WHERE {predicates}",
        ("directory_users",),
    )
    assert (
        nullable_count.reason_code
        is SemanticConformanceReason.AGGREGATION_MISMATCH
    )

    wrong_function = _check(
        metric,
        f"SELECT SUM(id) FROM directory_users WHERE {predicates}",
        ("directory_users",),
    )
    assert (
        wrong_function.reason_code
        is SemanticConformanceReason.AGGREGATION_MISMATCH
    )

    count_id = SemanticPlan(
        entity_ids=("directory_users",),
        concept_ids=(),
        composition_rule_ids=(),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(),
        output_fields=(),
        aggregations=(
            SemanticAggregationIntent(
                id="user_count",
                function="count",
                field=SemanticFieldRef(entity_id="directory_users", column="id"),
                distinct=True,
            ),
        ),
        group_by=(),
        having=(),
        order_by=(),
        limit=None,
    )
    assert _check(
        count_id,
        "SELECT COUNT(DISTINCT id) FROM directory_users",
        ("directory_users",),
    ).valid
    wrong_distinct = _check(
        count_id,
        "SELECT COUNT(id) FROM directory_users",
        ("directory_users",),
    )
    assert (
        wrong_distinct.reason_code
        is SemanticConformanceReason.AGGREGATION_MISMATCH
    )
    wrong_target = _check(
        count_id,
        "SELECT COUNT(DISTINCT department_id) FROM directory_users",
        ("directory_users",),
    )
    assert wrong_target.reason_code is SemanticConformanceReason.AGGREGATION_MISMATCH


def test_final_sanitized_sql_and_limit_contract() -> None:
    plan = _output_plan("devices", "hostname")
    candidate = "SELECT hostname FROM devices"
    assert _check(
        plan,
        candidate,
        ("devices",),
        sanitized_sql=f"{candidate} LIMIT 100",
    ).valid

    provider_limit = _check(
        plan,
        "SELECT hostname FROM devices LIMIT 10",
        ("devices",),
    )
    assert provider_limit.reason_code is SemanticConformanceReason.LIMIT_MISMATCH

    requested = plan.model_copy(update={"limit": 10})
    assert _check(
        requested,
        "SELECT hostname FROM devices LIMIT 10",
        ("devices",),
    ).valid
    changed_by_safety = _check(
        requested,
        "SELECT hostname FROM devices LIMIT 10",
        ("devices",),
        sanitized_sql="SELECT hostname FROM devices LIMIT 5",
    )
    assert changed_by_safety.reason_code is SemanticConformanceReason.LIMIT_MISMATCH

    final_mismatch = _check(
        plan,
        candidate,
        ("devices",),
        sanitized_sql="SELECT id FROM devices LIMIT 100",
    )
    assert final_mismatch.reason_code is SemanticConformanceReason.OUTPUT_MISMATCH


@pytest.mark.parametrize(
    ("concept_id", "predicate_sql"),
    [
        (
            "open_support_ticket_older_than_30_days",
            "status IN ('open', 'in_progress') AND opened_at < NOW() - INTERVAL '30 days'",
        ),
        (
            "failed_login_within_30_days",
            "event_type = 'failed' AND occurred_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'",
        ),
        (
            "stale_device",
            "last_seen_at IS NULL OR last_seen_at < CURRENT_TIMESTAMP - INTERVAL '30 days'",
        ),
    ],
)
def test_temporal_predicate_forms(concept_id: str, predicate_sql: str) -> None:
    entity_id = {
        "open_support_ticket_older_than_30_days": "support_tickets",
        "failed_login_within_30_days": "login_events",
        "stale_device": "devices",
    }[concept_id]
    output_column = {
        "support_tickets": "id",
        "login_events": "id",
        "devices": "id",
    }[entity_id]
    plan = SemanticPlan(
        **{
            **_output_plan(entity_id, output_column).model_dump(),
            "concept_ids": (concept_id,),
        }
    )
    assert _check(
        plan,
        f"SELECT {output_column} FROM {entity_id} WHERE {predicate_sql}",
        (entity_id,),
    ).valid


@pytest.mark.parametrize(
    "sql",
    [
        "WITH d AS (SELECT id FROM devices) SELECT id FROM d",
        "SELECT id FROM devices WHERE id IN (SELECT device_id FROM login_events)",
        "SELECT id, ROW_NUMBER() OVER (ORDER BY id) FROM devices",
        "SELECT id FROM devices UNION SELECT id FROM devices",
        "SELECT d.id FROM devices d JOIN LATERAL (SELECT 1) x ON true",
        "SELECT a.id FROM devices a JOIN devices b ON a.id = b.id",
        "SELECT d.id FROM devices d CROSS JOIN departments p",
        "SELECT d.id FROM devices d RIGHT JOIN departments p ON d.department_id = p.id",
        "SELECT d.id FROM devices d FULL JOIN departments p ON d.department_id = p.id",
    ],
)
def test_unsupported_v1_shapes_fail_closed(sql: str) -> None:
    result = _check(_output_plan("devices", "id"), sql, ("devices",))
    assert result.valid is False
    assert result.reason_code in {
        SemanticConformanceReason.SQL_SHAPE_UNSUPPORTED,
        SemanticConformanceReason.TABLE_MISMATCH,
    }


def _active_metric_plan() -> SemanticPlan:
    return SemanticPlan(
        entity_ids=("directory_users",),
        concept_ids=(),
        composition_rule_ids=(),
        metric_id="active_human_users",
        distinct=False,
        literal_filters=(),
        relationships=(),
        output_fields=(),
        aggregations=(),
        group_by=(),
        having=(),
        order_by=(),
        limit=None,
    )


def _check(
    plan: SemanticPlan,
    sql: str,
    tables: tuple[str, ...],
    *,
    sanitized_sql: str | None = None,
):
    domain_pack = load_it_operations_domain_pack()
    schema_context = {
        "allowed_tables": [table.name for table in domain_pack.tables],
        "allowed_columns": {
            table.name: [column.name for column in table.columns]
            for table in domain_pack.tables
        },
        "tables": [],
    }
    projection = build_semantic_catalog_projection(
        domain_pack.semantic_catalog,
        _question_for_plan(plan),
        schema_context,
        {
            "scope_type": "global",
            "has_global_scope": True,
            "scope_reference_resolved": True,
        },
    )
    validated = validate_semantic_plan(
        plan,
        domain_pack=domain_pack,
        projection=projection,
        schema_context=schema_context,
        scope_reference_resolved=True,
    )
    safety = SQLValidationResult(
        valid=True,
        sanitized_sql=sanitized_sql or sql,
        referenced_tables=list(tables),
    )
    return check_semantic_conformance(
        plan=validated,
        candidate_sql=sql,
        safety_result=safety,
        domain_pack=domain_pack,
        schema_context=schema_context,
    )


def _output_plan(entity_id: str, column: str) -> SemanticPlan:
    return SemanticPlan(
        entity_ids=(entity_id,),
        concept_ids=(),
        composition_rule_ids=(),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(),
        output_fields=(SemanticFieldRef(entity_id=entity_id, column=column),),
        aggregations=(),
        group_by=(),
        having=(),
        order_by=(),
        limit=None,
    )


def _literal_plan(operator: str, value: str) -> SemanticPlan:
    return SemanticPlan.model_validate(
        {
            **_active_metric_plan().model_dump(),
            "metric_id": None,
            "literal_filters": (
                {
                    "field": {
                        "entity_id": "directory_users",
                        "column": "account_status",
                    },
                    "operator": operator,
                    "value": value,
                },
            ),
            "aggregations": (
                {
                    "id": "row_count",
                    "function": "count",
                    "field": None,
                    "distinct": False,
                },
            ),
        }
    )
def _question_for_plan(plan: SemanticPlan) -> str:
    if plan.metric_id:
        return "How many active users are there?"
    if plan.literal_filters:
        return "How many users are not disabled?"
    entity_words = " and ".join(
        entity_id.replace("_", " ") for entity_id in plan.entity_ids
    )
    if "non_compliant_device_posture" in plan.composition_rule_ids:
        return f"Show non-compliant devices with {entity_words}."
    return f"Show {entity_words}."
