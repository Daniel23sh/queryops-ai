from __future__ import annotations

import re
from typing import Any

from app.query_engine.domain_pack import QueryTemplate


def render_template_sql(template: QueryTemplate) -> str | None:
    if template.sql is None:
        return None

    sql = template.sql
    for parameter in template.parameters:
        if parameter.default is None:
            return None
        sql = re.sub(
            rf":{re.escape(parameter.name)}\b",
            _sql_literal(parameter.default),
            sql,
        )
    return sql


def _sql_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"
