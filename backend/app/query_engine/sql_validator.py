from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


PUBLIC_SQL_VALIDATION_ERROR = "SQL is not allowed for safe read-only querying."
DEFAULT_QUERY_LIMIT = 100
MAX_QUERY_LIMIT = 500
FORBIDDEN_TABLES = frozenset({"it_audit_events"})
EXCLUDED_LLM_EXPOSURE_LEVELS = frozenset({"none"})
PROHIBITED_KEYWORDS = frozenset(
    {
        "alter",
        "call",
        "copy",
        "create",
        "delete",
        "do",
        "drop",
        "execute",
        "explain",
        "grant",
        "insert",
        "merge",
        "reset",
        "revoke",
        "set",
        "truncate",
        "update",
        "upsert",
    }
)
PROHIBITED_PHRASES = (
    re.compile(r"\bfor\s+update\b", re.IGNORECASE),
    re.compile(r"\bfor\s+share\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class SQLValidationOptions:
    default_limit: int = DEFAULT_QUERY_LIMIT
    max_limit: int = MAX_QUERY_LIMIT


@dataclass(frozen=True)
class SQLValidationResult:
    valid: bool
    sanitized_sql: str | None
    referenced_tables: list[str]
    referenced_columns: dict[str, list[str]] = field(default_factory=dict)
    error_code: str | None = None
    reason: str | None = None
    public_error: str | None = None


class SQLValidator:
    def __init__(self, options: SQLValidationOptions | None = None) -> None:
        self.options = options or SQLValidationOptions()

    def validate(
        self,
        sql: str,
        schema_context: dict[str, Any],
    ) -> SQLValidationResult:
        if not isinstance(sql, str) or not sql.strip():
            return _deny("invalid_sql", "SQL must be a non-empty string.")

        if _contains_comment(sql):
            return _deny("comments_not_allowed", "SQL comments are not allowed.")

        statement = sql.strip()
        if _starts_with_prohibited_statement(statement):
            return _deny(
                "prohibited_statement",
                "SQL contains a prohibited statement or command.",
            )
        if _has_multiple_statements(statement):
            return _deny("multiple_statements", "Only one SQL statement is allowed.")
        if statement.endswith(";"):
            statement = statement[:-1].strip()

        normalized_sql = _normalize_sql(statement)
        masked_sql = _mask_string_literals(normalized_sql)
        if masked_sql is None:
            return _deny("invalid_sql", "SQL contains an unterminated string literal.")

        if _contains_prohibited_statement(masked_sql):
            return _deny(
                "prohibited_statement",
                "SQL contains a prohibited statement or command.",
            )

        if not _is_select_statement(masked_sql):
            return _deny("not_read_only_select", "SQL must be SELECT-only.")

        if _select_star_is_used(masked_sql):
            return _deny("select_star_not_allowed", "SELECT * is not allowed.")

        context = _build_schema_context_index(schema_context)
        table_refs, alias_map = _extract_referenced_tables(masked_sql)
        cte_names = _extract_cte_names(masked_sql)
        referenced_tables = sorted(
            {
                table_name
                for table_name in table_refs
                if table_name not in cte_names
            }
        )
        if not referenced_tables:
            return _deny("no_table_reference", "SQL must reference an allowed table.")

        table_error = _validate_table_references(referenced_tables, context)
        if table_error is not None:
            return table_error

        limit_sql_or_error = _apply_limit(normalized_sql, masked_sql, self.options)
        if isinstance(limit_sql_or_error, SQLValidationResult):
            return limit_sql_or_error

        return SQLValidationResult(
            valid=True,
            sanitized_sql=limit_sql_or_error,
            referenced_tables=referenced_tables,
            referenced_columns=_extract_referenced_columns(
                masked_sql,
                referenced_tables,
                alias_map,
                context.allowed_columns,
            ),
            error_code=None,
            reason=None,
            public_error=None,
        )


def validate_sql(
    sql: str,
    schema_context: dict[str, Any],
    *,
    options: SQLValidationOptions | None = None,
) -> SQLValidationResult:
    return SQLValidator(options).validate(sql, schema_context)


@dataclass(frozen=True)
class _SchemaContextIndex:
    allowed_tables: frozenset[str]
    table_metadata: dict[str, dict[str, Any]]
    allowed_columns: dict[str, frozenset[str]]


def _deny(error_code: str, reason: str) -> SQLValidationResult:
    return SQLValidationResult(
        valid=False,
        sanitized_sql=None,
        referenced_tables=[],
        referenced_columns={},
        error_code=error_code,
        reason=reason,
        public_error=PUBLIC_SQL_VALIDATION_ERROR,
    )


def _contains_comment(sql: str) -> bool:
    return any(marker in sql for marker in ("--", "/*", "*/", "#"))


def _has_multiple_statements(sql: str) -> bool:
    stripped = sql.strip()
    if ";" not in stripped:
        return False
    if stripped.endswith(";"):
        return ";" in stripped[:-1]
    return True


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.strip().split())


def _mask_string_literals(sql: str) -> str | None:
    chars = list(sql)
    index = 0
    while index < len(chars):
        if chars[index] != "'":
            index += 1
            continue

        index += 1
        closed = False
        while index < len(chars):
            if chars[index] == "'":
                if index + 1 < len(chars) and chars[index + 1] == "'":
                    chars[index] = " "
                    chars[index + 1] = " "
                    index += 2
                    continue
                closed = True
                index += 1
                break
            chars[index] = " "
            index += 1
        if not closed:
            return None
    return "".join(chars)


def _contains_prohibited_statement(masked_sql: str) -> bool:
    lowered = masked_sql.lower()
    if any(pattern.search(masked_sql) for pattern in PROHIBITED_PHRASES):
        return True
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", lowered)
        for keyword in PROHIBITED_KEYWORDS
    )


def _starts_with_prohibited_statement(sql: str) -> bool:
    match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\b", sql)
    return match is not None and match.group(1).lower() in PROHIBITED_KEYWORDS


def _is_select_statement(masked_sql: str) -> bool:
    lowered = masked_sql.lstrip().lower()
    if not (lowered.startswith("select ") or lowered == "select" or lowered.startswith("with ")):
        return False
    return _has_top_level_select(masked_sql)


def _has_top_level_select(masked_sql: str) -> bool:
    depths = _depths_by_position(masked_sql)
    for match in re.finditer(r"\bselect\b", masked_sql, flags=re.IGNORECASE):
        if depths[match.start()] == 0:
            return True
    return False


def _select_star_is_used(masked_sql: str) -> bool:
    for match in re.finditer(
        r"\bselect\b(?P<select_list>.*?)\bfrom\b",
        masked_sql,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        select_list = match.group("select_list").strip()
        expressions = [item.strip() for item in select_list.split(",")]
        if any(expression == "*" for expression in expressions):
            return True
        if any(re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\.\s*\*$", expression) for expression in expressions):
            return True
    return False


def _build_schema_context_index(schema_context: dict[str, Any]) -> _SchemaContextIndex:
    allowed_tables = frozenset(str(name) for name in schema_context.get("allowed_tables", []))
    table_metadata = {
        str(table.get("name")): table
        for table in schema_context.get("tables", [])
        if isinstance(table, dict) and table.get("name")
    }

    explicit_allowed_columns = schema_context.get("allowed_columns", {})
    allowed_columns: dict[str, frozenset[str]] = {}
    for table_name in allowed_tables:
        columns = explicit_allowed_columns.get(table_name)
        if columns is None:
            table = table_metadata.get(table_name, {})
            columns = [
                column.get("name")
                for column in table.get("columns", [])
                if isinstance(column, dict)
            ]
        allowed_columns[table_name] = frozenset(str(column) for column in columns)

    return _SchemaContextIndex(
        allowed_tables=allowed_tables,
        table_metadata=table_metadata,
        allowed_columns=allowed_columns,
    )


def _extract_referenced_tables(masked_sql: str) -> tuple[list[str], dict[str, str]]:
    tokens = _tokenize(masked_sql)
    references: list[str] = []
    alias_map: dict[str, str] = {}
    expect_table = False
    in_table_source = False
    index = 0

    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()

        if lowered in {"from", "join"}:
            expect_table = True
            in_table_source = True
            index += 1
            continue

        if lowered in {"where", "group", "order", "having", "limit", "union", "intersect", "except", "on"}:
            expect_table = False
            in_table_source = False
            index += 1
            continue

        if in_table_source and token == ",":
            expect_table = True
            index += 1
            continue

        if expect_table:
            if token == "(":
                expect_table = False
                index += 1
                continue
            if lowered in {"lateral", "only"}:
                index += 1
                continue
            if _is_identifier(token):
                table_name, next_index = _consume_table_name(tokens, index)
                references.append(table_name)
                alias, alias_index = _consume_alias(tokens, next_index)
                if alias is not None:
                    alias_map[alias] = table_name
                    next_index = alias_index
                expect_table = False
                index = next_index
                continue
            expect_table = False

        index += 1

    return references, alias_map


def _extract_cte_names(masked_sql: str) -> frozenset[str]:
    if not masked_sql.lstrip().lower().startswith("with "):
        return frozenset()
    return frozenset(
        match.group(1).lower()
        for match in re.finditer(
            r"(?:\bwith|,)\s+([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(",
            masked_sql,
            flags=re.IGNORECASE,
        )
    )


def _validate_table_references(
    referenced_tables: list[str],
    context: _SchemaContextIndex,
) -> SQLValidationResult | None:
    for table_name in referenced_tables:
        if table_name in FORBIDDEN_TABLES:
            return _deny("forbidden_table", f"Table is never queryable: {table_name}.")

        table = context.table_metadata.get(table_name)
        if table_name not in context.allowed_tables or table is None:
            return _deny("table_not_allowed", f"Table is not in schema context: {table_name}.")

        resource = table.get("resource", {})
        if (
            resource.get("is_queryable") is not True
            or resource.get("llm_exposure_level") in EXCLUDED_LLM_EXPOSURE_LEVELS
        ):
            return _deny("non_queryable_resource", f"Table is not queryable: {table_name}.")
    return None


def _apply_limit(
    normalized_sql: str,
    masked_sql: str,
    options: SQLValidationOptions,
) -> str | SQLValidationResult:
    top_level_limits = _find_top_level_limits(masked_sql)
    if len(top_level_limits) > 1:
        return _deny("invalid_limit", "Only one top-level LIMIT is allowed.")
    if not top_level_limits:
        return f"{normalized_sql} LIMIT {options.default_limit}"

    limit = top_level_limits[0]
    raw_value = limit["value"]
    if not raw_value.isdigit():
        return _deny("invalid_limit", "LIMIT must be a numeric literal.")

    value = int(raw_value)
    if value <= options.max_limit:
        return normalized_sql

    return (
        normalized_sql[: limit["value_start"]]
        + str(options.max_limit)
        + normalized_sql[limit["value_end"] :]
    )


def _find_top_level_limits(masked_sql: str) -> list[dict[str, Any]]:
    depths = _depths_by_position(masked_sql)
    limits: list[dict[str, Any]] = []
    for match in re.finditer(
        r"\blimit\s+(?P<value>[A-Za-z0-9_]+)",
        masked_sql,
        flags=re.IGNORECASE,
    ):
        if depths[match.start()] == 0:
            limits.append(
                {
                    "value": match.group("value"),
                    "value_start": match.start("value"),
                    "value_end": match.end("value"),
                }
            )
    return limits


def _extract_referenced_columns(
    masked_sql: str,
    referenced_tables: list[str],
    alias_map: dict[str, str],
    allowed_columns: dict[str, frozenset[str]],
) -> dict[str, list[str]]:
    tokens = [token for token in _tokenize(masked_sql) if _is_identifier(token)]
    token_set = {token.lower() for token in tokens}
    referenced_columns: dict[str, set[str]] = {
        table_name: set() for table_name in referenced_tables
    }

    for table_name in referenced_tables:
        for column_name in allowed_columns.get(table_name, frozenset()):
            if column_name.lower() in token_set:
                referenced_columns[table_name].add(column_name)

    for alias, table_name in alias_map.items():
        pattern = re.compile(
            rf"\b{re.escape(alias)}\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\b",
            flags=re.IGNORECASE,
        )
        for match in pattern.finditer(masked_sql):
            column_name = match.group(1)
            if column_name in allowed_columns.get(table_name, frozenset()):
                referenced_columns.setdefault(table_name, set()).add(column_name)

    return {
        table_name: sorted(columns)
        for table_name, columns in referenced_columns.items()
        if columns
    }


def _tokenize(masked_sql: str) -> list[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[().,]", masked_sql)


def _is_identifier(token: str) -> bool:
    return re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", token) is not None


def _consume_table_name(tokens: list[str], index: int) -> tuple[str, int]:
    names = [tokens[index]]
    cursor = index + 1
    while (
        cursor + 1 < len(tokens)
        and tokens[cursor] == "."
        and _is_identifier(tokens[cursor + 1])
    ):
        names.append(tokens[cursor + 1])
        cursor += 2
    return names[-1].lower(), cursor


def _consume_alias(tokens: list[str], index: int) -> tuple[str | None, int]:
    if index >= len(tokens):
        return None, index

    lowered = tokens[index].lower()
    if lowered == "as" and index + 1 < len(tokens) and _is_identifier(tokens[index + 1]):
        return tokens[index + 1].lower(), index + 2
    if lowered in {"where", "group", "order", "having", "limit", "union", "intersect", "except", "join", "on"}:
        return None, index
    if _is_identifier(tokens[index]):
        return tokens[index].lower(), index + 1
    return None, index


def _depths_by_position(sql: str) -> list[int]:
    depths = [0] * (len(sql) + 1)
    depth = 0
    for index, char in enumerate(sql):
        depths[index] = depth
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
    depths[len(sql)] = depth
    return depths
