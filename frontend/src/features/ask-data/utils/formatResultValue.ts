import type { QueryResultRow, QueryRowValue } from "../types";

export function firstRowColumns(rows: QueryResultRow[]): string[] {
  return rows[0] ? Object.keys(rows[0]) : [];
}

export function valueForColumn(
  row: QueryResultRow,
  column: string
): QueryRowValue | undefined {
  return Object.prototype.hasOwnProperty.call(row, column)
    ? row[column]
    : undefined;
}

export function formatResultValue(value: QueryRowValue | undefined): string {
  if (value === undefined || value === null) {
    return "null";
  }

  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return JSON.stringify(value) ?? "";
}
