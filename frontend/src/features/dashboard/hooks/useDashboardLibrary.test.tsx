import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getDashboardLibrary } from "../../../api/dashboards";
import type { DashboardLibraryItem } from "../types";
import { useDashboardLibrary } from "./useDashboardLibrary";

vi.mock("../../../api/dashboards", () => ({ getDashboardLibrary: vi.fn() }));
const getDashboardLibraryMock = vi.mocked(getDashboardLibrary);

beforeEach(() => getDashboardLibraryMock.mockReset());

describe("useDashboardLibrary", () => {
  it("ignores a stale response after reload", async () => {
    const stale = deferred<DashboardLibraryItem[]>();
    const latest = deferred<DashboardLibraryItem[]>();
    getDashboardLibraryMock
      .mockReturnValueOnce(stale.promise)
      .mockReturnValueOnce(latest.promise);
    const { result } = renderHook(() => useDashboardLibrary());
    await waitFor(() => expect(getDashboardLibraryMock).toHaveBeenCalledTimes(1));

    act(() => void result.current.reload());
    await waitFor(() => expect(getDashboardLibraryMock).toHaveBeenCalledTimes(2));
    await act(async () => latest.resolve([dashboard("latest")]));
    expect(result.current.dashboards[0]?.id).toBe("latest");
    await act(async () => stale.resolve([dashboard("stale")]));
    expect(result.current.dashboards[0]?.id).toBe("latest");
  });
});

function dashboard(id: string): DashboardLibraryItem {
  return {
    id,
    title: id,
    description: null,
    visibility_scope: "personal",
    relationship: "owned",
    owner: null,
    scope: { type: "personal", display_name: "Personal" },
    card_count: 0,
    preview_cards: [],
    created_at: "2026-07-14T00:00:00Z",
    updated_at: "2026-07-14T00:00:00Z"
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
