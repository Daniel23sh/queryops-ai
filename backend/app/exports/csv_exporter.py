from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID


CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def rows_to_csv(
    columns: Iterable[str],
    rows: Iterable[Mapping[str, Any]],
    *,
    include_headers: bool = True,
) -> str:
    ordered_columns = [str(column) for column in columns]
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")

    if include_headers:
        writer.writerow(ordered_columns)

    for row in rows:
        writer.writerow([_cell_to_string(row.get(column)) for column in ordered_columns])

    return output.getvalue()


def _cell_to_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return _sanitize_csv_injection(value.isoformat())
    if isinstance(value, date):
        return _sanitize_csv_injection(value.isoformat())
    if isinstance(value, (Decimal, UUID)):
        return _sanitize_csv_injection(str(value))
    if isinstance(value, (dict, list)):
        return _sanitize_csv_injection(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                default=_json_default,
            )
        )
    return _sanitize_csv_injection(str(value))


def _sanitize_csv_injection(value: str) -> str:
    if value.startswith(CSV_INJECTION_PREFIXES):
        return f"'{value}"
    return value


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    raise TypeError(f"Value of type {type(value).__name__} is not JSON serializable.")
