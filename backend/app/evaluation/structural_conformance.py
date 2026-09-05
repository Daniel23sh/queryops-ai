"""Deterministic offline audit of V2 contracts against current grounding.

This module does not validate plans, invoke providers, execute SQL, persist
evaluation data, score cases, or participate in readiness decisions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Mapping

from app.evaluation.contracts import (
    CaseType,
    EvaluationAnswerability,
    EvaluationCase,
    ExpectedOutcome,
    ScopeMode,
)
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.selection import evaluation_dataset_digest
from app.evaluation.structural_intent_adapter import (
    evaluation_contract_to_structural_requirement,
)
from app.query_engine.domain_pack import DomainPack
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from app.query_engine.structural_intent import StructuralResultIntent
from app.query_engine.structural_intent_adapters import (
    StructuralMappingError,
    grounded_to_structural_requirement,
)
from app.query_engine.structural_intent_comparison import (
    COMPONENTS,
    StructuralRequirement,
    structural_component_identities,
)


REPORT_VERSION = "queryops-v2-structural-conformance-v1"
CURRENT_GROUNDING_UNAVAILABLE_COMPONENTS = frozenset({"ordering"})
ComponentName = Literal[
    "row_grain",
    "output_fields",
    "aggregations",
    "group_by",
    "having",
    "ordering",
    "distinct",
]


class Compatibility(str, Enum):
    COMPATIBLE = "compatible"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class Coverage(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NONE = "none"
    NOT_APPLICABLE = "not_applicable"


class ComponentRelation(str, Enum):
    EXACT = "exact"
    COVERED = "covered"
    PARTIALLY_COVERED = "partially_covered"
    MISSING = "missing"
    UNSPECIFIED = "unspecified"
    CONFLICT = "conflict"
    UNSUPPORTED = "unsupported_by_current_grounding_model"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class StructuralCapability(str, Enum):
    DETAIL = "DETAIL"
    DISTINCT_DETAIL = "DISTINCT_DETAIL"
    COUNT = "COUNT"
    DISTINCT_COUNT = "DISTINCT_COUNT"
    GROUP_BY_SINGLE = "GROUP_BY_SINGLE"
    GROUP_BY_MULTI = "GROUP_BY_MULTI"
    HAVING = "HAVING"
    MULTI_AGGREGATE = "MULTI_AGGREGATE"
    ORDERING = "ORDERING"
    MULTI_ORDERING = "MULTI_ORDERING"
    JOINED_DETAIL = "JOINED_DETAIL"
    JOINED_AGGREGATE = "JOINED_AGGREGATE"
    CANONICAL_METRIC = "CANONICAL_METRIC"
    COMPOSITION_RULE = "COMPOSITION_RULE"


@dataclass(frozen=True)
class ComponentDiagnostic:
    relation: ComponentRelation
    coverage_relation: ComponentRelation
    expected_state: str
    grounding_state: str
    expected_count: int | None
    grounding_count: int | None
    provable_conflict: bool

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "relation": self.relation.value,
            "coverage_relation": self.coverage_relation.value,
            "expected_state": self.expected_state,
            "grounding_state": self.grounding_state,
            "expected_count": self.expected_count,
            "grounding_count": self.grounding_count,
            "provable_conflict": self.provable_conflict,
        }


@dataclass(frozen=True)
class GroundingAxisReport:
    coverage: Coverage
    components: tuple[tuple[str, ComponentDiagnostic], ...]
    structural_intent: Mapping[str, Any]

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "coverage": self.coverage.value,
            "components": {
                name: diagnostic.as_safe_dict() for name, diagnostic in self.components
            },
            "structural_intent": dict(self.structural_intent),
        }


@dataclass(frozen=True)
class StructuralCaseReport:
    case_id: str
    case_type: str
    expected_outcome: str
    answerable: bool
    applicability: str
    compatibility: Compatibility
    capabilities: tuple[StructuralCapability, ...]
    expected: Mapping[str, Any] | None
    required: GroundingAxisReport
    suggested: GroundingAxisReport

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "expected_outcome": self.expected_outcome,
            "answerable": self.answerable,
            "applicability": self.applicability,
            "compatibility": self.compatibility.value,
            "capabilities": [item.value for item in self.capabilities],
            "expected": dict(self.expected) if self.expected is not None else None,
            "required": self.required.as_safe_dict(),
            "suggested": self.suggested.as_safe_dict(),
        }


@dataclass(frozen=True)
class StructuralSummary:
    case_count: int
    compatibility: Mapping[str, int]
    required_coverage: Mapping[str, int]
    suggested_coverage: Mapping[str, int]
    unavailable_dimensions: Mapping[str, int]

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "case_count": self.case_count,
            "compatibility": dict(self.compatibility),
            "required_coverage": dict(self.required_coverage),
            "suggested_coverage": dict(self.suggested_coverage),
            "unavailable_dimensions": dict(self.unavailable_dimensions),
        }


@dataclass(frozen=True)
class CapabilitySummary:
    capability: StructuralCapability
    total_applicable_cases: int
    required_coverage: Mapping[str, int]
    required_conflicts: int
    suggested_coverage: Mapping[str, int]
    unavailable_dimensions: Mapping[str, int]

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability.value,
            "total_applicable_cases": self.total_applicable_cases,
            "required_coverage": dict(self.required_coverage),
            "required_conflicts": self.required_conflicts,
            "suggested_coverage": dict(self.suggested_coverage),
            "unavailable_dimensions": dict(self.unavailable_dimensions),
        }


@dataclass(frozen=True)
class StructuralConformanceReport:
    report_version: str
    dataset_id: str
    dataset_version: str
    dataset_digest: str
    semantic_catalog_id: str
    semantic_catalog_version: str
    semantic_catalog_digest: str
    normalization_rules_reused: tuple[str, ...]
    cases: tuple[StructuralCaseReport, ...]
    all_cases: StructuralSummary
    answerable_cases: StructuralSummary
    free_query_answerable_cases: StructuralSummary
    capability_matrix: tuple[CapabilitySummary, ...]

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "report_version": self.report_version,
            "dataset": {
                "id": self.dataset_id,
                "version": self.dataset_version,
                "digest": self.dataset_digest,
            },
            "semantic_catalog": {
                "id": self.semantic_catalog_id,
                "version": self.semantic_catalog_version,
                "digest": self.semantic_catalog_digest,
            },
            "normalization_rules_reused": list(self.normalization_rules_reused),
            "summaries": {
                "all_cases": self.all_cases.as_safe_dict(),
                "answerable_cases": self.answerable_cases.as_safe_dict(),
                "free_query_answerable_cases": (
                    self.free_query_answerable_cases.as_safe_dict()
                ),
            },
            "capability_matrix": [
                item.as_safe_dict() for item in self.capability_matrix
            ],
            "cases": [case.as_safe_dict() for case in self.cases],
        }


def build_v2_structural_conformance_report() -> StructuralConformanceReport:
    """Build the complete report using static files and pure computation only."""
    evaluation_set = load_it_operations_evaluation_v2_set()
    pack = load_it_operations_domain_pack()
    schema_context = _authorized_schema_projection(pack)
    reports = tuple(
        _audit_case(case, pack, schema_context)
        for case in sorted(evaluation_set.cases, key=lambda item: item.id)
    )
    answerable = tuple(case for case in reports if case.answerable)
    free_answerable = tuple(
        case for case in answerable if case.case_type == CaseType.FREE_QUERY.value
    )
    return StructuralConformanceReport(
        report_version=REPORT_VERSION,
        dataset_id=evaluation_set.dataset_id,
        dataset_version=evaluation_set.version,
        dataset_digest=evaluation_dataset_digest(evaluation_set),
        semantic_catalog_id=pack.semantic_catalog.id,
        semantic_catalog_version=pack.semantic_catalog.version,
        semantic_catalog_digest=pack.semantic_catalog.digest,
        # Current FK/PK COUNT DISTINCT normalization needs a validated plan and
        # selected relationship graph. The offline grounding audit has neither,
        # so applying it would overstate equivalence. No normalization is reused.
        normalization_rules_reused=(),
        cases=reports,
        all_cases=_summarize(reports),
        answerable_cases=_summarize(answerable),
        free_query_answerable_cases=_summarize(free_answerable),
        capability_matrix=_capability_matrix(free_answerable),
    )


def _audit_case(
    case: EvaluationCase,
    pack: DomainPack,
    schema_context: Mapping[str, Any],
) -> StructuralCaseReport:
    projection = build_semantic_catalog_projection(
        pack.semantic_catalog,
        case.question,
        schema_context,
        _synthetic_user_context(case),
    )
    contract = case.semantic_contract
    answerable = (
        contract is not None
        and contract.answerability is EvaluationAnswerability.ANSWERABLE
        and case.expected_outcome is ExpectedOutcome.SUCCESS
    )
    if not answerable:
        empty = _not_applicable_axis()
        return StructuralCaseReport(
            case_id=case.id,
            case_type=case.case_type.value,
            expected_outcome=case.expected_outcome.value,
            answerable=False,
            applicability="not_applicable",
            compatibility=Compatibility.NOT_APPLICABLE,
            capabilities=(),
            expected=None,
            required=empty,
            suggested=empty,
        )
    assert contract is not None
    expected = evaluation_contract_to_structural_requirement(contract)
    assert expected is not None
    required_mapping_failed = False
    try:
        required = grounded_to_structural_requirement(
            projection.grounded_result_intent,
            pack.semantic_catalog,
            binding="required",
        )
        required_axis = _axis_report(expected, required)
    except StructuralMappingError:
        required_axis = _unavailable_axis(expected)
        required_mapping_failed = True
    try:
        suggested = grounded_to_structural_requirement(
            projection.suggested_result_intent,
            pack.semantic_catalog,
            binding="suggested",
        )
        suggested_axis = _axis_report(expected, suggested)
    except StructuralMappingError:
        suggested_axis = _unavailable_axis(expected)
    if required_mapping_failed:
        compatibility = Compatibility.UNAVAILABLE
    elif any(item.provable_conflict for _, item in required_axis.components):
        compatibility = Compatibility.CONFLICT
    elif any(
        item.relation is ComponentRelation.UNAVAILABLE
        for _, item in required_axis.components
    ):
        compatibility = Compatibility.UNAVAILABLE
    else:
        compatibility = Compatibility.COMPATIBLE
    return StructuralCaseReport(
        case_id=case.id,
        case_type=case.case_type.value,
        expected_outcome=case.expected_outcome.value,
        answerable=True,
        applicability="applicable",
        compatibility=compatibility,
        capabilities=_capabilities(case),
        expected=_safe_intent(expected.intent),
        required=required_axis,
        suggested=suggested_axis,
    )


def _axis_report(
    expected: StructuralRequirement,
    grounding: StructuralRequirement,
) -> GroundingAxisReport:
    diagnostics = tuple(
        (
            name,
            _component_diagnostic(
                name,
                expected,
                grounding,
            ),
        )
        for name in COMPONENTS
    )
    applicable = [
        diagnostic
        for _, diagnostic in diagnostics
        if diagnostic.relation is not ComponentRelation.NOT_APPLICABLE
    ]
    if not applicable:
        coverage = Coverage.NOT_APPLICABLE
    else:
        represented = sum(
            item.coverage_relation
            in {
                ComponentRelation.EXACT,
                ComponentRelation.COVERED,
                ComponentRelation.PARTIALLY_COVERED,
            }
            for item in applicable
        )
        fully_covered = all(
            item.coverage_relation
            in {ComponentRelation.EXACT, ComponentRelation.COVERED}
            for item in applicable
        )
        coverage = (
            Coverage.COMPLETE
            if fully_covered
            else Coverage.NONE
            if represented == 0
            else Coverage.PARTIAL
        )
    return GroundingAxisReport(
        coverage=coverage,
        components=diagnostics,
        structural_intent=_safe_intent(grounding.intent),
    )


def _component_diagnostic(
    name: str,
    expected: StructuralRequirement,
    grounding: StructuralRequirement,
) -> ComponentDiagnostic:
    expected_policy = getattr(expected.policy, name)
    grounding_policy = getattr(grounding.policy, name)
    expected_value = getattr(expected.intent, name)
    grounding_value = getattr(grounding.intent, name)
    counts = (_component_count(expected_value), _component_count(grounding_value))
    cross_component_conflict = (
        grounding.binding == "required"
        and name in _cross_component_conflicts(expected, grounding)
    )
    if cross_component_conflict:
        return _diagnostic(
            ComponentRelation.CONFLICT,
            expected_value.state,
            grounding_value.state,
            counts,
            provable_conflict=True,
            coverage_relation=(
                ComponentRelation.NOT_APPLICABLE
                if expected_policy == "ignored"
                else _coverage_relation(name, expected, grounding)
            ),
        )
    if expected_policy == "ignored":
        return _diagnostic(
            ComponentRelation.NOT_APPLICABLE,
            expected_value.state,
            grounding_value.state,
            counts,
        )
    if grounding_value.state == "unknown":
        return _diagnostic(
            ComponentRelation.UNAVAILABLE,
            expected_value.state,
            grounding_value.state,
            counts,
        )
    if grounding_policy == "ignored" or grounding_value.state == "unspecified":
        relation = (
            ComponentRelation.UNSUPPORTED
            if name in CURRENT_GROUNDING_UNAVAILABLE_COMPONENTS
            else ComponentRelation.UNSPECIFIED
        )
        return _diagnostic(
            relation,
            expected_value.state,
            grounding_value.state,
            counts,
        )
    conflict = grounding.binding == "required" and _components_conflict(
        name, expected, grounding
    )
    coverage_relation = _coverage_relation(name, expected, grounding)
    relation = ComponentRelation.CONFLICT if conflict else coverage_relation
    return _diagnostic(
        relation,
        expected_value.state,
        grounding_value.state,
        counts,
        provable_conflict=conflict,
        coverage_relation=coverage_relation,
    )


def _components_conflict(
    name: str,
    expected: StructuralRequirement,
    grounding: StructuralRequirement,
) -> bool:
    expected_intent = expected.intent
    grounded_intent = grounding.intent
    if name == "output_fields":
        return False  # Both current policies require subsets; their union is valid.
    if name == "row_grain":
        expected_grain = expected_intent.row_grain.value
        grounded_grain = grounded_intent.row_grain.value
        if expected_grain is None or grounded_grain is None:
            return False
        if expected_grain.mode != grounded_grain.mode:
            return True
        expected_keys = set(expected_grain.identity_fields.value or ())
        grounded_keys = set(grounded_grain.identity_fields.value or ())
        if expected_grain.mode == "grouped":
            return expected_keys != grounded_keys
        return False  # Detail output requirements can be combined.
    if name == "distinct":
        return (
            expected_intent.distinct.value is not None
            and grounded_intent.distinct.value is not None
            and expected_intent.distinct.value != grounded_intent.distinct.value
        )
    expected_items = set(structural_component_identities(expected_intent, name))
    grounded_items = set(structural_component_identities(grounded_intent, name))
    expected_policy = getattr(expected.policy, name)
    grounding_policy = getattr(grounding.policy, name)
    if grounding_policy == "exact" and expected_policy == "required_subset":
        return not expected_items <= grounded_items
    if grounding_policy == "exact" and expected_policy == "exact":
        return expected_items != grounded_items
    if grounding_policy == "required_subset" and expected_policy == "exact":
        return not grounded_items <= expected_items
    return False


def _coverage_relation(
    name: str,
    expected: StructuralRequirement,
    grounding: StructuralRequirement,
) -> ComponentRelation:
    if name == "row_grain":
        expected_grain = expected.intent.row_grain.value
        grounded_grain = grounding.intent.row_grain.value
        if expected_grain is None or grounded_grain is None:
            return ComponentRelation.MISSING
        if expected_grain.mode != grounded_grain.mode:
            return ComponentRelation.MISSING
        expected_items = set(expected_grain.identity_fields.value or ())
        grounded_items = set(grounded_grain.identity_fields.value or ())
    elif name == "distinct":
        return (
            ComponentRelation.EXACT
            if expected.intent.distinct.value == grounding.intent.distinct.value
            else ComponentRelation.MISSING
        )
    else:
        expected_items = set(structural_component_identities(expected.intent, name))
        grounded_items = set(structural_component_identities(grounding.intent, name))
    if expected_items == grounded_items:
        return ComponentRelation.EXACT
    if expected_items <= grounded_items:
        return ComponentRelation.COVERED
    if expected_items & grounded_items:
        return ComponentRelation.PARTIALLY_COVERED
    return ComponentRelation.MISSING


def _cross_component_conflicts(
    expected: StructuralRequirement,
    grounding: StructuralRequirement,
) -> frozenset[str]:
    """Reserved for constraints that are not local to one structural component."""
    expected_grain = expected.intent.row_grain.value
    if expected_grain is None or expected_grain.mode != "detail":
        return frozenset()
    conflicts: set[str] = set()
    if grounding.policy.aggregations == "exact" and grounding.intent.aggregations.value:
        conflicts.add("aggregations")
    if grounding.policy.group_by == "exact" and grounding.intent.group_by.value:
        conflicts.add("group_by")
    return frozenset(conflicts)


def _diagnostic(
    relation: ComponentRelation,
    expected_state: str,
    grounding_state: str,
    counts: tuple[int | None, int | None],
    *,
    provable_conflict: bool = False,
    coverage_relation: ComponentRelation | None = None,
) -> ComponentDiagnostic:
    return ComponentDiagnostic(
        relation=relation,
        coverage_relation=coverage_relation or relation,
        expected_state=expected_state,
        grounding_state=grounding_state,
        expected_count=counts[0],
        grounding_count=counts[1],
        provable_conflict=provable_conflict,
    )


def _component_count(value: Any) -> int | None:
    if value.state != "known":
        return None
    if isinstance(value.value, tuple):
        return len(value.value)
    return 1


def _safe_intent(intent: StructuralResultIntent) -> dict[str, Any]:
    return intent.model_dump(mode="json")


def _not_applicable_axis() -> GroundingAxisReport:
    return GroundingAxisReport(
        coverage=Coverage.NOT_APPLICABLE,
        components=tuple(
            (
                name,
                _diagnostic(
                    ComponentRelation.NOT_APPLICABLE,
                    "unspecified",
                    "unspecified",
                    (None, None),
                ),
            )
            for name in COMPONENTS
        ),
        structural_intent={},
    )


def _unavailable_axis(expected: StructuralRequirement) -> GroundingAxisReport:
    return GroundingAxisReport(
        coverage=Coverage.NONE,
        components=tuple(
            (
                name,
                _diagnostic(
                    ComponentRelation.UNAVAILABLE,
                    getattr(expected.intent, name).state,
                    "unknown",
                    (_component_count(getattr(expected.intent, name)), None),
                ),
            )
            for name in COMPONENTS
        ),
        structural_intent={},
    )


def _authorized_schema_projection(pack: DomainPack) -> dict[str, Any]:
    """Static equivalent of the authorized full domain-pack projection.

    The audit has no DB or actor. Frozen successful V2 cases use resources from
    the domain pack allowlist. This projects only those queryable resources and
    their declared columns; it does not fabricate database resource metadata.
    """
    allowed = frozenset(pack.allowed_resource_table_names)
    tables = tuple(
        table for table in pack.tables if table.name in allowed and table.queryable
    )
    return {
        "domain": pack.domain_id,
        "domain_name": pack.name,
        "domain_version": pack.version,
        "allowed_tables": [table.name for table in tables],
        "allowed_columns": {
            table.name: [column.name for column in table.columns] for table in tables
        },
        "tables": [
            {
                "name": table.name,
                "scope_type": table.scope_type,
                "scope_column": table.scope_column,
                "columns": [
                    {
                        "name": column.name,
                        "data_type": column.data_type,
                        "description": column.description,
                        "nullable": column.nullable,
                    }
                    for column in table.columns
                ],
            }
            for table in tables
        ],
        "business_terms": [],
    }


def _synthetic_user_context(case: EvaluationCase) -> dict[str, Any]:
    if case.scope_mode is ScopeMode.GLOBAL:
        return {
            "scope_type": "global",
            "has_global_scope": True,
            "scope_reference_resolved": True,
        }
    if case.scope_mode in {ScopeMode.ASSIGNED, ScopeMode.CROSS_SCOPE}:
        return {
            "scope_type": case.required_scope_type or "none",
            "has_global_scope": False,
            "scope_reference_resolved": True,
        }
    return {
        "scope_type": "none",
        "has_global_scope": False,
        "scope_reference_resolved": False,
    }


def _capabilities(case: EvaluationCase) -> tuple[StructuralCapability, ...]:
    contract = case.semantic_contract
    if (
        contract is None
        or contract.answerability is not EvaluationAnswerability.ANSWERABLE
    ):
        return ()
    result: set[StructuralCapability] = set()
    detail = (
        not contract.group_by
        and not contract.aggregations
        and contract.required_metric_id is None
    )
    if detail:
        result.add(StructuralCapability.DETAIL)
        if "distinct" in case.question.casefold().split():
            result.add(StructuralCapability.DISTINCT_DETAIL)
    if any(item.function == "count" for item in contract.aggregations):
        result.add(StructuralCapability.COUNT)
    if any(
        item.function == "count" and item.distinct for item in contract.aggregations
    ):
        result.add(StructuralCapability.DISTINCT_COUNT)
    if len(contract.group_by) == 1:
        result.add(StructuralCapability.GROUP_BY_SINGLE)
    elif len(contract.group_by) > 1:
        result.add(StructuralCapability.GROUP_BY_MULTI)
    if contract.having:
        result.add(StructuralCapability.HAVING)
    if len(contract.aggregations) > 1:
        result.add(StructuralCapability.MULTI_AGGREGATE)
    if contract.ordering:
        result.add(StructuralCapability.ORDERING)
    if len(contract.ordering) > 1:
        result.add(StructuralCapability.MULTI_ORDERING)
    if case.requires_join and detail:
        result.add(StructuralCapability.JOINED_DETAIL)
    if case.requires_join and (contract.aggregations or contract.required_metric_id):
        result.add(StructuralCapability.JOINED_AGGREGATE)
    if contract.required_metric_id is not None:
        result.add(StructuralCapability.CANONICAL_METRIC)
    if contract.required_composition_rule_ids:
        result.add(StructuralCapability.COMPOSITION_RULE)
    return tuple(sorted(result, key=lambda item: item.value))


def _summarize(cases: tuple[StructuralCaseReport, ...]) -> StructuralSummary:
    unavailable = Counter(
        name
        for case in cases
        for name, item in case.required.components
        if item.relation
        in {ComponentRelation.UNSUPPORTED, ComponentRelation.UNAVAILABLE}
    )
    return StructuralSummary(
        case_count=len(cases),
        compatibility=_enum_counts(cases, "compatibility", Compatibility),
        required_coverage=_nested_enum_counts(cases, "required", Coverage),
        suggested_coverage=_nested_enum_counts(cases, "suggested", Coverage),
        unavailable_dimensions=dict(sorted(unavailable.items())),
    )


def _capability_matrix(
    cases: tuple[StructuralCaseReport, ...],
) -> tuple[CapabilitySummary, ...]:
    result: list[CapabilitySummary] = []
    for capability in StructuralCapability:
        selected = tuple(case for case in cases if capability in case.capabilities)
        unavailable = Counter(
            name
            for case in selected
            for name, item in case.required.components
            if item.relation
            in {ComponentRelation.UNSUPPORTED, ComponentRelation.UNAVAILABLE}
        )
        result.append(
            CapabilitySummary(
                capability=capability,
                total_applicable_cases=len(selected),
                required_coverage=_nested_enum_counts(selected, "required", Coverage),
                required_conflicts=sum(
                    case.compatibility is Compatibility.CONFLICT for case in selected
                ),
                suggested_coverage=_nested_enum_counts(selected, "suggested", Coverage),
                unavailable_dimensions=dict(sorted(unavailable.items())),
            )
        )
    return tuple(result)


def _enum_counts(cases: tuple, attribute: str, enum_type: type[Enum]) -> dict[str, int]:
    counts = Counter(getattr(case, attribute).value for case in cases)
    return {item.value: counts[item.value] for item in enum_type}


def _nested_enum_counts(
    cases: tuple,
    attribute: str,
    enum_type: type[Enum],
) -> dict[str, int]:
    counts = Counter(
        getattr(getattr(case, attribute), "coverage").value for case in cases
    )
    return {item.value: counts[item.value] for item in enum_type}
