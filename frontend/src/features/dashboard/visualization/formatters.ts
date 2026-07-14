import type { QueryRowValue } from "../../ask-data/types";

export function formatVisualizationValue(value: QueryRowValue | undefined): string {
  if (value === undefined || value === null) return "—";
  if (typeof value === "number") {
    return Number.isFinite(value) ? new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value) : "—";
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value;
  return "[structured value]";
}

export function numericValue(value: QueryRowValue | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
