import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, downloadBlob } from "../../../api/client";
import { refreshDashboardCard } from "../../../api/dashboards";
import { exportDashboardCardCsv } from "../../../api/exports";
import type {
  DashboardCard,
  DashboardCardRefreshResult
} from "../types";
import { DashboardCardPreview } from "./DashboardCardPreview";

vi.mock("../../../api/dashboards", () => ({
  refreshDashboardCard: vi.fn()
}));

vi.mock("../../../api/exports", () => ({
  exportDashboardCardCsv: vi.fn()
}));

vi.mock("../../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/client")>();
  return { ...actual, downloadBlob: vi.fn() };
});

const refreshDashboardCardMock = vi.mocked(refreshDashboardCard);
const exportDashboardCardCsvMock = vi.mocked(exportDashboardCardCsv);
const downloadBlobMock = vi.mocked(downloadBlob);

afterEach(() => {
  vi.clearAllMocks();
});

describe("DashboardCardPreview refresh", () => {
  it("automatically refreshes once in StrictMode and renders an accessible safe table", async () => {
    refreshDashboardCardMock.mockResolvedValue(
      refreshResult({
        columns: ["product_name", "metadata"],
        rows: [
          {
            product_name: "Jira",
            metadata: { department: "IT", count: 2 }
          }
        ]
      })
    );

    render(
      <StrictMode>
        <DashboardCardPreview
          canExport={false}
          canRefresh
          card={dashboardCard()}
          csrfToken="csrf-token"
        />
      </StrictMode>
    );

    expect(refreshDashboardCardMock).toHaveBeenCalledWith(
      "card-id",
      "csrf-token"
    );
    expect(await screen.findByRole("table", { name: "Dashboard card results" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Dashboard card results" });
    expect(within(table).getByRole("columnheader", { name: "product_name" })).toHaveAttribute("scope", "col");
    expect(within(table).getByRole("cell", { name: "Jira" })).toBeInTheDocument();
    expect(
      within(table).getByRole("cell", {
        name: '{"department":"IT","count":2}'
      })
    ).toBeInTheDocument();
    expect(refreshDashboardCardMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Order").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Rows").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText(/Jul 11, 2026/i)).toBeInTheDocument();
  });

  it("shows an accessible loading state", () => {
    refreshDashboardCardMock.mockReturnValue(new Promise(() => undefined));

    renderCard();

    expect(screen.getByRole("status")).toHaveTextContent(
      "Refreshing card under your current access scope..."
    );
    expect(
      screen.getByRole("button", { name: "Refresh Unused licenses" })
    ).toBeDisabled();
  });

  it("renders a safe empty result", async () => {
    refreshDashboardCardMock.mockResolvedValue(
      refreshResult({ columns: ["product_name"], rows: [], row_count: 0 })
    );

    renderCard();

    expect(await screen.findByText("No rows returned.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders at most five rows and a truncation warning", async () => {
    refreshDashboardCardMock.mockResolvedValue(
      refreshResult({
        columns: ["row_number"],
        rows: Array.from({ length: 10 }, (_, index) => ({ row_number: index })),
        row_count: 100,
        truncated: true
      })
    );

    renderCard();

    const table = await screen.findByRole("table", {
      name: "Dashboard card results"
    });
    expect(within(table).getAllByRole("row")).toHaveLength(6);
    expect(screen.getByText(/first 100 returned rows/i)).toBeInTheDocument();
    expect(screen.getByText(/first 5 rows/i)).toBeInTheDocument();
  });

  it("manually refreshes and retains the prior result after a failure", async () => {
    refreshDashboardCardMock
      .mockResolvedValueOnce(refreshResult({ rows: [{ product_name: "Jira" }] }))
      .mockRejectedValueOnce(new Error("private failure"));
    renderCard();
    expect(await screen.findByRole("cell", { name: "Jira" })).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Refresh Unused licenses" })
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Card refresh could not be completed. Try again."
    );
    expect(screen.getByRole("cell", { name: "Jira" })).toBeInTheDocument();
    expect(screen.getByText("Unused licenses")).toBeInTheDocument();
    expect(screen.queryByText("private failure")).not.toBeInTheDocument();
  });

  it("prevents duplicate concurrent manual refresh requests", async () => {
    const manualRefresh = deferred<DashboardCardRefreshResult>();
    refreshDashboardCardMock
      .mockResolvedValueOnce(refreshResult())
      .mockReturnValueOnce(manualRefresh.promise);
    renderCard();
    await screen.findByRole("table", { name: "Dashboard card results" });

    const refreshButton = screen.getByRole("button", {
      name: "Refresh Unused licenses"
    });
    fireEvent.click(refreshButton);
    fireEvent.click(refreshButton);

    expect(refreshDashboardCardMock).toHaveBeenCalledTimes(2);
    expect(refreshButton).toBeDisabled();
    manualRefresh.resolve(refreshResult());
    await waitFor(() => expect(refreshButton).toBeEnabled());
  });

  it("does not refresh or show an active control without query permission", () => {
    renderCard({ canRefresh: false });

    expect(refreshDashboardCardMock).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: /Refresh Unused licenses/i })
    ).not.toBeInTheDocument();
    expect(screen.getByText("Unused licenses")).toBeInTheDocument();
  });

  it("keeps cards independent when one automatic refresh fails", async () => {
    refreshDashboardCardMock.mockImplementation((cardId) => {
      if (cardId === "failed-card") {
        return Promise.reject(new Error("private failed card detail"));
      }
      return Promise.resolve(
        refreshResult({ card_id: cardId, rows: [{ product_name: "Jira" }] })
      );
    });

    render(
      <>
        <DashboardCardPreview
          canExport={false}
          canRefresh
          card={dashboardCard({ id: "failed-card", title: "Failed card" })}
          csrfToken="csrf-token"
        />
        <DashboardCardPreview
          canExport={false}
          canRefresh
          card={dashboardCard({ id: "working-card", title: "Working card" })}
          csrfToken="csrf-token"
        />
      </>
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Card refresh could not be completed. Try again."
    );
    expect(screen.getByText("Failed card")).toBeInTheDocument();
    expect(screen.getByText("Working card")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Jira" })).toBeInTheDocument();
  });

  it("never renders SQL or referenced-table metadata", async () => {
    refreshDashboardCardMock.mockResolvedValue(refreshResult());
    renderCard({
      card: dashboardCard({
        config: {
          generated_sql: "SELECT leaked_config_sql",
          referenced_tables: ["licenses"]
        }
      })
    });

    await screen.findByRole("table", { name: "Dashboard card results" });
    expect(screen.queryByText(/SELECT /i)).not.toBeInTheDocument();
    expect(screen.queryByText("licenses")).not.toBeInTheDocument();
  });
});

describe("DashboardCardPreview export", () => {
  it.each(["analyst", "admin"])(
    "shows server-backed CSV export for an authorized %s",
    async () => {
      refreshDashboardCardMock.mockResolvedValue(refreshResult());
      exportDashboardCardCsvMock.mockResolvedValue({
        blob: new Blob(["product_name\nJira\n"]),
        filename: "card.csv",
        contentType: "text/csv"
      });
      renderCard({ canExport: true });
      await screen.findByRole("table", { name: "Dashboard card results" });

      fireEvent.click(
        screen.getByRole("button", {
          name: "Export Unused licenses as CSV"
        })
      );

      expect(exportDashboardCardCsvMock).toHaveBeenCalledWith(
        "card-id",
        "csrf-token",
        { include_headers: true }
      );
      await waitFor(() => expect(downloadBlobMock).toHaveBeenCalledOnce());
      expect(screen.getByRole("status")).toHaveTextContent(
        "Card CSV export downloaded."
      );
      expect(screen.getByText(/recorded in the audit log/i)).toBeInTheDocument();
    }
  );

  it.each(["manager", "user"])(
    "does not show CSV export for a %s without permission",
    async (role) => {
      refreshDashboardCardMock.mockResolvedValue(refreshResult());
      renderCard({ canExport: false, canRefresh: role === "manager" });

      expect(
        screen.queryByRole("button", { name: /Export .* as CSV/i })
      ).not.toBeInTheDocument();
      if (role === "manager") {
        expect(
          screen.getByRole("button", { name: "Refresh Unused licenses" })
        ).toBeInTheDocument();
        await waitFor(() =>
          expect(refreshDashboardCardMock).toHaveBeenCalledOnce()
        );
      }
    }
  );

  it("shows loading and blocks duplicate export clicks", async () => {
    refreshDashboardCardMock.mockResolvedValue(refreshResult());
    const cardExport = deferred<{
      blob: Blob;
      filename: string;
      contentType: string;
    }>();
    exportDashboardCardCsvMock.mockReturnValue(cardExport.promise);
    renderCard({ canExport: true });
    await screen.findByRole("table", { name: "Dashboard card results" });

    const button = screen.getByRole("button", {
      name: "Export Unused licenses as CSV"
    });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(exportDashboardCardCsvMock).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Preparing CSV export..."
    );
    cardExport.resolve({
      blob: new Blob(["product_name\nJira\n"]),
      filename: "card.csv",
      contentType: "text/csv"
    });
    await waitFor(() => expect(downloadBlobMock).toHaveBeenCalledOnce());
  });

  it("keeps refreshed data visible after a safe export error", async () => {
    refreshDashboardCardMock.mockResolvedValue(
      refreshResult({ rows: [{ product_name: "Jira" }] })
    );
    exportDashboardCardCsvMock.mockRejectedValue(
      new ApiError({
        code: "CSV_EXPORT_NOT_ALLOWED",
        message: "private policy detail",
        status: 403
      })
    );
    renderCard({ canExport: true });
    expect(await screen.findByRole("cell", { name: "Jira" })).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Export Unused licenses as CSV" })
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This card cannot be exported with your current permissions."
    );
    expect(screen.getByRole("cell", { name: "Jira" })).toBeInTheDocument();
    expect(screen.queryByText("private policy detail")).not.toBeInTheDocument();
  });
});

function renderCard({
  canExport = false,
  canRefresh = true,
  card = dashboardCard()
}: {
  canExport?: boolean;
  canRefresh?: boolean;
  card?: DashboardCard;
} = {}) {
  return render(
    <DashboardCardPreview
      canExport={canExport}
      canRefresh={canRefresh}
      card={card}
      csrfToken="csrf-token"
    />
  );
}

function dashboardCard(overrides: Partial<DashboardCard> = {}): DashboardCard {
  return {
    id: "card-id",
    dashboard_id: "dashboard-id",
    saved_query_id: "saved-query-id",
    title: "Unused licenses",
    description: "Current scoped unused license data.",
    card_type: "table",
    position: 0,
    layout: null,
    config: null,
    created_at: "2026-07-11T14:00:00Z",
    updated_at: "2026-07-11T14:00:00Z",
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
    rows: [{ product_name: "Microsoft 365 E3" }],
    row_count: 1,
    duration_ms: 8,
    truncated: false,
    refreshed_at: "2026-07-11T15:00:00Z",
    message: "Dashboard card refreshed successfully.",
    warnings: [],
    ...overrides
  };
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}
