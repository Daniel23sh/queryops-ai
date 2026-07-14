from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.dashboards.editor import (
    allowed_sizes_for,
    derive_positions,
    layouts_do_not_overlap,
    normalize_card_layouts,
    parse_layout_item,
    parse_visualization,
)
from app.models.product import DashboardCard


def test_visualization_parser_accepts_only_the_safe_bounded_shape() -> None:
    visualization = _visualization("bar")
    visualization["mapping"] = {
        "category_column": "department",
        "value_columns": ["device_count"],
        "series_column": None,
        "label_column": None,
        "target_column": None,
    }

    assert parse_visualization(visualization) == visualization

    unsafe_values = [
        {**visualization, "rows": [{"secret": True}]},
        {**visualization, "colors": ["#fff"]},
        {**visualization, "type": "script"},
        {
            **visualization,
            "mapping": {
                **visualization["mapping"],
                "value_columns": ["device_count", "device_count"],
            },
        },
        {
            **visualization,
            "mapping": {
                **visualization["mapping"],
                "category_column": "COUNT(*)",
            },
        },
    ]
    assert all(parse_visualization(value) is None for value in unsafe_values)


@pytest.mark.parametrize(
    ("visualization_type", "breakpoint", "expected"),
    [
        ("kpi", "desktop", {"w": 3, "h": 1}),
        ("bar", "tablet", {"w": 6, "h": 2}),
        ("table", "mobile", {"w": 1, "h": 3}),
        ("kpi", "mobile", {"w": 1, "h": 2}),
        ("donut", "mobile", {"w": 1, "h": 3}),
        ("semicircle_gauge", "mobile", {"w": 1, "h": 2}),
    ],
)
def test_size_policy_exposes_stable_grid_unit_presets(
    visualization_type: str,
    breakpoint: str,
    expected: dict[str, int],
) -> None:
    assert expected in allowed_sizes_for(visualization_type, breakpoint)


def test_layout_parser_rejects_boolean_arbitrary_and_mobile_free_resize() -> None:
    valid = {
        "desktop": {"x": 0, "y": 0, "w": 6, "h": 3},
        "tablet": {"x": 0, "y": 0, "w": 6, "h": 3},
        "mobile": {"x": 0, "y": 0, "w": 1, "h": 3},
    }
    assert parse_layout_item(valid, "table") == valid

    boolean_x = {**valid, "desktop": {**valid["desktop"], "x": True}}
    arbitrary_size = {**valid, "desktop": {**valid["desktop"], "w": 5}}
    mobile_resize = {**valid, "mobile": {**valid["mobile"], "w": 2}}
    assert parse_layout_item(boolean_x, "table") is None
    assert parse_layout_item(arbitrary_size, "table") is None
    assert parse_layout_item(mobile_resize, "table") is None


def test_normalization_is_deterministic_and_positions_follow_desktop_reading_order() -> None:
    cards = [
        _card(position=7),
        _card(position=2),
        _card(position=4),
    ]
    first = normalize_card_layouts(cards)
    second = normalize_card_layouts(list(reversed(cards)))

    assert first == second
    assert layouts_do_not_overlap(first)
    positions = derive_positions(first)
    ordered = sorted(cards, key=lambda card: positions[card.id])
    assert [card.position for card in ordered] == [2, 4, 7]
    assert sorted(positions.values()) == [0, 1, 2]


def _card(*, position: int) -> DashboardCard:
    now = datetime(2026, 7, 14, 12, position, tzinfo=UTC)
    return DashboardCard(
        id=uuid.uuid4(),
        dashboard_id=uuid.uuid4(),
        title=f"Card {position}",
        card_type="table",
        position=position,
        layout=None,
        config=None,
        created_at=now,
        updated_at=now,
    )


def _visualization(visualization_type: str) -> dict:
    return {
        "mode": "auto",
        "type": visualization_type,
        "recommended_type": visualization_type,
        "mapping": {
            "category_column": None,
            "value_columns": [],
            "series_column": None,
            "label_column": None,
            "target_column": None,
        },
    }
