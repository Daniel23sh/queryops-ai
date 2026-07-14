import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getHomeOverview } from "../../../api/home";
import type { HomeOverview } from "../types";
import { useHomeOverview } from "./useHomeOverview";

vi.mock("../../../api/home", () => ({ getHomeOverview: vi.fn() }));
const getHomeOverviewMock = vi.mocked(getHomeOverview);

beforeEach(() => getHomeOverviewMock.mockReset());

describe("useHomeOverview", () => {
  it("ignores a stale response after reload", async () => {
    const stale = deferred<HomeOverview>();
    const latest = deferred<HomeOverview>();
    getHomeOverviewMock.mockReturnValueOnce(stale.promise).mockReturnValueOnce(latest.promise);
    const { result } = renderHook(() => useHomeOverview());
    await waitFor(() => expect(getHomeOverviewMock).toHaveBeenCalledTimes(1));

    act(() => void result.current.reload());
    await waitFor(() => expect(getHomeOverviewMock).toHaveBeenCalledTimes(2));
    await act(async () => latest.resolve(overview("Latest")));
    expect(result.current.overview?.scope.display_name).toBe("Latest");
    await act(async () => stale.resolve(overview("Stale")));
    expect(result.current.overview?.scope.display_name).toBe("Latest");
  });
});

function overview(scopeName: string): HomeOverview {
  return {
    mode: "personal",
    scope: { type: "personal", display_name: scopeName, scope_count: 0 },
    personal_summary: {
      owned_dashboard_count: 0,
      shared_dashboard_count: 0,
      owned_card_count: 0,
      successful_queries_last_30_days: 0,
      pending_own_role_requests: 0
    },
    operational_metrics: null,
    admin_metrics: null
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  return {
    promise: new Promise<T>((currentResolve) => {
      resolve = currentResolve;
    }),
    resolve
  };
}
