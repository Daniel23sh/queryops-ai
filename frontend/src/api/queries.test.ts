import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import {
  clarifyQuery,
  getDepartmentQueryHistory,
  getQueryHistory,
  getScopeQueryHistory,
  runQuery
} from "./queries";
import type { QueryRunRequest } from "../features/ask-data/types";

const backendQueryResult = {
  query_run_id: "query-run-id",
  status: "succeeded",
  columns: ["priority", "ticket_count"],
  rows: [{ priority: "high", ticket_count: 3 }],
  row_count: 1,
  duration_ms: 2.4,
  truncated: false,
  message: "Query completed successfully.",
  warnings: [],
  clarification_required: false,
  metadata: {
    provider: "mock",
    model: "mock-queryops-v1",
    template_id: "open_support_tickets_by_department",
    referenced_tables: ["support_tickets"],
    scope_type: "department",
    clarification_required: false,
    validation: { valid: true, error_code: null },
    execution: {
      status: "succeeded",
      error_code: null,
      row_count: 1,
      duration_ms: 2.4,
      truncated: false
    }
  },
  generated_sql: "SELECT priority, count(*) FROM support_tickets",
  executed_sql: "SELECT priority, count(*) FROM support_tickets"
};

const backendHistoryItem = {
  id: "query-run-id",
  status: "succeeded",
  natural_language_question: "How many open tickets exist?",
  row_count: 1,
  duration_ms: 2,
  error_message: null,
  created_at: "2026-07-02T12:00:00Z",
  started_at: "2026-07-02T12:00:00Z",
  completed_at: "2026-07-02T12:00:02Z",
  metadata: backendQueryResult.metadata,
  generated_sql: "SELECT generated",
  executed_sql: "SELECT executed"
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("queries API client", () => {
  it("runs free queries with cookies and the CSRF header included", async () => {
    const fetchMock = stubFetch({
      data: backendQueryResult,
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-02T12:00:00Z"
      }
    });

    const result = await runQuery(
      { question: "How many open tickets exist?" },
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/queries/run",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: JSON.stringify({ question: "How many open tickets exist?" })
      }
    );
    expect(result).toEqual(backendQueryResult);
  });

  it("runs template queries without adding unsupported parameters by default", async () => {
    const fetchMock = stubFetch({
      data: backendQueryResult,
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-02T12:00:00Z"
      }
    });

    await runQuery(
      {
        question: "How many open support tickets exist in my department by priority?",
        template_id: "open_support_tickets_by_department"
      },
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/queries/run",
      expect.objectContaining({
        body: JSON.stringify({
          question:
            "How many open support tickets exist in my department by priority?",
          template_id: "open_support_tickets_by_department"
        })
      })
    );
  });

  it("allows null or empty query parameters only", async () => {
    const fetchMock = stubFetch({
      data: backendQueryResult,
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-02T12:00:00Z"
      }
    });

    await runQuery(
      {
        question: "Run template with explicit null parameters.",
        template_id: "open_support_tickets_by_department",
        parameters: null
      },
      "csrf-token"
    );
    await runQuery(
      {
        question: "Run template with explicit empty parameters.",
        template_id: "open_support_tickets_by_department",
        parameters: {}
      },
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/queries/run",
      expect.objectContaining({
        body: JSON.stringify({
          question: "Run template with explicit null parameters.",
          template_id: "open_support_tickets_by_department",
          parameters: null
        })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/queries/run",
      expect.objectContaining({
        body: JSON.stringify({
          question: "Run template with explicit empty parameters.",
          template_id: "open_support_tickets_by_department",
          parameters: {}
        })
      })
    );

    await expect(
      runQuery(
        {
          question: "Do not send non-empty parameters.",
          parameters: { unsupported: "value" }
        } as unknown as QueryRunRequest,
        "csrf-token"
      )
    ).rejects.toThrow("Query parameters are not supported yet.");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("clarifies queries with an encoded query run id and CSRF header", async () => {
    const fetchMock = stubFetch({
      data: backendQueryResult,
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-02T12:00:00Z"
      }
    });

    const result = await clarifyQuery(
      "folder/query run id",
      "Show non-compliant devices in my department.",
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/queries/folder%2Fquery%20run%20id/clarify",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: JSON.stringify({
          question: "Show non-compliant devices in my department."
        })
      }
    );
    expect(result).toEqual(backendQueryResult);
  });

  it("gets own query history with encoded pagination params", async () => {
    const fetchMock = stubFetch({
      data: [backendHistoryItem],
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-02T12:00:00Z"
      }
    });

    const result = await getQueryHistory({ limit: 10, offset: 5 });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/queries/history?limit=10&offset=5",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
    expect(result).toEqual([backendHistoryItem]);
  });

  it("gets scope query history with encoded pagination params", async () => {
    const fetchMock = stubFetch({
      data: [backendHistoryItem],
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-02T12:00:00Z"
      }
    });

    await getScopeQueryHistory({ limit: 25, offset: 10 });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/queries/scope-history?limit=25&offset=10",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
  });

  it("gets department query history through the V1 compatibility alias", async () => {
    const fetchMock = stubFetch({
      data: [backendHistoryItem],
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-02T12:00:00Z"
      }
    });

    await getDepartmentQueryHistory({ limit: 30, offset: 20 });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/queries/department-history?limit=30&offset=20",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
  });

  it("surfaces API errors through the shared ApiError type", async () => {
    stubFetch(
      {
        error: {
          code: "INVALID_QUERY_REQUEST",
          message: "Query request is invalid or unsupported.",
          details: {},
          request_id: "request-id"
        }
      },
      { ok: false, status: 400 }
    );

    try {
      await runQuery({ question: "" }, "csrf-token");
      throw new Error("Expected runQuery to reject");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({
        code: "INVALID_QUERY_REQUEST",
        message: "Query request is invalid or unsupported.",
        status: 400
      });
    }
  });
});

function stubFetch(
  payload: unknown,
  options: { ok?: boolean; status?: number } = {}
) {
  const response = {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    json: vi.fn().mockResolvedValue(payload)
  };
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
