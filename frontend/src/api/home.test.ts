import { afterEach, describe, expect, it, vi } from "vitest";

import { getHomeOverview } from "./home";

afterEach(() => vi.unstubAllGlobals());

describe("Home API", () => {
  it("unwraps the overview and forwards cancellation", async () => {
    const overview = {
      mode: "personal",
      scope: { type: "department", display_name: "Sales", scope_count: 1 },
      personal_summary: {
        owned_dashboard_count: 1,
        shared_dashboard_count: 0,
        owned_card_count: 2,
        successful_queries_last_30_days: 3,
        pending_own_role_requests: 0
      },
      operational_metrics: null,
      admin_metrics: null
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ data: overview, meta: {} })
    });
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(getHomeOverview(controller.signal)).resolves.toEqual(overview);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/home/overview",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
  });
});
