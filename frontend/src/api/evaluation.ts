import type {
  EvaluationCapability,
  EvaluationOverview,
  EvaluationReadiness,
  EvaluationQueries,
  EvaluationQueryFilters,
  EvaluationSecurity
} from "../features/evaluation/types";
import { apiRequest } from "./client";

const MAX_QUERY_PAGE_SIZE = 100;

export function getEvaluationReadiness(
  signal?: AbortSignal
): Promise<EvaluationReadiness> {
  return apiRequest<EvaluationReadiness>("/api/v1/evaluation/readiness", {
    method: "GET",
    signal
  });
}

export function getEvaluationOverview(
  runId?: string,
  signal?: AbortSignal
): Promise<EvaluationOverview> {
  return apiRequest<EvaluationOverview>(evaluationPath("overview", runId), {
    method: "GET",
    signal
  });
}

export function getEvaluationQueries(
  filters: EvaluationQueryFilters,
  signal?: AbortSignal
): Promise<EvaluationQueries> {
  const query = new URLSearchParams();
  query.set("run_id", filters.runId);
  append(query, "difficulty", filters.difficulty);
  append(query, "category", boundedCategory(filters.category));
  append(query, "case_type", filters.caseType);
  append(query, "outcome", filters.outcome);
  if (filters.passed !== undefined) query.set("passed", String(filters.passed));
  query.set("limit", String(boundedInteger(filters.limit ?? 25, 1, MAX_QUERY_PAGE_SIZE)));
  query.set("offset", String(boundedInteger(filters.offset ?? 0, 0, Number.MAX_SAFE_INTEGER)));
  return apiRequest<EvaluationQueries>(`/api/v1/evaluation/queries?${query}`, {
    method: "GET",
    signal
  });
}

export function getEvaluationActions(
  runId: string,
  signal?: AbortSignal
): Promise<EvaluationCapability> {
  return apiRequest<EvaluationCapability>(evaluationPath("actions", runId), {
    method: "GET",
    signal
  });
}

export function getEvaluationSecurity(
  runId: string,
  signal?: AbortSignal
): Promise<EvaluationSecurity> {
  return apiRequest<EvaluationSecurity>(evaluationPath("security", runId), {
    method: "GET",
    signal
  });
}

export function getEvaluationDashboards(
  runId: string,
  signal?: AbortSignal
): Promise<EvaluationCapability> {
  return apiRequest<EvaluationCapability>(evaluationPath("dashboards", runId), {
    method: "GET",
    signal
  });
}

export function evaluationRequestKey(
  identityKey: string,
  endpoint: "overview" | "queries" | "actions" | "security" | "dashboards" | "readiness",
  runId: string | null,
  filters = ""
): string {
  return JSON.stringify([identityKey, endpoint, runId, filters]);
}

function evaluationPath(endpoint: string, runId?: string): string {
  const query = new URLSearchParams();
  if (runId) query.set("run_id", runId);
  const suffix = query.size ? `?${query}` : "";
  return `/api/v1/evaluation/${endpoint}${suffix}`;
}

function append(
  query: URLSearchParams,
  key: string,
  value: string | undefined
) {
  if (value) query.set(key, value);
}

function boundedCategory(value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  const normalized = value.trim();
  if (!normalized || normalized.length > 64) {
    throw new Error("Invalid Evaluation category filter.");
  }
  return normalized;
}

function boundedInteger(value: number, minimum: number, maximum: number): number {
  if (!Number.isFinite(value)) return minimum;
  return Math.min(maximum, Math.max(minimum, Math.trunc(value)));
}

export { MAX_QUERY_PAGE_SIZE };
