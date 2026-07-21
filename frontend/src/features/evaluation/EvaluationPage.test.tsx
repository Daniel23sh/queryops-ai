import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendEvaluationCapability,
  backendEvaluationOverview,
  backendEvaluationQueries,
  backendEvaluationSecurity,
  demoAnalyst,
  demoManager,
  errorResponse,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  successResponse
} from "../../test/appTestUtils";

afterEach(resetAppTestState);

describe("Evaluation workspace", () => {
  it("uses the overview-selected run for tab requests and preserves deep links", async () => {
    const runId = "00000000-0000-4000-8000-000000009999";
    const fetchMock = installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview({ runId })),
      "GET /api/v1/evaluation/queries": successResponse(backendEvaluationQueries({ runId }))
    }));
    renderAppAt("/evaluation?tab=queries");

    expect(await screen.findByRole("heading", { name: "Query measurements" })).toBeInTheDocument();
    const queryCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/evaluation/queries"));
    expect(String(queryCall?.[0])).toContain(`run_id=${runId}`);
    expect(window.location.search).toContain("tab=queries");
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/evaluation/overview"))).toHaveLength(1);
  });

  it("restores tab state with browser Back and does not expose run controls", async () => {
    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview()),
      "GET /api/v1/evaluation/queries": successResponse(backendEvaluationQueries())
    }));
    renderAppAt("/evaluation");
    await screen.findByRole("heading", { name: "MockLLM quality measurement" });
    const tabs = screen.getByRole("navigation", { name: "Evaluation sections" });
    fireEvent.click(within(tabs).getByRole("link", { name: "Queries" }));
    expect(await screen.findByRole("heading", { name: "Query measurements" })).toBeInTheDocument();
    window.history.back();
    await waitFor(() => expect(window.location.search).toBe(""));
    expect(await screen.findByRole("heading", { name: "MockLLM quality measurement" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /run/i })).not.toBeInTheDocument();
  });

  it("keeps Manager results business-level even when SQL visibility is unrelated", async () => {
    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview()),
      "GET /api/v1/evaluation/queries": successResponse(backendEvaluationQueries({ technical: false }))
    }));
    renderAppAt("/evaluation?tab=queries");

    expect(await screen.findByText("itops-security-003")).toBeInTheDocument();
    expect(screen.getByText("Expected behavior")).toBeInTheDocument();
    expect(screen.queryByText("Technical measurement details")).not.toBeInTheDocument();
    expect(screen.queryByText("directory_users")).not.toBeInTheDocument();
  });

  it("fails closed when a tab response does not match the Overview-selected run", async () => {
    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview({ runId: "00000000-0000-4000-8000-000000009999" })),
      "GET /api/v1/evaluation/queries": successResponse(backendEvaluationQueries())
    }));
    renderAppAt("/evaluation?tab=queries");

    expect(await screen.findByRole("heading", { name: "The selected run could not be verified" })).toBeInTheDocument();
    expect(screen.queryByText("itops-security-003")).not.toBeInTheDocument();
  });

  it("renders only API-returned technical fields for an authorized projection", async () => {
    installApiMock(authenticatedRoutes(demoAnalyst, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview()),
      "GET /api/v1/evaluation/queries": successResponse(backendEvaluationQueries({ technical: true }))
    }));
    renderAppAt("/evaluation?tab=queries");

    const disclosure = await screen.findByText("Technical measurement details");
    fireEvent.click(disclosure);
    expect(screen.getByText("Unsafe query blocked")).toBeInTheDocument();
    expect(screen.getAllByText("Execution failed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("directory users").length).toBeGreaterThan(0);
  });

  it("reports explicit unmeasured capabilities and honest 4-of-5 security behavior", async () => {
    installApiMock(authenticatedRoutes(demoAnalyst, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview()),
      "GET /api/v1/evaluation/actions": successResponse(backendEvaluationCapability("actions")),
      "GET /api/v1/evaluation/security": successResponse(backendEvaluationSecurity({ technical: true })),
      "GET /api/v1/evaluation/dashboards": successResponse(backendEvaluationCapability("dashboards"))
    }));
    renderAppAt("/evaluation");
    await screen.findByRole("heading", { name: "MockLLM quality measurement" });

    const tabNavigation = screen.getByRole("navigation", { name: "Evaluation sections" });
    fireEvent.click(within(tabNavigation).getByRole("link", { name: "Actions" }));
    expect(await screen.findByRole("heading", { name: "Action evaluation" })).toBeInTheDocument();
    expect(screen.getByText("Not measured in this dataset")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start|run|rerun/i })).not.toBeInTheDocument();

    fireEvent.click(within(tabNavigation).getByRole("link", { name: "Security" }));
    expect(await screen.findByText("4/5")).toBeInTheDocument();
    expect(screen.getByText("Unsafe-query block")).toBeInTheDocument();
    expect(screen.getByText("0 passed · 1 failed")).toBeInTheDocument();

    fireEvent.click(within(tabNavigation).getByRole("link", { name: "Dashboards" }));
    expect(await screen.findByRole("heading", { name: "Dashboard evaluation" })).toBeInTheDocument();
    expect(screen.getAllByText("Not available").length).toBeGreaterThan(0);
  });

  it("serializes supported URL filters, resets pagination, and never sends scope filters", async () => {
    const fetchMock = installApiMock(authenticatedRoutes(demoAnalyst, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview()),
      "GET /api/v1/evaluation/queries": [successResponse(backendEvaluationQueries({ technical: true })), successResponse(backendEvaluationQueries({ technical: true }))]
    }));
    renderAppAt("/evaluation?tab=queries&page=3");
    const difficulty = await screen.findByRole("combobox", { name: "Difficulty" });
    fireEvent.change(difficulty, { target: { value: "security" } });
    await waitFor(() => expect(window.location.search).not.toContain("page=3"));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/evaluation/queries"))).toHaveLength(2));
    const urls = fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes("/evaluation/queries"));
    const latestUrl = urls[urls.length - 1];
    expect(latestUrl).toContain("difficulty=security");
    expect(latestUrl).not.toContain("scope");
    expect(latestUrl).not.toContain("department");
  });

  it("removes visible metrics after a forbidden tab response without leaking server detail", async () => {
    installApiMock(authenticatedRoutes(demoAnalyst, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview()),
      "GET /api/v1/evaluation/security": errorResponse("FORBIDDEN", 403, "raw secret driver detail")
    }));
    renderAppAt("/evaluation");
    expect((await screen.findAllByText("25.0%")).length).toBeGreaterThan(0);
    fireEvent.click(within(screen.getByRole("navigation", { name: "Evaluation sections" })).getByRole("link", { name: "Security" }));
    await waitFor(() => expect(screen.getByText(/Previously loaded metrics have been removed/)).toBeInTheDocument());
    expect(screen.queryByText("25.0%")).not.toBeInTheDocument();
    expect(screen.queryByText("raw secret driver detail")).not.toBeInTheDocument();
  });

  it("falls back from an unknown tab to Overview without arbitrary run lookup", async () => {
    const fetchMock = installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview())
    }));
    renderAppAt("/evaluation?tab=history&run_id=attacker-selected");
    expect(await screen.findByRole("heading", { name: "MockLLM quality measurement" })).toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toBe(""));
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("attacker-selected"))).toBe(false);
  });

  it("labels partial metrics without fabricating missing-case scores", async () => {
    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview({ availability: "partially_measured", completed: 20, passed: 8, failed: 12 }))
    }));
    renderAppAt("/evaluation");
    expect(await screen.findByRole("heading", { name: "Partial measurement" })).toBeInTheDocument();
    expect(screen.getByText(/Missing cases are visible/)).toBeInTheDocument();
  });

  it("handles a disappeared selected run with a controlled latest-run action", async () => {
    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview()),
      "GET /api/v1/evaluation/queries": errorResponse("NOT_FOUND", 404, "raw missing-row detail")
    }));
    renderAppAt("/evaluation?tab=queries");
    expect(await screen.findByRole("heading", { name: "This run is no longer available" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load latest run" })).toBeInTheDocument();
    expect(screen.queryByText("raw missing-row detail")).not.toBeInTheDocument();
  });
});
