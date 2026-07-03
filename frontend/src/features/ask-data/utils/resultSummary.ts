import type { QueryResultRow, QueryRunMode, QueryRunResult } from "../types";
import { valueForColumn } from "./formatResultValue";

export function runningQueryMessage(mode: QueryRunMode): string {
  if (mode === "template") {
    return "Running selected template...";
  }

  if (mode === "clarification") {
    return "Submitting clarification...";
  }

  return "Running free query...";
}

export function buildVisualizationSuggestion(
  columns: string[],
  rows: QueryResultRow[]
): string {
  if (columns.length === 0 || rows.length === 0) {
    return "Chart available later when rows are returned.";
  }

  const numericColumn = columns.find((column) =>
    rows.some((row) => {
      const value = valueForColumn(row, column);
      return typeof value === "number" && Number.isFinite(value);
    })
  );

  if (!numericColumn) {
    return "Chart available later: table view is the safest display for this result shape.";
  }

  const labelColumn = columns.find(
    (column) =>
      column !== numericColumn &&
      rows.some((row) => typeof valueForColumn(row, column) === "string")
  );

  if (!labelColumn) {
    return `Chart available later: summarize ${numericColumn}.`;
  }

  return `Chart available later: compare ${numericColumn} by ${labelColumn}.`;
}

export function clarificationDisabledReason(
  result: QueryRunResult,
  csrfToken: string | null
): string | null {
  if (!result.query_run_id) {
    return "This clarification cannot be continued. Run a new query instead.";
  }

  if (!csrfToken) {
    return "Refresh your session before submitting clarification.";
  }

  return null;
}
