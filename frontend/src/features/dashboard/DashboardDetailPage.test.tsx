import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

  it("saves a complete responsive layout with the expected version", async () => {
    setCsrfCookie("csrf-token");
    const card = backendDashboardCard();
    const initial = backendDashboardDetail({ cards: [card] });
    const fetchMock = installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/dashboards/dashboard-id": [successResponse(initial), successResponse(initial)],
        "POST /api/v1/cards/card-id/refresh": successResponse(refreshResult("card-id")),
        "PATCH /api/v1/dashboards/dashboard-id/layout": successResponse({ layout_version: 2, items: [] })
      })
    );
    renderAppAt("/dashboards/dashboard-id");
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Card actions for Open tickets" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Resize" }));
    fireEvent.click(screen.getByRole("button", { name: "8 × 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Edit" })).toHaveAttribute("aria-pressed", "false"));
    const request = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/dashboards/dashboard-id/layout"));
    const payload = JSON.parse(String(request?.[1]?.body));
    expect(payload.expected_layout_version).toBe(1);
    expect(payload.items).toHaveLength(1);
    expect(payload.items[0]).toEqual(expect.objectContaining({
      card_id: "card-id",
      desktop: expect.objectContaining({ w: 8, h: 3 }),
      tablet: expect.objectContaining({ w: 6 }),
      mobile: expect.objectContaining({ x: 0, w: 1 })
    }));
  });

  it("preserves a local layout draft when the backend reports a conflict", async () => {
    setCsrfCookie("csrf-token");
    const initial = backendDashboardDetail({ cards: [backendDashboardCard()] });
    installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/dashboards/dashboard-id": successResponse(initial),
        "POST /api/v1/cards/card-id/refresh": successResponse(refreshResult("card-id")),
        "PATCH /api/v1/dashboards/dashboard-id/layout": errorResponse(
          "DASHBOARD_LAYOUT_CONFLICT",
          409,
          "Dashboard cards changed."
        )
      })
    );
    renderAppAt("/dashboards/dashboard-id");
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Card actions for Open tickets" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Resize" }));
    fireEvent.click(screen.getByRole("button", { name: "8 × 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("button", { name: "Reload latest layout" })).toBeInTheDocument();
    expect(screen.getByText(/draft is still here/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  });

  it("opens card actions from Shift+F10 and limits source to question and SQL", async () => {
    setCsrfCookie("csrf-token");
    installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/dashboards/dashboard-id": successResponse(
          backendDashboardDetail({ cards: [backendDashboardCard()] })
        ),
        "POST /api/v1/cards/card-id/refresh": successResponse(refreshResult("card-id")),
        "GET /api/v1/cards/card-id/source": successResponse({
          question: "How many open tickets?",
          sql: "SELECT count(*) FROM support_tickets"
        })
      })
    );
    renderAppAt("/dashboards/dashboard-id");
    const card = await screen.findByRole("article", { name: "Dashboard card Open tickets" });
    fireEvent.keyDown(card, { key: "F10", shiftKey: true });
    fireEvent.click(screen.getByRole("menuitem", { name: "View source" }));

    const dialog = await screen.findByRole("dialog", { name: "Source for Open tickets" });
    expect(dialog).toHaveTextContent("How many open tickets?");
    expect(dialog).toHaveTextContent("SELECT count(*) FROM support_tickets");
    expect(dialog).not.toHaveTextContent(/diagnostic|runtime role|correction/i);
  });

  it("uses one-column mobile controls without drag-resize", async () => {
    const rect = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      width: 390, height: 100, top: 0, right: 390, bottom: 100, left: 0, x: 0, y: 0, toJSON: () => ({})
    });
    setCsrfCookie("csrf-token");
    installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/dashboards/dashboard-id": successResponse(
          backendDashboardDetail({ cards: [backendDashboardCard({ id: "one", position: 0 }), backendDashboardCard({ id: "two", title: "Devices", position: 1 })] })
        ),
        "POST /api/v1/cards/one/refresh": successResponse(refreshResult("one")),
        "POST /api/v1/cards/two/refresh": successResponse(refreshResult("two"))
      })
    );
    renderAppAt("/dashboards/dashboard-id");
    fireEvent(window, new Event("resize"));
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await waitFor(() => expect(document.querySelector('.dashboard-editor-grid[data-breakpoint="mobile"]')).not.toBeNull());
    expect(screen.queryByRole("button", { name: /Drag / })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Move down" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Size preset" })).toHaveLength(2);
    rect.mockRestore();
  });

  it("renames, duplicates, and archives dashboards from the full route only", async () => {
    setCsrfCookie("csrf-token");
    const initial = backendDashboardDetail({ cards: [] });
    const renamed = { ...initial, title: "Renamed operations" };
    const copy = { ...initial, id: "copy-id", title: "Copy of Renamed operations" };
    const fetchMock = installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/dashboards/dashboard-id": [successResponse(initial), successResponse(renamed)],
        "PATCH /api/v1/dashboards/dashboard-id": successResponse({ id: "dashboard-id" }),
        "POST /api/v1/dashboards/dashboard-id/duplicate": successResponse({ id: "copy-id" }),
        "GET /api/v1/dashboards/copy-id": successResponse(copy),
        "DELETE /api/v1/dashboards/copy-id": successResponse({ id: "copy-id", is_archived: true }),
        "GET /api/v1/home/overview": successResponse(backendHomeOverview(demoAnalyst)),
        "GET /api/v1/dashboards/library": successResponse([])
      })
    );
    renderAppAt("/dashboards/dashboard-id");
    fireEvent.click(await screen.findByRole("button", { name: "Dashboard actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename dashboard" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Renamed operations" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("heading", { name: "Renamed operations" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dashboard actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Duplicate dashboard" }));
    await waitFor(() => expect(window.location.pathname).toBe("/dashboards/copy-id"));
    expect(await screen.findByRole("heading", { name: "Copy of Renamed operations" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dashboard actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Archive dashboard" }));
    fireEvent.click(screen.getByRole("button", { name: "Archive dashboard" }));
    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(await screen.findByRole("region", { name: "My Dashboard" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/copy-id") && init?.method === "DELETE")).toBe(true);
  });

  it("renames, duplicates, and removes cards while keeping the dashboard in Edit mode", async () => {
    setCsrfCookie("csrf-token");
    const original = backendDashboardCard();
    const renamedCard = { ...original, title: "Renamed card" };
    const copiedCard = backendDashboardCard({ id: "copy-card", title: "Renamed card Copy", position: 1 });
    const detailWith = (cards: Array<Record<string, unknown>>) => backendDashboardDetail({ cards });
    const fetchMock = installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/dashboards/dashboard-id": [
          successResponse(detailWith([original])),
          successResponse(detailWith([renamedCard])),
          successResponse(detailWith([renamedCard, copiedCard])),
          successResponse(detailWith([renamedCard]))
        ],
        "POST /api/v1/cards/card-id/refresh": successResponse(refreshResult("card-id")),
        "POST /api/v1/cards/copy-card/refresh": successResponse(refreshResult("copy-card")),
        "PATCH /api/v1/cards/card-id": successResponse({ card: renamedCard, layout_version: 2 }),
        "POST /api/v1/cards/card-id/duplicate": successResponse({ card: copiedCard, layout_version: 3 }),
        "DELETE /api/v1/cards/copy-card": successResponse({ id: "copy-card", layout_version: 4 })
      })
    );
    renderAppAt("/dashboards/dashboard-id");
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Card actions for Open tickets" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Renamed card" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("button", { name: "Card actions for Renamed card" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Card actions for Renamed card" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Duplicate" }));
    expect(await screen.findByRole("button", { name: "Card actions for Renamed card Copy" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Card actions for Renamed card Copy" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Remove" }));
    expect(screen.getByText(/saved query and all query-run history are preserved/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove card" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Card actions for Renamed card Copy" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Edit" })).toHaveAttribute("aria-pressed", "true");
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/copy-card") && init?.method === "DELETE")).toBe(true);
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
