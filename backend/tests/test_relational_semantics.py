from dataclasses import replace
import os

import pytest
from sqlalchemy import create_engine, text

from action_postgres_test_db import validated_disposable_database_url
from app.query_engine.domain_pack import DomainColumn, DomainPack, DomainTable
from app.query_engine.relational_semantics import field_is_non_null, population_may_multiply
from app.query_engine.semantic_catalog import (
    SemanticAggregation, SemanticCatalog, SemanticCatalogProjection, SemanticEntity,
    SemanticMetric, SemanticRelationship, SemanticRelationshipCardinality,
)
from app.query_engine.semantic_conformance import check_semantic_conformance
from app.query_engine.semantic_plan import (
    SemanticAggregationIntent, SemanticFieldRef, SemanticHavingIntent,
    SemanticOrderIntent, SemanticPlan, SemanticPlanValidationError,
    SemanticRelationshipIntent, validate_semantic_plan,
)
from app.query_engine.sql_renderer import render_validated_semantic_plan
from app.query_engine.sql_validator import validate_sql


def field(entity="parents", column="id"):
    return SemanticFieldRef(entity_id=entity, column=column)


def aggregate(function="count", target=None, distinct=False, name="n"):
    return SemanticAggregationIntent(id=name, function=function, field=target, distinct=distinct)


def plan(**changes):
    values = dict(entity_ids=("parents",), concept_ids=(), composition_rule_ids=(),
                  metric_id=None, distinct=False, literal_filters=(), relationships=(),
                  output_fields=(), aggregations=(aggregate(),), group_by=(),
                  having=(), order_by=(), limit=None)
    values.update(changes)
    return SemanticPlan(**values)


def pack(cardinality=SemanticRelationshipCardinality.MANY_TO_ONE):
    columns = (DomainColumn("id", "integer", "identity", False),
               DomainColumn("parent_id", "integer", "reference", True),
               DomainColumn("amount", "numeric", "amount", True),
               DomainColumn("label", "text", "label", False))
    entities = tuple(SemanticEntity(name, name, name, (), ()) for name in ("parents", "children", "peers"))
    catalog = SemanticCatalog(
        "relational_test", "1", "relational_test", "relational_test", entities,
        (SemanticRelationship("child_parent", "children", "parent_id", "parents", "id", cardinality, True, "reference"),
         SemanticRelationship("peer_parent", "peers", "parent_id", "parents", "id", cardinality, True, "reference")),
        (), (SemanticMetric("parent_count", "parents", "count source rows", (), (), SemanticAggregation("count", "count")),),
        (), (), (), (),
    )
    return DomainPack("relational_test", "relational test", "1", tuple(e.table for e in entities),
                      tuple(DomainTable(e.table, e.table, e.table, columns) for e in entities), (), (), catalog)


def inputs(domain):
    catalog = domain.semantic_catalog
    projection = SemanticCatalogProjection(catalog.id, catalog.version, catalog.digest,
        tuple({"id": e.id} for e in catalog.entities),
        tuple({"id": r.id} for r in catalog.relationships), (),
        tuple({"id": m.id} for m in catalog.metrics), (), (), (), (), ())
    schema = {"allowed_tables": list(domain.allowed_resource_table_names),
              "allowed_columns": {t.name: [c.name for c in t.columns] for t in domain.tables},
              "tables": [{"name": t.name, "resource": {
                  "resource_type": "table", "schema_name": "public", "table_name": t.name,
                  "is_queryable": True, "llm_exposure_level": "aggregate_safe",
              }, "columns": [
                  {"name": c.name, "data_type": c.data_type, "nullable": c.nullable}
                  for c in t.columns]} for t in domain.tables]}
    return projection, schema


def validated(value, domain=None):
    domain = domain or pack()
    projection, schema = inputs(domain)
    return validate_semantic_plan(value, domain_pack=domain, projection=projection,
                                  schema_context=schema, scope_reference_resolved=False)


def joined(join_type="inner", **changes):
    return plan(entity_ids=("parents", "children"), relationships=(
        SemanticRelationshipIntent(relationship_id="child_parent", join_type=join_type),), **changes)


@pytest.mark.parametrize("value,reason", [
    (plan(aggregations=(aggregate(distinct=True),)), "count_distinct_target_missing"),
    (plan(aggregations=(aggregate("sum", field(column="label")),)), "sum_target_not_numeric"),
    (plan(aggregations=(aggregate("sum", field(column="amount"), True),)), "sum_distinct_unsupported"),
    (plan(order_by=(SemanticOrderIntent(target_kind="field", field=field(), aggregation_id=None, direction="asc"),)), "order_field_not_grouped"),
    (plan(aggregations=(), output_fields=(field(column="label"),), distinct=True,
          order_by=(SemanticOrderIntent(target_kind="field", field=field(), aggregation_id=None, direction="asc"),)), "distinct_order_field_not_output"),
    (plan(having=(SemanticHavingIntent(aggregation_id="missing", operator="equals", value=1),)), "having_aggregation_missing"),
    (joined(metric_id="parent_count", aggregations=()), "metric_population_unsupported"),
    (joined("left", metric_id="parent_count", aggregations=()), "metric_population_unsupported"),
    (plan(entity_ids=("parents", "children", "peers"), relationships=(
        SemanticRelationshipIntent(relationship_id="child_parent", join_type="left"),
        SemanticRelationshipIntent(relationship_id="peer_parent", join_type="left"))), "left_join_orientation_unsupported"),
])
def test_invalid_declared_algebra(value, reason):
    with pytest.raises(SemanticPlanValidationError) as error:
        validated(value)
    assert error.value.reason == reason


@pytest.mark.parametrize("data_type", ["integer", "numeric", "decimal"])
def test_numeric_sum_types(data_type):
    domain = pack()
    domain = replace(domain, tables=tuple(replace(t, columns=tuple(
        replace(c, data_type=data_type) if c.name == "amount" else c for c in t.columns
    )) for t in domain.tables))
    assert validated(plan(aggregations=(aggregate("sum", field(column="amount")),)), domain)


def test_targetless_catalog_sum_is_rejected():
    domain = pack()
    metric = replace(domain.semantic_catalog.metrics[0], aggregation=SemanticAggregation("sum", "sum"))
    domain = replace(domain, semantic_catalog=replace(domain.semantic_catalog, metrics=(metric,)))
    with pytest.raises(SemanticPlanValidationError) as error:
        validated(plan(metric_id=metric.id, aggregations=()), domain)
    assert error.value.reason == "metric_sum_target_missing"


@pytest.mark.parametrize("cardinality", list(SemanticRelationshipCardinality))
def test_population_bounds_from_each_side(cardinality):
    domain = pack(cardinality)
    value = joined()
    assert not population_may_multiply("children", value, domain)
    assert population_may_multiply("parents", value, domain) == (cardinality == SemanticRelationshipCardinality.MANY_TO_ONE)
    if cardinality == SemanticRelationshipCardinality.ONE_TO_ONE:
        assert validated(joined(metric_id="parent_count", aggregations=()), domain)


def test_fanout_along_a_second_branch_is_not_missed():
    value = plan(entity_ids=("parents", "children", "peers"), relationships=(
        SemanticRelationshipIntent(relationship_id="child_parent", join_type="inner"),
        SemanticRelationshipIntent(relationship_id="peer_parent", join_type="inner")))
    assert population_may_multiply("children", value, pack())
    assert validated(value)  # It explicitly counts joined rows.


@pytest.mark.parametrize("join_type", ["inner", "left"])
def test_non_null_proof_respects_left_extension(join_type):
    value = joined(join_type)
    assert field_is_non_null(field(), value, pack()) == (join_type == "inner")
    assert field_is_non_null(field("children"), value, pack())
    assert not field_is_non_null(field(column="amount"), value, pack())


def test_multiple_aggregates_do_not_invent_source_grain():
    value = joined(aggregations=(aggregate(), aggregate(target=field(), distinct=True, name="unique_parents"),
        aggregate("sum", field(column="amount"), name="parent_sum"),
        aggregate("sum", field("children", "amount"), name="child_sum")))
    assert set(validated(value).plan.aggregations) == set(value.aggregations)


@pytest.fixture
def postgres_connection():
    url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not url:
        pytest.skip("explicit disposable PostgreSQL database required")
    engine = create_engine(validated_disposable_database_url(url))
    with engine.connect() as connection:
        transaction = connection.begin()
        for name in ("parents", "children", "peers"):
            connection.execute(text(f"CREATE TEMP TABLE {name} (id integer PRIMARY KEY, parent_id integer, amount numeric, label text NOT NULL) ON COMMIT DROP"))
        connection.execute(text("INSERT INTO parents VALUES (1,NULL,10,'a'),(2,NULL,NULL,'b')"))
        connection.execute(text("INSERT INTO children VALUES (11,1,2,'x'),(12,1,3,'y'),(13,NULL,4,'z')"))
        try:
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


def execute(connection, value, domain=None):
    domain = domain or pack()
    checked = validated(value, domain)
    sql = render_validated_semantic_plan(checked, domain)
    _, schema = inputs(domain)
    safety = validate_sql(sql, schema)
    assert safety.valid, safety.reason
    conformance = check_semantic_conformance(plan=checked, candidate_sql=sql,
        safety_result=safety, domain_pack=domain, schema_context=schema)
    assert conformance.valid, conformance.reason_code
    return [tuple(row[c.column] for c in value.output_fields)
            + tuple(row[a.id] for a in value.aggregations)
            for row in connection.execute(text(sql)).mappings()]


@pytest.mark.parametrize("join_type,expected", [("inner", (2, 2, 1, 20, 5)), ("left", (3, 2, 1, 20, 9))])
def test_postgres_join_population_and_multiple_aggregates(postgres_connection, join_type, expected):
    value = joined(join_type, aggregations=(aggregate(), aggregate(target=field(), name="non_null"),
        aggregate(target=field(), distinct=True, name="unique_parents"),
        aggregate("sum", field(column="amount"), name="parent_sum"),
        aggregate("sum", field("children", "amount"), name="child_sum")))
    assert execute(postgres_connection, value) == [expected]


def test_postgres_empty_input_and_nullable_counts(postgres_connection):
    value = plan(aggregations=(aggregate(), aggregate(target=field(), name="ids"),
        aggregate(target=field(column="amount"), name="amounts"),
        aggregate("sum", field(column="amount"), name="total")))
    assert execute(postgres_connection, value) == [(2, 2, 1, 10)]
    postgres_connection.execute(text("DELETE FROM parents"))
    assert execute(postgres_connection, value) == [(0, 0, 0, None)]


def test_postgres_group_having_and_order(postgres_connection):
    key = field("children", "parent_id")
    value = plan(entity_ids=("children",), output_fields=(key,), group_by=(key,),
        having=(SemanticHavingIntent(aggregation_id="n", operator="greater_than", value=1),),
        order_by=(SemanticOrderIntent(target_kind="aggregation", field=None, aggregation_id="n", direction="desc"),))
    assert execute(postgres_connection, value) == [(1, 2)]


def test_postgres_relationship_identity_equivalence_counterexample(postgres_connection):
    # A reference without an enforced FK need not have a visible target.
    postgres_connection.execute(text("INSERT INTO children VALUES (14,999,5,'unmatched')"))
    for join_type, expected in (("inner", (1, 1)), ("left", (2, 1))):
        value = joined(join_type, aggregations=(aggregate(target=field("children", "parent_id"), distinct=True),
            aggregate(target=field(), distinct=True, name="referenced")))
        assert execute(postgres_connection, value) == [expected]


@pytest.mark.parametrize("data_type", ["text", "boolean", "uuid", "timestamp", "unknown"])
def test_sum_rejects_non_numeric_or_unknown_metadata(data_type):
    domain = pack()
    domain = replace(domain, tables=tuple(replace(t, columns=tuple(
        replace(c, data_type=data_type) if c.name == "amount" else c for c in t.columns
    )) for t in domain.tables))
    with pytest.raises(SemanticPlanValidationError) as error:
        validated(plan(aggregations=(aggregate("sum", field(column="amount")),)), domain)
    assert error.value.reason == "sum_target_not_numeric"


@pytest.mark.parametrize("join_type,valid", [("inner", True), ("left", False)])
def test_metric_count_conformance_requires_input_non_null_proof(join_type, valid):
    domain = pack()
    # Exercise conformance's independent defense with a formerly accepted shape.
    checked = replace(validated(plan(metric_id="parent_count", aggregations=())),
                      plan=joined(join_type, metric_id="parent_count", aggregations=()))
    sql = render_validated_semantic_plan(checked, domain).replace("COUNT(*)", "COUNT(parents.id)")
    _, schema = inputs(domain)
    safety = validate_sql(sql, schema)
    assert safety.valid, safety.reason
    result = check_semantic_conformance(plan=checked, candidate_sql=sql, safety_result=safety,
                                       domain_pack=domain, schema_context=schema)
    assert result.valid == valid


def test_postgres_one_to_one_has_no_fanout(postgres_connection):
    postgres_connection.execute(text("DELETE FROM children WHERE id=12"))
    postgres_connection.execute(text("ALTER TABLE children ADD UNIQUE (parent_id)"))
    domain = pack(SemanticRelationshipCardinality.ONE_TO_ONE)
    value = joined(aggregations=(aggregate(), aggregate(target=field(), distinct=True, name="unique_parents")))
    assert not population_may_multiply("parents", value, domain)
    assert execute(postgres_connection, value, domain) == [(1, 1)]


def test_postgres_distinct_order_and_multi_dimension_group(postgres_connection):
    keys = (field("children", "parent_id"), field("children", "label"))
    value = plan(entity_ids=("children",), distinct=True, output_fields=keys, group_by=keys,
        order_by=(SemanticOrderIntent(target_kind="field", field=keys[1], aggregation_id=None, direction="desc"),))
    assert execute(postgres_connection, value) == [(None, "z", 1), (1, "y", 1), (1, "x", 1)]
