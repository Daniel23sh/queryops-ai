import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../../api/client";
import {
  refreshDashboardCard,
  updateMyDashboardLayout
} from "../../../api/dashboards";
import { exportDashboardCardCsv } from "../../../api/exports";
import type {
  Dashboard,
  DashboardCard,
  DashboardCardRefreshResult
} from "../types";
import { DashboardCardGrid } from "./DashboardCardGrid";

vi.mock("../../../api/dashboards", () => ({
  refreshDashboardCard: vi.fn(),
  updateMyDashboardLayout: vi.fn()
}));

vi.mock("../../../api/exports", () => ({
  exportDashboardCardCsv: vi.fn()
}));

const refreshDashboardCardMock = vi.mocked(refreshDashboardCard);
const updateMyDashboardLayoutMock = vi.mocked(updateMyDashboardLayout);
const exportDashboardCardCsvMock = vi.mocked(exportDashboardCardCsv);

afterEach(() => {
  vi.clearAllMocks();
});

describe("DashboardCardGrid ordering", () => {
  it("renders backend order as one-based labels with bounded move controls", () => {
    renderGrid();

    expect(
      within(screen.getByLabelText("First card order controls")).getByText("Order 1")
    ).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Second card order controls")).getByText("Order 2")
    ).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Third card order controls")).getByText("Order 3")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move First card up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Third card down" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Reorder Second card/i })).toBeEnabled();
  });

  it("hides reorder controls when a dashboard has only one card", () => {
    renderGrid({ dashboard: dashboard({ cards: [card({ id: "only-card", position: 0 })] }) });

    expect(screen.getByText("Order").nextElementSibling).toHaveTextContent("1");
    expect(screen.queryByRole("button", { name: /Reorder/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Move .* up/i })).not.toBeInTheDocument();
  });

  it("activates keyboard drag from the dedicated handle and exposes live feedback", () => {
    renderGrid();

    const handle = screen.getByRole("button", { name: /Reorder Third card/i });
    fireEvent.keyDown(handle, { code: "Space", key: " " });

    expect(handle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Third card is over First card.")).toBeInTheDocument();
    fireEvent.keyDown(document, { code: "Escape", key: "Escape" });
  });

  it("optimistically moves a card and persists the complete normalized order", async () => {
    const pendingSave = deferred<Dashboard>();
    updateMyDashboardLayoutMock.mockReturnValue(pendingSave.promise);
    renderGrid();

    fireEvent.click(screen.getByRole("button", { name: "Move Second card up" }));

    expect(updateMyDashboardLayoutMock).toHaveBeenCalledWith(
      {
        items: [
          { card_id: "second-card", position: 0 },
          { card_id: "first-card", position: 1 },
          { card_id: "third-card", position: 2 }
        ]
      },
      "csrf-token"
    );
    expect(screen.getByText("Saving card order...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move First card up" })).toBeDisabled();

    await act(async () => {
      pendingSave.resolve(
        dashboard({
          cards: [
            card({ id: "second-card", position: 0, title: "Second card" }),
            card({ id: "first-card", position: 1, title: "First card" }),
            card({ id: "third-card", position: 2, title: "Third card" })
          ]
        })
      );
      await pendingSave.promise;
    });

    expect(await screen.findByText("Card order saved.")).toBeInTheDocument();
    expect(cardTitles()).toEqual(["Second card", "First card", "Third card"]);
  });

  it("restores the prior order after a generic save failure", async () => {
    updateMyDashboardLayoutMock.mockRejectedValue(new Error("private failure"));
    renderGrid();

    fireEvent.click(screen.getByRole("button", { name: "Move Second card up" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Card order could not be saved. The previous order was restored."
    );
    expect(cardTitles()).toEqual(["First card", "Second card", "Third card"]);
    expect(screen.queryByText("private failure")).not.toBeInTheDocument();
  });

  it("offers explicit reload recovery after a conflict", async () => {
    const onReload = vi.fn().mockResolvedValue(undefined);
    updateMyDashboardLayoutMock.mockRejectedValue(
      new ApiError({
        code: "DASHBOARD_LAYOUT_CONFLICT",
        message: "private conflict detail",
        status: 409
      })
    );
    renderGrid({ onReload });

    fireEvent.click(screen.getByRole("button", { name: "Move Second card up" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dashboard cards changed. Reload the dashboard and try again."
    );
    fireEvent.click(screen.getByRole("button", { name: "Reload dashboard" }));
    expect(onReload).toHaveBeenCalledOnce();
    expect(screen.queryByText("private conflict detail")).not.toBeInTheDocument();
  });

  it("keeps save state isolated between personal dashboards", async () => {
    const pendingSave = deferred<Dashboard>();
    updateMyDashboardLayoutMock.mockReturnValue(pendingSave.promise);
    render(
      <>
        <DashboardCardGrid
          canExportCards={false}
          canRefreshCards={false}
          csrfToken="csrf-token"
          dashboard={dashboard({ id: "first-dashboard" })}
          onReload={vi.fn().mockResolvedValue(undefined)}
        />
        <DashboardCardGrid
          canExportCards={false}
          canRefreshCards={false}
          csrfToken="csrf-token"
          dashboard={dashboard({
            id: "second-dashboard",
            cards: [
              card({ id: "fourth-card", position: 0, title: "Fourth card" }),
              card({ id: "fifth-card", position: 1, title: "Fifth card" })
            ]
          })}
          onReload={vi.fn().mockResolvedValue(undefined)}
        />
      </>
    );

    fireEvent.click(screen.getByRole("button", { name: "Move Second card up" }));

    expect(screen.getByRole("button", { name: "Move First card up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Fifth card up" })).toBeEnabled();
    await act(async () => {
      pendingSave.resolve(dashboard({ id: "first-dashboard" }));
      await pendingSave.promise;
    });
  });

  it("uses a dedicated handle and does not invoke refresh or export during an order move", async () => {
    refreshDashboardCardMock.mockResolvedValue(refreshResult());
    updateMyDashboardLayoutMock.mockResolvedValue(
      dashboard({
        cards: [
          card({ id: "second-card", position: 0 }),
          card({ id: "first-card", position: 1 }),
          card({ id: "third-card", position: 2 })
        ]
      })
    );
    renderGrid({ canExportCards: true, canRefreshCards: true });

    await screen.findAllByRole("table", { name: "Dashboard card results" });
    expect(screen.getByRole("button", { name: /Reorder Second card/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Move Second card up" }));

    await waitFor(() => expect(updateMyDashboardLayoutMock).toHaveBeenCalledOnce());
    expect(refreshDashboardCardMock).toHaveBeenCalledTimes(3);
    expect(exportDashboardCardCsvMock).not.toHaveBeenCalled();
    expect(screen.getAllByRole("table", { name: "Dashboard card results" })).toHaveLength(3);
  });
});

function renderGrid({
  canExportCards = false,
  canRefreshCards = false,
  dashboard: currentDashboard = dashboard(),
  onReload = vi.fn().mockResolvedValue(undefined)
}: {
  canExportCards?: boolean;
  canRefreshCards?: boolean;
  dashboard?: Dashboard;
  onReload?: () => Promise<void>;
} = {}) {
  return render(
    <DashboardCardGrid
      canExportCards={canExportCards}
      canRefreshCards={canRefreshCards}
      csrfToken="csrf-token"
      dashboard={currentDashboard}
      onReload={onReload}
    />
  );
}

function cardTitles() {
  return screen
    .getAllByRole("heading", { level: 4 })
    .map((heading) => heading.textContent);
}

function dashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    id: "dashboard-id",
    title: "Personal dashboard",
    description: "Saved views.",
    visibility_scope: "personal",
    department_id: null,
    is_archived: false,
    created_at: "2026-07-12T10:00:00Z",
    updated_at: "2026-07-12T10:00:00Z",
    cards: [
      card({ id: "third-card", position: 8, title: "Third card" }),
      card({ id: "second-card", position: 1, title: "Second card" }),
      card({ id: "first-card", position: 0, title: "First card" })
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

function refreshResult(
  overrides: Partial<DashboardCardRefreshResult> = {}
): DashboardCardRefreshResult {
  return {
    card_id: "card-id",
    dashboard_id: "dashboard-id",
    saved_query_id: "saved-query-id",
    query_run_id: "refresh-run-id",
    status: "succeeded",
    columns: ["product_name"],
    rows: [{ product_name: "Jira" }],
    row_count: 1,
    duration_ms: 4,
    truncated: false,
    refreshed_at: "2026-07-12T12:00:00Z",
    message: "Dashboard card refreshed successfully.",
    warnings: [],
    ...overrides
  };
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}
