import { afterEach, describe, expect, it, vi } from "vitest";

import {
  approveApproval,
  getApprovalDetail,
  listPendingApprovals,
  rejectApproval
} from "./approvals";

afterEach(() => vi.unstubAllGlobals());

describe("approvals API client", () => {
  it("serializes bounded reads, URL-encodes IDs, and forwards AbortSignal", async () => {
    const fetchMock = stubFetch({});
    const controller = new AbortController();

    await listPendingApprovals({ limit: 10, offset: 20 }, controller.signal);
    await getApprovalDetail("approval/id", controller.signal);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/approvals/pending?limit=10&offset=20",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/approvals/approval%2Fid",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
  });

  it("sends only the trimmed reason and CSRF token for both decisions", async () => {
    const fetchMock = stubFetch({});

    await approveApproval("approval/id", "  Reviewed safely.  ", "csrf");
    await rejectApproval("approval/id", "  Needs more review.  ", "csrf");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/approvals/approval%2Fid/approve",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf" }),
        body: JSON.stringify({ decision_reason: "Reviewed safely." })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/approvals/approval%2Fid/reject",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ decision_reason: "Needs more review." })
      })
    );
  });
});

function stubFetch(data: unknown) {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
    new Response(JSON.stringify({ data }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  ));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
