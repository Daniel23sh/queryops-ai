from __future__ import annotations

from typing import Literal

import pytest
from pydantic import ValidationError

from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticHavingIntent,
    SemanticLiteralFilter,
    SemanticOrderIntent,
    SemanticPlan,
    SemanticPlanValidationError,
    SemanticRelationshipIntent,
    validate_semantic_plan,
)


def test_valid_simple_plan_preserves_order_priority() -> None:
    plan = _plan(
        entity_ids=("devices",),
        output_fields=(
            _field("devices", "hostname"),
            _field("devices", "os"),
        ),
        order_by=(
            _order("devices", "os", "desc"),
            _order("devices", "hostname", "asc"),
        ),
    )

    validated = _validate(plan, "Show devices by operating system and hostname.")

    assert validated.plan.order_by == plan.order_by
    assert validated.effective_predicates == ()


def test_canonical_metric_is_mandatory_for_exact_active_users_reference() -> None:
    plan = _plan(entity_ids=("directory_users",), metric_id="active_human_users")
    validated = _validate(plan, "How many active users are there?")

    assert {
        (item.entity_id, item.column, item.operator.value, item.value)
        for item in validated.effective_predicates
    } == {
        ("directory_users", "account_type", "equals", "human"),
        ("directory_users", "employee_status", "equals", "active"),
        ("directory_users", "account_status", "equals", "active"),
    }

    weaker = _plan(
        entity_ids=("directory_users",),
        concept_ids=("active_directory_account",),
        aggregations=(_count(),),
    )
    with pytest.raises(
        SemanticPlanValidationError,
        match="semantic plan is invalid",
    ) as exc_info:
        _validate(weaker, "How many active users are there?")
    assert exc_info.value.reason == "mandatory_metric_missing"


def test_v1_canonical_metric_rejects_grouped_or_ranked_shapes() -> None:
    metric = _plan(
        entity_ids=("directory_users",),
        metric_id="active_human_users",
    )
    grouped = metric.model_copy(
        update={
            "output_fields": (_field("directory_users", "employee_status"),),
            "group_by": (_field("directory_users", "employee_status"),),
        }
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(grouped, "Show active users by employee status.")
    assert exc_info.value.reason == "metric_shape_unsupported"

    limited = metric.model_copy(update={"limit": 1})
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(limited, "How many active users are there?")
    assert exc_info.value.reason == "metric_shape_unsupported"


def test_literal_not_disabled_is_not_forced_to_active_users_metric() -> None:
    plan = _plan(
        entity_ids=("directory_users",),
        literal_filters=(
            SemanticLiteralFilter(
                field=_field("directory_users", "account_status"),
                operator="not_equals",
                value="disabled",
            ),
        ),
        aggregations=(_count(),),
    )

    validated = _validate(plan, "How many users are not disabled?")

    assert validated.plan.metric_id is None
    assert validated.effective_predicates == ()


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"entity_ids": ("missing_entity",)}, "entity_not_candidate"),
        ({"concept_ids": ("missing_concept",)}, "concept_not_candidate"),
        ({"metric_id": "missing_metric"}, "metric_not_candidate"),
        (
            {
                "relationships": (
                    SemanticRelationshipIntent(
                        relationship_id="missing_relationship",
                        join_type="inner",
                    ),
                )
            },
            "relationship_not_candidate",
        ),
    ],
)
def test_unknown_or_non_candidate_catalog_ids_fail_closed(
    change: dict[str, object],
    reason: str,
) -> None:
    plan = _plan(entity_ids=("devices",), output_fields=(_field("devices", "id"),))
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(plan.model_copy(update=change), "Show devices.")
    assert exc_info.value.reason == reason


def test_unauthorized_entity_and_column_fail_closed() -> None:
    plan = _plan(
        entity_ids=("devices",),
        output_fields=(_field("devices", "hostname"),),
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(
            plan,
            "Show devices.",
            allowed_tables=("directory_users",),
        )
    assert exc_info.value.reason == "entity_not_candidate"


def test_invalid_literal_value_type_and_known_enum_fail_closed() -> None:
    wrong_type = _plan(
        entity_ids=("devices",),
        literal_filters=(
            SemanticLiteralFilter(
                field=_field("devices", "encryption_enabled"),
                operator="equals",
                value="true",
            ),
        ),
        output_fields=(_field("devices", "id"),),
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(wrong_type, "Show devices with encryption state true.")
    assert exc_info.value.reason == "literal_type_invalid"

    unknown_enum = _plan(
        entity_ids=("devices",),
        literal_filters=(
            SemanticLiteralFilter(
                field=_field("devices", "compliance_status"),
                operator="equals",
                value="invented",
            ),
        ),
        output_fields=(_field("devices", "id"),),
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(unknown_enum, "Show devices with invented compliance state.")
    assert exc_info.value.reason == "literal_value_not_known"


def test_duplicate_ids_and_relationships_fail_closed() -> None:
    duplicate_entity = _plan(
        entity_ids=("devices", "devices"),
        output_fields=(_field("devices", "id"),),
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(duplicate_entity, "Show devices.")
    assert exc_info.value.reason == "duplicate_entity"

    duplicate_relationship = _plan(
        entity_ids=("devices", "directory_users"),
        concept_ids=("non_compliant_device", "active_employee"),
        relationships=(
            _relationship("device_assignee", "left"),
            _relationship("device_assignee", "left"),
        ),
        output_fields=(_field("devices", "hostname"),),
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(
            duplicate_relationship,
            "Which active employees have non-compliant devices?",
        )
    assert exc_info.value.reason == "duplicate_relationship"


def test_entity_qualified_predicate_conflicts_do_not_cross_entities() -> None:
    plan = _plan(
        entity_ids=("devices", "directory_users"),
        literal_filters=(
            SemanticLiteralFilter(
                field=_field("devices", "department_id"),
                operator="equals",
                value="department-a",
            ),
            SemanticLiteralFilter(
                field=_field("directory_users", "department_id"),
                operator="not_equals",
                value="department-a",
            ),
        ),
        relationships=(_relationship("device_assignee", "left"),),
        output_fields=(_field("devices", "hostname"),),
    )

    validated = _validate(
        plan,
        "Show devices and directory users.",
        scope_reference_resolved=False,
    )
    assert len(validated.plan.literal_filters) == 2


def test_same_entity_contradictory_predicates_fail() -> None:
    plan = _plan(
        entity_ids=("directory_users",),
        concept_ids=("active_directory_account",),
        literal_filters=(
            SemanticLiteralFilter(
                field=_field("directory_users", "account_status"),
                operator="equals",
                value="disabled",
            ),
        ),
        output_fields=(_field("directory_users", "id"),),
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(plan, "Show active accounts that are disabled.")
    assert exc_info.value.reason == "predicate_contradiction"


def test_valid_relationship_tree_and_invalid_graphs() -> None:
    valid = _plan(
        entity_ids=("devices", "directory_users", "departments"),
        relationships=(
            _relationship("device_assignee", "left"),
            _relationship("directory_user_department", "inner"),
        ),
        output_fields=(_field("devices", "hostname"),),
    )
    assert _validate(valid, "Show devices, directory users, and departments.")

    disconnected = valid.model_copy(
        update={"relationships": (_relationship("device_assignee", "left"),)}
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(disconnected, "Show devices, directory users, and departments.")
    assert exc_info.value.reason == "relationship_graph_disconnected"

    cyclic = valid.model_copy(
        update={
            "relationships": (
                _relationship("device_assignee", "left"),
                _relationship("directory_user_department", "inner"),
                _relationship("device_department", "inner"),
            )
        }
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(cyclic, "Show devices, directory users, and departments.")
    assert exc_info.value.reason == "relationship_graph_cycle"


def test_grouping_having_and_order_references_are_validated() -> None:
    aggregation = _count()
    valid = _plan(
        entity_ids=("support_tickets",),
        output_fields=(_field("support_tickets", "priority"),),
        aggregations=(aggregation,),
        group_by=(_field("support_tickets", "priority"),),
        having=(
            SemanticHavingIntent(
                aggregation_id="row_count",
                operator="greater_than",
                value=2,
            ),
        ),
        order_by=(
            SemanticOrderIntent(
                target_kind="aggregation",
                field=None,
                aggregation_id="row_count",
                direction="desc",
            ),
        ),
    )
    assert _validate(valid, "Show support tickets by priority with more than two.")

    missing_group = valid.model_copy(update={"group_by": ()})
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(missing_group, "Show support tickets by priority with more than two.")
    assert exc_info.value.reason == "group_by_incomplete"

    missing_aggregate = valid.model_copy(
        update={
            "having": (
                SemanticHavingIntent(
                    aggregation_id="missing",
                    operator="greater_than",
                    value=2,
                ),
            )
        }
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(missing_aggregate, "Show support tickets by priority with more than two.")
    assert exc_info.value.reason == "having_aggregation_missing"


def test_output_and_limit_contracts_fail_closed() -> None:
    empty = _plan(entity_ids=("devices",))
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(empty, "Show devices.")
    assert exc_info.value.reason == "output_intent_missing"

    with pytest.raises(ValidationError):
        _plan(
            entity_ids=("devices",),
            output_fields=(_field("devices", "id"),),
            limit=0,
        )


def test_resolved_scope_column_cannot_be_literal_business_filter() -> None:
    plan = _plan(
        entity_ids=("directory_users",),
        literal_filters=(
            SemanticLiteralFilter(
                field=_field("directory_users", "department_id"),
                operator="equals",
                value="department-a",
            ),
        ),
        output_fields=(_field("directory_users", "id"),),
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(plan, "Show directory users in my department.")
    assert exc_info.value.reason == "scope_filter_not_allowed"


def _validate(
    plan: SemanticPlan,
    question: str,
    *,
    allowed_tables: tuple[str, ...] | None = None,
    scope_reference_resolved: bool = True,
):
    domain_pack = load_it_operations_domain_pack()
    selected_tables = allowed_tables or domain_pack.allowed_resource_table_names
    schema_context = {
        "allowed_tables": list(selected_tables),
        "allowed_columns": {
            name: sorted(domain_pack.table(name).columns_by_name)
            for name in selected_tables
        },
        "tables": [
            {
                "name": name,
                "scope_column": domain_pack.table(name).scope_column,
            }
            for name in selected_tables
        ],
    }
    projection = build_semantic_catalog_projection(
        domain_pack.semantic_catalog,
        question,
        schema_context,
        {
            "scope_type": "department",
            "scope_reference_resolved": scope_reference_resolved,
        },
    )
    return validate_semantic_plan(
        plan,
        domain_pack=domain_pack,
        projection=projection,
        schema_context=schema_context,
        scope_reference_resolved=scope_reference_resolved,
    )


def _plan(**changes: object) -> SemanticPlan:
    values: dict[str, object] = {
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


def _field(entity_id: str, column: str) -> SemanticFieldRef:
    return SemanticFieldRef(entity_id=entity_id, column=column)


def _count() -> SemanticAggregationIntent:
    return SemanticAggregationIntent(
        id="row_count",
        function="count",
        field=None,
        distinct=False,
    )


def _order(
    entity_id: str,
    column: str,
    direction: Literal["asc", "desc"],
) -> SemanticOrderIntent:
    return SemanticOrderIntent(
        target_kind="field",
        field=_field(entity_id, column),
        aggregation_id=None,
        direction=direction,
    )


def _relationship(
    relationship_id: str,
    join_type: Literal["inner", "left"],
) -> SemanticRelationshipIntent:
    return SemanticRelationshipIntent(
        relationship_id=relationship_id,
        join_type=join_type,
    )
