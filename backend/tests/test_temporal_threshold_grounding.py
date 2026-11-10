import pytest

from app.query_engine.openai_provider import build_safe_prompt_projection
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from scripts.semantic_ownership_fixtures import architecture_fixtures, fixture_packs, offline_schema


@pytest.mark.parametrize(
    "question",
    next(fixture.questions for fixture in architecture_fixtures() if fixture.id == "temporal_only"),
)
def test_laboratory_age_does_not_suggest_having(question: str) -> None:
    intent = _project_intent("laboratory", question, "old_sample")
    assert intent["group_by"] == [{"table": "samples", "column": "kind"}]
    assert intent["aggregations"][0]["function"] == "count"
    assert intent["having"] == []


@pytest.mark.parametrize(
    "age,population,expected",
    [
        ("more than 30 days", "", []),
        ("more than 30 days", " with more than 5 tickets", [("greater_than", 5)]),
        ("more than 30 days", " with at least 5 tickets", [("greater_than_or_equal", 5)]),
        ("at least one day", "", []),
        ("more than 1.5 hours", " with more than 5 tickets", [("greater_than", 5)]),
        ("more than twenty-one days", " with more than 5 tickets", [("greater_than", 5)]),
        ("more than twenty  one days", " with more than 5 tickets", [("greater_than", 5)]),
        ("more than 24 business hours", " with more than 5 tickets", [("greater_than", 5)]),
    ],
)
def test_ticket_age_and_group_size_are_independent(
    age: str, population: str, expected: list[tuple[str, int]]
) -> None:
    intent = _project_intent(
        "it_operations",
        f"Count open support tickets {age} old by category{population}.",
        "open_support_ticket",
    )
    assert intent["group_by"] == [{"table": "support_tickets", "column": "category"}]
    assert [(item["operator"], item["value"]) for item in intent["having"]] == expected


def test_nonbreaking_hyphen_attaches_age_quantity_to_unit() -> None:
    intent = _project_intent(
        "it_operations",
        "Count open support tickets more than 30\u2011day\u2011old by category with more than 5 tickets.",
        "open_support_ticket",
    )
    assert [(item["operator"], item["value"]) for item in intent["having"]] == [("greater_than", 5)]


@pytest.mark.parametrize(
    "counted,value",
    [
        ("5 30-day-old", 5),
        ("five day-old", 5),
        ("five day\u2011old", 5),
        ("five day shift", 5),
        ("5 second-level", 5),
        ("twenty one-day-old", 20),
    ],
)
def test_count_of_duration_qualified_tickets_survives(counted: str, value: int) -> None:
    intent = _project_intent(
        "it_operations",
        f"Count open support tickets by category with more than {counted} tickets.",
        "open_support_ticket",
    )
    assert [(item["operator"], item["value"]) for item in intent["having"]] == [("greater_than", value)]


def _project_intent(domain: str, question: str, expected_concept: str) -> dict:
    pack = fixture_packs()[domain]
    schema = offline_schema(pack)
    projection = build_semantic_catalog_projection(pack.semantic_catalog, question, schema, {})
    catalog = build_safe_prompt_projection(question, schema, {}, projection)["semantic_catalog"]
    assert expected_concept in {item["id"] for item in catalog["concepts"]}
    assert catalog["result_intent"]["required"] is None
    return catalog["result_intent"]["suggested"]
