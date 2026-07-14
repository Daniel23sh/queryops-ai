import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendDashboardCard,
  backendDashboardDetail,
  backendDashboardLibraryItem,
  backendHomeOverview,
  demoAnalyst,
  demoManager,
  errorResponse,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  setCsrfCookie,
  successResponse
} from "../../test/appTestUtils";

afterEach(resetAppTestState);

describe("DashboardDetailPage", () => {
  it("loads directly in View mode, renders safe cards, and exposes secure actions through menus", async () => {
    setCsrfCookie("csrf-token");
    const firstCard = {
      ...backendDashboardCard({ id: "first-card", title: "Open tickets" }),
      generated_sql: "SELECT private_sql"
    };
    const secondCard = backendDashboardCard({ id: "second-card", title: "Devices" });
    const fetchMock = installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/dashboards/dashboard-id": successResponse(
          backendDashboardDetail({ cards: [firstCard, secondCard] })
        ),
        "POST /api/v1/cards/first-card/refresh": [
          successResponse(refreshResult("first-card")),
          successResponse(refreshResult("first-card"))
        ],
        "POST /api/v1/cards/second-card/refresh": [
          successResponse(refreshResult("second-card")),
          successResponse(refreshResult("second-card"))
        ]
      })
    );

    renderAppAt("/dashboards/dashboard-id");

    expect(await screen.findByRole("heading", { name: "Operations review" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to My Dashboard" })).toHaveAttribute(
      "href",
      "/"
    );
    expect(await screen.findAllByRole("table", { name: "Dashboard card results" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /Export .* as CSV/ })).not.toBeInTheDocument();
    const menus = screen.getAllByRole("button", { name: /Card actions for/ });
    expect(menus).toHaveLength(2);
    fireEvent.click(menus[0]);
    expect(screen.getByRole("menuitem", { name: "Export CSV" })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByText("SELECT private_sql")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Card" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Drag / })).toHaveLength(2);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) => String(url).includes("/cards/first-card/refresh"))
      ).toHaveLength(1)
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/dashboards/dashboard-id",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("does not expose arrange controls for a shared dashboard", async () => {
    setCsrfCookie("csrf-token");
    const card = backendDashboardCard();
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/shared-id": successResponse(
          backendDashboardDetail({
            id: "shared-id",
            relationship: "shared",
            visibilityScope: "department",
            cards: [card]
          })
        ),
        "POST /api/v1/cards/card-id/refresh": successResponse(refreshResult("card-id"))
      })
    );

    renderAppAt("/dashboards/shared-id");

    expect(await screen.findByRole("heading", { name: "Operations review" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Export .* as CSV/ })).not.toBeInTheDocument();
  });

  it("shows a safe not-found state for unknown or invisible dashboards", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/unknown": errorResponse(
          "DASHBOARD_NOT_FOUND",
          404,
          "Dashboard was not found."
        )
      })
    );

    renderAppAt("/dashboards/unknown");

    expect(await screen.findByRole("heading", { name: "Dashboard not found" })).toBeInTheDocument();
    expect(screen.getByText(/unavailable or is not visible/i)).toBeInTheDocument();
    expect(screen.queryByText(/policy|permission|sql/i)).not.toBeInTheDocument();
  });

  it("returns to Home through the explicit back link", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/dashboard-id": successResponse(
          backendDashboardDetail({ cards: [] })
        )
      })
    );
    renderAppAt("/dashboards/dashboard-id");
    fireEvent.click(await screen.findByRole("link", { name: "Back to My Dashboard" }));

    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(await screen.findByRole("region", { name: "My Dashboard" })).toBeInTheDocument();
  });

  it("returns to Home through Browser Back after opening from preview", async () => {
    const libraryItem = backendDashboardLibraryItem({
      id: "browser-back",
      title: "Browser back"
    });
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/home/overview": [
          successResponse(backendHomeOverview(demoManager)),
          successResponse(backendHomeOverview(demoManager))
        ],
        "GET /api/v1/dashboards/library": [
          successResponse([libraryItem]),
          successResponse([libraryItem])
        ],
        "GET /api/v1/dashboards/browser-back": successResponse(
          backendDashboardDetail({ id: "browser-back", cards: [] })
        )
      })
    );
    renderAppAt("/");
    fireEvent.click(
      await screen.findByRole("button", { name: "Preview dashboard Browser back" })
    );
    fireEvent.click(screen.getByRole("button", { name: "Open dashboard" }));
    expect(await screen.findByRole("heading", { name: "Operations review" })).toBeInTheDocument();

    window.history.back();

    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(await screen.findByRole("region", { name: "My Dashboard" })).toBeInTheDocument();
  });
});

function refreshResult(cardId: string) {
  return {
    card_id: cardId,
    dashboard_id: "dashboard-id",
    saved_query_id: "saved-query-id",
    query_run_id: `${cardId}-run`,
    status: "succeeded",
    columns: ["name"],
    rows: [{ name: "Safe aggregate" }],
    row_count: 1,
    duration_ms: 12,
    truncated: false,
    refreshed_at: "2026-07-14T12:00:00Z",
    message: "Refreshed.",
    warnings: []
  };
}
