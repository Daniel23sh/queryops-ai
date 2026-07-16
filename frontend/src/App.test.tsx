import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendDashboard,
  backendDashboardCard,
  backendDashboardLibraryItem,
  backendHomeOverview,
  backendQueryResult,
  backendQueryTemplate,
  demoAnalyst,
  demoManager,
  demoUser,
  errorResponse,
  installApiMock,
  pendingResponse,
  renderAppAt,
  resetAppTestState,
  setCsrfCookie,
  successResponse
} from "./test/appTestUtils";

afterEach(resetAppTestState);

describe("App", () => {
  it("shows authentication hydration before rendering a route", () => {
    installApiMock({ "GET /api/v1/auth/me": pendingResponse() });

    renderAppAt("/ask");

    expect(screen.getByText("Checking your session...")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ask Data" })).not.toBeInTheDocument();
  });

  it("logs in and lands on the live My Dashboard route", async () => {
    const fetchMock = installApiMock({
      "GET /api/v1/auth/me": errorResponse("UNAUTHORIZED", 401),
      "POST /api/v1/demo/login": successResponse({
        user: demoManager,
        requires_onboarding: false,
        csrf_token: "csrf-from-login"
      }),
      "GET /api/v1/home/overview": successResponse(backendHomeOverview(demoManager)),
      "GET /api/v1/dashboards/library": successResponse([])
    });

    renderAppAt("/login");
    fireEvent.click(await screen.findByRole("button", { name: /demo manager/i }));

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/demo/login",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "demo.manager@queryops.local" })
      })
    );
  });

  it("renders only real Home data and corrected empty copy", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/library": successResponse([])
      })
    );

    renderAppAt("/");
    const dashboard = await screen.findByRole("region", { name: "My Dashboard" });

    expect(within(dashboard).getByRole("heading", { name: "My Dashboard" })).toBeInTheDocument();
    expect(within(dashboard).getByText(/Manager.*Scope: Finance/)).toBeInTheDocument();
    expect(
      await within(dashboard).findByText("No dashboards are available yet.")
    ).toBeInTheDocument();
    expect(within(dashboard).getByRole("link", { name: "Open Ask Data" })).toHaveAttribute(
      "href",
      "/ask"
    );
    expect(within(dashboard).queryByText("Governance Posture")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText("Demo Activity Preview")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText("QueryOps Command Center")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText(/SELECT /i)).not.toBeInTheDocument();
  });

  it("loads saved dashboards without exposing server-only SQL fields", async () => {
    const card = {
      ...backendDashboardCard({ title: "Scoped incident review" }),
      generated_sql: "SELECT secret_generated_sql",
      executed_sql: "SELECT secret_executed_sql"
    };
    installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/dashboards/library": successResponse([
          {
            ...backendDashboardLibraryItem({ title: "Operations review" }),
            preview_cards: [card],
            generated_sql: "SELECT dashboard_secret"
          }
        ])
      })
    );

    renderAppAt("/");

    expect(
      await screen.findByRole("button", { name: "Preview dashboard Operations review" })
    ).toBeInTheDocument();
    expect(screen.getByText("Scoped incident review")).toBeInTheDocument();
    expect(screen.queryByText("SELECT secret_generated_sql")).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT secret_executed_sql")).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT dashboard_secret")).not.toBeInTheDocument();
  });

  it("shows genuine Home loading and retryable error states", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/library": pendingResponse()
      })
    );
    const firstRender = renderAppAt("/");
    expect(
      await screen.findByText("Loading dashboard library...")
    ).toBeInTheDocument();

    firstRender.unmount();
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/library": [
          errorResponse("DASHBOARDS_UNAVAILABLE", 503),
          successResponse([])
        ]
      })
    );
    renderAppAt("/");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dashboard library could not be loaded."
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByText("No dashboards are available yet.")
    ).toBeInTheDocument();
  });

  it("creates a personal dashboard with CSRF and refreshes Home", async () => {
    setCsrfCookie("csrf-from-cookie");
    const createdDashboard = backendDashboard({ title: "Quarterly review" });
    const createdLibraryItem = backendDashboardLibraryItem({
      title: "Quarterly review"
    });
    const fetchMock = installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/home/overview": [
          successResponse(backendHomeOverview(demoManager)),
          successResponse(backendHomeOverview(demoManager))
        ],
        "GET /api/v1/dashboards/library": [
          successResponse([]),
          successResponse([createdLibraryItem])
        ],
        "POST /api/v1/dashboards": successResponse(createdDashboard)
      })
    );

    renderAppAt("/");
    await screen.findByText("No dashboards are available yet.");
    fireEvent.click(screen.getByRole("button", { name: "New dashboard" }));
    fireEvent.change(screen.getByLabelText("Dashboard title"), {
      target: { value: "Quarterly review" }
    });
    fireEvent.change(screen.getByLabelText("Description (optional)"), {
      target: { value: "Leadership review" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Create dashboard" }));

    expect(await screen.findByText("Quarterly review was created.")).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Preview dashboard Quarterly review" })
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/dashboards",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-from-cookie" })
      })
    );
  });

  it("keeps personal dashboard creation hidden without its permission", async () => {
    installApiMock(
      authenticatedRoutes(demoUser, {
        "GET /api/v1/dashboards/library": successResponse([])
      })
    );

    renderAppAt("/");
    await screen.findByRole("region", { name: "My Dashboard" });

    expect(screen.queryByRole("button", { name: "New dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByText(/not available for your role/i)).not.toBeInTheDocument();
  });

  it("restores Ask Data directly on refresh and runs a free query", async () => {
    setCsrfCookie("csrf-from-cookie");
    const fetchMock = installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "POST /api/v1/queries/run": successResponse(backendQueryResult({
          generatedSql: "SELECT manager_generated_secret",
          executedSql: "SELECT manager_executed_secret"
        }))
      })
    );

    renderAppAt("/ask");
    expect(await screen.findByRole("heading", { name: "Ask Data" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/ask");
    expect(screen.queryByText("Unused paid licenses")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Question"), {
      target: { value: "Show reclaimable licenses in my scope." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/queries/run",
      expect.objectContaining({ method: "POST" })
    ));
    expect(await screen.findByText("succeeded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(await screen.findByText("Microsoft 365 E5")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Result details" }));
    expect(screen.getByText("Found one reclaim opportunity.")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "SQL" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
    expect(screen.queryByText(/manager_(generated|executed)_secret/)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/queries/run",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-from-cookie" })
      })
    );
  });

  it("keeps SQL and diagnostics hidden from template-only users", async () => {
    setCsrfCookie("csrf-from-cookie");
    installApiMock(
      authenticatedRoutes(demoUser, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "POST /api/v1/queries/run": successResponse(
          backendQueryResult({
            generatedSql: "SELECT generated_secret",
            executedSql: "SELECT executed_secret"
          })
        )
      })
    );

    renderAppAt("/ask");
    expect(await screen.findByText("Template-only")).toBeInTheDocument();
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Choose a template" }));
    fireEvent.click(await screen.findByRole("button", { name: "Use template" }));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByText("succeeded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(screen.getByText("Microsoft 365 E5")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Result details" }));
    expect(screen.queryByRole("tab", { name: "SQL" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT generated_secret")).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT executed_secret")).not.toBeInTheDocument();
    expect(screen.queryByText("deterministic")).not.toBeInTheDocument();
  });

  it("keeps analyst technical details contained in Ask Data result tabs", async () => {
    setCsrfCookie("csrf-from-cookie");
    installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "POST /api/v1/queries/run": successResponse(
          backendQueryResult({
            generatedSql: "SELECT generated_safe_sql",
            executedSql: "SELECT executed_safe_sql"
          })
        )
      })
    );

    renderAppAt("/ask");
    fireEvent.click((await screen.findAllByRole("button", { name: "Templates" }))[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Use template" }));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByText("succeeded");

    fireEvent.click(screen.getByRole("button", { name: "Result details" }));
    fireEvent.click(screen.getByRole("tab", { name: "SQL" }));
    expect(screen.getByText("SELECT generated_safe_sql")).toBeInTheDocument();
    expect(screen.getByText("SELECT executed_safe_sql")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Diagnostics" }));
    expect(screen.getByText("deterministic")).toBeInTheDocument();
  });

  it("preserves the successful Save as Card workflow", async () => {
    setCsrfCookie("csrf-from-cookie");
    const dashboard = backendDashboard();
    const savedCard = backendDashboardCard();
    const fetchMock = installApiMock(
      authenticatedRoutes(demoAnalyst, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "POST /api/v1/queries/run": successResponse(backendQueryResult()),
        "GET /api/v1/dashboards/my": successResponse([dashboard]),
        "POST /api/v1/query-runs/query-run-id/save-card": successResponse(savedCard),
        "PATCH /api/v1/cards/card-id": successResponse({ card: savedCard, layout_version: 2 })
      })
    );

    renderAppAt("/ask");
    fireEvent.click((await screen.findAllByRole("button", { name: "Templates" }))[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Use template" }));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByText("succeeded");
    fireEvent.click(screen.getByRole("button", { name: "Save to Dashboard" }));
    expect(await screen.findByLabelText("Target dashboard")).toHaveValue("dashboard-id");
    fireEvent.change(screen.getByLabelText("Card title"), {
      target: { value: "License opportunities" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Saved to Operations review")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/query-runs/query-run-id/save-card",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-from-cookie" })
      })
    );
    const visualizationRequest = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/api/v1/cards/card-id")
    );
    expect(visualizationRequest?.[1]?.body).not.toContain("rows");
  });

  it("clears a selected template association when a free-query user edits its question", async () => {
    setCsrfCookie("csrf-from-cookie");
    const fetchMock = installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "POST /api/v1/queries/run": successResponse(backendQueryResult())
      })
    );

    renderAppAt("/ask");
    fireEvent.click((await screen.findAllByRole("button", { name: "Templates" }))[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Use template" }));
    expect(screen.getByText(/Template:/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Question"), {
      target: { value: "Show unused paid licenses in my active scope." }
    });
    expect(screen.queryByText(/Template:/)).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByLabelText("Question"), { key: "Enter" });

    await screen.findByText("succeeded");
    const runRequest = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/api/v1/queries/run")
    );
    expect(JSON.parse(String(runRequest?.[1]?.body))).toEqual({
      question: "Show unused paid licenses in my active scope."
    });
  });

  it("loads only five own-history items without SQL and safely disables an unavailable template", async () => {
    const historyItems = Array.from({ length: 7 }, (_, index) => ({
      id: `history-${index}`,
      status: "succeeded",
      natural_language_question: `Historic question ${index}`,
      row_count: index,
      duration_ms: 20,
      error_message: null,
      created_at: "2026-07-15T10:00:00Z",
      started_at: null,
      completed_at: "2026-07-15T10:00:01Z",
      metadata: index === 0 ? { template_id: "retired-template" } : {},
      generated_sql: "SELECT hidden_history_sql",
      executed_sql: "SELECT hidden_executed_sql"
    }));
    const fetchMock = installApiMock(
      authenticatedRoutes(demoUser, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "GET /api/v1/queries/history": successResponse(historyItems)
      })
    );

    renderAppAt("/ask");
    fireEvent.click(await screen.findByRole("button", { name: "History" }));

    expect((await screen.findAllByText(/Historic question/))).toHaveLength(5);
    expect(screen.getByText("Template is no longer available.")).toBeInTheDocument();
    expect(screen.queryByText(/hidden_history_sql|hidden_executed_sql/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open result" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/queries/history?limit=5&offset=0&include_sql=false",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("keeps the original clarification context and allows retry after a safe failure", async () => {
    setCsrfCookie("csrf-from-cookie");
    const clarificationResult = {
      ...backendQueryResult(),
      status: "clarification_required",
      rows: [],
      columns: [],
      row_count: 0,
      clarification_required: true,
      message: "Which time range should be used?"
    };
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/query-templates": successResponse([]),
        "POST /api/v1/queries/run": successResponse(clarificationResult),
        "POST /api/v1/queries/query-run-id/clarify": errorResponse(
          "CLARIFICATION_FAILED",
          400,
          "Clarification could not be applied."
        )
      })
    );

    renderAppAt("/ask");
    fireEvent.change(await screen.findByLabelText("Question"), {
      target: { value: "Show incidents." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByText("More detail needed")).toBeInTheDocument();
    expect(screen.getByText((_, element) =>
      element?.tagName === "P" && element.textContent === "Original question: Show incidents."
    )).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Clarification"), {
      target: { value: "Use the last 30 days." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit clarification" }));

    expect(await screen.findByText("Clarification could not be applied.")).toBeInTheDocument();
    expect(screen.getByText("More detail needed")).toBeInTheDocument();
    expect(screen.getByLabelText("Clarification")).toHaveValue("Use the last 30 days.");
    expect(screen.getByRole("button", { name: "Submit clarification" })).toBeEnabled();
  });

  it("keeps navigation state aligned with routed content", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": successResponse([]),
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "GET /api/v1/role-requests/my": successResponse([])
      })
    );

    renderAppAt("/");
    const nav = await screen.findByRole("navigation", { name: "Workspace navigation" });
    expect(within(nav).getByRole("link", { name: "My Dashboard" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    fireEvent.click(within(nav).getByRole("link", { name: "Profile" }));
    expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Profile" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(window.location.pathname).toBe("/profile");
  });
});
