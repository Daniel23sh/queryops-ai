import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getMyDashboards } from "../../../api/dashboards";
import type { Dashboard } from "../types";
import { useMyDashboards } from "./useMyDashboards";

vi.mock("../../../api/dashboards", () => ({
  getMyDashboards: vi.fn()
}));

const getMyDashboardsMock = vi.mocked(getMyDashboards);

afterEach(() => {
  vi.clearAllMocks();
});

describe("useMyDashboards", () => {
  it("keeps the newest result when an earlier load resolves after reload", async () => {
    const initialLoad = deferred<Dashboard[]>();
    const reload = deferred<Dashboard[]>();
    getMyDashboardsMock
      .mockReturnValueOnce(initialLoad.promise)
      .mockReturnValueOnce(reload.promise);

    const { result } = renderHook(() => useMyDashboards());
    await waitFor(() => expect(getMyDashboardsMock).toHaveBeenCalledTimes(1));

    act(() => {
      void result.current.reload();
    });
    await waitFor(() => expect(getMyDashboardsMock).toHaveBeenCalledTimes(2));

    await act(async () => {
      reload.resolve([dashboard({ id: "new-dashboard" })]);
      await reload.promise;
    });

    expect(result.current.status).toBe("success");
    expect(result.current.dashboards.map((currentDashboard) => currentDashboard.id)).toEqual([
      "new-dashboard"
    ]);

    await act(async () => {
      initialLoad.resolve([dashboard({ id: "stale-dashboard" })]);
      await initialLoad.promise;
    });

    expect(result.current.status).toBe("success");
    expect(result.current.dashboards.map((currentDashboard) => currentDashboard.id)).toEqual([
      "new-dashboard"
    ]);
  });
});

function dashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    id: "dashboard-id",
    title: "Personal dashboard",
    description: null,
    visibility_scope: "personal",
    department_id: null,
    is_archived: false,
    created_at: "2026-07-12T10:00:00Z",
    updated_at: "2026-07-12T10:00:00Z",
    cards: [],
    ...overrides
  };
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  let reject: (reason?: unknown) => void = () => undefined;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}
