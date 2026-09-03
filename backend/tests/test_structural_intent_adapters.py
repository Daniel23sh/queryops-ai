import ast
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.scoring import score_evaluation_semantic_contract
from app.evaluation.structural_intent_adapter import (
    evaluation_contract_to_structural_requirement,
)
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.result_intent import (
    GroundedAggregationIntent,
    GroundedFieldIdentity,
    GroundedHavingIntent,
    GroundedResultIntent,
    GroundedRowGrain,
)
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticHavingIntent,
    SemanticOrderIntent,
    SemanticPlan,
    validate_semantic_plan,
)
from app.query_engine.structural_intent_adapters import (
    StructuralMappingError,
    grounded_to_structural_requirement,
    validated_plan_to_structural_observation,
)
from app.query_engine.structural_intent_comparison import compare_structural_requirement


PACK = load_it_operations_domain_pack()
CATALOG = PACK.semantic_catalog
PHYSICAL = GroundedFieldIdentity(table="devices", column="id")
FIELD = SemanticFieldRef(entity_id="devices", column="id")
GROUP = SemanticFieldRef(entity_id="devices", column="os")


def validated_plan(question="Show devices.", **changes):
    values = dict(
        entity_ids=("devices",),
        concept_ids=(),
        composition_rule_ids=(),
        metric_id=None,
        distinct=False,
        literal_filters=(),
        relationships=(),
        output_fields=(FIELD,),
        aggregations=(),
        group_by=(),
        having=(),
        order_by=(),
        limit=None,
    )
    values.update(changes)
    schema = {
        "allowed_tables": list(PACK.allowed_resource_table_names),
        "allowed_columns": {
            table.name: list(table.columns_by_name) for table in PACK.tables
        },
    }
    projection = build_semantic_catalog_projection(CATALOG, question, schema, {})
    return validate_semantic_plan(
        SemanticPlan(**values),
        domain_pack=PACK,
        projection=projection,
        schema_context=schema,
        scope_reference_resolved=False,
    )


def test_grounded_empty_means_unspecified_and_binding_is_explicit():
    for source in [None, GroundedResultIntent()]:
        result = grounded_to_structural_requirement(source, CATALOG, binding="required")
        assert all(
            getattr(result.intent, name).state == "unspecified"
            for name in type(result.intent).model_fields
        )
        assert set(result.policy.model_dump().values()) == {"ignored"}
    with pytest.raises(TypeError):
        grounded_to_structural_requirement(GroundedResultIntent(), CATALOG)


def test_grounded_table_is_translated_not_assumed_to_be_entity():
    entity = next(item for item in CATALOG.entities if item.table == "devices")
    catalog = replace(CATALOG, entities=(replace(entity, id="endpoint"),))
    source = GroundedResultIntent(required_output_fields=(PHYSICAL,))
    before = source.model_dump_json()
    result = grounded_to_structural_requirement(source, catalog, binding="required")
    assert result.intent.output_fields.value == (
        SemanticFieldRef(entity_id="endpoint", column="id"),
    )
    assert result.policy.output_fields == "required_subset"
    assert result.intent.ordering.state == "unspecified"
    assert source.model_dump_json() == before
    assert '"table"' not in result.intent.model_dump_json()


@pytest.mark.parametrize("ambiguous", [False, True])
def test_missing_or_ambiguous_mapping_fails_safely(ambiguous):
    entity = next(item for item in CATALOG.entities if item.table == "devices")
    entities = (entity, replace(entity, id="other")) if ambiguous else ()
    with pytest.raises(StructuralMappingError) as exc:
        grounded_to_structural_requirement(
            GroundedResultIntent(required_output_fields=(PHYSICAL,)),
            replace(CATALOG, entities=entities),
            binding="required",
        )
    assert "devices" not in str(exc.value)


def test_partial_grounded_distinct_and_decimal_threshold():
    source = GroundedResultIntent(
        aggregations=(
            GroundedAggregationIntent(
                id="n", function="count", target_field=PHYSICAL, distinct=True
            ),
        ),
        having=(
            GroundedHavingIntent(
                aggregation_id="n", operator="greater_than", value=0.1
            ),
        ),
        distinct=False,
    )
    result = grounded_to_structural_requirement(source, CATALOG, binding="required")
    assert result.intent.row_grain.state == "unspecified"
    assert result.intent.group_by.state == "unspecified"
    assert result.intent.having.value[0].value == Decimal("0.1")
    assert result.intent.aggregations.value[0].field == FIELD
    assert result.intent.aggregations.value[0].distinct is True
    assert result.intent.distinct.value is False
    assert (
        result.policy.aggregations
        == result.policy.having
        == result.policy.distinct
        == "exact"
    )


@pytest.mark.parametrize(
    "mode,policy", [("detail", "required_subset"), ("grouped", "exact")]
)
def test_grounded_grain_preserved(mode, policy):
    result = grounded_to_structural_requirement(
        GroundedResultIntent(
            row_grain=GroundedRowGrain(mode=mode, identity_fields=(PHYSICAL,)),
        ),
        CATALOG,
        binding="required",
    )
    assert result.intent.row_grain.value.mode == mode
    assert result.intent.row_grain.value.identity_fields.value == (FIELD,)
    assert result.policy.row_grain == policy
    assert result.intent.output_fields.state == "unspecified"


def test_actual_projection_required_and_suggested_are_not_merged():
    schema = {
        "allowed_tables": list(PACK.allowed_resource_table_names),
        "allowed_columns": {
            table.name: list(table.columns_by_name) for table in PACK.tables
        },
    }
    projection = build_semantic_catalog_projection(
        CATALOG,
        "Show unused licenses assigned to inactive users.",
        schema,
        {},
    )
    assert projection.suggested_result_intent is not None
    required = grounded_to_structural_requirement(
        projection.grounded_result_intent, CATALOG, binding="required"
    )
    suggested = grounded_to_structural_requirement(
        projection.suggested_result_intent, CATALOG, binding="suggested"
    )
    assert required.intent.row_grain.state == "unspecified"
    assert suggested.intent.row_grain.state == "known"
    with pytest.raises(ValueError, match="Suggested"):
        compare_structural_requirement(suggested, required.intent)


def test_detail_observation_and_source_immutability():
    validated = validated_plan(distinct=True)
    before = json.dumps(validated.as_observation(), sort_keys=True)
    actual = validated_plan_to_structural_observation(validated)
    assert actual.row_grain.value.mode == "detail"
    assert actual.row_grain.value.identity_fields.state == "unknown"
    assert actual.output_fields.value == (FIELD,)
    assert (
        actual.aggregations.value
        == actual.group_by.value
        == actual.ordering.value
        == ()
    )
    assert actual.distinct.value is True
    assert json.dumps(validated.as_observation(), sort_keys=True) == before
    with pytest.raises(TypeError):
        validated_plan_to_structural_observation(validated.plan)


def test_grouped_observation_preserves_multiple_aggregates_having_order():
    counts = (
        SemanticAggregationIntent(
            id="rows", function="count", field=None, distinct=False
        ),
        SemanticAggregationIntent(
            id="ids", function="count", field=FIELD, distinct=True
        ),
    )
    order = (
        SemanticOrderIntent(
            target_kind="aggregation",
            field=None,
            aggregation_id="rows",
            direction="desc",
        ),
        SemanticOrderIntent(
            target_kind="field", field=GROUP, aggregation_id=None, direction="asc"
        ),
    )
    validated = validated_plan(
        output_fields=(GROUP,),
        aggregations=counts,
        group_by=(GROUP,),
        having=(
            SemanticHavingIntent(
                aggregation_id="rows", operator="greater_than", value=0.1
            ),
        ),
        order_by=order,
    )
    actual = validated_plan_to_structural_observation(validated)
    assert actual.row_grain.value.mode == "grouped"
    assert actual.row_grain.value.identity_fields.value == (GROUP,)
    assert actual.aggregations.value == validated.plan.aggregations
    assert actual.group_by.value == (GROUP,)
    assert actual.having.value[0].value == Decimal("0.1")
    assert actual.ordering.value == order


def test_explicit_scalar_and_named_metric_remain_distinguishable():
    count = SemanticAggregationIntent(
        id="n", function="count", field=None, distinct=False
    )
    scalar = validated_plan_to_structural_observation(
        validated_plan(output_fields=(), aggregations=(count,))
    )
    metric = validated_plan_to_structural_observation(
        validated_plan(
            question="How many active human users?",
            entity_ids=("directory_users",),
            output_fields=(),
            metric_id="active_human_users",
        )
    )
    assert scalar.row_grain == metric.row_grain
    assert scalar.row_grain.value.mode == "scalar"
    assert scalar.row_grain.value.identity_fields.value == ()
    assert scalar.aggregations.value == (count,)
    assert metric.aggregations.state == "known"
    assert metric.aggregations.value == ()
    assert metric.output_fields.value == metric.group_by.value == ()


def test_named_metric_does_not_satisfy_explicit_v2_aggregate_requirement():
    metric = validated_plan(
        question="How many active human users?",
        entity_ids=("directory_users",),
        output_fields=(),
        metric_id="active_human_users",
    )
    case = load_it_operations_evaluation_v2_set().cases_by_id["itops-easy-003"]
    requirement = evaluation_contract_to_structural_requirement(case.semantic_contract)
    result = compare_structural_requirement(
        requirement,
        validated_plan_to_structural_observation(metric),
    )
    assert dict(result.components)["aggregations"] == "mismatch"
    assert (
        score_evaluation_semantic_contract(
            case, metric.as_observation()
        ).aggregations_correct
        is False
    )


def test_adapter_does_not_tighten_validated_duplicate_output_shape():
    actual = validated_plan_to_structural_observation(
        validated_plan(output_fields=(FIELD, FIELD))
    )
    assert actual.output_fields.value == (FIELD, FIELD)


def test_foundation_dependency_direction_and_no_production_wiring():
    new_modules = {
        "app.query_engine.structural_intent",
        "app.query_engine.structural_intent_adapters",
        "app.query_engine.structural_intent_comparison",
        "app.evaluation.structural_intent_adapter",
        "app.evaluation.structural_conformance",
    }
    for path in Path("app").rglob("*.py"):
        module = ".".join(path.with_suffix("").parts)
        imports = []
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        if "query_engine" in path.parts:
            assert not any(name.startswith("app.evaluation") for name in imports), path
        if module not in new_modules:
            assert not set(imports) & new_modules, path
