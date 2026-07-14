import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendDashboardLibraryItem,
  backendHomeOverview,
  demoAdmin,
  demoAnalyst,
  demoManager,
  demoUser,
  errorResponse,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  setCsrfCookie,
  successResponse
} from "../../test/appTestUtils";
import type { HomeOverview } from "./types";

afterEach(resetAppTestState);

describe("role-aware Home", () => {
  it("shows only personal product summary for User", async () => {
    const overview = backendHomeOverview(demoUser);
    overview.personal_summary.owned_dashboard_count = 2;
    overview.personal_summary.owned_card_count = 7;
    installApiMock(
      authenticatedRoutes(demoUser, {
        "GET /api/v1/home/overview": successResponse(overview)
      })
    );

    renderAppAt("/");

    expect(await screen.findByText("Personal summary")).toBeInTheDocument();
    expect(screen.getByText("Owned dashboards").nextElementSibling).toHaveTextContent("2");
    expect(screen.queryByText("Operational metrics")).not.toBeInTheDocument();
    expect(screen.queryByText("Administrative metrics")).not.toBeInTheDocument();
    expect(screen.queryByText(/device compliance/i)).not.toBeInTheDocument();
  });

  it.each([
    ["Manager", demoManager],
    ["Analyst", demoAnalyst]
  ])("shows scoped operational metrics for %s", async (_label, user) => {
    installApiMock(authenticatedRoutes(user));

    renderAppAt("/");

    expect(await screen.findByText("Operational metrics")).toBeInTheDocument();
    expect(screen.getByText("93.2%")).toBeInTheDocument();
    expect(screen.getByText("$18,432.50")).toBeInTheDocument();
    expect(screen.queryByText("Administrative metrics")).not.toBeInTheDocument();
  });

  it("shows global and only returned administrative metrics for Admin", async () => {
    installApiMock(authenticatedRoutes(demoAdmin));

    renderAppAt("/");

    expect(await screen.findByText("Operational metrics")).toBeInTheDocument();
    expect(screen.getByText("Administrative metrics")).toBeInTheDocument();
    expect(screen.getByText("Active QueryOps users")).toBeInTheDocument();
    expect(screen.getByText("Pending role requests")).toBeInTheDocument();
    expect(screen.queryByText("Audit events · 7 days")).not.toBeInTheDocument();
  });

  it("renders unavailable for null operational values", async () => {
    const overview = backendHomeOverview(demoManager) as HomeOverview;
    if (overview.operational_metrics) {
      overview.operational_metrics.device_compliance_rate = null;
      overview.operational_metrics.monthly_license_cost_usd = null;
    }
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/home/overview": successResponse(overview)
      })
    );

    renderAppAt("/");

    expect((await screen.findAllByText("Unavailable")).length).toBe(2);
  });

  it("keeps the library visible when overview fails", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/home/overview": errorResponse("HOME_UNAVAILABLE", 503),
        "GET /api/v1/dashboards/library": successResponse([
          backendDashboardLibraryItem({ title: "Still visible" })
        ])
      })
    );

    renderAppAt("/");

    expect(await screen.findByText("Home overview could not be loaded.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Preview dashboard Still visible" })
    ).toBeInTheDocument();
  });

  it("keeps loaded overview metrics visible when the library fails", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/library": errorResponse("LIBRARY_UNAVAILABLE", 503)
      })
    );

    renderAppAt("/");

    expect(await screen.findByText("Operational metrics")).toBeInTheDocument();
    expect(screen.getByText("Dashboard library could not be loaded.")).toBeInTheDocument();
  });

  it("keeps personal creation choices constrained and validates the title", async () => {
    setCsrfCookie("csrf-token");
    installApiMock(authenticatedRoutes(demoManager));
    renderAppAt("/");
    fireEvent.click(await screen.findByRole("button", { name: "New dashboard" }));

    expect(screen.getByRole("dialog", { name: "New dashboard" })).toBeInTheDocument();
    expect(screen.getByText("Visibility: Personal")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /visibility/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create dashboard" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a dashboard title.");
  });
});
