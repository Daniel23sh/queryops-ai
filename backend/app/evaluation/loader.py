from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

from app.evaluation.contracts import (
    CaseType,
    ComparisonMode,
    EvaluationAnswerability,
    EvaluationCase,
    EvaluationDifficulty,
    EvaluationSemanticAggregation,
    EvaluationSemanticContract,
    EvaluationSemanticField,
    EvaluationSemanticHaving,
    EvaluationSemanticOrdering,
    EvaluationSemanticSource,
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
EVALUATION_V2_DATASET_PATH = (
    IT_OPERATIONS_DOMAIN_PACK_DIR / "evaluation_questions_v2.yaml"
)
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
V2_CASE_FIELDS = CASE_FIELDS | {"semantic_contract"}
SEMANTIC_CONTRACT_FIELDS = frozenset(
    {
        "answerability",
        "semantic_source",
        "required_concept_ids",
        "required_metric_id",
        "required_composition_rule_ids",
        "grain_fields",
        "output_fields",
        "aggregations",
        "group_by",
        "having",
        "ordering",
    }
)
SEMANTIC_FIELD_FIELDS = frozenset({"entity_id", "column"})
SEMANTIC_AGGREGATION_FIELDS = frozenset(
    {"id", "function", "field", "distinct"}
)
SEMANTIC_HAVING_FIELDS = frozenset({"aggregation_id", "operator", "value"})
SEMANTIC_ORDERING_FIELDS = frozenset(
    {"target_kind", "field", "aggregation_id", "direction"}
)
CASE_ID = re.compile(r"^itops-(easy|medium|hard|security)-[0-9]{3}$")
SEMANTIC_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
SUPPORTED_SCOPE_TYPES = frozenset({"department", "global"})
MAX_SEMANTIC_ITEMS = 64
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
    if version not in {"1", "2"}:
        raise EvaluationDatasetValidationError("Evaluation dataset version is unsupported")
    if version == "2" and dataset_id != "it_operations_v2":
        raise EvaluationDatasetValidationError(
            "Evaluation V2 dataset_id must be it_operations_v2"
        )
    if domain_id != pack.domain_id:
        raise EvaluationDatasetValidationError("Evaluation domain_id does not match domain pack")

    raw_cases = _list(root["cases"], "cases")
    cases = tuple(
        _parse_case(item, index, pack, dataset_version=version)
        for index, item in enumerate(raw_cases)
    )
    _validate_complete_set(cases)
    return EvaluationSet(
        dataset_id=dataset_id,
        domain_id=domain_id,
        version=version,
        cases=tuple(sorted(cases, key=lambda case: case.id)),
    )


def load_it_operations_evaluation_v2_set(
    *,
    domain_pack: DomainPack | None = None,
) -> EvaluationSet:
    """Load the reviewed V2 suite without changing the historical V1 default."""
    return load_it_operations_evaluation_set(
        EVALUATION_V2_DATASET_PATH,
        domain_pack=domain_pack,
    )


def _parse_case(
    raw: Any,
    index: int,
    pack: DomainPack,
    *,
    dataset_version: str,
) -> EvaluationCase:
    path = f"cases[{index}]"
    item = _mapping(raw, path)
    is_v2 = dataset_version == "2"
    _require_exact_fields(item, V2_CASE_FIELDS if is_v2 else CASE_FIELDS, path)
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

    semantic_contract = (
        _parse_semantic_contract(item["semantic_contract"], path, pack)
        if is_v2
        else None
    )
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
        semantic_contract=semantic_contract,
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


def _parse_semantic_contract(
    raw: Any,
    case_path: str,
    pack: DomainPack,
) -> EvaluationSemanticContract:
    path = f"{case_path}.semantic_contract"
    item = _mapping(raw, path)
    _require_exact_fields(item, SEMANTIC_CONTRACT_FIELDS, path)
    answerability = _enum(
        EvaluationAnswerability,
        item["answerability"],
        f"{path}.answerability",
    )
    semantic_source = _enum(
        EvaluationSemanticSource,
        item["semantic_source"],
        f"{path}.semantic_source",
    )
    required_concept_ids = _semantic_identifiers(
        item["required_concept_ids"], f"{path}.required_concept_ids"
    )
    required_metric_id = _optional_semantic_identifier(
        item["required_metric_id"], f"{path}.required_metric_id"
    )
    required_rule_ids = _semantic_identifiers(
        item["required_composition_rule_ids"],
        f"{path}.required_composition_rule_ids",
    )
    grain_fields = _parse_semantic_fields(
        item["grain_fields"], f"{path}.grain_fields", pack
    )
    output_fields = _parse_semantic_fields(
        item["output_fields"], f"{path}.output_fields", pack
    )
    aggregations = _parse_semantic_aggregations(
        item["aggregations"], f"{path}.aggregations", pack
    )
    group_by = _parse_semantic_fields(
        item["group_by"], f"{path}.group_by", pack
    )
    aggregation_ids = {aggregation.id for aggregation in aggregations}
    having = _parse_semantic_having(
        item["having"], f"{path}.having", aggregation_ids
    )
    ordering = _parse_semantic_ordering(
        item["ordering"], f"{path}.ordering", pack, aggregation_ids
    )

    concept_ids = pack.semantic_catalog.concepts_by_id
    unknown_concepts = sorted(set(required_concept_ids) - set(concept_ids))
    if unknown_concepts:
        raise EvaluationDatasetValidationError(
            f"{path}.required_concept_ids references unknown concept"
        )
    if (
        required_metric_id is not None
        and required_metric_id not in pack.semantic_catalog.metrics_by_id
    ):
        raise EvaluationDatasetValidationError(
            f"{path}.required_metric_id references unknown metric"
        )
    known_rule_ids = {
        rule.id for rule in pack.semantic_catalog.composition_rules
    }
    if set(required_rule_ids) - known_rule_ids:
        raise EvaluationDatasetValidationError(
            f"{path}.required_composition_rule_ids references unknown rule"
        )

    return EvaluationSemanticContract(
        answerability=answerability,
        semantic_source=semantic_source,
        required_concept_ids=required_concept_ids,
        required_metric_id=required_metric_id,
        required_composition_rule_ids=required_rule_ids,
        grain_fields=grain_fields,
        output_fields=output_fields,
        aggregations=aggregations,
        group_by=group_by,
        having=having,
        ordering=ordering,
    )


def _parse_semantic_fields(
    raw: Any,
    path: str,
    pack: DomainPack,
) -> tuple[EvaluationSemanticField, ...]:
    fields = tuple(
        _parse_semantic_field(item, f"{path}[{index}]", pack)
        for index, item in enumerate(_bounded_list(raw, path))
    )
    if len(fields) != len(set(fields)):
        raise EvaluationDatasetValidationError(f"{path} must not contain duplicates")
    return fields


def _parse_semantic_field(
    raw: Any,
    path: str,
    pack: DomainPack,
) -> EvaluationSemanticField:
    item = _mapping(raw, path)
    _require_exact_fields(item, SEMANTIC_FIELD_FIELDS, path)
    entity_id = _semantic_identifier(item["entity_id"], f"{path}.entity_id")
    column = _semantic_identifier(item["column"], f"{path}.column")
    entity = pack.semantic_catalog.entities_by_id.get(entity_id)
    if entity is None:
        raise EvaluationDatasetValidationError(f"{path} references unknown entity")
    table = pack.tables_by_name.get(entity.table)
    if table is None or column not in table.columns_by_name:
        raise EvaluationDatasetValidationError(
            f"{path} references unknown entity field"
        )
    return EvaluationSemanticField(entity_id=entity_id, column=column)


def _parse_semantic_aggregations(
    raw: Any,
    path: str,
    pack: DomainPack,
) -> tuple[EvaluationSemanticAggregation, ...]:
    aggregations: list[EvaluationSemanticAggregation] = []
    for index, raw_item in enumerate(_bounded_list(raw, path)):
        item_path = f"{path}[{index}]"
        item = _mapping(raw_item, item_path)
        _require_exact_fields(item, SEMANTIC_AGGREGATION_FIELDS, item_path)
        aggregation_id = _semantic_identifier(item["id"], f"{item_path}.id")
        function = _one_of(
            item["function"], {"count", "sum"}, f"{item_path}.function"
        )
        field = (
            None
            if item["field"] is None
            else _parse_semantic_field(item["field"], f"{item_path}.field", pack)
        )
        if function == "sum" and field is None:
            raise EvaluationDatasetValidationError(
                f"{item_path}.field is required for sum"
            )
        aggregations.append(
            EvaluationSemanticAggregation(
                id=aggregation_id,
                function=cast(Literal["count", "sum"], function),
                field=field,
                distinct=_boolean(item["distinct"], f"{item_path}.distinct"),
            )
        )
    if len({item.id for item in aggregations}) != len(aggregations):
        raise EvaluationDatasetValidationError(
            f"{path} must use unique aggregation ids"
        )
    return tuple(aggregations)


def _parse_semantic_having(
    raw: Any,
    path: str,
    aggregation_ids: set[str],
) -> tuple[EvaluationSemanticHaving, ...]:
    having: list[EvaluationSemanticHaving] = []
    operators = {
        "equals",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
    }
    for index, raw_item in enumerate(_bounded_list(raw, path)):
        item_path = f"{path}[{index}]"
        item = _mapping(raw_item, item_path)
        _require_exact_fields(item, SEMANTIC_HAVING_FIELDS, item_path)
        aggregation_id = _semantic_identifier(
            item["aggregation_id"], f"{item_path}.aggregation_id"
        )
        if aggregation_id not in aggregation_ids:
            raise EvaluationDatasetValidationError(
                f"{item_path}.aggregation_id references unknown aggregation"
            )
        operator = _one_of(item["operator"], operators, f"{item_path}.operator")
        value = _required_decimal(item["value"], f"{item_path}.value")
        having.append(
            EvaluationSemanticHaving(
                aggregation_id=aggregation_id,
                operator=cast(
                    Literal[
                        "equals",
                        "greater_than",
                        "greater_than_or_equal",
                        "less_than",
                        "less_than_or_equal",
                    ],
                    operator,
                ),
                value=value,
            )
        )
    return tuple(having)


def _parse_semantic_ordering(
    raw: Any,
    path: str,
    pack: DomainPack,
    aggregation_ids: set[str],
) -> tuple[EvaluationSemanticOrdering, ...]:
    ordering: list[EvaluationSemanticOrdering] = []
    for index, raw_item in enumerate(_bounded_list(raw, path)):
        item_path = f"{path}[{index}]"
        item = _mapping(raw_item, item_path)
        _require_exact_fields(item, SEMANTIC_ORDERING_FIELDS, item_path)
        target_kind = _one_of(
            item["target_kind"], {"field", "aggregation"}, f"{item_path}.target_kind"
        )
        direction = _one_of(
            item["direction"], {"asc", "desc"}, f"{item_path}.direction"
        )
        field = (
            None
            if item["field"] is None
            else _parse_semantic_field(item["field"], f"{item_path}.field", pack)
        )
        aggregation_id = _optional_semantic_identifier(
            item["aggregation_id"], f"{item_path}.aggregation_id"
        )
        if target_kind == "field":
            if field is None or aggregation_id is not None:
                raise EvaluationDatasetValidationError(
                    f"{item_path} has an inconsistent field ordering target"
                )
        elif field is not None or aggregation_id not in aggregation_ids:
            raise EvaluationDatasetValidationError(
                f"{item_path} has an inconsistent aggregation ordering target"
            )
        ordering.append(
            EvaluationSemanticOrdering(
                target_kind=cast(Literal["field", "aggregation"], target_kind),
                field=field,
                aggregation_id=aggregation_id,
                direction=cast(Literal["asc", "desc"], direction),
            )
        )
    return tuple(ordering)


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
    if case.semantic_contract is not None:
        _validate_semantic_contract_expectations(case, path, pack)
    if case.baseline_sql is not None:
        _validate_baseline_sql(case, path, pack)


def _validate_semantic_contract_expectations(
    case: EvaluationCase,
    path: str,
    pack: DomainPack,
) -> None:
    contract = case.semantic_contract
    if contract is None:
        return
    answerability_by_outcome = {
        ExpectedOutcome.SUCCESS: EvaluationAnswerability.ANSWERABLE,
        ExpectedOutcome.CLARIFICATION: EvaluationAnswerability.CLARIFICATION,
        ExpectedOutcome.DENIED: EvaluationAnswerability.DENIED,
        ExpectedOutcome.UNSAFE_BLOCKED: EvaluationAnswerability.UNSAFE,
    }
    if contract.answerability is not answerability_by_outcome[case.expected_outcome]:
        raise EvaluationDatasetValidationError(
            f"{path}.semantic_contract contradicts expected_outcome"
        )
    semantic_details = (
        contract.required_concept_ids,
        contract.required_composition_rule_ids,
        contract.grain_fields,
        contract.output_fields,
        contract.aggregations,
        contract.group_by,
        contract.having,
        contract.ordering,
    )
    if contract.answerability is not EvaluationAnswerability.ANSWERABLE:
        if contract.required_metric_id is not None or any(semantic_details):
            raise EvaluationDatasetValidationError(
                f"{path}.semantic_contract defines result semantics for a non-answerable case"
            )
    elif contract.semantic_source is EvaluationSemanticSource.NOT_APPLICABLE:
        raise EvaluationDatasetValidationError(
            f"{path}.semantic_contract must document an answerability source"
        )
    if contract.having and not contract.aggregations:
        raise EvaluationDatasetValidationError(
            f"{path}.semantic_contract has HAVING without aggregation"
        )
    if contract.group_by and not (
        contract.aggregations or contract.required_metric_id is not None
    ):
        raise EvaluationDatasetValidationError(
            f"{path}.semantic_contract has group_by without aggregation"
        )

    expected_columns = {
        item.table: set(item.columns) for item in case.expected_columns
    }
    contract_fields = [
        *contract.grain_fields,
        *contract.output_fields,
        *contract.group_by,
        *(
            item.field
            for item in contract.aggregations
            if item.field is not None
        ),
        *(
            item.field
            for item in contract.ordering
            if item.field is not None
        ),
    ]
    catalog = pack.semantic_catalog
    for field in contract_fields:
        table = catalog.entities_by_id[field.entity_id].table
        if field.column not in expected_columns.get(table, set()):
            raise EvaluationDatasetValidationError(
                f"{path}.semantic_contract field contradicts expected_columns"
            )

    semantic_entity_ids = {
        catalog.concepts_by_id[concept_id].entity_id
        for concept_id in contract.required_concept_ids
    }
    if contract.required_metric_id is not None:
        semantic_entity_ids.add(
            catalog.metrics_by_id[contract.required_metric_id].entity_id
        )
    rules_by_id = {rule.id: rule for rule in catalog.composition_rules}
    for rule_id in contract.required_composition_rule_ids:
        rule = rules_by_id[rule_id]
        for concept_id in (*rule.all_of_concept_ids, *rule.or_concept_ids):
            semantic_entity_ids.add(catalog.concepts_by_id[concept_id].entity_id)
    semantic_tables = {
        catalog.entities_by_id[entity_id].table
        for entity_id in semantic_entity_ids
    }
    if not semantic_tables <= set(case.expected_tables):
        raise EvaluationDatasetValidationError(
            f"{path}.semantic_contract concepts contradict expected_tables"
        )


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


def _bounded_list(value: Any, path: str) -> Sequence[Any]:
    items = _list(value, path)
    if len(items) > MAX_SEMANTIC_ITEMS:
        raise EvaluationDatasetValidationError(
            f"{path} exceeds the maximum item count"
        )
    return items


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationDatasetValidationError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _semantic_identifier(value: Any, path: str) -> str:
    identifier = _string(value, path)
    if not SEMANTIC_IDENTIFIER.fullmatch(identifier):
        raise EvaluationDatasetValidationError(f"{path} must be a safe identifier")
    return identifier


def _optional_semantic_identifier(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _semantic_identifier(value, path)


def _semantic_identifiers(value: Any, path: str) -> tuple[str, ...]:
    items = tuple(
        _semantic_identifier(item, f"{path}[{index}]")
        for index, item in enumerate(_bounded_list(value, path))
    )
    if len(items) != len(set(items)):
        raise EvaluationDatasetValidationError(f"{path} must not contain duplicates")
    return tuple(sorted(items))


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


def _required_decimal(value: Any, path: str) -> Decimal:
    parsed = _optional_decimal(value, path)
    if parsed is None:
        raise EvaluationDatasetValidationError(f"{path} must be a decimal string")
    return parsed


def _one_of(value: Any, choices: set[str], path: str) -> str:
    candidate = _string(value, path)
    if candidate not in choices:
        raise EvaluationDatasetValidationError(f"{path} has an unknown value")
    return candidate


def _enum(enum_type: type[TEnum], value: Any, path: str) -> TEnum:
    if not isinstance(value, str):
        raise EvaluationDatasetValidationError(f"{path} must be a string")
    try:
        return enum_type(value)  # type: ignore[call-arg]
    except ValueError as exc:
        raise EvaluationDatasetValidationError(f"{path} has an unknown value") from exc
