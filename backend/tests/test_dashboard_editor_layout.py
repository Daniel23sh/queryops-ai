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


def test_size_policy_exposes_complete_table_presets() -> None:
    assert _size_pairs("table") == {
        "desktop": {
            (4, 2), (4, 3), (4, 4),
            (6, 2), (6, 3), (6, 4),
            (8, 2), (8, 3), (8, 4),
            (12, 2), (12, 3), (12, 4),
        },
        "tablet": {
            (3, 2), (3, 3), (3, 4),
            (4, 2), (4, 3), (4, 4),
            (6, 2), (6, 3), (6, 4),
        },
        "mobile": {(1, 2), (1, 3), (1, 4)},
    }


def test_size_policy_exposes_complete_cartesian_chart_presets() -> None:
    expected = {
        "desktop": {
            (4, 2), (4, 3),
            (6, 2), (6, 3), (6, 4),
            (8, 2), (8, 3), (8, 4),
            (12, 2), (12, 3), (12, 4),
        },
        "tablet": {(3, 2), (3, 3), (4, 2), (4, 3), (6, 2), (6, 3), (6, 4)},
        "mobile": {(1, 2), (1, 3)},
    }
    for visualization_type in ("bar", "line", "area", "stacked_bar"):
        assert _size_pairs(visualization_type) == expected


def test_size_policy_exposes_complete_donut_and_gauge_presets() -> None:
    expected = {
        "desktop": {(3, 2), (3, 3), (4, 2), (4, 3), (6, 2), (6, 3)},
        "tablet": {(3, 2), (3, 3), (4, 2), (4, 3), (6, 2), (6, 3)},
        "mobile": {(1, 2), (1, 3)},
    }
    assert _size_pairs("donut") == expected
    assert _size_pairs("semicircle_gauge") == expected


def test_size_policy_exposes_complete_status_list_presets() -> None:
    assert _size_pairs("status_list") == {
        "desktop": {(4, 2), (4, 3), (6, 2), (6, 3), (8, 2), (8, 3), (8, 4), (12, 4)},
        "tablet": {(4, 2), (4, 3), (6, 2), (6, 3), (6, 4)},
        "mobile": {(1, 2), (1, 3)},
    }


def test_size_policy_preserves_existing_kpi_presets() -> None:
    assert _size_pairs("kpi") == {
        "desktop": {(3, 1), (4, 1), (6, 1)},
        "tablet": {(3, 1), (4, 1), (6, 1)},
        "mobile": {(1, 1), (1, 2)},
    }


@pytest.mark.parametrize(
    ("visualization_type", "layout"),
    [
        (
            "table",
            {
                "desktop": {"x": 0, "y": 0, "w": 12, "h": 2},
                "tablet": {"x": 0, "y": 0, "w": 3, "h": 2},
                "mobile": {"x": 0, "y": 0, "w": 1, "h": 2},
            },
        ),
        (
            "bar",
            {
                "desktop": {"x": 0, "y": 0, "w": 4, "h": 2},
                "tablet": {"x": 0, "y": 0, "w": 3, "h": 2},
                "mobile": {"x": 0, "y": 0, "w": 1, "h": 2},
            },
        ),
        (
            "line",
            {
                "desktop": {"x": 0, "y": 0, "w": 12, "h": 4},
                "tablet": {"x": 0, "y": 0, "w": 6, "h": 4},
                "mobile": {"x": 0, "y": 0, "w": 1, "h": 3},
            },
        ),
        (
            "donut",
            {
                "desktop": {"x": 0, "y": 0, "w": 6, "h": 3},
                "tablet": {"x": 0, "y": 0, "w": 6, "h": 3},
                "mobile": {"x": 0, "y": 0, "w": 1, "h": 3},
            },
        ),
        (
            "semicircle_gauge",
            {
                "desktop": {"x": 0, "y": 0, "w": 6, "h": 3},
                "tablet": {"x": 0, "y": 0, "w": 6, "h": 3},
                "mobile": {"x": 0, "y": 0, "w": 1, "h": 3},
            },
        ),
        (
            "status_list",
            {
                "desktop": {"x": 0, "y": 0, "w": 12, "h": 4},
                "tablet": {"x": 0, "y": 0, "w": 6, "h": 4},
                "mobile": {"x": 0, "y": 0, "w": 1, "h": 3},
            },
        ),
    ],
)
def test_layout_parser_accepts_new_resize_presets(
    visualization_type: str,
    layout: dict[str, dict[str, int]],
) -> None:
    assert parse_layout_item(layout, visualization_type) == layout


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
    compact_bar = {
        "desktop": {"x": 0, "y": 0, "w": 4, "h": 4},
        "tablet": {"x": 0, "y": 0, "w": 4, "h": 3},
        "mobile": {"x": 0, "y": 0, "w": 1, "h": 2},
    }
    assert parse_layout_item(boolean_x, "table") is None
    assert parse_layout_item(arbitrary_size, "table") is None
    assert parse_layout_item(mobile_resize, "table") is None
    assert parse_layout_item(compact_bar, "bar") is None


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
    assert all(
        {
            breakpoint: (item[breakpoint]["w"], item[breakpoint]["h"])
            for breakpoint in ("desktop", "tablet", "mobile")
        }
        == {"desktop": (6, 3), "tablet": (6, 3), "mobile": (1, 3)}
        for item in first.values()
    )


def _size_pairs(visualization_type: str) -> dict[str, set[tuple[int, int]]]:
    return {
        breakpoint: {
            (size["w"], size["h"])
            for size in allowed_sizes_for(visualization_type, breakpoint)
        }
        for breakpoint in ("desktop", "tablet", "mobile")
    }


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
