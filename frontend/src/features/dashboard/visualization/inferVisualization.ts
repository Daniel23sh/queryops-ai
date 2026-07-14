import type { QueryResultRow, QueryRowValue } from "../../ask-data/types";
import type { DashboardCardType, VisualizationMapping } from "../types";
import type {
  ColumnKind,
  ColumnProfile,
  VisualizationInput,
  VisualizationRecommendation
} from "./types";

const MAX_CATEGORY_COUNT = 24;
const DONUT_MAX_CATEGORY_COUNT = 6;
const STACKED_MAX_SERIES_COUNT = 8;

export function inferVisualization(input: VisualizationInput): VisualizationRecommendation {
  const profiles = input.columns
    .map((column) => profileColumn(column, input.rows))
    .filter((profile) => profile.nonNullCount > 0);
  const numeric = profiles.filter((profile) => profile.kind === "numeric");
  const temporal = profiles.find((profile) => profile.kind === "temporal");
  const status = profiles.find((profile) => profile.kind === "status");
  const categories = profiles.filter((profile) => profile.kind === "categorical");
  const compatible = new Set<DashboardCardType>(["table"]);
  let recommendedType: DashboardCardType = "table";
  let confidence: VisualizationRecommendation["confidence"] = "low";
  let reason = "The result shape is safest to read as a table.";

  if (input.rows.length === 1 && numeric.length >= 1) {
    compatible.add("kpi");
    recommendedType = "kpi";
    confidence = "high";
    reason = "A single row with a primary numeric value is best summarized as a KPI.";
    if (hasGaugeSemantics(numeric, profiles)) {
      compatible.add("semicircle_gauge");
      recommendedType = "semicircle_gauge";
      reason = "The result contains a bounded percentage or value-and-target pair.";
    }
  }

  if (temporal && numeric.length > 0 && input.rows.length >= 2) {
    compatible.add("line");
    compatible.add("area");
    recommendedType = hasVolumeSemantics(numeric) ? "area" : "line";
    confidence = "high";
    reason = "A temporal dimension and numeric measure form a time series.";
  } else if (categories.length > 0 && numeric.length > 0) {
    const category = categories[0];
    if (category.distinctCount <= MAX_CATEGORY_COUNT) {
      compatible.add("bar");
      recommendedType = "bar";
      confidence = "high";
      reason = "A category and numeric measure form a comparison.";
    }
    const series = categories[1] ?? status;
    if (series && series.distinctCount <= STACKED_MAX_SERIES_COUNT && category.distinctCount <= 12) {
      compatible.add("stacked_bar");
      if (categories.length > 1) {
        recommendedType = "stacked_bar";
        reason = "The result has bounded category, series, and numeric dimensions.";
      }
    }
    if (
      category.distinctCount >= 2 &&
      category.distinctCount <= DONUT_MAX_CATEGORY_COUNT &&
      hasPartToWholeSemantics(numeric) &&
      valuesAreNonNegative(numeric[0].name, input.rows)
    ) {
      compatible.add("donut");
      recommendedType = "donut";
      reason = "The result is a bounded non-negative share distribution.";
    }
  }

  if (status && input.rows.length > 0 && input.rows.length <= 12) {
    compatible.add("status_list");
    if (numeric.length === 0 || categories.length === 0) {
      recommendedType = "status_list";
      confidence = "medium";
      reason = "A small set of status-like rows is clearest as a status list.";
    }
  }

  const mapping = mappingForType(recommendedType, profiles);
  const manualType = input.currentConfig?.mode === "manual" ? input.currentConfig.type : null;
  const manualCompatible = manualType ? compatible.has(manualType) : true;
  return {
    recommendedType,
    renderType: manualType && manualCompatible ? manualType : manualType ? "table" : recommendedType,
    compatibleTypes: orderCompatible(compatible),
    mapping,
    confidence,
    reason,
    warning: manualType && !manualCompatible
      ? "The saved visualization is not compatible with this result. Showing Table until you choose another visualization or reset to recommended."
      : null,
    profiles
  };
}

export function profileColumn(name: string, rows: QueryResultRow[]): ColumnProfile {
  const values = rows.map((row) => row[name]).filter((value) => value !== null && value !== undefined);
  return {
    name,
    kind: classifyColumn(name, values),
    distinctCount: new Set(values.map(stableValue)).size,
    nonNullCount: values.length
  };
}

function classifyColumn(name: string, values: QueryRowValue[]): ColumnKind {
  if (values.length === 0) return "unsupported";
  const normalized = name.toLowerCase();
  if (values.every((value) => typeof value === "boolean")) return "status";
  if (values.every((value) => typeof value === "number" && Number.isFinite(value))) {
    return /(^id$|_id$|identifier|serial|account_number)/i.test(normalized)
      ? "categorical"
      : "numeric";
  }
  if (values.every((value) => typeof value === "string")) {
    const strings = values as string[];
    if (isTemporalColumn(normalized, strings)) return "temporal";
    if (/(status|state|health|compliance|severity|enabled|active)/i.test(normalized)) return "status";
    return "categorical";
  }
  return "unsupported";
}

function isTemporalColumn(name: string, values: string[]): boolean {
  if (!/(date|time|month|year|week|day|created|updated|period)/i.test(name)) return false;
  return values.every((value) => value.trim() !== "" && Number.isFinite(Date.parse(value)));
}

export function mappingForType(type: DashboardCardType, profiles: ColumnProfile[]): VisualizationMapping {
  const numeric = profiles.filter((profile) => profile.kind === "numeric");
  const temporal = profiles.find((profile) => profile.kind === "temporal");
  const category = temporal ?? profiles.find((profile) => profile.kind === "categorical" || profile.kind === "status");
  const series = profiles.find((profile) => profile !== category && (profile.kind === "categorical" || profile.kind === "status"));
  const target = numeric.find((profile) => /(target|total|max|limit|capacity)/i.test(profile.name));
  return {
    category_column: ["bar", "line", "area", "donut", "stacked_bar"].includes(type) ? category?.name ?? null : null,
    value_columns: numeric.filter((profile) => profile !== target).slice(0, 4).map((profile) => profile.name),
    series_column: type === "stacked_bar" ? series?.name ?? null : null,
    label_column: ["kpi", "semicircle_gauge", "status_list"].includes(type) ? category?.name ?? null : null,
    target_column: type === "semicircle_gauge" ? target?.name ?? null : null
  };
}

function hasGaugeSemantics(numeric: ColumnProfile[], profiles: ColumnProfile[]): boolean {
  return numeric.some((profile) => /(percent|percentage|rate|ratio|progress|utilization)/i.test(profile.name)) ||
    (numeric.some((profile) => /(current|value|count)/i.test(profile.name)) &&
      profiles.some((profile) => /(target|total|max|limit|capacity)/i.test(profile.name)));
}
function hasVolumeSemantics(numeric: ColumnProfile[]): boolean {
  return numeric.some((profile) => /(cumulative|volume|usage|traffic|total_over_time)/i.test(profile.name));
}
function hasPartToWholeSemantics(numeric: ColumnProfile[]): boolean {
  return numeric.some((profile) => /(share|percent|percentage|distribution|proportion)/i.test(profile.name));
}
function valuesAreNonNegative(column: string, rows: QueryResultRow[]): boolean {
  return rows.every((row) => row[column] == null || (typeof row[column] === "number" && row[column] >= 0));
}
function stableValue(value: QueryRowValue): string {
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
function orderCompatible(types: Set<DashboardCardType>): DashboardCardType[] {
  const order: DashboardCardType[] = ["kpi", "table", "bar", "line", "area", "donut", "semicircle_gauge", "stacked_bar", "status_list"];
  return order.filter((type) => types.has(type));
}
