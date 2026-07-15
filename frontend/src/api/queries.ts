import { apiRequest } from "./client";
import type {
  EmptyQueryParameters,
  QueryHistoryItem,
  QueryHistoryParams,
  QueryRunRequest,
  QueryRunResult,
  ScopeQueryHistoryParams
} from "../features/ask-data/types";

export async function runQuery(
  payload: QueryRunRequest,
  csrfToken: string
): Promise<QueryRunResult> {
  return apiRequest<QueryRunResult>("/api/v1/queries/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken
    },
    body: JSON.stringify(queryRunRequestBody(payload))
  });
}

export function clarifyQuery(
  queryRunId: string,
  question: string,
  csrfToken: string
): Promise<QueryRunResult> {
  return apiRequest<QueryRunResult>(
    `/api/v1/queries/${encodeURIComponent(queryRunId)}/clarify`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken
      },
      body: JSON.stringify({ question })
    }
  );
}

export function getQueryHistory(
  params?: QueryHistoryParams
): Promise<QueryHistoryItem[]> {
  return getHistory("/api/v1/queries/history", params);
}

export function getScopeQueryHistory(
  params?: ScopeQueryHistoryParams
): Promise<QueryHistoryItem[]> {
  return getHistory("/api/v1/queries/scope-history", params);
}

export function getDepartmentQueryHistory(
  params?: ScopeQueryHistoryParams
): Promise<QueryHistoryItem[]> {
  return getHistory("/api/v1/queries/department-history", params);
}

function getHistory(
  path: string,
  params?: QueryHistoryParams
): Promise<QueryHistoryItem[]> {
  return apiRequest<QueryHistoryItem[]>(pathWithQueryParams(path, params), {
    method: "GET"
  });
}

function queryRunRequestBody(payload: QueryRunRequest): QueryRunRequest {
  const body: QueryRunRequest = {
    question: payload.question
  };

  if (payload.template_id !== undefined) {
    body.template_id = payload.template_id;
  }

  if (payload.parameters !== undefined) {
    assertSupportedParameters(payload.parameters);
    body.parameters = payload.parameters;
  }

  return body;
}

function assertSupportedParameters(
  parameters: EmptyQueryParameters | null
): void {
  if (parameters === null) {
    return;
  }

  if (
    typeof parameters !== "object" ||
    Array.isArray(parameters) ||
    Object.keys(parameters).length > 0
  ) {
    throw new Error("Query parameters are not supported yet.");
  }
}

function pathWithQueryParams(
  path: string,
  params?: QueryHistoryParams
): string {
  if (params === undefined) {
    return path;
  }

  const queryParams = new URLSearchParams();
  if (params.limit !== undefined) {
    queryParams.set("limit", String(params.limit));
  }
  if (params.offset !== undefined) {
    queryParams.set("offset", String(params.offset));
  }
  if (params.include_sql !== undefined) {
    queryParams.set("include_sql", String(params.include_sql));
  }

  const queryString = queryParams.toString();
  return queryString ? `${path}?${queryString}` : path;
}
