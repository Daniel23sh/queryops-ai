import { afterEach, describe, expect, it, vi } from "vitest";

import { listAuditLogs } from "./audit";

afterEach(() => vi.unstubAllGlobals());

describe("audit API client", () => {
  it("serializes the supported filters safely and forwards AbortSignal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(apiResponse());
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await listAuditLogs(
      {
        eventType: "action executed",
        actorAppUserId: "actor/id",
        scopeId: "scope/id",
        scopeType: "department",
        scopeKey: "finance & legal",
        departmentId: "department/id",
        fromDate: "2026-07-01T00:00:00Z",
        toDate: "2026-07-20T23:59:59Z",
        limit: 10,
        offset: 30
      },
      controller.signal
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/audit/logs?event_type=action+executed&actor_app_user_id=actor%2Fid&scope_id=scope%2Fid&scope_type=department&scope_key=finance+%26+legal&department_id=department%2Fid&from_date=2026-07-01T00%3A00%3A00Z&to_date=2026-07-20T23%3A59%3A59Z&limit=10&offset=30",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
  });
});

function apiResponse() {
  return new Response(JSON.stringify({ data: {} }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}
