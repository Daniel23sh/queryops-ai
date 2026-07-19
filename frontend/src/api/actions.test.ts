import { afterEach, describe, expect, it, vi } from "vitest";

import type { ActionPreviewRequest } from "../features/actions/types";
import {
  cancelActionRequest,
  createActionPreview,
  getActionDetail,
  listOwnActionRequests,
  submitActionRequest
} from "./actions";

afterEach(() => vi.unstubAllGlobals());

describe("actions API client", () => {
  it.each([
    [
      "reclaim",
      {
        action_type: "reclaim_unused_license",
        source_query_run_id: "00000000-0000-4000-8000-000000000001",
        scope_id: "00000000-0000-4000-8000-000000000002",
        department_id: "00000000-0000-4000-8000-000000000003",
        reason: "Review unused licenses.",
        license_assignment_ids: ["00000000-0000-4000-8000-000000000004"]
      } satisfies ActionPreviewRequest
    ],
    [
      "disable",
      {
        action_type: "disable_inactive_user",
        source_query_run_id: "00000000-0000-4000-8000-000000000001",
        scope_id: "00000000-0000-4000-8000-000000000002",
        reason: "Review inactive users.",
        target_user_ids: ["00000000-0000-4000-8000-000000000005"]
      } satisfies ActionPreviewRequest
    ]
  ])("sends the exact %s preview body and CSRF header", async (_label, payload) => {
    const fetchMock = stubFetch({ id: "action-id" });

    await createActionPreview(payload, "csrf-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/actions/preview",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: JSON.stringify(payload)
      }
    );
  });

  it("submits, lists, loads, and cancels through the generic lifecycle routes", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(apiResponse({})));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await submitActionRequest(
      { action_request_id: "action/id", reason: "Submit safely." },
      "csrf"
    );
    await listOwnActionRequests(
      { statusGroup: "closed", limit: 10, offset: 20 },
      controller.signal
    );
    await getActionDetail("action/id", controller.signal);
    await cancelActionRequest("action/id", "No longer needed.", "csrf");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/actions/request",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ action_request_id: "action/id", reason: "Submit safely." })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/actions?status_group=closed&limit=10&offset=20",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/v1/actions/action%2Fid",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "http://localhost:8000/api/v1/actions/action%2Fid/cancel",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf" }),
        body: JSON.stringify({ reason: "No longer needed." })
      })
    );
  });
});

function stubFetch(data: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(apiResponse(data));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function apiResponse(data: unknown) {
  return new Response(JSON.stringify({ data }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}
