import type { DiagnosticItem, QuerySelfCorrectionMetadata } from "../types";

export function safeSqlText(sql: string | null | undefined): string | null {
  if (typeof sql !== "string") {
    return null;
  }

  const trimmedSql = sql.trim();
  return trimmedSql.length > 0 ? trimmedSql : null;
}

export function safeDiagnosticText(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmedValue = value.trim();
  if (!trimmedValue || containsSqlLikeText(trimmedValue)) {
    return null;
  }

  return trimmedValue;
}

export function formatDiagnosticValue(
  value: boolean | number | string | null | undefined
): string | null {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (typeof value === "number") {
    return String(value);
  }

  return safeDiagnosticText(value);
}

export function formatReferencedTables(tables: string[] | undefined): string | null {
  if (!Array.isArray(tables)) {
    return null;
  }

  const safeTables = tables
    .map(safeDiagnosticText)
    .filter((table): table is string => table !== null);

  return safeTables.length > 0 ? safeTables.join(", ") : null;
}

export function formatValidationStatus(valid: boolean | null): string | null {
  if (valid === true) {
    return "Valid";
  }

  if (valid === false) {
    return "Invalid";
  }

  return null;
}

export function selfCorrectionItems(
  selfCorrection: QuerySelfCorrectionMetadata
): DiagnosticItem[] {
  return [
    {
      label: "Correction attempted",
      value: selfCorrection.attempted
    },
    {
      label: "Correction status",
      value: formatSelfCorrectionStatus(selfCorrection)
    },
    {
      label: "Original correction error code",
      value: selfCorrection.original_error_code
    },
    {
      label: "Final correction error code",
      value: selfCorrection.final_error_code
    }
  ];
}

function formatSelfCorrectionStatus(
  selfCorrection: QuerySelfCorrectionMetadata
): string | null {
  if (selfCorrection.attempted === false) {
    return "Not attempted";
  }

  if (selfCorrection.attempted !== true) {
    return null;
  }

  if (selfCorrection.succeeded === true) {
    return "Succeeded";
  }

  if (selfCorrection.succeeded === false) {
    return "Failed";
  }

  return "Attempted";
}

function containsSqlLikeText(value: string): boolean {
  return /\b(select|with|insert|update|delete|drop|alter|create|truncate)\b/i.test(
    value
  );
}
