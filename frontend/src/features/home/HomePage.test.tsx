import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendActionList,
  backendApprovalDetail,
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
    expect(screen.queryByText("My Action Requests")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Approval activity" })).not.toBeInTheDocument();
  });

  it.each([
    ["Manager", demoManager],
    ["Analyst", demoAnalyst]
  ])("shows scoped operational metrics for %s", async (label, user) => {
    installApiMock(authenticatedRoutes(user));

    renderAppAt("/");

    expect(await screen.findByText("Operational metrics")).toBeInTheDocument();
    expect(screen.getByText("93.2%")).toBeInTheDocument();
    expect(screen.getByText("$18,432.50")).toBeInTheDocument();
    expect(screen.queryByText("Administrative metrics")).not.toBeInTheDocument();
    if (label === "Manager") {
      expect(screen.queryByRole("heading", { name: "Approval activity" })).not.toBeInTheDocument();
    }
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

  it("shows eligible approval and Audit summaries only to authorized roles", async () => {
    const approval = backendApprovalDetail();
    installApiMock(authenticatedRoutes(demoAnalyst, {
      "GET /api/v1/approvals/pending": successResponse({ items: [approval], pagination: { limit: 3, offset: 0, returned: 1, total: 1 } })
    }));
    const analystView = renderAppAt("/");
    expect(await screen.findByRole("heading", { name: "Approval activity" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open scoped Audit/ })).toHaveAttribute("href", "/audit");
    analystView.unmount();

    installApiMock(authenticatedRoutes(demoAdmin, {
      "GET /api/v1/approvals/pending": successResponse({ items: [approval], pagination: { limit: 3, offset: 0, returned: 1, total: 1 } })
    }));
    renderAppAt("/");
    expect(await screen.findByText("Admin required")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open global Audit/ })).toHaveAttribute("href", "/audit");
  });

  it("shows requester-owned counts and isolates an action-summary failure", async () => {
    const summary = backendActionList();
    summary.summary = { pending: 2, completed: 4, closed: 1 };
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/actions": successResponse(summary)
      })
    );
    const first = renderAppAt("/");
    const actionHeading = await screen.findByRole("heading", { name: "My Action Requests" });
    const actionSection = actionHeading.closest("section");
    expect(actionSection).not.toBeNull();
    expect((await within(actionSection!).findByText("Pending")).nextElementSibling).toHaveTextContent("2");
    expect(screen.getByRole("link", { name: "View Actions" })).toHaveAttribute("href", "/actions");

    first.unmount();
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/actions": errorResponse("ACTIONS_UNAVAILABLE", 503)
      })
    );
    renderAppAt("/");
    expect(await screen.findByText(/Action counts are temporarily unavailable/)).toBeInTheDocument();
    expect(screen.getByText("Operational metrics")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "My dashboards" })).toBeInTheDocument();
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
