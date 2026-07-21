from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypeVar

from app.evaluation.contracts import (
    CaseType,
    ComparisonMode,
    EvaluationCase,
    EvaluationDifficulty,
    EvaluationSet,
    ExpectedOutcome,
    ExpectedTableColumns,
    RequestingRole,
    ScopeMode,
)
from app.query_engine.domain_pack import DomainPack
from app.query_engine.domain_pack_loader import (
    IT_OPERATIONS_DOMAIN_PACK_DIR,
    load_it_operations_domain_pack,
)
from app.query_engine.sql_validator import validate_sql


EVALUATION_DATASET_PATH = IT_OPERATIONS_DOMAIN_PACK_DIR / "evaluation_questions.yaml"
EXPECTED_CASE_COUNT = 40
EXPECTED_DIFFICULTY_COUNTS = {
    EvaluationDifficulty.EASY: 10,
    EvaluationDifficulty.MEDIUM: 15,
    EvaluationDifficulty.HARD: 10,
    EvaluationDifficulty.SECURITY: 5,
}
DATASET_FIELDS = frozenset({"dataset_id", "domain_id", "version", "cases"})
CASE_FIELDS = frozenset(
    {
        "id",
        "question",
        "category",
        "difficulty",
        "case_type",
        "requesting_role",
        "required_scope_type",
        "scope_mode",
        "expected_outcome",
        "expected_tables",
        "expected_columns",
        "baseline_sql",
        "requires_join",
        "clarification_expected",
        "security_sensitive",
        "comparison_mode",
        "numeric_tolerance",
        "stable_key_columns",
        "template_id",
    }
)
CASE_ID = re.compile(r"^itops-(easy|medium|hard|security)-[0-9]{3}$")
SUPPORTED_SCOPE_TYPES = frozenset({"department", "global"})
TEnum = TypeVar("TEnum")


class EvaluationDatasetValidationError(ValueError):
    """Raised when evaluator-only dataset material violates its strict contract."""


def load_it_operations_evaluation_set(
    path: str | Path = EVALUATION_DATASET_PATH,
    *,
    domain_pack: DomainPack | None = None,
) -> EvaluationSet:
    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise EvaluationDatasetValidationError(
            f"Evaluation dataset file not found: {dataset_path.name}"
        )

    try:
        document = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationDatasetValidationError(
            f"Invalid JSON-compatible evaluation dataset: {dataset_path.name}"
        ) from exc

    root = _mapping(document, "evaluation dataset")
    _require_exact_fields(root, DATASET_FIELDS, "evaluation dataset")
    pack = domain_pack or load_it_operations_domain_pack()
    dataset_id = _string(root["dataset_id"], "dataset_id")
    domain_id = _string(root["domain_id"], "domain_id")
    version = _string(root["version"], "version")
    if domain_id != pack.domain_id:
        raise EvaluationDatasetValidationError("Evaluation domain_id does not match domain pack")

    raw_cases = _list(root["cases"], "cases")
    cases = tuple(_parse_case(item, index, pack) for index, item in enumerate(raw_cases))
    _validate_complete_set(cases)
    return EvaluationSet(
        dataset_id=dataset_id,
        domain_id=domain_id,
        version=version,
        cases=tuple(sorted(cases, key=lambda case: case.id)),
    )


def _parse_case(raw: Any, index: int, pack: DomainPack) -> EvaluationCase:
    path = f"cases[{index}]"
    item = _mapping(raw, path)
    _require_exact_fields(item, CASE_FIELDS, path)
    case_id = _string(item["id"], f"{path}.id")
    if not CASE_ID.fullmatch(case_id):
        raise EvaluationDatasetValidationError(f"{path}.id is not a stable case id")

    difficulty = _enum(EvaluationDifficulty, item["difficulty"], f"{path}.difficulty")
    case_type = _enum(CaseType, item["case_type"], f"{path}.case_type")
    requesting_role = _enum(
        RequestingRole, item["requesting_role"], f"{path}.requesting_role"
    )
    scope_mode = _enum(ScopeMode, item["scope_mode"], f"{path}.scope_mode")
    expected_outcome = _enum(
        ExpectedOutcome, item["expected_outcome"], f"{path}.expected_outcome"
    )
    comparison_mode = _enum(
        ComparisonMode, item["comparison_mode"], f"{path}.comparison_mode"
    )
    required_scope_type = _optional_string(
        item["required_scope_type"], f"{path}.required_scope_type"
    )
    if required_scope_type not in SUPPORTED_SCOPE_TYPES | {None}:
        raise EvaluationDatasetValidationError(f"{path}.required_scope_type is unknown")

    expected_tables = _unique_strings(item["expected_tables"], f"{path}.expected_tables")
    expected_columns = _parse_expected_columns(item["expected_columns"], path, pack)
    table_names = pack.tables_by_name
    for table_name in expected_tables:
        if table_name not in table_names:
            raise EvaluationDatasetValidationError(f"{path} references unknown table: {table_name}")
    if {entry.table for entry in expected_columns} != set(expected_tables):
        raise EvaluationDatasetValidationError(
            f"{path}.expected_columns must cover exactly expected_tables"
        )

    baseline_sql = _optional_string(item["baseline_sql"], f"{path}.baseline_sql")
    requires_join = _boolean(item["requires_join"], f"{path}.requires_join")
    clarification_expected = _boolean(
        item["clarification_expected"], f"{path}.clarification_expected"
    )
    security_sensitive = _boolean(
        item["security_sensitive"], f"{path}.security_sensitive"
    )
    tolerance = _optional_decimal(item["numeric_tolerance"], f"{path}.numeric_tolerance")
    stable_keys = _unique_strings(
        item["stable_key_columns"], f"{path}.stable_key_columns"
    )
    template_id = _optional_string(item["template_id"], f"{path}.template_id")
    if template_id is not None and template_id not in pack.templates_by_id:
        raise EvaluationDatasetValidationError(f"{path}.template_id is unknown")

    case = EvaluationCase(
        id=case_id,
        question=_string(item["question"], f"{path}.question"),
        category=_string(item["category"], f"{path}.category"),
        difficulty=difficulty,
        case_type=case_type,
        requesting_role=requesting_role,
        required_scope_type=required_scope_type,
        scope_mode=scope_mode,
        expected_outcome=expected_outcome,
        expected_tables=expected_tables,
        expected_columns=expected_columns,
        baseline_sql=baseline_sql,
        requires_join=requires_join,
        clarification_expected=clarification_expected,
        security_sensitive=security_sensitive,
        comparison_mode=comparison_mode,
        numeric_tolerance=tolerance,
        stable_key_columns=stable_keys,
        template_id=template_id,
    )
    _validate_case_expectations(case, path, pack)
    return case


def _parse_expected_columns(
    raw: Any,
    case_path: str,
    pack: DomainPack,
) -> tuple[ExpectedTableColumns, ...]:
    mapping = _mapping(raw, f"{case_path}.expected_columns")
    entries: list[ExpectedTableColumns] = []
    for table_name in sorted(mapping):
        if not isinstance(table_name, str) or not table_name:
            raise EvaluationDatasetValidationError(
                f"{case_path}.expected_columns has an invalid table name"
            )
        table = pack.tables_by_name.get(table_name)
        if table is None:
            raise EvaluationDatasetValidationError(
                f"{case_path}.expected_columns references unknown table: {table_name}"
            )
        columns = _unique_strings(
            mapping[table_name], f"{case_path}.expected_columns.{table_name}"
        )
        for column in columns:
            if column not in table.columns_by_name:
                raise EvaluationDatasetValidationError(
                    f"{case_path} references unknown column: {table_name}.{column}"
                )
        entries.append(ExpectedTableColumns(table=table_name, columns=columns))
    return tuple(entries)


def _validate_case_expectations(case: EvaluationCase, path: str, pack: DomainPack) -> None:
    expected_case_outcomes = {
        CaseType.TEMPLATE_QUERY: ExpectedOutcome.SUCCESS,
        CaseType.FREE_QUERY: ExpectedOutcome.SUCCESS,
        CaseType.AUTHORIZATION: ExpectedOutcome.DENIED,
        CaseType.UNSAFE_SQL: ExpectedOutcome.UNSAFE_BLOCKED,
        CaseType.CLARIFICATION: ExpectedOutcome.CLARIFICATION,
    }
    if case.expected_outcome is not expected_case_outcomes[case.case_type]:
        raise EvaluationDatasetValidationError(f"{path} has contradictory case outcome")
    is_success = case.expected_outcome is ExpectedOutcome.SUCCESS
    if is_success != (case.baseline_sql is not None):
        raise EvaluationDatasetValidationError(
            f"{path} baseline_sql must exist only for successful executable cases"
        )
    if case.clarification_expected != (
        case.expected_outcome is ExpectedOutcome.CLARIFICATION
    ):
        raise EvaluationDatasetValidationError(f"{path} has contradictory clarification expectation")
    if is_success == (case.comparison_mode is ComparisonMode.NONE):
        raise EvaluationDatasetValidationError(f"{path} has contradictory comparison mode")
    if case.requires_join and len(case.expected_tables) < 2:
        raise EvaluationDatasetValidationError(f"{path} requires a join but names fewer than two tables")
    if case.comparison_mode is ComparisonMode.STABLE_KEYS and not case.stable_key_columns:
        raise EvaluationDatasetValidationError(f"{path} stable-key comparison requires keys")
    if case.comparison_mode is not ComparisonMode.STABLE_KEYS and case.stable_key_columns:
        raise EvaluationDatasetValidationError(f"{path} defines unused stable keys")
    if case.numeric_tolerance is not None and not is_success:
        raise EvaluationDatasetValidationError(f"{path} defines tolerance for a non-result case")
    if case.difficulty is EvaluationDifficulty.SECURITY and not case.security_sensitive:
        raise EvaluationDatasetValidationError(f"{path} security case must be security-sensitive")
    if case.scope_mode is ScopeMode.NONE and case.required_scope_type is not None:
        raise EvaluationDatasetValidationError(f"{path} has scope type without a scope mode")
    if case.scope_mode is not ScopeMode.NONE and case.required_scope_type is None:
        raise EvaluationDatasetValidationError(f"{path} has scope mode without a scope type")
    if case.baseline_sql is not None:
        _validate_baseline_sql(case, path, pack)


def _validate_baseline_sql(case: EvaluationCase, path: str, pack: DomainPack) -> None:
    context = {
        "allowed_tables": list(pack.allowed_resource_table_names),
        "allowed_columns": {
            table.name: [column.name for column in table.columns]
            for table in pack.tables
            if table.queryable
        },
        "tables": [
            {
                "name": table.name,
                "columns": [{"name": column.name} for column in table.columns],
                "resource": {
                    "is_queryable": table.queryable,
                    "llm_exposure_level": "full" if table.queryable else "none",
                },
            }
            for table in pack.tables
            if table.queryable
        ],
    }
    validation = validate_sql(case.baseline_sql or "", context)
    if not validation.valid:
        raise EvaluationDatasetValidationError(
            f"{path}.baseline_sql is not safe read-only SQL: {validation.error_code}"
        )
    if tuple(validation.referenced_tables) != tuple(sorted(case.expected_tables)):
        raise EvaluationDatasetValidationError(
            f"{path}.baseline_sql tables do not match expected_tables"
        )
    for table_name in validation.referenced_tables:
        if table_name not in pack.allowed_resource_table_names or not pack.table(table_name).queryable:
            raise EvaluationDatasetValidationError(
                f"{path}.baseline_sql references a protected resource"
            )


def _validate_complete_set(cases: tuple[EvaluationCase, ...]) -> None:
    if len(cases) != EXPECTED_CASE_COUNT:
        raise EvaluationDatasetValidationError(
            f"Evaluation dataset must contain exactly {EXPECTED_CASE_COUNT} cases"
        )
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise EvaluationDatasetValidationError("Evaluation dataset contains duplicate case ids")
    counts = Counter(case.difficulty for case in cases)
    if counts != Counter(EXPECTED_DIFFICULTY_COUNTS):
        raise EvaluationDatasetValidationError("Evaluation dataset has an incorrect difficulty distribution")


def _require_exact_fields(mapping: Mapping[str, Any], fields: frozenset[str], path: str) -> None:
    missing = sorted(fields - set(mapping))
    unknown = sorted(set(mapping) - fields)
    if missing:
        raise EvaluationDatasetValidationError(f"{path} is missing fields: {', '.join(missing)}")
    if unknown:
        raise EvaluationDatasetValidationError(f"{path} has unknown fields: {', '.join(unknown)}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationDatasetValidationError(f"{path} must be a mapping")
    return value


def _list(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise EvaluationDatasetValidationError(f"{path} must be a list")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationDatasetValidationError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise EvaluationDatasetValidationError(f"{path} must be a boolean")
    return value


def _unique_strings(value: Any, path: str) -> tuple[str, ...]:
    items = tuple(_string(item, path) for item in _list(value, path))
    if len(items) != len(set(items)):
        raise EvaluationDatasetValidationError(f"{path} must not contain duplicates")
    return tuple(sorted(items))


def _optional_decimal(value: Any, path: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EvaluationDatasetValidationError(f"{path} must be a decimal string or null")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise EvaluationDatasetValidationError(f"{path} must be a valid decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise EvaluationDatasetValidationError(f"{path} must be finite and non-negative")
    return parsed


def _enum(enum_type: type[TEnum], value: Any, path: str) -> TEnum:
    if not isinstance(value, str):
        raise EvaluationDatasetValidationError(f"{path} must be a string")
    try:
        return enum_type(value)  # type: ignore[call-arg]
    except ValueError as exc:
        raise EvaluationDatasetValidationError(f"{path} has an unknown value") from exc
