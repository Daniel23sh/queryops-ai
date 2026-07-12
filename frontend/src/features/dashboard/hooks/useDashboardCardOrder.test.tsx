import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../../api/client";
import { updateMyDashboardLayout } from "../../../api/dashboards";
import type { Dashboard, DashboardCard } from "../types";
import {
  normalizeCardPositions,
  sortDashboardCards,
  useDashboardCardOrder
} from "./useDashboardCardOrder";

vi.mock("../../../api/dashboards", () => ({
  updateMyDashboardLayout: vi.fn()
}));

const updateMyDashboardLayoutMock = vi.mocked(updateMyDashboardLayout);

afterEach(() => {
  vi.clearAllMocks();
});

describe("useDashboardCardOrder", () => {
  it("sorts backend cards deterministically and normalizes an optimistic move", async () => {
    const pendingSave = deferred<Dashboard>();
    updateMyDashboardLayoutMock.mockReturnValue(pendingSave.promise);
    const { result } = renderHook(() =>
      useDashboardCardOrder({ dashboard: dashboard(), csrfToken: "csrf-token" })
    );

    expect(result.current.cards.map((card) => card.id)).toEqual([
      "first-card",
      "second-card",
      "third-card"
    ]);

    act(() => {
      void result.current.moveCard("third-card", 0);
    });

    expect(result.current.cards.map((card) => [card.id, card.position])).toEqual([
      ["third-card", 0],
      ["first-card", 1],
      ["second-card", 2]
    ]);
    expect(result.current.isSaving).toBe(true);
    expect(updateMyDashboardLayoutMock).toHaveBeenCalledWith(
      {
        items: [
          { card_id: "third-card", position: 0 },
          { card_id: "first-card", position: 1 },
          { card_id: "second-card", position: 2 }
        ]
      },
      "csrf-token"
    );

    pendingSave.resolve(
      dashboard({
        cards: [
          card({ id: "third-card", position: 0 }),
          card({ id: "first-card", position: 1 }),
          card({ id: "second-card", position: 2 })
        ]
      })
    );

    await waitFor(() => expect(result.current.isSaving).toBe(false));
    expect(result.current.saveState).toEqual({
      status: "success",
      message: "Card order saved."
    });
  });

  it("restores the prior order after a generic save failure", async () => {
    updateMyDashboardLayoutMock.mockRejectedValue(new Error("private failure"));
    const { result } = renderHook(() =>
      useDashboardCardOrder({ dashboard: dashboard(), csrfToken: "csrf-token" })
    );

    await act(async () => {
      await result.current.moveCard("third-card", 0);
    });

    expect(result.current.cards.map((card) => card.id)).toEqual([
      "first-card",
      "second-card",
      "third-card"
    ]);
    expect(result.current.saveState).toEqual({
      status: "error",
      message: "Card order could not be saved. The previous order was restored.",
      canReload: false
    });
  });

  it("restores the prior order and exposes reload recovery on a conflict", async () => {
    updateMyDashboardLayoutMock.mockRejectedValue(
      new ApiError({
        code: "DASHBOARD_LAYOUT_CONFLICT",
        message: "private conflict detail",
        status: 409
      })
    );
    const { result } = renderHook(() =>
      useDashboardCardOrder({ dashboard: dashboard(), csrfToken: "csrf-token" })
    );

    await act(async () => {
      await result.current.moveCard("third-card", 0);
    });

    expect(result.current.cards.map((card) => card.id)).toEqual([
      "first-card",
      "second-card",
      "third-card"
    ]);
    expect(result.current.saveState).toEqual({
      status: "error",
      message: "Dashboard cards changed. Reload the dashboard and try again.",
      canReload: true
    });
  });

  it("prevents duplicate saves while one dashboard order is in flight", async () => {
    const pendingSave = deferred<Dashboard>();
    updateMyDashboardLayoutMock.mockReturnValue(pendingSave.promise);
    const { result } = renderHook(() =>
      useDashboardCardOrder({ dashboard: dashboard(), csrfToken: "csrf-token" })
    );

    act(() => {
      void result.current.moveCard("third-card", 0);
      void result.current.moveCard("second-card", 0);
    });

    expect(updateMyDashboardLayoutMock).toHaveBeenCalledTimes(1);
    await act(async () => {
      pendingSave.resolve(dashboard());
      await pendingSave.promise;
    });
  });

  it("synchronizes ordered cards after a server reload", () => {
    const { result, rerender } = renderHook(
      ({ currentDashboard }) =>
        useDashboardCardOrder({
          dashboard: currentDashboard,
          csrfToken: "csrf-token"
        }),
      { initialProps: { currentDashboard: dashboard() } }
    );

    rerender({
      currentDashboard: dashboard({
        cards: [
          card({ id: "third-card", position: 0 }),
          card({ id: "second-card", position: 1 }),
          card({ id: "first-card", position: 2 })
        ]
      })
    });

    expect(result.current.cards.map((currentCard) => currentCard.id)).toEqual([
      "third-card",
      "second-card",
      "first-card"
    ]);
    expect(result.current.saveState).toEqual({ status: "idle" });
  });
});

describe("card-order helpers", () => {
  it("orders equal positions by created time and id", () => {
    const ordered = sortDashboardCards([
      card({ id: "b", position: 0, created_at: "2026-07-12T12:00:00Z" }),
      card({ id: "c", position: 0, created_at: "2026-07-12T11:00:00Z" }),
      card({ id: "a", position: 0, created_at: "2026-07-12T12:00:00Z" })
    ]);

    expect(ordered.map((currentCard) => currentCard.id)).toEqual(["c", "a", "b"]);
  });

  it("normalizes positions without mutating source cards", () => {
    const sourceCards = [card({ id: "b", position: 8 }), card({ id: "a", position: 4 })];

    expect(normalizeCardPositions(sourceCards).map((currentCard) => currentCard.position)).toEqual([
      0,
      1
    ]);
    expect(sourceCards.map((currentCard) => currentCard.position)).toEqual([8, 4]);
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
    cards: [
      card({ id: "third-card", position: 4, created_at: "2026-07-12T12:00:00Z" }),
      card({ id: "second-card", position: 1, created_at: "2026-07-12T11:00:00Z" }),
      card({ id: "first-card", position: 1, created_at: "2026-07-12T10:00:00Z" })
    ],
    ...overrides
  };
}

function card(overrides: Partial<DashboardCard> = {}): DashboardCard {
  return {
    id: "card-id",
    dashboard_id: "dashboard-id",
    saved_query_id: "saved-query-id",
    title: "Saved card",
    description: null,
    card_type: "table",
    position: 0,
    layout: null,
    config: null,
    created_at: "2026-07-12T10:00:00Z",
    updated_at: "2026-07-12T10:00:00Z",
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
