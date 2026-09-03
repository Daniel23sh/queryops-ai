from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.query_engine.semantic_plan import (
    SemanticAggregationIntent,
    SemanticFieldRef,
    SemanticOrderIntent,
)
from app.query_engine.structural_intent import (
    StructuralHaving,
    StructuralResultIntent,
    StructuralRowGrain,
    StructuralValue,
    empty_structural_intent,
    known,
    unknown,
)
from app.query_engine.structural_intent_comparison import (
    StructuralComparisonPolicy,
    StructuralRequirement,
    compare_structural_requirement,
)


FIELD = SemanticFieldRef(entity_id="devices", column="id")
GROUP = SemanticFieldRef(entity_id="devices", column="os")


def intent(**changes):
    values = {
        name: getattr(empty_structural_intent(), name)
        for name in StructuralResultIntent.model_fields
    }
    values.update(changes)
    return StructuralResultIntent(**values)


def aggregate(id="count", field=FIELD, distinct=False, function="count"):
    return SemanticAggregationIntent(
        id=id, function=function, field=field, distinct=distinct
    )


def order(id="count", direction="desc"):
    return SemanticOrderIntent(
        target_kind="aggregation",
        field=None,
        aggregation_id=id,
        direction=direction,
    )


def compare(expected, actual, **policies):
    return compare_structural_requirement(
        StructuralRequirement(
            intent=expected,
            policy=StructuralComparisonPolicy(**policies),
            binding="required",
        ),
        actual,
    )


def test_presence_states_and_explicit_empty_and_false_are_distinct():
    states = [
        StructuralValue[tuple](state="unknown"),
        StructuralValue[tuple](state="unspecified"),
        known(()),
    ]
    assert len({item.model_dump_json() for item in states}) == 3
    assert known(False).value is False
    assert (
        compare(
            intent(output_fields=known(())),
            intent(output_fields=known((FIELD,))),
            output_fields="exact",
        ).passed
        is False
    )
    assert (
        compare(
            intent(output_fields=known(())),
            intent(output_fields=known((FIELD,))),
            output_fields="required_subset",
        ).passed
        is True
    )
    assert (
        compare(
            intent(output_fields=unknown()),
            intent(output_fields=known(())),
            output_fields="exact",
        ).passed
        is None
    )
    assert (
        compare(
            intent(output_fields=known(())),
            intent(output_fields=unknown()),
            output_fields="exact",
        ).passed
        is None
    )
    assert compare(intent(), intent()).passed is None
    with pytest.raises(ValueError, match="unspecified"):
        compare(intent(), intent(output_fields=known(())), output_fields="exact")


@pytest.mark.parametrize(
    "data",
    [
        {"state": "known"},
        {"state": "unknown", "value": ()},
        {"state": "unspecified", "value": False},
        {"state": "other"},
        {"state": "known", "value": (), "extra": True},
    ],
)
def test_invalid_presence(data):
    with pytest.raises(ValidationError):
        StructuralValue(**data)


def test_strict_bounded_immutable_model():
    with pytest.raises(ValidationError):
        intent(output_fields=known([FIELD]))
    with pytest.raises(ValidationError):
        intent(output_fields=known((FIELD,) * 65))
    with pytest.raises(ValidationError):
        intent(distinct=known("false"))
    with pytest.raises(ValidationError):
        intent().distinct = known(True)
    with pytest.raises(ValidationError):
        intent(output_fields=known(({"table": "devices", "column": "id"},)))


def test_shape_and_identity_knownness():
    detail = StructuralRowGrain(mode="detail", identity_fields=unknown())
    grouped = StructuralRowGrain(mode="grouped", identity_fields=known((GROUP,)))
    scalar = StructuralRowGrain(mode="scalar", identity_fields=known(()))
    assert detail.identity_fields.state == "unknown"
    assert grouped.identity_fields.value == (GROUP,)
    assert scalar.identity_fields.value == ()
    with pytest.raises(ValidationError):
        StructuralRowGrain(mode="scalar", identity_fields=known((FIELD,)))
    with pytest.raises(ValidationError):
        StructuralRowGrain(mode="scalar", identity_fields=unknown())


def test_detail_key_requirement_uses_projection_without_inventing_identity():
    expected = intent(
        row_grain=known(
            StructuralRowGrain(
                mode="detail",
                identity_fields=known((FIELD,)),
            )
        )
    )
    actual = intent(
        row_grain=known(
            StructuralRowGrain(
                mode="detail",
                identity_fields=unknown(),
            )
        ),
        output_fields=known((FIELD, GROUP)),
    )
    assert compare(expected, actual, row_grain="required_subset").passed is True
    assert compare(expected, actual, row_grain="exact").passed is None
    assert actual.row_grain.value.identity_fields.state == "unknown"


def test_grouped_grain_requires_same_mode_and_identity():
    expected = intent(
        row_grain=known(
            StructuralRowGrain(
                mode="grouped",
                identity_fields=known((GROUP,)),
            )
        )
    )
    for mode, keys in [("detail", (GROUP,)), ("grouped", (FIELD,)), ("scalar", ())]:
        actual = intent(
            row_grain=known(StructuralRowGrain(mode=mode, identity_fields=known(keys)))
        )
        assert compare(expected, actual, row_grain="exact").passed is False


def test_multiple_aggregations_and_decimal_having_roundtrip():
    threshold = Decimal("9007199254740993.1234567890123456789")
    expected = intent(
        aggregations=known((aggregate(), aggregate("total", function="sum"))),
        group_by=known((GROUP,)),
        having=known(
            (
                StructuralHaving(
                    aggregation_id="total", operator="greater_than", value=threshold
                ),
            )
        ),
        ordering=known((order("total"), order())),
        distinct=known(True),
    )
    restored = StructuralResultIntent.model_validate_json(expected.model_dump_json())
    assert restored == expected
    assert restored.having.value[0].value == threshold
    assert (
        compare(
            expected,
            restored,
            aggregations="exact",
            group_by="exact",
            having="exact",
            ordering="exact",
            distinct="exact",
        ).passed
        is True
    )


@pytest.mark.parametrize("threshold", [Decimal("NaN"), Decimal("Infinity"), True, 0.1])
def test_having_requires_finite_decimal(threshold):
    with pytest.raises(ValidationError):
        StructuralHaving(aggregation_id="count", operator="equals", value=threshold)


def test_aggregation_reference_integrity():
    with pytest.raises(ValidationError, match="unique"):
        intent(aggregations=known((aggregate(), aggregate())))
    with pytest.raises(ValidationError, match="no declared aggregation"):
        intent(ordering=known((order(),)))
    with pytest.raises(ValidationError, match="no declared aggregation"):
        intent(
            aggregations=known((aggregate(),)),
            having=known(
                (
                    StructuralHaving(
                        aggregation_id="missing",
                        operator="equals",
                        value=Decimal(1),
                    ),
                )
            ),
        )
    with pytest.raises(ValidationError):
        SemanticOrderIntent(
            target_kind="field", field=FIELD, aggregation_id="count", direction="asc"
        )


def test_alias_independent_comparison_and_priority():
    expected = intent(
        aggregations=known((aggregate(),)),
        ordering=known((order(),)),
        having=known(
            (
                StructuralHaving(
                    aggregation_id="count", operator="equals", value=Decimal("0.1")
                ),
            )
        ),
    )
    actual = intent(
        aggregations=known((aggregate("alias"), aggregate("extra", function="sum"))),
        ordering=known((order("alias"), order("extra"))),
        having=known(
            (
                StructuralHaving(
                    aggregation_id="alias", operator="equals", value=Decimal("0.10")
                ),
            )
        ),
    )
    assert (
        compare(
            expected,
            actual,
            aggregations="required_subset",
            having="required_subset",
            ordering="ordered_prefix",
        ).passed
        is True
    )
    assert compare(expected, actual, aggregations="exact").passed is False
    assert compare(expected, actual, ordering="exact").passed is False
    reordered = intent(
        aggregations=actual.aggregations,
        ordering=known(tuple(reversed(actual.ordering.value))),
    )
    assert compare(expected, reordered, ordering="ordered_prefix").passed is False
    descending = intent(
        aggregations=actual.aggregations, ordering=known((order("alias", "asc"),))
    )
    assert compare(expected, descending, ordering="ordered_prefix").passed is False


def test_exact_aggregation_retains_multiplicity_but_subset_uses_identity():
    expected = intent(aggregations=known((aggregate(),)))
    actual = intent(aggregations=known((aggregate(), aggregate("alias"))))
    assert compare(expected, actual, aggregations="exact").passed is False
    assert compare(expected, actual, aggregations="required_subset").passed is True


@pytest.mark.parametrize(
    "different",
    [
        aggregate(field=None),
        aggregate(distinct=True),
        aggregate(function="sum"),
        aggregate(field=SemanticFieldRef(entity_id="other_entity", column="id")),
    ],
)
def test_no_count_or_fk_equivalences(different):
    assert (
        compare(
            intent(aggregations=known((aggregate(),))),
            intent(aggregations=known((different,))),
            aggregations="exact",
        ).passed
        is False
    )


def test_having_and_group_by_policies_do_not_leak_into_semantics():
    clause = StructuralHaving(
        aggregation_id="count", operator="greater_than", value=Decimal(5)
    )
    extra = StructuralHaving(
        aggregation_id="count", operator="less_than", value=Decimal(10)
    )
    expected = intent(
        aggregations=known((aggregate(),)),
        group_by=known((GROUP,)),
        having=known((clause,)),
    )
    actual = intent(
        aggregations=expected.aggregations,
        group_by=known((GROUP, FIELD)),
        having=known((clause, extra)),
    )
    assert compare(expected, actual, having="required_subset").passed is True
    assert compare(expected, actual, having="exact").passed is False
    assert compare(expected, actual, group_by="exact").passed is False
    assert compare(expected, actual, group_by="required_subset").passed is True
    assert "policy" not in expected.model_dump()


def test_top_level_distinct_is_independent_of_aggregate_distinct():
    expected = intent(
        aggregations=known((aggregate(distinct=True),)), distinct=known(False)
    )
    actual = intent(aggregations=expected.aggregations, distinct=known(True))
    assert compare(expected, actual, aggregations="exact").passed is True
    assert compare(expected, actual, distinct="exact").passed is False
