from __future__ import annotations

from typing import Any

import pytest

from app.query_engine.domain_pack import DomainPack
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import (
    SemanticPredicateOperator,
    build_semantic_catalog_projection,
)
from app.query_engine.semantic_conformance import check_semantic_conformance
from app.query_engine.semantic_plan import (
    EntitySemanticPredicate,
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticHavingIntent,
    SemanticLiteralFilter,
    SemanticOrderIntent,
    SemanticPlan,
    SemanticRelationshipIntent,
    ValidatedSemanticPlan,
    validate_semantic_plan,
)
from app.query_engine.sql_renderer import (
    SemanticSQLRenderError,
    render_validated_semantic_plan,
)
from app.query_engine.sql_validator import validate_sql


DOMAIN_PACK = load_it_operations_domain_pack()


def _field(entity_id: str, column: str) -> SemanticFieldRef:
    return SemanticFieldRef(entity_id=entity_id, column=column)


def _predicate(
    entity_id: str,
    column: str,
    operator: SemanticPredicateOperator,
    value: Any,
) -> EntitySemanticPredicate:
    return EntitySemanticPredicate(
        entity_id=entity_id,
        column=column,
        operator=operator,
        value=value,
    )


def _literal(
    entity_id: str,
    column: str,
    operator: str,
    value: Any,
) -> SemanticLiteralFilter:
    return SemanticLiteralFilter.model_validate(
        {
            "field": {"entity_id": entity_id, "column": column},
            "operator": operator,
            "value": value,
        }
    )


def _relationship(
    relationship_id: str,
    join_type: str,
) -> SemanticRelationshipIntent:
    return SemanticRelationshipIntent.model_validate(
        {"relationship_id": relationship_id, "join_type": join_type}
    )


def _aggregation(
    aggregation_id: str,
    function: str,
    field: SemanticFieldRef | None = None,
    *,
    distinct: bool = False,
) -> SemanticAggregationIntent:
    return SemanticAggregationIntent.model_validate(
        {
            "id": aggregation_id,
            "function": function,
            "field": field,
            "distinct": distinct,
        }
    )


def test_single_entity_detail_multiple_fields_and_distinct_render_exactly() -> None:
    plan = _validated(
        _plan(
            entity_ids=("directory_users",),
            distinct=True,
            output_fields=(
                _field("directory_users", "full_name"),
                _field("directory_users", "email"),
            ),
        )
    )

    assert _render(plan) == (
        "SELECT DISTINCT directory_users.full_name, directory_users.email "
        "FROM directory_users"
    )


def test_raw_semantic_plan_is_not_accepted() -> None:
    raw_plan = _plan(
        entity_ids=("directory_users",),
        output_fields=(_field("directory_users", "id"),),
    )

    with pytest.raises(TypeError, match="ValidatedSemanticPlan"):
        render_validated_semantic_plan(raw_plan, DOMAIN_PACK)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        (
            _predicate(
                "directory_users",
                "account_status",
                SemanticPredicateOperator.EQUALS,
                "active",
            ),
            "directory_users.account_status = 'active'",
        ),
        (
            _predicate(
                "support_tickets",
                "status",
                SemanticPredicateOperator.IN,
                ("open", "in_progress"),
            ),
            "support_tickets.status IN ('open', 'in_progress')",
        ),
        (
            _predicate(
                "support_tickets",
                "opened_at",
                SemanticPredicateOperator.OLDER_THAN_DAYS,
                30,
            ),
            "support_tickets.opened_at < CURRENT_TIMESTAMP - INTERVAL '30 days'",
        ),
        (
            _predicate(
                "login_events",
                "occurred_at",
                SemanticPredicateOperator.WITHIN_LAST_DAYS,
                30,
            ),
            "login_events.occurred_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'",
        ),
        (
            _predicate(
                "devices",
                "last_seen_at",
                SemanticPredicateOperator.IS_NULL_OR_OLDER_THAN_DAYS,
                30,
            ),
            "(devices.last_seen_at IS NULL OR devices.last_seen_at < "
            "CURRENT_TIMESTAMP - INTERVAL '30 days')",
        ),
    ],
)
def test_concept_predicate_operators_render_deterministically(
    predicate: EntitySemanticPredicate,
    expected: str,
) -> None:
    plan = _validated(
        _plan(
            entity_ids=(predicate.entity_id,),
            output_fields=(_field(predicate.entity_id, "id"),),
        ),
        predicates=(predicate,),
    )

    assert _render(plan).endswith(f"WHERE {expected}")


@pytest.mark.parametrize(
    ("literal_filter", "expected"),
    [
        (
            _literal("devices", "hostname", "equals", "workstation-1"),
            "devices.hostname = 'workstation-1'",
        ),
        (
            _literal("devices", "hostname", "not_equals", "retired-1"),
            "devices.hostname <> 'retired-1'",
        ),
        (
            _literal("devices", "hostname", "in", ("one", "two")),
            "devices.hostname IN ('one', 'two')",
        ),
        (
            _literal("devices", "hostname", "not_in", ("one", "two")),
            "devices.hostname NOT IN ('one', 'two')",
        ),
        (
            _literal("devices", "hostname", "equals", "O'Reilly"),
            "devices.hostname = 'O''Reilly'",
        ),
    ],
)
def test_literal_filter_operators_and_escaping(
    literal_filter: SemanticLiteralFilter,
    expected: str,
) -> None:
    plan = _validated(
        _plan(
            entity_ids=("devices",),
            literal_filters=(literal_filter,),
            output_fields=(_field("devices", "id"),),
        )
    )

    assert _render(plan).endswith(f"WHERE {expected}")


def test_or_composition_preserves_branch_structure() -> None:
    plan = _validated(
        _plan(
            entity_ids=("devices",),
            output_fields=(_field("devices", "hostname"),),
        ),
        predicates=(
            _predicate(
                "devices",
                "device_type",
                SemanticPredicateOperator.EQUALS,
                "endpoint",
            ),
        ),
        or_groups=(
            (
                (
                    _predicate(
                        "devices",
                        "compliance_status",
                        SemanticPredicateOperator.EQUALS,
                        "non_compliant",
                    ),
                ),
                (
                    _predicate(
                        "devices",
                        "antivirus_status",
                        SemanticPredicateOperator.IN,
                        ("missing", "outdated"),
                    ),
                    _predicate(
                        "devices",
                        "encryption_enabled",
                        SemanticPredicateOperator.EQUALS,
                        False,
                    ),
                ),
            ),
        ),
    )

    assert _render(plan) == (
        "SELECT devices.hostname FROM devices "
        "WHERE devices.device_type = 'endpoint' AND "
        "((devices.compliance_status = 'non_compliant') OR "
        "(devices.antivirus_status IN ('missing', 'outdated') AND "
        "devices.encryption_enabled = FALSE))"
    )


@pytest.mark.parametrize(
    ("join_type", "join_sql"),
    [
        (
            "inner",
            "INNER JOIN directory_users ON devices.assigned_user_id = "
            "directory_users.id",
        ),
        (
            "left",
            "LEFT JOIN directory_users ON devices.assigned_user_id = "
            "directory_users.id",
        ),
    ],
)
def test_single_join_preserves_selected_relationship_and_type(
    join_type: str,
    join_sql: str,
) -> None:
    plan = _validated(
        _plan(
            entity_ids=("devices", "directory_users"),
            relationships=(_relationship("device_assignee", join_type),),
            output_fields=(
                _field("devices", "hostname"),
                _field("directory_users", "full_name"),
            ),
        )
    )

    sql = _render(plan)

    assert f"FROM devices {join_sql}" in sql
    if join_type == "left":
        assert sql.index("FROM devices") < sql.index("LEFT JOIN directory_users")


def test_multi_entity_tree_uses_executable_canonical_traversal() -> None:
    plan = _validated(
        _plan(
            entity_ids=("directory_users", "license_assignments", "licenses"),
            relationships=(
                _relationship("license_assignment_user", "inner"),
                _relationship("license_assignment_license", "inner"),
            ),
            output_fields=(
                _field("directory_users", "full_name"),
                _field("licenses", "product_name"),
            ),
        )
    )

    assert _render(plan) == (
        "SELECT directory_users.full_name, licenses.product_name "
        "FROM directory_users "
        "INNER JOIN license_assignments ON license_assignments.user_id = "
        "directory_users.id "
        "INNER JOIN licenses ON license_assignments.license_id = licenses.id"
    )


def test_same_validated_plan_always_renders_identical_sql() -> None:
    plan = _validated(
        _plan(
            entity_ids=("departments", "devices", "directory_users"),
            relationships=(
                _relationship("device_assignee", "inner"),
                _relationship("device_department", "inner"),
            ),
            output_fields=(
                _field("departments", "name"),
                _field("directory_users", "full_name"),
            ),
        )
    )

    assert {_render(plan) for _ in range(20)} == {_render(plan)}


def test_revised_v2_hard_010_is_representable_by_current_plan_algebra() -> None:
    plan = _validated(
        _plan(
            entity_ids=("departments", "devices", "directory_users"),
            concept_ids=("inactive_directory_user", "risky_device"),
            relationships=(
                _relationship("device_department", "inner"),
                _relationship("directory_user_department", "inner"),
            ),
            output_fields=(
                _field("departments", "id"),
                _field("departments", "name"),
            ),
            aggregations=(
                _aggregation(
                    "risky_device_count",
                    "count",
                    _field("devices", "id"),
                    distinct=True,
                ),
                _aggregation(
                    "inactive_user_count",
                    "count",
                    _field("directory_users", "id"),
                    distinct=True,
                ),
            ),
            group_by=(
                _field("departments", "id"),
                _field("departments", "name"),
            ),
            order_by=(
                SemanticOrderIntent(
                    target_kind="aggregation",
                    field=None,
                    aggregation_id="risky_device_count",
                    direction="desc",
                ),
                SemanticOrderIntent(
                    target_kind="aggregation",
                    field=None,
                    aggregation_id="inactive_user_count",
                    direction="desc",
                ),
            ),
        ),
        predicates=(
            _predicate(
                "devices",
                "compliance_status",
                SemanticPredicateOperator.EQUALS,
                "non_compliant",
            ),
            _predicate(
                "directory_users",
                "last_login_at",
                SemanticPredicateOperator.IS_NULL_OR_OLDER_THAN_DAYS,
                90,
            ),
        ),
    )

    sql = _render(plan)
    assert "LEFT JOIN" not in sql
    assert "INNER JOIN devices" in sql
    assert "INNER JOIN directory_users" in sql
    assert "WHERE" in sql

    schema_context = _schema_context(DOMAIN_PACK)
    safety = validate_sql(sql, schema_context)
    assert safety.valid, safety.reason
    conformance = check_semantic_conformance(
        plan=plan,
        candidate_sql=sql,
        safety_result=safety,
        domain_pack=DOMAIN_PACK,
        schema_context=schema_context,
    )
    assert conformance.valid, conformance.reason_code


def test_revised_v2_hard_007_validates_renders_and_conforms() -> None:
    question = (
        "Count distinct non-compliant devices assigned to inactive human users by "
        "user ID, ordered by device count descending and then user ID ascending."
    )
    plan = _plan(
        entity_ids=("directory_users", "devices"),
        concept_ids=("inactive_human_directory_user",),
        composition_rule_ids=("non_compliant_device_posture",),
        relationships=(_relationship("device_assignee", "inner"),),
        output_fields=(_field("directory_users", "id"),),
        aggregations=(
            _aggregation(
                "non_compliant_device_count",
                "count",
                _field("devices", "id"),
                distinct=True,
            ),
        ),
        group_by=(_field("directory_users", "id"),),
        order_by=(
            SemanticOrderIntent(
                target_kind="aggregation",
                field=None,
                aggregation_id="non_compliant_device_count",
                direction="desc",
            ),
            SemanticOrderIntent(
                target_kind="field",
                field=_field("directory_users", "id"),
                aggregation_id=None,
                direction="asc",
            ),
        ),
    )
    schema_context = _schema_context(DOMAIN_PACK)
    projection = build_semantic_catalog_projection(
        DOMAIN_PACK.semantic_catalog,
        question,
        schema_context,
        {
            "scope_type": "global",
            "has_global_scope": True,
            "scope_reference_resolved": True,
        },
    )
    validated = validate_semantic_plan(
        plan,
        domain_pack=DOMAIN_PACK,
        projection=projection,
        schema_context=schema_context,
        scope_reference_resolved=True,
    )

    sql = _render(validated)
    assert "LEFT JOIN" not in sql
    assert "FROM devices INNER JOIN directory_users" in sql
    assert "COUNT(DISTINCT devices.id)" in sql

    safety = validate_sql(sql, schema_context)
    assert safety.valid, safety.reason
    conformance = check_semantic_conformance(
        plan=validated,
        candidate_sql=sql,
        safety_result=safety,
        domain_pack=DOMAIN_PACK,
        schema_context=schema_context,
    )
    assert conformance.valid, conformance.reason_code


def test_unsupported_left_join_tree_orientation_fails_closed() -> None:
    plan = _validated(
        _plan(
            entity_ids=("devices", "directory_users", "login_events"),
            relationships=(
                _relationship("device_assignee", "left"),
                _relationship("login_event_user", "left"),
            ),
            output_fields=(
                _field("devices", "hostname"),
                _field("login_events", "id"),
            ),
        )
    )

    with pytest.raises(SemanticSQLRenderError) as exc_info:
        _render(plan)

    assert exc_info.value.reason == "left_join_orientation_unsupported"
    assert str(exc_info.value) == "The validated semantic plan cannot be rendered."


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [
        (_aggregation("row_count", "count"), "COUNT(*) AS row_count"),
        (
            _aggregation(
                "user_count",
                "count",
                _field("directory_users", "id"),
            ),
            "COUNT(directory_users.id) AS user_count",
        ),
        (
            _aggregation(
                "user_count",
                "count",
                _field("directory_users", "id"),
                distinct=True,
            ),
            "COUNT(DISTINCT directory_users.id) AS user_count",
        ),
        (
            _aggregation(
                "monthly_cost",
                "sum",
                _field("licenses", "monthly_cost"),
            ),
            "SUM(licenses.monthly_cost) AS monthly_cost",
        ),
    ],
)
def test_supported_aggregations_render_exactly(
    aggregation: SemanticAggregationIntent,
    expected: str,
) -> None:
    entity_id = aggregation.field.entity_id if aggregation.field else "directory_users"
    plan = _validated(
        _plan(entity_ids=(entity_id,), aggregations=(aggregation,))
    )

    assert _render(plan) == f"SELECT {expected} FROM {entity_id}"


def test_validated_single_entity_count_star_renders_from_intended_entity() -> None:
    question = "How many devices are there?"
    schema_context = _schema_context(DOMAIN_PACK)
    projection = build_semantic_catalog_projection(
        DOMAIN_PACK.semantic_catalog,
        question,
        schema_context,
        {
            "scope_type": "global",
            "has_global_scope": True,
            "scope_reference_resolved": True,
        },
    )
    validated = validate_semantic_plan(
        _plan(
            entity_ids=("devices",),
            aggregations=(_aggregation("row_count", "count"),),
        ),
        domain_pack=DOMAIN_PACK,
        projection=projection,
        schema_context=schema_context,
        scope_reference_resolved=True,
    )

    assert _render(validated) == "SELECT COUNT(*) AS row_count FROM devices"


def test_group_having_order_and_limit_render_from_plan() -> None:
    aggregation = _aggregation(
        "failed_login_count",
        "count",
        _field("login_events", "id"),
    )
    plan = _validated(
        _plan(
            entity_ids=("directory_users", "login_events"),
            relationships=(_relationship("login_event_user", "inner"),),
            output_fields=(_field("directory_users", "full_name"),),
            aggregations=(aggregation,),
            group_by=(_field("directory_users", "full_name"),),
            having=(
                SemanticHavingIntent(
                    aggregation_id="failed_login_count",
                    operator="greater_than",
                    value=5,
                ),
            ),
            order_by=(
                SemanticOrderIntent(
                    target_kind="field",
                    field=_field("directory_users", "full_name"),
                    aggregation_id=None,
                    direction="asc",
                ),
                SemanticOrderIntent(
                    target_kind="aggregation",
                    field=None,
                    aggregation_id="failed_login_count",
                    direction="desc",
                ),
            ),
            limit=25,
        )
    )

    assert _render(plan) == (
        "SELECT directory_users.full_name, COUNT(login_events.id) AS "
        "failed_login_count FROM directory_users "
        "INNER JOIN login_events ON login_events.user_id = directory_users.id "
        "GROUP BY directory_users.full_name "
        "HAVING COUNT(login_events.id) > 5 "
        "ORDER BY directory_users.full_name ASC, COUNT(login_events.id) DESC "
        "LIMIT 25"
    )


def test_canonical_scalar_metric_uses_validated_metric_contract() -> None:
    plan = _validated(
        _plan(entity_ids=("directory_users",), metric_id="active_human_users"),
        predicates=(
            _predicate(
                "directory_users",
                "account_status",
                SemanticPredicateOperator.EQUALS,
                "active",
            ),
            _predicate(
                "directory_users",
                "account_type",
                SemanticPredicateOperator.EQUALS,
                "human",
            ),
            _predicate(
                "directory_users",
                "employee_status",
                SemanticPredicateOperator.EQUALS,
                "active",
            ),
        ),
        metric_function="count",
    )

    assert _render(plan) == (
        "SELECT COUNT(*) AS active_human_users FROM directory_users "
        "WHERE directory_users.account_status = 'active' AND "
        "directory_users.account_type = 'human' AND "
        "directory_users.employee_status = 'active'"
    )


@pytest.mark.parametrize("case", ["detail", "or", "join", "aggregate", "metric"])
def test_representative_rendered_sql_passes_safety_and_conformance(
    case: str,
) -> None:
    plan = _conformance_case(case)
    sql = _render(plan)
    schema_context = _schema_context(DOMAIN_PACK)
    safety = validate_sql(sql, schema_context)

    assert safety.valid, safety.reason
    conformance = check_semantic_conformance(
        plan=plan,
        candidate_sql=sql,
        safety_result=safety,
        domain_pack=DOMAIN_PACK,
        schema_context=schema_context,
    )
    assert conformance.valid, conformance.reason_code


def _conformance_case(case: str) -> ValidatedSemanticPlan:
    if case == "detail":
        return _validated(
            _plan(
                entity_ids=("devices",),
                distinct=True,
                output_fields=(
                    _field("devices", "hostname"),
                    _field("devices", "os"),
                ),
                literal_filters=(
                    _literal("devices", "hostname", "equals", "O'Reilly"),
                ),
                order_by=(
                    SemanticOrderIntent(
                        target_kind="field",
                        field=_field("devices", "hostname"),
                        aggregation_id=None,
                        direction="asc",
                    ),
                ),
                limit=10,
            )
        )
    if case == "or":
        return _validated(
            _plan(
                entity_ids=("devices",),
                composition_rule_ids=("non_compliant_device_posture",),
                output_fields=(_field("devices", "hostname"),),
            ),
            or_groups=(
                (
                    (
                        _predicate(
                            "devices",
                            "compliance_status",
                            SemanticPredicateOperator.EQUALS,
                            "non_compliant",
                        ),
                    ),
                    (
                        _predicate(
                            "devices",
                            "antivirus_status",
                            SemanticPredicateOperator.IN,
                            ("missing", "outdated"),
                        ),
                    ),
                    (
                        _predicate(
                            "devices",
                            "encryption_enabled",
                            SemanticPredicateOperator.EQUALS,
                            False,
                        ),
                    ),
                ),
            ),
        )
    if case == "join":
        return _validated(
            _plan(
                entity_ids=("devices", "directory_users"),
                relationships=(_relationship("device_assignee", "left"),),
                output_fields=(
                    _field("devices", "hostname"),
                    _field("directory_users", "full_name"),
                ),
            )
        )
    if case == "aggregate":
        aggregation = _aggregation(
            "failed_login_count",
            "count",
            _field("login_events", "id"),
        )
        return _validated(
            _plan(
                entity_ids=("directory_users", "login_events"),
                relationships=(_relationship("login_event_user", "inner"),),
                output_fields=(_field("directory_users", "full_name"),),
                aggregations=(aggregation,),
                group_by=(_field("directory_users", "full_name"),),
                having=(
                    SemanticHavingIntent(
                        aggregation_id="failed_login_count",
                        operator="greater_than",
                        value=5,
                    ),
                ),
                order_by=(
                    SemanticOrderIntent(
                        target_kind="aggregation",
                        field=None,
                        aggregation_id="failed_login_count",
                        direction="desc",
                    ),
                ),
            )
        )
    if case == "metric":
        return _validated(
            _plan(entity_ids=("directory_users",), metric_id="active_human_users"),
            predicates=(
                _predicate(
                    "directory_users",
                    "account_status",
                    SemanticPredicateOperator.EQUALS,
                    "active",
                ),
                _predicate(
                    "directory_users",
                    "account_type",
                    SemanticPredicateOperator.EQUALS,
                    "human",
                ),
                _predicate(
                    "directory_users",
                    "employee_status",
                    SemanticPredicateOperator.EQUALS,
                    "active",
                ),
            ),
            metric_function="count",
        )
    raise AssertionError(f"Unknown case: {case}")


def _render(plan: ValidatedSemanticPlan) -> str:
    return render_validated_semantic_plan(plan, DOMAIN_PACK)


def _validated(
    plan: SemanticPlan,
    *,
    predicates: tuple[EntitySemanticPredicate, ...] = (),
    or_groups: tuple[
        tuple[tuple[EntitySemanticPredicate, ...], ...], ...
    ] = (),
    metric_function: str | None = None,
) -> ValidatedSemanticPlan:
    return ValidatedSemanticPlan(
        plan=plan,
        effective_concept_ids=(),
        effective_predicates=predicates,
        rule_or_predicate_groups=or_groups,
        rule_all_of_concept_ids=(),
        rule_or_concept_groups=(),
        metric_aggregation_function=metric_function,
    )


def _plan(**changes: Any) -> SemanticPlan:
    values: dict[str, Any] = {
        "entity_ids": (),
        "concept_ids": (),
        "composition_rule_ids": (),
        "metric_id": None,
        "distinct": False,
        "literal_filters": (),
        "relationships": (),
        "output_fields": (),
        "aggregations": (),
        "group_by": (),
        "having": (),
        "order_by": (),
        "limit": None,
    }
    values.update(changes)
    return SemanticPlan.model_validate(values)


def _schema_context(domain_pack: DomainPack) -> dict[str, Any]:
    tables = [
        {
            "name": table_name,
            "scope_column": domain_pack.table(table_name).scope_column,
            "columns": [
                {
                    "name": column.name,
                    "data_type": column.data_type,
                    "description": column.description,
                    "nullable": column.nullable,
                }
                for column in domain_pack.table(table_name).columns
            ],
            "resource": {
                "resource_type": "table",
                "schema_name": "public",
                "table_name": table_name,
                "sensitivity_level": "scoped_restricted",
                "scope_type": domain_pack.table(table_name).scope_type,
                "scope_column": domain_pack.table(table_name).scope_column,
                "is_queryable": True,
                "llm_exposure_level": "aggregate_safe",
            },
        }
        for table_name in domain_pack.allowed_resource_table_names
    ]
    return {
        "allowed_tables": list(domain_pack.allowed_resource_table_names),
        "allowed_columns": {
            table_name: sorted(domain_pack.table(table_name).columns_by_name)
            for table_name in domain_pack.allowed_resource_table_names
        },
        "tables": tables,
    }
