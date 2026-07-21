export type EvaluationAvailability =
  | "measured"
  | "partially_measured"
  | "not_measured"
  | "unavailable";

export type EvaluationRunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type EvaluationDifficulty = "easy" | "medium" | "hard" | "security";

export type EvaluationCaseType =
  | "template_query"
  | "free_query"
  | "authorization"
  | "unsafe_sql"
  | "clarification";

export type EvaluationExpectedOutcome =
  | "success"
  | "denied"
  | "unsafe_blocked"
  | "clarification";

export type EvaluationActualOutcome =
  | EvaluationExpectedOutcome
  | "execution_failed"
  | "internal_error";

export type EvaluationFailureReason =
  | "unexpected_outcome"
  | "execution_state_mismatch"
  | "referenced_tables_mismatch"
  | "row_count_mismatch"
  | "result_semantics_mismatch"
  | "missing_stable_key"
  | "invalid_numeric_value";

export type EvaluationErrorCode =
  | "access_denied"
  | "clarification_required"
  | "execution_failed"
  | "internal_error"
  | "unsafe_sql_blocked"
  | "evaluation_baseline_failed"
  | "evaluation_case_internal_error"
  | "evaluation_setup_failed"
  | "provider_authentication_failed"
  | "provider_timeout"
  | "provider_unavailable"
  | "provider_response_invalid";

export type EvaluationProvider = "mock" | "openai";

export type ReadinessVerdict = "ready" | "not_ready" | "incomplete";
export type ReadinessGateStatus = "passed" | "failed" | "incomplete";

export type ReadinessGate = {
  code: string;
  label: string;
  status: ReadinessGateStatus;
  threshold: number | null;
  actual: number | null;
  reason_code: string | null;
};

export type EvaluationReadiness = {
  policy_id: "queryops-v1-readiness-v1";
  verdict: ReadinessVerdict;
  provider: "openai" | null;
  model_label: string | null;
  dataset_version: string;
  completed_count: number | null;
  gates: ReadinessGate[];
  technical: {
    run_id: string;
    dataset_id: string;
    dataset_digest: string;
    selected_count: number | null;
    average_latency_ms: number | null;
    usage: {
      call_count: number;
      attempt_count: number;
      duration_ms: number;
      input_tokens: number;
      cached_input_tokens: number;
      output_tokens: number;
      total_tokens: number;
    } | null;
  } | null;
};

export type EvaluationRun = {
  id: string;
  provider: EvaluationProvider;
  model_label: string;
  dataset_id: string;
  dataset_version: string;
  dataset_digest: string;
  status: EvaluationRunStatus;
  started_at: string | null;
  completed_at: string | null;
};

export type EvaluationMetricSummary = {
  availability: EvaluationAvailability;
  eligible_count: number;
  selected_count: number;
  completed_count: number;
  passed_count: number;
  failed_count: number;
  overall_score: number | null;
  expected_behavior_match_rate: number | null;
  security_pass_rate: number | null;
  query_execution_succeeded_count: number;
  query_execution_failed_count: number;
};

export type EvaluationBreakdown = {
  key: string;
  eligible_count: number;
  completed_count: number;
  passed_count: number;
  failed_count: number;
  score: number | null;
};

export type EvaluationCoverage = {
  capability: "queries" | "actions" | "security" | "dashboards";
  availability: EvaluationAvailability;
  measured_case_count: number;
  score: number | null;
};

export type EvaluationOverview = {
  run: EvaluationRun | null;
  metrics: EvaluationMetricSummary;
  by_difficulty: EvaluationBreakdown[];
  by_category: EvaluationBreakdown[];
  by_case_type: EvaluationBreakdown[];
  coverage: EvaluationCoverage[];
};

export type EvaluationTechnicalDetails = {
  expected_outcome: EvaluationExpectedOutcome;
  actual_outcome: EvaluationActualOutcome;
  execution_succeeded: boolean;
  query_execution_attempted: boolean;
  expected_row_count: number;
  actual_row_count: number;
  missing_row_count: number;
  extra_row_count: number;
  failure_reasons: EvaluationFailureReason[];
  error_code: EvaluationErrorCode | null;
  duration_ms: number;
  referenced_tables: string[] | null;
};

export type EvaluationCaseMetric = {
  case_id: string;
  category: string;
  difficulty: EvaluationDifficulty;
  case_type: EvaluationCaseType;
  passed: boolean;
  score: number;
  technical: EvaluationTechnicalDetails | null;
};

export type EvaluationPagination = {
  limit: number;
  offset: number;
  returned: number;
  total: number;
};

export type EvaluationQueries = {
  run: EvaluationRun | null;
  metrics: EvaluationMetricSummary;
  by_difficulty: EvaluationBreakdown[];
  by_category: EvaluationBreakdown[];
  by_case_type: EvaluationBreakdown[];
  items: EvaluationCaseMetric[];
  pagination: EvaluationPagination;
};

export type EvaluationSecurity = {
  run: EvaluationRun | null;
  metrics: EvaluationMetricSummary;
  by_expected_behavior: EvaluationBreakdown[];
  items: EvaluationCaseMetric[];
};

export type EvaluationCapability = {
  run: EvaluationRun | null;
  capability: "actions" | "dashboards";
  availability: EvaluationAvailability;
  measured_cases: number;
  score: number | null;
  reason_code:
    | "action_evaluation_not_available"
    | "dashboard_evaluation_not_available";
};

export type EvaluationQueryFilters = {
  runId: string;
  difficulty?: EvaluationDifficulty;
  category?: string;
  caseType?: EvaluationCaseType;
  outcome?: EvaluationActualOutcome;
  passed?: boolean;
  limit?: number;
  offset?: number;
};

export type EvaluationTab =
  | "overview"
  | "queries"
  | "actions"
  | "security"
  | "dashboards";
