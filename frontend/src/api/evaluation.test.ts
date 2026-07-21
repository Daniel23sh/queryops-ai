import { afterEach, describe, expect, it, vi } from "vitest";

import {
  evaluationRequestKey,
  getEvaluationActions,
  getEvaluationDashboards,
  getEvaluationOverview,
  getEvaluationQueries,
  getEvaluationSecurity
} from "./evaluation";

afterEach(() => vi.unstubAllGlobals());

describe("evaluation API client", () => {
  it("uses GET and forwards the exact run to every metrics endpoint", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(apiResponse()));
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    await getEvaluationOverview(undefined, signal);
    await getEvaluationActions("run/id", signal);
    await getEvaluationSecurity("run/id", signal);
    await getEvaluationDashboards("run/id", signal);

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://localhost:8000/api/v1/evaluation/overview",
      "http://localhost:8000/api/v1/evaluation/actions?run_id=run%2Fid",
      "http://localhost:8000/api/v1/evaluation/security?run_id=run%2Fid",
      "http://localhost:8000/api/v1/evaluation/dashboards?run_id=run%2Fid"
    ]);
    for (const [, init] of fetchMock.mock.calls) expect(init).toEqual(expect.objectContaining({ method: "GET", signal }));
  });

  it("serializes only supported query filters and bounds pagination", async () => {
    const fetchMock = vi.fn().mockResolvedValue(apiResponse());
    vi.stubGlobal("fetch", fetchMock);
    await getEvaluationQueries({ runId: "stable-run", difficulty: "security", category: "directory users", caseType: "unsafe_sql", outcome: "execution_failed", passed: false, limit: 500, offset: -20 });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toBe("http://localhost:8000/api/v1/evaluation/queries?run_id=stable-run&difficulty=security&category=directory+users&case_type=unsafe_sql&outcome=execution_failed&passed=false&limit=100&offset=0");
    expect(url).not.toContain("scope");
    expect(url).not.toContain("department");
  });

  it("keeps identity, endpoint, run and filters in request isolation keys", () => {
    expect(evaluationRequestKey("user-a", "queries", "run-a", "page=1")).not.toBe(evaluationRequestKey("user-b", "queries", "run-a", "page=1"));
    expect(evaluationRequestKey("user-a", "queries", "run-a", "page=1")).not.toBe(evaluationRequestKey("user-a", "queries", "run-b", "page=1"));
  });
});

function apiResponse() {
  return new Response(JSON.stringify({ data: {} }), { status: 200, headers: { "Content-Type": "application/json" } });
}
