from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from uuid import UUID

from app.models.product import DashboardCard


LAYOUT_SCHEMA_VERSION = 1
MAX_LAYOUT_Y = 10_000
MAX_COLUMN_NAME_LENGTH = 128
MAX_VALUE_COLUMNS = 8

BREAKPOINT_COLUMNS = {
    "desktop": 12,
    "tablet": 6,
    "mobile": 1,
}

VISUALIZATION_TYPES = frozenset(
    {
        "kpi",
        "table",
        "bar",
        "line",
        "area",
        "donut",
        "semicircle_gauge",
        "stacked_bar",
        "status_list",
    }
)
VISUALIZATION_MODES = frozenset({"auto", "manual"})

SIZE_POLICY: dict[str, dict[str, frozenset[tuple[int, int]]]] = {
    "kpi": {
        "desktop": frozenset({(3, 1), (4, 1), (6, 1)}),
        "tablet": frozenset({(3, 1), (4, 1), (6, 1)}),
        "mobile": frozenset({(1, 1), (1, 2)}),
    },
    "donut": {
        "desktop": frozenset({(3, 2), (4, 2), (6, 2)}),
        "tablet": frozenset({(3, 2), (4, 2), (6, 2)}),
        "mobile": frozenset({(1, 2), (1, 3)}),
    },
    "semicircle_gauge": {
        "desktop": frozenset({(3, 2), (4, 2), (6, 2)}),
        "tablet": frozenset({(3, 2), (4, 2), (6, 2)}),
        "mobile": frozenset({(1, 2), (1, 3)}),
    },
    "bar": {
        "desktop": frozenset(
            {(6, 2), (8, 2), (12, 2), (6, 3), (8, 3), (12, 3)}
        ),
        "tablet": frozenset({(6, 2), (6, 3)}),
        "mobile": frozenset({(1, 2), (1, 3)}),
    },
    "line": {
        "desktop": frozenset(
            {(6, 2), (8, 2), (12, 2), (6, 3), (8, 3), (12, 3)}
        ),
        "tablet": frozenset({(6, 2), (6, 3)}),
        "mobile": frozenset({(1, 2), (1, 3)}),
    },
    "area": {
        "desktop": frozenset(
            {(6, 2), (8, 2), (12, 2), (6, 3), (8, 3), (12, 3)}
        ),
        "tablet": frozenset({(6, 2), (6, 3)}),
        "mobile": frozenset({(1, 2), (1, 3)}),
    },
    "stacked_bar": {
        "desktop": frozenset(
            {(6, 2), (8, 2), (12, 2), (6, 3), (8, 3), (12, 3)}
        ),
        "tablet": frozenset({(6, 2), (6, 3)}),
        "mobile": frozenset({(1, 2), (1, 3)}),
    },
    "table": {
        "desktop": frozenset(
            {(6, 3), (8, 3), (12, 3), (6, 4), (8, 4), (12, 4)}
        ),
        "tablet": frozenset({(6, 3), (6, 4)}),
        "mobile": frozenset({(1, 3), (1, 4)}),
    },
    "status_list": {
        "desktop": frozenset({(4, 2), (6, 2), (8, 2), (6, 3)}),
        "tablet": frozenset({(4, 2), (6, 2), (6, 3)}),
        "mobile": frozenset({(1, 2), (1, 3)}),
    },
}

DEFAULT_SIZES: dict[str, dict[str, tuple[int, int]]] = {
    "kpi": {"desktop": (3, 1), "tablet": (3, 1), "mobile": (1, 1)},
    "donut": {"desktop": (3, 2), "tablet": (3, 2), "mobile": (1, 2)},
    "semicircle_gauge": {
        "desktop": (3, 2),
        "tablet": (3, 2),
        "mobile": (1, 2),
    },
    "bar": {"desktop": (6, 2), "tablet": (6, 2), "mobile": (1, 2)},
    "line": {"desktop": (6, 2), "tablet": (6, 2), "mobile": (1, 2)},
    "area": {"desktop": (6, 2), "tablet": (6, 2), "mobile": (1, 2)},
    "stacked_bar": {
        "desktop": (6, 2),
        "tablet": (6, 2),
        "mobile": (1, 2),
    },
    "table": {"desktop": (6, 3), "tablet": (6, 3), "mobile": (1, 3)},
    "status_list": {
        "desktop": (4, 2),
        "tablet": (4, 2),
        "mobile": (1, 2),
    },
}

_VISUALIZATION_FIELDS = frozenset({"mode", "type", "recommended_type", "mapping"})
_MAPPING_FIELDS = frozenset(
    {
        "category_column",
        "value_columns",
        "series_column",
        "label_column",
        "target_column",
    }
)
_LAYOUT_FIELDS = frozenset({"version", "desktop", "tablet", "mobile"})
_COORDINATE_FIELDS = frozenset({"x", "y", "w", "h"})
_SAFE_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def default_visualization(visualization_type: str = "table") -> dict[str, Any]:
    safe_type = visualization_type if visualization_type in VISUALIZATION_TYPES else "table"
    return {
        "mode": "auto",
        "type": safe_type,
        "recommended_type": safe_type,
        "mapping": {
            "category_column": None,
            "value_columns": [],
            "series_column": None,
            "label_column": None,
            "target_column": None,
        },
    }


def parse_visualization(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != _VISUALIZATION_FIELDS:
        return None

    mode = value.get("mode")
    visualization_type = value.get("type")
    recommended_type = value.get("recommended_type")
    mapping = value.get("mapping")
    if mode not in VISUALIZATION_MODES:
        return None
    if visualization_type not in VISUALIZATION_TYPES:
        return None
    if recommended_type not in VISUALIZATION_TYPES:
        return None
    if not isinstance(mapping, dict) or set(mapping) != _MAPPING_FIELDS:
        return None

    value_columns = mapping.get("value_columns")
    if not isinstance(value_columns, list) or len(value_columns) > MAX_VALUE_COLUMNS:
        return None
    parsed_value_columns: list[str] = []
    for column in value_columns:
        parsed_column = _parse_column_name(column)
        if parsed_column is None or parsed_column in parsed_value_columns:
            return None
        parsed_value_columns.append(parsed_column)

    parsed_mapping: dict[str, str | list[str] | None] = {
        "value_columns": parsed_value_columns
    }
    for key in (
        "category_column",
        "series_column",
        "label_column",
        "target_column",
    ):
        raw_column = mapping.get(key)
        if raw_column is None:
            parsed_mapping[key] = None
            continue
        parsed_column = _parse_column_name(raw_column)
        if parsed_column is None:
            return None
        parsed_mapping[key] = parsed_column

    return {
        "mode": mode,
        "type": visualization_type,
        "recommended_type": recommended_type,
        "mapping": parsed_mapping,
    }


def safe_visualization_for_card(card: DashboardCard) -> dict[str, Any]:
    config = card.config
    if isinstance(config, dict) and set(config) == {"visualization"}:
        parsed = parse_visualization(config.get("visualization"))
        if parsed is not None:
            return parsed
    return default_visualization(card.card_type)


def safe_config_for_card(card: DashboardCard) -> dict[str, Any]:
    return {"visualization": safe_visualization_for_card(card)}


def visualization_type_for_card(card: DashboardCard) -> str:
    return str(safe_visualization_for_card(card)["type"])


def parse_layout_for_card(
    value: Any,
    visualization_type: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != _LAYOUT_FIELDS:
        return None
    version = value.get("version")
    if isinstance(version, bool) or version != LAYOUT_SCHEMA_VERSION:
        return None

    parsed: dict[str, Any] = {"version": LAYOUT_SCHEMA_VERSION}
    for breakpoint, columns in BREAKPOINT_COLUMNS.items():
        coordinates = _parse_coordinates(
            value.get(breakpoint),
            columns=columns,
            mobile=breakpoint == "mobile",
        )
        if coordinates is None:
            return None
        if (coordinates["w"], coordinates["h"]) not in SIZE_POLICY[
            visualization_type
        ][breakpoint]:
            return None
        parsed[breakpoint] = coordinates
    return parsed


def parse_layout_item(
    value: Any,
    visualization_type: str,
) -> dict[str, dict[str, int]] | None:
    if not isinstance(value, dict) or set(value) != set(BREAKPOINT_COLUMNS):
        return None

    parsed: dict[str, dict[str, int]] = {}
    for breakpoint, columns in BREAKPOINT_COLUMNS.items():
        coordinates = _parse_coordinates(
            value.get(breakpoint),
            columns=columns,
            mobile=breakpoint == "mobile",
        )
        if coordinates is None:
            return None
        if (coordinates["w"], coordinates["h"]) not in SIZE_POLICY[
            visualization_type
        ][breakpoint]:
            return None
        parsed[breakpoint] = coordinates
    return parsed


def persisted_layout(
    coordinates: Mapping[str, Mapping[str, int]],
) -> dict[str, Any]:
    return {
        "version": LAYOUT_SCHEMA_VERSION,
        **{
            breakpoint: dict(coordinates[breakpoint])
            for breakpoint in BREAKPOINT_COLUMNS
        },
    }


def layouts_do_not_overlap(
    layouts: Mapping[UUID, Mapping[str, Mapping[str, int]]],
) -> bool:
    for breakpoint in BREAKPOINT_COLUMNS:
        items = [layout[breakpoint] for layout in layouts.values()]
        for index, first in enumerate(items):
            if any(_overlaps(first, second) for second in items[index + 1 :]):
                return False
    return True


def normalize_card_layouts(
    cards: Sequence[DashboardCard],
) -> dict[UUID, dict[str, Any]]:
    ordered_cards = sorted(
        cards,
        key=lambda card: (card.position, card.created_at, str(card.id)),
    )
    normalized: dict[UUID, dict[str, Any]] = {
        card.id: {"version": LAYOUT_SCHEMA_VERSION} for card in ordered_cards
    }

    for breakpoint, columns in BREAKPOINT_COLUMNS.items():
        placed: dict[UUID, dict[str, int]] = {}

        for card in ordered_cards:
            visualization_type = visualization_type_for_card(card)
            existing_layout = parse_layout_for_card(card.layout, visualization_type)
            if existing_layout is None:
                continue
            candidate = existing_layout[breakpoint]
            if not any(_overlaps(candidate, other) for other in placed.values()):
                placed[card.id] = dict(candidate)

        for card in ordered_cards:
            if card.id in placed:
                continue
            visualization_type = visualization_type_for_card(card)
            width, height = DEFAULT_SIZES[visualization_type][breakpoint]
            placed[card.id] = _first_available_coordinates(
                columns=columns,
                width=width,
                height=height,
                occupied=placed.values(),
            )

        for card in ordered_cards:
            normalized[card.id][breakpoint] = placed[card.id]

    return normalized


def derive_positions(
    layouts: Mapping[UUID, Mapping[str, Any]],
) -> dict[UUID, int]:
    ordered_ids = sorted(
        layouts,
        key=lambda card_id: (
            int(layouts[card_id]["desktop"]["y"]),
            int(layouts[card_id]["desktop"]["x"]),
            str(card_id),
        ),
    )
    return {card_id: position for position, card_id in enumerate(ordered_ids)}


def allowed_sizes_for(
    visualization_type: str,
    breakpoint: str,
) -> list[dict[str, int]]:
    safe_type = visualization_type if visualization_type in VISUALIZATION_TYPES else "table"
    if breakpoint not in BREAKPOINT_COLUMNS:
        return []
    return [
        {"w": width, "h": height}
        for width, height in sorted(SIZE_POLICY[safe_type][breakpoint])
    ]


def _parse_column_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    column = value.strip()
    if not column or len(column) > MAX_COLUMN_NAME_LENGTH:
        return None
    if _SAFE_COLUMN_RE.fullmatch(column) is None:
        return None
    return column


def _parse_coordinates(
    value: Any,
    *,
    columns: int,
    mobile: bool,
) -> dict[str, int] | None:
    if not isinstance(value, dict) or set(value) != _COORDINATE_FIELDS:
        return None

    parsed: dict[str, int] = {}
    for field in _COORDINATE_FIELDS:
        coordinate = value.get(field)
        if isinstance(coordinate, bool) or not isinstance(coordinate, int):
            return None
        parsed[field] = coordinate

    if parsed["x"] < 0 or parsed["y"] < 0 or parsed["y"] > MAX_LAYOUT_Y:
        return None
    if parsed["w"] <= 0 or parsed["h"] <= 0:
        return None
    if parsed["x"] + parsed["w"] > columns:
        return None
    if mobile and (parsed["x"] != 0 or parsed["w"] != 1):
        return None
    return parsed


def _first_available_coordinates(
    *,
    columns: int,
    width: int,
    height: int,
    occupied: Iterable[Mapping[str, int]],
) -> dict[str, int]:
    occupied_items = list(occupied)
    for y in range(MAX_LAYOUT_Y + 1):
        for x in range(columns - width + 1):
            candidate = {"x": x, "y": y, "w": width, "h": height}
            if not any(_overlaps(candidate, item) for item in occupied_items):
                return candidate
    raise ValueError("A normalized dashboard layout could not be generated.")


def _overlaps(first: Mapping[str, int], second: Mapping[str, int]) -> bool:
    return not (
        first["x"] + first["w"] <= second["x"]
        or second["x"] + second["w"] <= first["x"]
        or first["y"] + first["h"] <= second["y"]
        or second["y"] + second["h"] <= first["y"]
    )
