import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendDashboard,
  backendDashboardCard,
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
      "GET /api/v1/dashboards/my": successResponse([])
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
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );

    renderAppAt("/");
    const dashboard = await screen.findByRole("region", { name: "My Dashboard" });

    expect(within(dashboard).getByRole("heading", { name: "My Dashboard" })).toBeInTheDocument();
    expect(within(dashboard).getByText(/Manager.*Scope: Finance/)).toBeInTheDocument();
    expect(
      await within(dashboard).findByText(
        "No dashboards or saved cards yet. Run a query in Ask Data and save it to a dashboard."
      )
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
        "GET /api/v1/dashboards/my": successResponse([
          {
            ...backendDashboard({ cards: [card] }),
            generated_sql: "SELECT dashboard_secret"
          }
        ])
      })
    );

    renderAppAt("/");

    expect(await screen.findByRole("heading", { name: "Operations review" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Scoped incident review" })).toBeInTheDocument();
    expect(screen.queryByText("SELECT secret_generated_sql")).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT secret_executed_sql")).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT dashboard_secret")).not.toBeInTheDocument();
  });

  it("shows genuine Home loading and retryable error states", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": pendingResponse()
      })
    );
    const firstRender = renderAppAt("/");
    expect(
      await screen.findByText("Loading your saved dashboard cards...")
    ).toBeInTheDocument();

    firstRender.unmount();
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": [
          errorResponse("DASHBOARDS_UNAVAILABLE", 503),
          successResponse([])
        ]
      })
    );
    renderAppAt("/");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dashboard cards could not be loaded."
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByText(/No dashboards or saved cards yet/)
    ).toBeInTheDocument();
  });

  it("creates a personal dashboard with CSRF and refreshes Home", async () => {
    setCsrfCookie("csrf-from-cookie");
    const createdDashboard = backendDashboard({ title: "Quarterly review" });
    const fetchMock = installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": [
          successResponse([]),
          successResponse([createdDashboard])
        ],
        "POST /api/v1/dashboards": successResponse(createdDashboard)
      })
    );

    renderAppAt("/");
    await screen.findByText(/No dashboards or saved cards yet/);
    fireEvent.change(screen.getByLabelText("Dashboard title"), {
      target: { value: "Quarterly review" }
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Leadership review" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Create dashboard" }));

    expect(await screen.findByText("Personal dashboard created.")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Quarterly review" })).toBeInTheDocument();
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
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );

    renderAppAt("/");
    await screen.findByRole("region", { name: "My Dashboard" });

    expect(screen.queryByRole("heading", { name: "Create personal dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByText(/not available for your role/i)).not.toBeInTheDocument();
  });

  it("restores Ask Data directly on refresh and runs a free query", async () => {
    setCsrfCookie("csrf-from-cookie");
    const fetchMock = installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "POST /api/v1/queries/run": successResponse(backendQueryResult())
      })
    );

    renderAppAt("/ask");
    expect(await screen.findByRole("heading", { name: "Ask Data" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/ask");
    expect((await screen.findAllByText("Unused paid licenses")).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("Free question"), {
      target: { value: "Show reclaimable licenses in my scope." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Microsoft 365 E5")).toBeInTheDocument();
    expect(screen.getByText("Found one reclaim opportunity.")).toBeInTheDocument();
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
    expect((await screen.findAllByText("Template-only mode")).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Free question")).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));
    expect(await screen.findByText("Microsoft 365 E5")).toBeInTheDocument();

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
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));
    await screen.findByText("Microsoft 365 E5");

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
        "POST /api/v1/query-runs/query-run-id/save-card": successResponse(savedCard)
      })
    );

    renderAppAt("/ask");
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));
    await screen.findByText("Microsoft 365 E5");
    fireEvent.click(screen.getByRole("button", { name: "Choose dashboard" }));
    expect(await screen.findByLabelText("Target dashboard")).toHaveValue("dashboard-id");
    fireEvent.change(screen.getByLabelText("Card title"), {
      target: { value: "License opportunities" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save card" }));

    expect(await screen.findByText("Dashboard card saved.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/query-runs/query-run-id/save-card",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-from-cookie" })
      })
    );
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
