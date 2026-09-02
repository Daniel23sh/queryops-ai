from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Literal, cast

import pytest
from pydantic import ValidationError

from app.query_engine.domain_pack import DomainPack
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.result_intent import (
    GroundedAggregationIntent,
    GroundedFieldIdentity,
    GroundedResultIntent,
    GroundedRowGrain,
)
from app.query_engine.semantic_catalog import (
    SemanticRelationshipCardinality,
    build_semantic_catalog_projection,
)
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


def test_single_entity_count_star_uses_its_row_source_entity() -> None:
    plan = _plan(
        entity_ids=("devices",),
        aggregations=(_count(),),
    )

    validated = _validate(plan, "How many devices are there?")

    assert validated.plan == plan


def test_grounded_or_rule_rejects_provider_full_branch_conjunction() -> None:
    domain_pack, schema_context, projection = _validation_inputs(
        "How many non-compliant devices are there?"
    )
    assert projection.mandatory_evidence() == {
        "entity_ids": ["devices"],
        "concept_ids": [],
        "metric_ids": [],
        "rule_ids": ["non_compliant_device_posture"],
    }
    plan = _plan(
        entity_ids=("devices",),
        concept_ids=(
            "antivirus_attention_device", "non_compliant_device", "unencrypted_device",
        ),
        composition_rule_ids=("non_compliant_device_posture",),
        aggregations=(_count(),),
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        validate_semantic_plan(
            plan, domain_pack=domain_pack, projection=projection,
            schema_context=schema_context, scope_reference_resolved=True,
        )

    assert exc_info.value.reason == "composition_rule_overconstraint"


def test_count_star_does_not_make_extra_selected_entities_used() -> None:
    plan = _plan(
        entity_ids=("devices", "directory_users"),
        aggregations=(_count(),),
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(plan, "How many devices and directory users are there?")

    assert exc_info.value.reason == "relationship_graph_disconnected"


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


def test_suggested_grouped_count_and_detail_plans_both_pass() -> None:
    grouped = _plan(
        entity_ids=(
            "departments",
            "directory_users",
            "groups",
            "user_group_memberships",
        ),
        concept_ids=("privileged_group",),
        relationships=(
            _relationship("directory_user_department", "inner"),
            _relationship("user_group_membership_group", "inner"),
            _relationship("user_group_membership_user", "inner"),
        ),
        output_fields=(_field("departments", "name"),),
        aggregations=(
            SemanticAggregationIntent(
                id="user_count",
                function="count",
                field=_field("directory_users", "id"),
                distinct=True,
            ),
        ),
        group_by=(_field("departments", "name"),),
    )
    question = "Show users in privileged groups by department."

    assert _validate(grouped, question)

    detailed = grouped.model_copy(
        update={
            "output_fields": (_field("directory_users", "id"),),
            "aggregations": (),
            "group_by": (),
        }
    )

    assert _validate(detailed, question)


def test_grounded_required_output_and_group_grain_fail_closed() -> None:
    aggregation = SemanticAggregationIntent(
        id="user_count",
        function="count",
        field=_field("directory_users", "id"),
        distinct=True,
    )
    base = _plan(
        entity_ids=(
            "departments",
            "directory_users",
            "groups",
            "user_group_memberships",
        ),
        concept_ids=("privileged_group",),
        relationships=(
            _relationship("directory_user_department", "inner"),
            _relationship("user_group_membership_group", "inner"),
            _relationship("user_group_membership_user", "inner"),
        ),
        aggregations=(aggregation,),
        group_by=(_field("departments", "name"),),
    )
    question = "How many privileged users by department?"

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(base, question)
    assert exc_info.value.reason == "required_output_missing"
    assert exc_info.value.safe_observation == {
        "expected": ["departments.name"],
        "actual": [],
    }

    extra_group = base.model_copy(
        update={
            "output_fields": (
                _field("departments", "name"),
                _field("groups", "name"),
            ),
            "group_by": (
                _field("departments", "name"),
                _field("groups", "name"),
            ),
        }
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(extra_group, question)
    assert exc_info.value.reason == "grounded_group_by_mismatch"
    assert exc_info.value.safe_observation == {
        "expected": ["departments.name"],
        "actual": ["departments.name", "groups.name"],
    }


@pytest.mark.parametrize(
    ("entity_id", "column", "distinct"),
    [
        ("directory_users", "id", False),
        ("user_group_memberships", "user_id", False),
        ("groups", "id", True),
        ("user_group_memberships", "group_id", True),
        ("departments", "id", True),
    ],
)
def test_grounded_aggregation_target_and_distinctness_fail_closed(
    entity_id: str,
    column: str,
    distinct: bool,
) -> None:
    aggregation = SemanticAggregationIntent(
        id="user_count",
        function="count",
        field=_field(entity_id, column),
        distinct=distinct,
    )
    plan = _plan(
        entity_ids=(
            "departments",
            "directory_users",
            "groups",
            "user_group_memberships",
        ),
        concept_ids=("privileged_group",),
        relationships=(
            _relationship("directory_user_department", "inner"),
            _relationship("user_group_membership_group", "inner"),
            _relationship("user_group_membership_user", "inner"),
        ),
        output_fields=(_field("departments", "name"),),
        aggregations=(aggregation,),
        group_by=(_field("departments", "name"),),
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(plan, "How many privileged users by department?")
    assert exc_info.value.reason == "grounded_aggregation_mismatch"


def test_grounded_distinct_count_accepts_direct_fk_identity_equivalence() -> None:
    plan = _medium_006_plan(
        SemanticAggregationIntent(
            id="user_count",
            function="count",
            field=_field("user_group_memberships", "user_id"),
            distinct=True,
        )
    )

    assert _validate(plan, "How many privileged users by department?")


def test_grounded_distinct_count_refuses_count_star() -> None:
    plan = _medium_006_plan(
        SemanticAggregationIntent(
            id="user_count",
            function="count",
            field=None,
            distinct=True,
        )
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(plan, "How many privileged users by department?")
    assert exc_info.value.reason == "grounded_aggregation_mismatch"


def test_grounded_distinct_count_equivalence_is_symmetric() -> None:
    domain_pack, schema_context, projection = _validation_inputs(
        "How many privileged users by department?"
    )
    assert projection.grounded_result_intent is not None
    reversed_intent = projection.grounded_result_intent.model_copy(
        update={
            "aggregations": (
                GroundedAggregationIntent(
                    id="subject_count",
                    function="count",
                    target_field=GroundedFieldIdentity(
                        table="user_group_memberships",
                        column="user_id",
                    ),
                    distinct=True,
                ),
            )
        }
    )
    projection = replace(projection, grounded_result_intent=reversed_intent)
    plan = _medium_006_plan(
        SemanticAggregationIntent(
            id="user_count",
            function="count",
            field=_field("directory_users", "id"),
            distinct=True,
        )
    )

    assert validate_semantic_plan(
        plan,
        domain_pack=domain_pack,
        projection=projection,
        schema_context=schema_context,
        scope_reference_resolved=True,
    )


def test_grounded_distinct_count_refuses_nullable_fk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.base import Base

    source_column = Base.metadata.tables[
        "user_group_memberships"
    ].columns["user_id"]
    monkeypatch.setattr(source_column, "nullable", True)

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(
            _medium_006_fk_count_plan(),
            "How many privileged users by department?",
        )
    assert exc_info.value.reason == "grounded_aggregation_mismatch"


@pytest.mark.parametrize(
    "relationship_change",
    [
        {"optional": True},
        {"cardinality": SemanticRelationshipCardinality.ONE_TO_ONE},
        {
            "cardinality": cast(
                SemanticRelationshipCardinality,
                SimpleNamespace(value="many_to_many"),
            )
        },
    ],
)
def test_grounded_distinct_count_refuses_unproven_relationship_shape(
    relationship_change: dict[str, object],
) -> None:
    domain_pack = load_it_operations_domain_pack()
    relationship = next(
        item
        for item in domain_pack.semantic_catalog.relationships
        if item.id == "user_group_membership_user"
    )
    changed_relationship = replace(relationship, **relationship_change)
    catalog = replace(
        domain_pack.semantic_catalog,
        relationships=tuple(
            changed_relationship if item.id == relationship.id else item
            for item in domain_pack.semantic_catalog.relationships
        ),
    )
    changed_pack = replace(domain_pack, semantic_catalog=catalog)

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(
            _medium_006_fk_count_plan(),
            "How many privileged users by department?",
            domain_pack=changed_pack,
        )
    assert exc_info.value.reason == "grounded_aggregation_mismatch"


def test_grounded_distinct_count_refuses_left_or_missing_direct_relationship() -> None:
    left_join = _medium_006_fk_count_plan().model_copy(
        update={
            "relationships": (
                _relationship("directory_user_department", "inner"),
                _relationship("user_group_membership_group", "inner"),
                _relationship("user_group_membership_user", "left"),
            )
        }
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(left_join, "How many privileged users by department?")
    assert exc_info.value.reason == "grounded_aggregation_mismatch"

    indirect_only = _medium_006_fk_count_plan().model_copy(
        update={
            "relationships": (
                _relationship("directory_user_department", "inner"),
                _relationship("user_group_membership_department", "inner"),
                _relationship("user_group_membership_group", "inner"),
            )
        }
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(indirect_only, "How many privileged users by department?")
    assert exc_info.value.reason == "grounded_aggregation_mismatch"


def test_grounded_distinct_count_refuses_different_function_and_grouping() -> None:
    wrong_function = _medium_006_plan(
        SemanticAggregationIntent(
            id="user_count",
            function="sum",
            field=_field("user_group_memberships", "user_id"),
            distinct=True,
        )
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(wrong_function, "How many privileged users by department?")
    assert exc_info.value.reason == "grounded_aggregation_mismatch"

    wrong_group = _medium_006_fk_count_plan().model_copy(
        update={
            "output_fields": (
                _field("departments", "name"),
                _field("groups", "name"),
            ),
            "group_by": (
                _field("departments", "name"),
                _field("groups", "name"),
            ),
        }
    )
    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(wrong_group, "How many privileged users by department?")
    assert exc_info.value.reason == "grounded_aggregation_mismatch"


def test_grounded_distinct_count_refuses_different_having_semantics() -> None:
    plan = _medium_006_fk_count_plan().model_copy(
        update={
            "having": (
                SemanticHavingIntent(
                    aggregation_id="user_count",
                    operator="greater_than",
                    value=5,
                ),
            )
        }
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(plan, "How many privileged users by department?")
    assert exc_info.value.reason == "grounded_aggregation_mismatch"


def test_grounded_aggregation_mismatch_exposes_only_safe_identity() -> None:
    wrong = _medium_006_plan(
        SemanticAggregationIntent(
            id="provider_alias_is_not_observed",
            function="count",
            field=_field("groups", "id"),
            distinct=True,
        )
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(wrong, "How many privileged users by department?")

    assert exc_info.value.safe_observation == {
        "expected": [
            {
                "function": "count",
                "target": "directory_users.id",
                "distinct": True,
            }
        ],
        "actual": [
            {"function": "count", "target": "groups.id", "distinct": True}
        ],
    }
    serialized = str(exc_info.value.safe_observation).lower()
    assert "provider_alias_is_not_observed" not in serialized
    assert "select " not in serialized
    assert "prompt" not in serialized
    assert "literal" not in serialized
    assert "rows" not in serialized


def test_grounded_explicit_having_mismatch_fails_closed() -> None:
    aggregation = SemanticAggregationIntent(
        id="failed_count",
        function="count",
        field=_field("login_events", "id"),
        distinct=False,
    )
    plan = _plan(
        entity_ids=("login_events",),
        concept_ids=("failed_login_within_30_days",),
        output_fields=(_field("login_events", "user_id"),),
        aggregations=(aggregation,),
        group_by=(_field("login_events", "user_id"),),
        having=(
            SemanticHavingIntent(
                aggregation_id="failed_count",
                operator="greater_than",
                value=6,
            ),
        ),
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        _validate(
            plan,
            "Show users with more than five failed logins in the last 30 days.",
        )
    assert exc_info.value.reason == "grounded_having_mismatch"
    assert exc_info.value.safe_observation == {
        "expected": [
            {
                "aggregation": {
                    "function": "count",
                    "target": "login_events.id",
                    "distinct": False,
                },
                "operator": "greater_than",
            }
        ],
        "actual": [
            {
                "aggregation": {
                    "function": "count",
                    "target": "login_events.id",
                    "distinct": False,
                },
                "operator": "greater_than",
            }
        ],
    }
    assert "5" not in str(exc_info.value.safe_observation)
    assert "6" not in str(exc_info.value.safe_observation)
    assert "failed_count" not in str(exc_info.value.safe_observation)

    correct = plan.model_copy(
        update={
            "having": (
                SemanticHavingIntent(
                    aggregation_id="failed_count",
                    operator="greater_than",
                    value=5,
                ),
            )
        }
    )
    assert _validate(
        correct,
        "Show users with more than five failed logins in the last 30 days.",
    )


def test_required_distinct_mismatch_exposes_only_booleans() -> None:
    domain_pack, schema_context, projection = _validation_inputs(
        "Show directory users."
    )
    projection = replace(
        projection,
        grounded_result_intent=GroundedResultIntent(distinct=True),
    )
    plan = _plan(
        entity_ids=("directory_users",),
        distinct=False,
        output_fields=(_field("directory_users", "id"),),
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        validate_semantic_plan(
            plan,
            domain_pack=domain_pack,
            projection=projection,
            schema_context=schema_context,
            scope_reference_resolved=True,
        )

    assert exc_info.value.reason == "grounded_distinct_mismatch"
    assert exc_info.value.safe_observation == {
        "expected": True,
        "actual": False,
    }


def test_required_grain_mismatch_exposes_mode_and_canonical_identities() -> None:
    domain_pack, schema_context, projection = _validation_inputs(
        "Show directory users."
    )
    identity = GroundedFieldIdentity(table="directory_users", column="id")
    projection = replace(
        projection,
        grounded_result_intent=GroundedResultIntent(
            row_grain=GroundedRowGrain(
                mode="detail",
                identity_fields=(identity,),
            ),
            required_output_fields=(identity,),
        ),
    )
    plan = _plan(
        entity_ids=("directory_users",),
        output_fields=(_field("directory_users", "id"),),
        aggregations=(_count(),),
        group_by=(_field("directory_users", "id"),),
    )

    with pytest.raises(SemanticPlanValidationError) as exc_info:
        validate_semantic_plan(
            plan,
            domain_pack=domain_pack,
            projection=projection,
            schema_context=schema_context,
            scope_reference_resolved=True,
        )

    assert exc_info.value.reason == "result_grain_mismatch"
    assert exc_info.value.safe_observation == {
        "expected": {
            "mode": "detail",
            "identities": ["directory_users.id"],
        },
        "actual": {
            "mode": "grouped",
            "identities": ["directory_users.id"],
        },
    }


def test_suggested_assignment_detail_does_not_reject_valid_plan() -> None:
    question = "Show inactive users with active mandatory licenses."
    collapsed = _plan(
        entity_ids=("directory_users", "license_assignments"),
        concept_ids=(
            "active_mandatory_license_assignment",
            "inactive_directory_user",
        ),
        relationships=(_relationship("license_assignment_user", "inner"),),
        distinct=True,
        output_fields=(_field("directory_users", "id"),),
    )

    assert _validate(collapsed, question)


def test_suggested_implicit_count_mismatch_does_not_reject_valid_plan() -> None:
    plan = _plan(
        entity_ids=("directory_users", "license_assignments", "licenses"),
        concept_ids=("active_license_assignment",),
        relationships=(
            _relationship("license_assignment_user", "inner"),
            _relationship("license_assignment_license", "inner"),
        ),
        output_fields=(_field("licenses", "product_name"),),
        aggregations=(
            SemanticAggregationIntent(
                id="assignment_count",
                function="count",
                field=_field("license_assignments", "id"),
                distinct=False,
            ),
        ),
        group_by=(_field("licenses", "product_name"),),
    )

    # Grounding suggests distinct users, but that inference is not explicit.
    assert _validate(
        plan,
        "Show users with active license assignments by product.",
    )


def test_partial_grounded_intent_does_not_require_unspecified_aggregate() -> None:
    plan = _plan(
        entity_ids=("license_assignments", "licenses"),
        concept_ids=("high_confidence_unused_license_assignment",),
        relationships=(_relationship("license_assignment_license", "inner"),),
        output_fields=(_field("licenses", "product_name"),),
        aggregations=(
            SemanticAggregationIntent(
                id="assignment_count",
                function="count",
                field=_field("license_assignments", "id"),
                distinct=False,
            ),
        ),
        group_by=(_field("licenses", "product_name"),),
    )

    assert _validate(plan, "Show high-confidence unused licenses by product.")


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
    domain_pack: DomainPack | None = None,
):
    domain_pack = domain_pack or load_it_operations_domain_pack()
    domain_pack, schema_context, projection = _validation_inputs(
        question,
        allowed_tables=allowed_tables,
        scope_reference_resolved=scope_reference_resolved,
        domain_pack=domain_pack,
    )
    return validate_semantic_plan(
        plan,
        domain_pack=domain_pack,
        projection=projection,
        schema_context=schema_context,
        scope_reference_resolved=scope_reference_resolved,
    )


def _validation_inputs(
    question: str,
    *,
    allowed_tables: tuple[str, ...] | None = None,
    scope_reference_resolved: bool = True,
    domain_pack: DomainPack | None = None,
):
    domain_pack = domain_pack or load_it_operations_domain_pack()
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
    return domain_pack, schema_context, projection


def _medium_006_plan(
    aggregation: SemanticAggregationIntent,
) -> SemanticPlan:
    return _plan(
        entity_ids=(
            "departments",
            "directory_users",
            "groups",
            "user_group_memberships",
        ),
        concept_ids=("privileged_group",),
        relationships=(
            _relationship("directory_user_department", "inner"),
            _relationship("user_group_membership_group", "inner"),
            _relationship("user_group_membership_user", "inner"),
        ),
        output_fields=(_field("departments", "name"),),
        aggregations=(aggregation,),
        group_by=(_field("departments", "name"),),
    )


def _medium_006_fk_count_plan() -> SemanticPlan:
    return _medium_006_plan(
        SemanticAggregationIntent(
            id="user_count",
            function="count",
            field=_field("user_group_memberships", "user_id"),
            distinct=True,
        )
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
