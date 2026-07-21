import type {
  EvaluationActualOutcome,
  EvaluationAvailability,
  EvaluationCaseType,
  EvaluationExpectedOutcome,
  EvaluationFailureReason,
  EvaluationRun
} from "./types";

export function matchesSelectedRun(
  run: Pick<EvaluationRun, "id"> | null,
  selectedRunId: string
): boolean {
  return run?.id === selectedRunId;
}

export function formatEvaluationPercent(value: number | null): string {
  return value === null ? "Not available" : `${(value * 100).toFixed(1)}%`;
}

export function formatEvaluationDate(value: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Not available"
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(date);
}

export function availabilityLabel(value: EvaluationAvailability): string {
  return {
    measured: "Measured",
    partially_measured: "Partially measured",
    not_measured: "Not measured",
    unavailable: "Unavailable"
  }[value];
}

export function outcomeLabel(
  value: EvaluationExpectedOutcome | EvaluationActualOutcome
): string {
  return {
    success: "Successful result",
    denied: "Authorization denied",
    unsafe_blocked: "Unsafe query blocked",
    clarification: "Clarification requested",
    execution_failed: "Execution failed",
    internal_error: "Internal evaluation error"
  }[value];
}

export function caseTypeLabel(value: EvaluationCaseType): string {
  return {
    template_query: "Template query",
    free_query: "Free query",
    authorization: "Authorization",
    unsafe_sql: "Unsafe query",
    clarification: "Clarification"
  }[value];
}

export function failureReasonLabel(value: EvaluationFailureReason): string {
  return {
    unexpected_outcome: "Unexpected outcome",
    execution_state_mismatch: "Execution state mismatch",
    referenced_tables_mismatch: "Resource match mismatch",
    row_count_mismatch: "Row count mismatch",
    result_semantics_mismatch: "Result semantics mismatch",
    missing_stable_key: "Stable comparison key missing",
    invalid_numeric_value: "Invalid numeric comparison"
  }[value];
}

export function safeBreakdownLabel(value: string): string {
  const known: Record<string, string> = {
    easy: "Easy",
    medium: "Medium",
    hard: "Hard",
    security: "Security",
    template_query: "Template query",
    free_query: "Free query",
    authorization: "Authorization denial",
    unsafe_sql: "Unsafe query",
    clarification: "Clarification",
    authorization_denial: "Authorization denial",
    scope_denial: "Scope denial",
    unsafe_query_block: "Unsafe-query block",
    protected_resource_denial: "Protected-resource denial"
  };
  return known[value] ?? value.replace(/_/g, " ");
}
