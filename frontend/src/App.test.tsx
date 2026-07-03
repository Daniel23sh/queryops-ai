import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import type { AuthUser } from "./auth/types";
import { AskDataPage } from "./features/ask-data";

const demoUser = backendUser({
  id: "user-id",
  email: "demo.user@queryops.local",
  fullName: "Demo User",
  role: "user",
  departmentId: "sales-id",
  departmentName: "Sales",
  permissions: [
    "can_use_query_templates",
    "can_star_dashboard",
    "can_view_own_data"
  ]
});

const demoManager = backendUser({
  id: "manager-id",
  email: "demo.manager@queryops.local",
  fullName: "Demo Manager",
  role: "manager",
  departmentId: "finance-id",
  departmentName: "Finance",
  permissions: [
    "can_use_query_templates",
    "can_star_dashboard",
    "can_view_own_data",
    "can_run_free_query",
    "can_query_department_data",
    "can_query_scoped_data",
    "can_view_department_data",
    "can_view_scoped_data",
    "can_create_personal_dashboard",
    "can_request_action",
    "can_view_department_evaluation",
    "can_view_scope_evaluation"
  ]
});

const demoAnalyst = backendUser({
  id: "analyst-id",
  email: "demo.analyst@queryops.local",
  fullName: "Demo Analyst",
  role: "analyst",
  departmentId: "it-id",
  departmentName: "IT",
  permissions: [
    "can_use_query_templates",
    "can_star_dashboard",
    "can_view_own_data",
    "can_run_free_query",
    "can_query_department_data",
    "can_query_scoped_data",
    "can_view_department_data",
    "can_view_scoped_data",
    "can_create_personal_dashboard",
    "can_request_action",
    "can_view_department_evaluation",
    "can_view_scope_evaluation",
    "can_view_sql",
    "can_create_card",
    "can_create_department_dashboard",
    "can_create_scope_dashboard",
    "can_manage_department_dashboard",
    "can_manage_scope_dashboard",
    "can_view_query_history_department",
    "can_view_query_history_scope",
    "can_view_department_audit",
    "can_view_scope_audit",
    "can_approve_department_action",
    "can_approve_scoped_action"
  ]
});

const demoAdmin = backendUser({
  id: "admin-id",
  email: "demo.admin@queryops.local",
  fullName: "Demo Admin",
  role: "admin",
  departmentId: "it-id",
  departmentName: "IT",
  permissions: [
    "can_use_query_templates",
    "can_run_free_query",
    "can_query_department_data",
    "can_query_scoped_data",
    "can_query_global_data",
    "can_query_product_tables",
    "can_view_own_data",
    "can_view_department_data",
    "can_view_scoped_data",
    "can_view_global_data",
    "can_view_sql",
    "can_view_query_history_department",
    "can_view_query_history_scope",
    "can_star_dashboard",
    "can_create_personal_dashboard",
    "can_create_department_dashboard",
    "can_create_scope_dashboard",
    "can_create_global_dashboard",
    "can_manage_department_dashboard",
    "can_manage_scope_dashboard",
    "can_manage_global_dashboard",
    "can_create_card",
    "can_request_action",
    "can_approve_department_action",
    "can_approve_scoped_action",
    "can_approve_global_action",
    "can_approve_policy_override",
    "can_self_approve_admin_action",
    "can_manage_users",
    "can_disable_app_user",
    "can_downgrade_user_role",
    "can_approve_role_requests",
    "can_view_department_audit",
    "can_view_scope_audit",
    "can_view_global_audit",
    "can_view_department_evaluation",
    "can_view_scope_evaluation",
    "can_view_global_evaluation"
  ]
});

const askDataTemplates = [
  backendQueryTemplate({
    id: "unused_licenses_department",
    category: "Licenses",
    title: "Unused paid licenses",
    description: "Find reclaimable paid licenses in the current scope.",
    naturalLanguageQuestion: "Show unused paid licenses in my department.",
    parameters: [
      {
        name: "days_unused",
        data_type: "integer",
        description: "Days since the license was last used.",
        required: false,
        default: 60
      }
    ]
  }),
  backendQueryTemplate({
    id: "security_events_review",
    category: "Security",
    title: "Security events",
    description: "Review recent security events by scope.",
    naturalLanguageQuestion: "Show recent security events in my scope."
  })
];

afterEach(() => {
  clearCsrfCookie();
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  document.documentElement.removeAttribute("data-theme");
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows an app-loading state while auth hydration is pending", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));

    renderApp();

    expect(screen.getByText("Checking your session...")).toBeInTheDocument();
  });

  it("shows the four demo login choices when unauthenticated", async () => {
    stubFetchSequence(errorResponse("UNAUTHORIZED", 401));

    renderApp();

    expect(
      await screen.findByRole("heading", { name: "Choose a demo profile" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /demo admin/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /demo analyst/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /demo manager/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /demo user/i })).toBeInTheDocument();
  });

  it("toggles the app theme and stores the preference", async () => {
    stubSystemTheme(false);
    stubFetchSequence(errorResponse("UNAUTHORIZED", 401));

    renderApp();

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute("data-theme", "light");
    });
    expect(document.documentElement).not.toHaveClass("dark");

    fireEvent.click(
      screen.getByRole("button", { name: "Switch to dark mode" })
    );

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("queryops-theme")).toBe("dark");
    expect(
      screen.getByRole("button", { name: "Switch to light mode" })
    ).toBeInTheDocument();
  });

  it("hydrates the app theme from a stored preference", async () => {
    localStorage.setItem("queryops-theme", "dark");
    stubSystemTheme(false);
    stubFetchSequence(errorResponse("UNAUTHORIZED", 401));

    renderApp();

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    });
    expect(document.documentElement).toHaveClass("dark");
    expect(
      screen.getByRole("button", { name: "Switch to light mode" })
    ).toBeInTheDocument();
  });

  it("logs in as the selected demo user and renders the authenticated workspace", async () => {
    const fetchMock = stubFetchSequence(
      errorResponse("UNAUTHORIZED", 401),
      successResponse({
        user: demoManager,
        requires_onboarding: false,
        csrf_token: "csrf-from-login"
      })
    );

    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /demo manager/i }));

    expect(
      await screen.findByRole("heading", { name: "Templates" })
    ).toBeInTheDocument();
    expect(screen.getByText("demo.manager@queryops.local")).toBeInTheDocument();
    expect(screen.getByText("Manager")).toBeInTheDocument();
    expect(screen.getByText("Finance")).toBeInTheDocument();

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/demo/login",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ email: "demo.manager@queryops.local" })
      })
    );
  });

  it("shows an error when demo login fails", async () => {
    stubFetchSequence(
      errorResponse("UNAUTHORIZED", 401),
      errorResponse("INVALID_DEMO_USER", 400, "Demo login failed.")
    );

    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /demo admin/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Demo login failed.");
  });

  it("keeps authenticated users out of the login screen after hydration", async () => {
    stubFetchSequence(successResponse(demoManager));

    renderApp();

    expect(
      await screen.findByRole("heading", { name: "Templates" })
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Choose a demo profile" })).not.toBeInTheDocument();
    });
  });

  it("shows common navigation and limited Ask Data access for demo user", async () => {
    stubFetchSequence(successResponse(demoUser));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    expect(within(nav).getByRole("button", { name: "Templates" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "My Dashboard" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Role Upgrade" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Ask Data" })).toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Role Requests" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "SQL / Technical" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Admin Console" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Users" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Audit" })).not.toBeInTheDocument();
  });

  it("shows Ask Data for demo manager but hides analyst and admin navigation", async () => {
    stubFetchSequence(successResponse(demoManager));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    expect(within(nav).getByRole("button", { name: "Ask Data" })).toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Query History" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "SQL / Technical" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Role Requests" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Admin Console" })).not.toBeInTheDocument();
  });

  it("renders a role-aware dashboard for demo manager without extra API calls", async () => {
    const fetchMock = stubFetchSequence(successResponse(demoManager));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "My Dashboard" }));

    const dashboard = await screen.findByRole("region", {
      name: "My Dashboard"
    });
    expect(
      within(dashboard).getByRole("heading", { name: "QueryOps Command Center" })
    ).toBeInTheDocument();
    expect(within(dashboard).getByText("Manager")).toBeInTheDocument();
    expect(within(dashboard).getByText("Finance")).toBeInTheDocument();
    expect(within(dashboard).getByText("Free-query access")).toBeInTheDocument();
    expect(within(dashboard).getByText("SQL hidden")).toBeInTheDocument();
    expect(within(dashboard).getByText("Diagnostics hidden")).toBeInTheDocument();
    expect(
      within(dashboard).getByRole("button", { name: "Open Ask Data" })
    ).toBeEnabled();
    expect(
      within(dashboard).getByRole("button", { name: "Review query history" })
    ).toBeDisabled();
    expect(
      within(dashboard).getByRole("button", { name: "Save dashboard card" })
    ).toBeDisabled();
    expect(within(dashboard).queryByText("Generated SQL")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText("Executed SQL")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText(/SELECT /i)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renders template-only dashboard access for demo user", async () => {
    const fetchMock = stubFetchSequence(successResponse(demoUser));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "My Dashboard" }));

    const dashboard = await screen.findByRole("region", {
      name: "My Dashboard"
    });
    expect(within(dashboard).getByText("User")).toBeInTheDocument();
    expect(within(dashboard).getByText("Sales")).toBeInTheDocument();
    expect(within(dashboard).getByText("Template-only access")).toBeInTheDocument();
    expect(within(dashboard).getByText("SQL hidden")).toBeInTheDocument();
    expect(within(dashboard).getByText("Diagnostics hidden")).toBeInTheDocument();
    expect(
      within(dashboard).getByText(/Approved templates are the safe starting point/i)
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renders technical dashboard access for demo analyst without exposing SQL content", async () => {
    const fetchMock = stubFetchSequence(successResponse(demoAnalyst));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "My Dashboard" }));

    const dashboard = await screen.findByRole("region", {
      name: "My Dashboard"
    });
    expect(within(dashboard).getByText("Analyst")).toBeInTheDocument();
    expect(within(dashboard).getByText("IT")).toBeInTheDocument();
    expect(within(dashboard).getByText("Free-query access")).toBeInTheDocument();
    expect(within(dashboard).getByText("SQL visible in Ask Data")).toBeInTheDocument();
    expect(
      within(dashboard).getByText("Diagnostics visible in Ask Data")
    ).toBeInTheDocument();
    expect(within(dashboard).queryByText("Generated SQL")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText("Executed SQL")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText(/SELECT /i)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renders the Ask Data page shell from workspace navigation", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    expect(
      await screen.findByRole("heading", { name: "Ask Data" })
    ).toBeInTheDocument();
    expect(screen.getByText("Command workspace")).toBeInTheDocument();
    expect((await screen.findAllByText("Unused paid licenses")).length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/query-templates",
      expect.objectContaining({
        method: "GET",
        credentials: "include"
      })
    );
    expectNoQueryRun(fetchMock);
  });

  it("renders template loading state while query templates are pending", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(successResponse(demoManager))
      .mockReturnValueOnce(new Promise(() => undefined));
    vi.stubGlobal("fetch", fetchMock);

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    expect(
      await screen.findByRole("heading", { name: "Ask Data" })
    ).toBeInTheDocument();
    expect(screen.getByText("Loading query templates...")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expectNoQueryRun(fetchMock);
  });

  it("loads real Ask Data templates and updates selected template details", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    const templateRegion = await screen.findByRole("region", {
      name: "Template catalog"
    });
    expect(within(templateRegion).getByText("Licenses")).toBeInTheDocument();
    expect(within(templateRegion).getByText("Security")).toBeInTheDocument();
    const unusedLicensesTemplate = within(templateRegion).getByRole("button", {
      name: /Unused paid licenses/i
    });
    expect(unusedLicensesTemplate).toBeInTheDocument();
    expect(
      within(unusedLicensesTemplate).getByText(
        "Find reclaimable paid licenses in the current scope."
      )
    ).toBeInTheDocument();
    expect(
      within(templateRegion).getByText(/Custom parameters are not supported yet/i)
    ).toBeInTheDocument();
    expect(
      within(templateRegion).getByText(/backend template defaults will be used/i)
    ).toBeInTheDocument();

    fireEvent.click(
      within(templateRegion).getByRole("button", { name: /Security events/i })
    );

    const selectedTemplate = within(templateRegion).getByLabelText(
      "Selected template details"
    );
    expect(within(selectedTemplate).getByText("Security events")).toBeInTheDocument();
    expect(
      within(selectedTemplate).getByText("Show recent security events in my scope.")
    ).toBeInTheDocument();
    expectNoQueryRun(fetchMock);
  });

  it("runs the selected template with CSRF and hides returned SQL fields", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "Template query completed.",
          generatedSql: "SELECT secret_value FROM internal_table",
          executedSql: "SELECT secret_value FROM internal_table"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    expect(await screen.findByText("Template query completed.")).toBeInTheDocument();
    expect(screen.getByText("Status: succeeded")).toBeInTheDocument();
    expect(screen.queryByText("SELECT secret_value FROM internal_table")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/v1/queries/run",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-from-cookie"
        }),
        body: JSON.stringify({
          question: "Show unused paid licenses in my department.",
          template_id: "unused_licenses_department"
        })
      })
    );
  });

  it("renders dynamic result table values from template query results", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "Dynamic table ready.",
          columns: [
            "product_name",
            "unused_count",
            "has_owner",
            "last_seen",
            "owner",
            "metadata",
            "tags"
          ],
          rows: [
            {
              product_name: "Microsoft 365 E5",
              unused_count: 12,
              has_owner: true,
              last_seen: "2026-07-01T12:30:00Z",
              owner: null,
              metadata: {
                department: "Finance",
                priority: 2
              },
              tags: ["license", "unused"]
            }
          ],
          durationMs: 87,
          generatedSql: "SELECT dynamic_hidden_sql",
          executedSql: "SELECT dynamic_hidden_sql"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    const resultSummary = await screen.findByLabelText("Query result summary");
    expect(within(resultSummary).getByText("Dynamic table ready.")).toBeInTheDocument();
    expect(within(resultSummary).getByText("Status: succeeded")).toBeInTheDocument();
    expect(within(resultSummary).getByText("87 ms")).toBeInTheDocument();
    expect(
      within(resultSummary).getByLabelText("Visualization suggestion")
    ).toHaveTextContent("Chart available later: compare unused_count by product_name.");

    const table = screen.getByRole("table", { name: "Query results" });
    expect(
      within(table).getByRole("columnheader", { name: "product_name" })
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("columnheader", { name: "unused_count" })
    ).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "Microsoft 365 E5" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "12" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "true" })).toBeInTheDocument();
    expect(
      within(table).getByRole("cell", { name: "2026-07-01T12:30:00Z" })
    ).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "null" })).toBeInTheDocument();
    expect(
      within(table).getByRole("cell", {
        name: '{"department":"Finance","priority":2}'
      })
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("cell", { name: '["license","unused"]' })
    ).toBeInTheDocument();
    expect(screen.queryByText("SELECT dynamic_hidden_sql")).not.toBeInTheDocument();

    const insightRegion = screen.getByRole("region", {
      name: "Ask Data insights"
    });
    openInsightsPanel(insightRegion);
    expect(
      within(insightRegion).getByRole("button", { name: "Save as Card" })
    ).toBeDisabled();
    expect(
      within(insightRegion).getByRole("button", { name: "CSV Export" })
    ).toBeDisabled();
    expect(
      within(insightRegion).getByRole("button", { name: "Preview Action" })
    ).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders a no rows state for successful empty query results", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoUser),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "No matching records.",
          columns: ["product_name", "unused_count"],
          rows: [],
          rowCount: 0
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    expect(await screen.findByText("No matching records.")).toBeInTheDocument();
    const resultSummary = screen.getByLabelText("Query result summary");
    expect(
      within(resultSummary).getByLabelText("Visualization suggestion")
    ).toHaveTextContent("Chart available later when rows are returned.");
    expect(screen.getByText("No rows returned.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Query results" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders truncated and warning states for free query results", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "Free query returned many rows.",
          columns: ["priority", "ticket_count"],
          rows: [
            {
              priority: "high",
              ticket_count: 500
            }
          ],
          rowCount: 500,
          durationMs: 120,
          truncated: true,
          warnings: [
            "Results were limited to 100 rows.",
            "Some matching rows are not shown."
          ],
          generatedSql: "SELECT warning_hidden_sql",
          executedSql: "SELECT warning_hidden_sql"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.change(await screen.findByLabelText("Free question"), {
      target: { value: "Show support ticket counts by priority." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Free query returned many rows.")).toBeInTheDocument();
    const resultSummary = screen.getByLabelText("Query result summary");
    expect(
      within(resultSummary).getByLabelText("Visualization suggestion")
    ).toHaveTextContent("Chart available later: compare ticket_count by priority.");
    expect(screen.getByText("Results truncated")).toBeInTheDocument();
    expect(screen.getByText("Results were limited to 100 rows.")).toBeInTheDocument();
    expect(screen.getByText("Some matching rows are not shown.")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Query results" });
    expect(within(table).getByRole("cell", { name: "high" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "500" })).toBeInTheDocument();
    expect(screen.queryByText("SELECT warning_hidden_sql")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("prevents selected template run without a CSRF token", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    const runButton = await screen.findByRole("button", {
      name: "Run selected template"
    });
    expect(runButton).toBeDisabled();
    expect(
      screen.getByText("Refresh your session before running a template query.")
    ).toBeInTheDocument();
    fireEvent.click(runButton);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expectNoQueryRun(fetchMock);
  });

  it("keeps the selected template run button disabled while running", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(successResponse(demoManager))
      .mockResolvedValueOnce(successResponse(askDataTemplates))
      .mockReturnValueOnce(new Promise(() => undefined));
    vi.stubGlobal("fetch", fetchMock);

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    expect(await screen.findByText("Running selected template...")).toBeInTheDocument();
    const runningButton = screen.getByRole("button", { name: "Running template..." });
    expect(runningButton).toBeDisabled();
    fireEvent.click(runningButton);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders selected template run API errors safely", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates),
      errorResponse("QUERY_RUN_FAILED", 500, "Template query could not be run.")
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Template query could not be run."
    );
    expect(screen.queryByText("QUERY_RUN_FAILED")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("lets demo manager submit a free query with CSRF and without template id", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "Free query completed.",
          generatedSql: "SELECT manager_hidden_sql",
          executedSql: "SELECT manager_hidden_sql"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    const freeQuestionInput = await screen.findByLabelText("Free question");
    const submitButton = screen.getByRole("button", { name: "Run free query" });
    expect(submitButton).toBeDisabled();

    fireEvent.change(freeQuestionInput, {
      target: { value: "Show open support tickets by priority." }
    });
    expect(submitButton).not.toBeDisabled();
    fireEvent.click(submitButton);

    expect(await screen.findByText("Free query completed.")).toBeInTheDocument();
    expect(
      screen.getByText("Question: Show open support tickets by priority.")
    ).toBeInTheDocument();
    expect(screen.queryByText("SELECT manager_hidden_sql")).not.toBeInTheDocument();
    expect(screen.queryByText("Generated SQL")).not.toBeInTheDocument();
    expect(screen.queryByText("Executed SQL")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "SQL" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/v1/queries/run",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-from-cookie"
        }),
        body: JSON.stringify({
          question: "Show open support tickets by priority."
        })
      })
    );
  });

  it("lets demo analyst submit a free query", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoAnalyst),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "Analyst free query completed.",
          generatedSql: "SELECT analyst_hidden_sql",
          executedSql: "SELECT analyst_hidden_sql"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.change(await screen.findByLabelText("Free question"), {
      target: { value: "Show inactive privileged accounts." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Analyst free query completed.")).toBeInTheDocument();
    expect(screen.queryByText("SELECT analyst_hidden_sql")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders generated and executed SQL for demo analyst only in the SQL tab", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoAnalyst),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "Analyst SQL query completed.",
          generatedSql: "SELECT generated_analyst_sql FROM safe_scope",
          executedSql: "SELECT executed_analyst_sql FROM safe_scope"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.change(await screen.findByLabelText("Free question"), {
      target: { value: "Show inactive privileged accounts." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Analyst SQL query completed.")).toBeInTheDocument();
    expect(screen.queryByText("SELECT generated_analyst_sql FROM safe_scope")).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT executed_analyst_sql FROM safe_scope")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Summary" }));
    expect(screen.queryByText("SELECT generated_analyst_sql FROM safe_scope")).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT executed_analyst_sql FROM safe_scope")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "SQL" }));
    const sqlPanel = screen.getByRole("tabpanel", { name: "SQL" });
    expect(within(sqlPanel).getByText("Generated SQL")).toBeInTheDocument();
    expect(within(sqlPanel).getByText("Executed SQL")).toBeInTheDocument();
    expect(
      within(sqlPanel).getByText("SELECT generated_analyst_sql FROM safe_scope")
    ).toBeInTheDocument();
    expect(
      within(sqlPanel).getByText("SELECT executed_analyst_sql FROM safe_scope")
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("lets demo admin submit a free query", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoAdmin),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "Admin free query completed.",
          generatedSql: "SELECT admin_hidden_sql",
          executedSql: "SELECT admin_hidden_sql"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.change(await screen.findByLabelText("Free question"), {
      target: { value: "Show global license spend by department." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Admin free query completed.")).toBeInTheDocument();
    expect(screen.queryByText("SELECT admin_hidden_sql")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders generated and executed SQL for demo admin in the SQL tab", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoAdmin),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "Admin SQL query completed.",
          generatedSql: "SELECT generated_admin_sql FROM safe_scope",
          executedSql: "SELECT executed_admin_sql FROM safe_scope"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.change(await screen.findByLabelText("Free question"), {
      target: { value: "Show global license spend by department." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Admin SQL query completed.")).toBeInTheDocument();
    expect(screen.queryByText("SELECT generated_admin_sql FROM safe_scope")).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT executed_admin_sql FROM safe_scope")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "SQL" }));
    const sqlPanel = screen.getByRole("tabpanel", { name: "SQL" });
    expect(
      within(sqlPanel).getByText("SELECT generated_admin_sql FROM safe_scope")
    ).toBeInTheDocument();
    expect(
      within(sqlPanel).getByText("SELECT executed_admin_sql FROM safe_scope")
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders SQL empty and unavailable states for demo analyst", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoAnalyst),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "Analyst result without SQL.",
          generatedSql: null,
          executedSql: null
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.click(await screen.findByRole("tab", { name: "SQL" }));
    expect(
      screen.getByText("Run a query to inspect SQL for this role.")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Results" }));
    fireEvent.change(screen.getByLabelText("Free question"), {
      target: { value: "Show inactive privileged accounts." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Analyst result without SQL.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "SQL" }));
    expect(
      screen.getByText("SQL is not available for this query result.")
    ).toBeInTheDocument();
    expect(screen.queryByText("Generated SQL")).not.toBeInTheDocument();
    expect(screen.queryByText("Executed SQL")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders safe diagnostics for demo analyst without exposing SQL metadata", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoAnalyst),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          queryRunId: "analyst-diagnostics-id",
          message: "Analyst diagnostics ready.",
          rowCount: 7,
          durationMs: 31,
          warnings: ["Result warning without SQL"],
          generatedSql: "SELECT generated_analyst_sql FROM safe_scope",
          executedSql: "SELECT executed_analyst_sql FROM safe_scope",
          metadata: {
            provider: "mock",
            model: "mock-queryops-v1",
            template_id: "inactive_users_by_department",
            scope_type: "department",
            referenced_tables: ["directory_users", "login_events"],
            clarification_required: false,
            validation: {
              valid: true,
              error_code: null,
              generated_sql: "SELECT metadata_generated_sql"
            },
            execution: {
              status: "succeeded",
              error_code: null,
              row_count: 7,
              duration_ms: 31,
              truncated: false,
              executed_sql: "SELECT metadata_executed_sql"
            },
            self_correction: {
              attempted: true,
              succeeded: true,
              original_error_code: "select_star",
              final_error_code: null,
              generated_sql: "SELECT correction_sql"
            },
            generated_sql: "SELECT metadata_generated_sql",
            executed_sql: "SELECT metadata_executed_sql"
          }
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.change(await screen.findByLabelText("Free question"), {
      target: { value: "Show inactive privileged accounts." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Analyst diagnostics ready.")).toBeInTheDocument();
    expect(screen.queryByText("mock-queryops-v1")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Summary" }));
    expect(screen.queryByText("mock-queryops-v1")).not.toBeInTheDocument();
    expect(screen.queryByText("directory_users, login_events")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Diagnostics" }));
    const diagnosticsPanel = screen.getByRole("tabpanel", { name: "Diagnostics" });
    expect(within(diagnosticsPanel).getByText("Query run ID")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("analyst-diagnostics-id")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Provider")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("mock")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Model")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("mock-queryops-v1")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Template")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("inactive_users_by_department")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Referenced tables")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("directory_users, login_events")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Validation status")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Valid")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Execution row count")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("7")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Correction attempted")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Yes")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Correction status")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Succeeded")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Original correction error code")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("select_star")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Result warning without SQL")).toBeInTheDocument();
    expect(within(diagnosticsPanel).queryByText("SELECT metadata_generated_sql")).not.toBeInTheDocument();
    expect(within(diagnosticsPanel).queryByText("SELECT metadata_executed_sql")).not.toBeInTheDocument();
    expect(within(diagnosticsPanel).queryByText("SELECT correction_sql")).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT generated_analyst_sql FROM safe_scope")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "SQL" }));
    expect(screen.getByText("SELECT generated_analyst_sql FROM safe_scope")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders diagnostics content for demo admin", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoAdmin),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          queryRunId: "admin-diagnostics-id",
          message: "Admin diagnostics ready.",
          metadata: {
            provider: "mock",
            model: "mock-queryops-v1",
            scope_type: "global",
            validation: {
              valid: false,
              error_code: "forbidden_table"
            },
            execution: {
              status: "failed",
              error_code: "validation_failed",
              row_count: 0,
              duration_ms: 0,
              truncated: false
            },
            self_correction: {
              attempted: true,
              succeeded: false,
              original_error_code: "forbidden_table",
              final_error_code: "forbidden_table"
            }
          }
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.change(await screen.findByLabelText("Free question"), {
      target: { value: "Show global license spend by department." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Admin diagnostics ready.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Diagnostics" }));
    const diagnosticsPanel = screen.getByRole("tabpanel", { name: "Diagnostics" });
    expect(within(diagnosticsPanel).getByText("admin-diagnostics-id")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("global")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Invalid")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("validation_failed")).toBeInTheDocument();
    expect(within(diagnosticsPanel).getByText("Failed")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it.each([
    ["demo user", demoUser, null],
    ["demo manager", demoManager, "Show open support tickets by priority."]
  ] as const)("keeps diagnostics hidden from %s", async (_label, user, question) => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(user),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: `${user.role} diagnostics hidden.`,
          metadata: {
            provider: `hidden-provider-${user.role}`,
            model: `hidden-model-${user.role}`,
            template_id: `hidden-template-${user.role}`,
            validation: {
              valid: true,
              error_code: null
            },
            execution: {
              status: "succeeded",
              error_code: null,
              row_count: 1,
              duration_ms: 10,
              truncated: false
            },
            self_correction: {
              attempted: true,
              succeeded: true,
              original_error_code: "hidden_original_error",
              final_error_code: null
            }
          }
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    if (question === null) {
      fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));
    } else {
      fireEvent.change(await screen.findByLabelText("Free question"), {
        target: { value: question }
      });
      fireEvent.click(screen.getByRole("button", { name: "Run free query" }));
    }

    expect(await screen.findByText(`${user.role} diagnostics hidden.`)).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
    expect(screen.queryByText(`hidden-provider-${user.role}`)).not.toBeInTheDocument();
    expect(screen.queryByText(`hidden-model-${user.role}`)).not.toBeInTheDocument();
    expect(screen.queryByText(`hidden-template-${user.role}`)).not.toBeInTheDocument();
    expect(screen.queryByText("hidden_original_error")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders diagnostics empty state before a query", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoAnalyst),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.click(await screen.findByRole("tab", { name: "Diagnostics" }));
    expect(
      screen.getByText("Run a query to inspect diagnostics for this role.")
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  describe("Ask Data role matrix", () => {
    it("covers demo user template-only behavior and hides technical response data", async () => {
      document.cookie = "qo_csrf=csrf-from-cookie; path=/";
      const fetchMock = stubFetchSequence(
        successResponse(demoUser),
        successResponse(askDataTemplates),
        successResponse(
          sensitiveQueryRunResult({
            role: "user",
            message: "User matrix template completed."
          })
        )
      );

      renderApp();

      await openAskData();
      expectApprovedTemplatesVisible();
      expect(screen.queryByLabelText("Free question")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Run free query" })).not.toBeInTheDocument();
      expectFutureControlsDisabled();

      fireEvent.click(screen.getByRole("button", { name: "Run selected template" }));

      expect(await screen.findByText("User matrix template completed.")).toBeInTheDocument();
      expect(screen.getByRole("table", { name: "Query results" })).toBeInTheDocument();
      expectSensitiveTechnicalFieldsHidden("user");
      expect(fetchMock).toHaveBeenNthCalledWith(
        3,
        "http://localhost:8000/api/v1/queries/run",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            question: "Show unused paid licenses in my department.",
            template_id: "unused_licenses_department"
          })
        })
      );
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it("covers demo manager template and free-query behavior without technical visibility", async () => {
      document.cookie = "qo_csrf=csrf-from-cookie; path=/";
      const fetchMock = stubFetchSequence(
        successResponse(demoManager),
        successResponse(askDataTemplates),
        successResponse(
          sensitiveQueryRunResult({
            role: "manager-template",
            message: "Manager matrix template completed."
          })
        ),
        successResponse(
          sensitiveQueryRunResult({
            role: "manager-free",
            message: "Manager matrix free query completed."
          })
        )
      );

      renderApp();

      await openAskData();
      expectApprovedTemplatesVisible();
      expect(screen.getByLabelText("Free question")).not.toBeDisabled();
      expectFutureControlsDisabled();

      fireEvent.click(screen.getByRole("button", { name: "Run selected template" }));
      expect(await screen.findByText("Manager matrix template completed.")).toBeInTheDocument();
      expectSensitiveTechnicalFieldsHidden("manager-template");

      fireEvent.change(screen.getByLabelText("Free question"), {
        target: { value: "Show open support tickets by priority." }
      });
      fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

      expect(await screen.findByText("Manager matrix free query completed.")).toBeInTheDocument();
      expectSensitiveTechnicalFieldsHidden("manager-free");
      expect(fetchMock).toHaveBeenNthCalledWith(
        4,
        "http://localhost:8000/api/v1/queries/run",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            question: "Show open support tickets by priority."
          })
        })
      );
      expect(fetchMock).toHaveBeenCalledTimes(4);
    });

    it.each([
      ["demo analyst", demoAnalyst, "analyst", "Show inactive privileged accounts."],
      ["demo admin", demoAdmin, "admin", "Show global license spend by department."]
    ] as const)(
      "covers %s template, free-query, SQL, and diagnostics behavior",
      async (_label, user, role, question) => {
        document.cookie = "qo_csrf=csrf-from-cookie; path=/";
        const fetchMock = stubFetchSequence(
          successResponse(user),
          successResponse(askDataTemplates),
          successResponse(
            sensitiveQueryRunResult({
              role: `${role}-template`,
              message: `${role} matrix template completed.`
            })
          ),
          successResponse(
            sensitiveQueryRunResult({
              role,
              message: `${role} matrix free query completed.`
            })
          )
        );

        renderApp();

        await openAskData();
        expectApprovedTemplatesVisible();
        expect(screen.getByLabelText("Free question")).not.toBeDisabled();
        expect(screen.getByRole("tab", { name: "SQL" })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: "Diagnostics" })).toBeInTheDocument();
        expectFutureControlsDisabled();

        fireEvent.click(screen.getByRole("button", { name: "Run selected template" }));
        expect(await screen.findByText(`${role} matrix template completed.`)).toBeInTheDocument();
        expect(screen.queryByText(`SELECT generated_${role}-template_matrix_sql FROM safe_scope`)).not.toBeInTheDocument();

        fireEvent.change(screen.getByLabelText("Free question"), {
          target: { value: question }
        });
        fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

        expect(await screen.findByText(`${role} matrix free query completed.`)).toBeInTheDocument();
        expect(screen.queryByText(`SELECT generated_${role}_matrix_sql FROM safe_scope`)).not.toBeInTheDocument();
        expect(screen.queryByText(`SELECT executed_${role}_matrix_sql FROM safe_scope`)).not.toBeInTheDocument();
        expect(screen.queryByText(`matrix-provider-${role}`)).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole("tab", { name: "Diagnostics" }));
        const diagnosticsPanel = screen.getByRole("tabpanel", { name: "Diagnostics" });
        expect(within(diagnosticsPanel).getByText(`matrix-provider-${role}`)).toBeInTheDocument();
        expect(within(diagnosticsPanel).getByText(`matrix-model-${role}`)).toBeInTheDocument();
        expect(within(diagnosticsPanel).getByText(`matrix-template-${role}`)).toBeInTheDocument();
        expect(within(diagnosticsPanel).getByText("Valid")).toBeInTheDocument();
        expect(within(diagnosticsPanel).getAllByText("succeeded").length).toBeGreaterThan(0);
        expect(within(diagnosticsPanel).getByText("matrix_original_error")).toBeInTheDocument();
        expect(within(diagnosticsPanel).queryByText(`SELECT metadata_generated_${role}`)).not.toBeInTheDocument();
        expect(within(diagnosticsPanel).queryByText(`SELECT metadata_executed_${role}`)).not.toBeInTheDocument();
        expect(within(diagnosticsPanel).queryByText(`SELECT correction_${role}`)).not.toBeInTheDocument();
        expect(screen.queryByText(`SELECT generated_${role}_matrix_sql FROM safe_scope`)).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole("tab", { name: "SQL" }));
        expect(screen.getByText(`SELECT generated_${role}_matrix_sql FROM safe_scope`)).toBeInTheDocument();
        expect(screen.getByText(`SELECT executed_${role}_matrix_sql FROM safe_scope`)).toBeInTheDocument();

        fireEvent.click(screen.getByRole("tab", { name: "Results" }));
        expect(screen.queryByText(`SELECT generated_${role}_matrix_sql FROM safe_scope`)).not.toBeInTheDocument();
        expect(fetchMock).toHaveBeenNthCalledWith(
          4,
          "http://localhost:8000/api/v1/queries/run",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({
              question
            })
          })
        );
        expect(fetchMock).toHaveBeenCalledTimes(4);
      }
    );
  });

  it("prevents free query submit without CSRF", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.change(await screen.findByLabelText("Free question"), {
      target: { value: "Show open support tickets." }
    });

    expect(screen.getByRole("button", { name: "Run free query" })).toBeDisabled();
    expect(
      screen.getByText("Refresh your session before running a free query.")
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expectNoQueryRun(fetchMock);
  });

  it("keeps the free query submit disabled while running", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(successResponse(demoManager))
      .mockResolvedValueOnce(successResponse(askDataTemplates))
      .mockReturnValueOnce(new Promise(() => undefined));
    vi.stubGlobal("fetch", fetchMock);

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    fireEvent.change(await screen.findByLabelText("Free question"), {
      target: { value: "Show stale devices." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Run free query" }));

    expect(await screen.findByText("Running free query...")).toBeInTheDocument();
    const runningButton = screen.getByRole("button", { name: "Running query..." });
    expect(runningButton).toBeDisabled();
    fireEvent.click(runningButton);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders clarification and submits a revised manager question", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          queryRunId: "query run/id",
          status: "clarification_required",
          message: "Which inactive asset type should QueryOps use?",
          columns: [],
          rows: [],
          rowCount: 0,
          clarificationRequired: true,
          generatedSql: "SELECT clarification_hidden_sql",
          executedSql: "SELECT clarification_hidden_sql"
        })
      ),
      successResponse(
        backendQueryRunResult({
          message: "Clarified query completed.",
          columns: ["asset_type", "inactive_count"],
          rows: [
            {
              asset_type: "users",
              inactive_count: 7
            }
          ],
          generatedSql: "SELECT clarified_hidden_sql",
          executedSql: "SELECT clarified_hidden_sql"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    const clarificationPanel = await screen.findByLabelText("Clarification required");
    expect(
      within(clarificationPanel).getByText("Which inactive asset type should QueryOps use?")
    ).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Query results" })).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT clarification_hidden_sql")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit clarification" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Revised question"), {
      target: { value: "Show inactive users, not devices." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit clarification" }));

    expect(await screen.findByText("Clarified query completed.")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Query results" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "users" })).toBeInTheDocument();
    expect(screen.queryByText("SELECT clarified_hidden_sql")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "http://localhost:8000/api/v1/queries/query%20run%2Fid/clarify",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-from-cookie"
        }),
        body: JSON.stringify({
          question: "Show inactive users, not devices."
        })
      })
    );
  });

  it("keeps demo user clarification in template-only mode", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoUser),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          status: "clarification_required",
          message: "Which license timeframe should QueryOps use?",
          columns: [],
          rows: [],
          rowCount: 0,
          clarificationRequired: true,
          metadata: {
            provider: "hidden-user-clarification-provider",
            model: "hidden-user-clarification-model",
            validation: {
              valid: true,
              error_code: null
            },
            execution: {
              status: "clarification_required",
              error_code: null,
              row_count: 0,
              duration_ms: 0,
              truncated: false
            }
          },
          generatedSql: "SELECT user_clarification_hidden_sql",
          executedSql: "SELECT user_clarification_hidden_sql"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    const clarificationPanel = await screen.findByLabelText("Clarification required");
    expect(
      within(clarificationPanel).getByText("Which license timeframe should QueryOps use?")
    ).toBeInTheDocument();
    expect(
      within(clarificationPanel).getByText(/Choose a different approved template/i)
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Revised question")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "SQL" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT user_clarification_hidden_sql")).not.toBeInTheDocument();
    expect(screen.queryByText("hidden-user-clarification-provider")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it.each([
    ["demo analyst", demoAnalyst, "Show inactive privileged users."],
    ["demo admin", demoAdmin, "Show inactive accounts globally."]
  ])("lets %s submit clarification", async (_label, user, revisedQuestion) => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(user),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          queryRunId: `${user.role}-clarify-id`,
          status: "clarification_required",
          message: "Clarify which inactive records to inspect.",
          columns: [],
          rows: [],
          rowCount: 0,
          clarificationRequired: true
        })
      ),
      successResponse(
        backendQueryRunResult({
          message: "Clarification completed.",
          columns: ["record_type"],
          rows: [
            {
              record_type: user.role
            }
          ],
          generatedSql: `SELECT ${user.role}_clarification_generated_sql`,
          executedSql: `SELECT ${user.role}_clarification_executed_sql`
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    fireEvent.change(await screen.findByLabelText("Revised question"), {
      target: { value: revisedQuestion }
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit clarification" }));

    expect(await screen.findByText("Clarification completed.")).toBeInTheDocument();
    expect(screen.queryByText(`SELECT ${user.role}_clarification_generated_sql`)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "SQL" }));
    expect(screen.getByText(`SELECT ${user.role}_clarification_generated_sql`)).toBeInTheDocument();
    expect(screen.getByText(`SELECT ${user.role}_clarification_executed_sql`)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      `http://localhost:8000/api/v1/queries/${user.role}-clarify-id/clarify`,
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-CSRF-Token": "csrf-from-cookie"
        }),
        body: JSON.stringify({
          question: revisedQuestion
        })
      })
    );
  });

  it("prevents clarification submit when the query run id is missing", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          queryRunId: null,
          status: "clarification_required",
          message: "QueryOps needs a more specific question.",
          columns: [],
          rows: [],
          rowCount: 0,
          clarificationRequired: true
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    fireEvent.change(await screen.findByLabelText("Revised question"), {
      target: { value: "Use inactive users." }
    });

    expect(screen.getByRole("button", { name: "Submit clarification" })).toBeDisabled();
    expect(
      screen.getByText("This clarification cannot be continued. Run a new query instead.")
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("prevents clarification submit when the CSRF token is missing", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          queryRunId: "missing-csrf-query-id",
          status: "clarification_required",
          message: "QueryOps needs one more detail.",
          columns: [],
          rows: [],
          rowCount: 0,
          clarificationRequired: true
        })
      )
    );

    renderAskDataPageWithMutableCsrf(demoManager, "csrf-from-state");

    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));
    await screen.findByLabelText("Clarification required");
    fireEvent.click(screen.getByRole("button", { name: "Drop CSRF" }));
    fireEvent.change(screen.getByLabelText("Revised question"), {
      target: { value: "Use inactive users." }
    });

    expect(screen.getByRole("button", { name: "Submit clarification" })).toBeDisabled();
    expect(
      screen.getByText("Refresh your session before submitting clarification.")
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("renders clarification API errors safely", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          queryRunId: "clarify-error-id",
          status: "clarification_required",
          message: "QueryOps needs one more detail.",
          columns: [],
          rows: [],
          rowCount: 0,
          clarificationRequired: true
        })
      ),
      errorResponse("CLARIFICATION_FAILED", 500, "Clarification could not be run safely.")
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run selected template" }));

    fireEvent.change(await screen.findByLabelText("Revised question"), {
      target: { value: "Use inactive users." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit clarification" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Clarification could not be run safely."
    );
    expect(screen.queryByText("CLARIFICATION_FAILED")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("renders query template loading errors safely", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      errorResponse(
        "QUERY_TEMPLATES_UNAVAILABLE",
        500,
        "Templates are temporarily unavailable."
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Templates are temporarily unavailable."
    );
    expect(screen.queryByText("unused_licenses_department")).not.toBeInTheDocument();
    expectNoQueryRun(fetchMock);
  });

  it("renders an empty state when no query templates are returned", async () => {
    const fetchMock = stubFetchSequence(successResponse(demoManager), successResponse([]));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    expect(
      await screen.findByText("No query templates are available yet.")
    ).toBeInTheDocument();
    expectNoQueryRun(fetchMock);
  });

  it("renders template-only Ask Data mode for demo user while loading templates", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoUser),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    expect(
      await screen.findByRole("heading", { name: "Ask Data" })
    ).toBeInTheDocument();
    expect(screen.getAllByText("Template-only mode").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/Selected templates can be used here/i).length
    ).toBeGreaterThan(0);
    expect((await screen.findAllByText("Unused paid licenses")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Results" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Summary" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "SQL" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
    expectNoQueryRun(fetchMock);
  });

  it("allows demo user to run a selected template without exposing SQL", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoUser),
      successResponse(askDataTemplates),
      successResponse(
        backendQueryRunResult({
          message: "User template query completed.",
          generatedSql: "SELECT hidden_user_sql",
          executedSql: "SELECT hidden_user_sql"
        })
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    expect((await screen.findAllByText("Unused paid licenses")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run selected template" }));

    expect(await screen.findByText("User template query completed.")).toBeInTheDocument();
    expect(screen.queryByText("SELECT hidden_user_sql")).not.toBeInTheDocument();
    expect(screen.queryByText("Generated SQL")).not.toBeInTheDocument();
    expect(screen.queryByText("Executed SQL")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "SQL" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders a live free-query composer for demo manager without technical details", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    const workspaceRegion = await screen.findByRole("region", {
      name: "Ask Data command workspace"
    });
    expect(within(workspaceRegion).getByLabelText("Free question")).not.toBeDisabled();
    expect(
      within(workspaceRegion).getByRole("button", { name: "Run free query" })
    ).toBeDisabled();
    expect(screen.queryByText("Technical capability")).not.toBeInTheDocument();
    expect(within(workspaceRegion).getByRole("tab", { name: "Results" })).toBeInTheDocument();
    expect(within(workspaceRegion).getByRole("tab", { name: "Summary" })).toBeInTheDocument();
    expect(within(workspaceRegion).queryByRole("tab", { name: "SQL" })).not.toBeInTheDocument();
    expect(
      within(workspaceRegion).queryByRole("tab", { name: "Diagnostics" })
    ).not.toBeInTheDocument();
    expectNoQueryRun(fetchMock);
  });

  it("renders role-gated SQL and diagnostics tab shells for demo analyst", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoAnalyst),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    const workspaceRegion = await screen.findByRole("region", {
      name: "Ask Data command workspace"
    });
    expect(within(workspaceRegion).getByRole("tab", { name: "Results" })).toBeInTheDocument();
    expect(within(workspaceRegion).getByRole("tab", { name: "Summary" })).toBeInTheDocument();
    expect(within(workspaceRegion).getByRole("tab", { name: "SQL" })).toBeInTheDocument();
    expect(
      within(workspaceRegion).getByRole("tab", { name: "Diagnostics" })
    ).toBeInTheDocument();
    expect(screen.queryByText("Technical capability")).not.toBeInTheDocument();
    expectNoQueryRun(fetchMock);
  });

  it("renders the admin global Ask Data shell indicator", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoAdmin),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    expect(await screen.findByText(/Admin global scope indicator/i)).toBeInTheDocument();
    expect(screen.getAllByText(/backend authorization/i).length).toBeGreaterThan(0);
    const workspaceRegion = screen.getByRole("region", {
      name: "Ask Data command workspace"
    });
    expect(within(workspaceRegion).getByRole("tab", { name: "SQL" })).toBeInTheDocument();
    expect(
      within(workspaceRegion).getByRole("tab", { name: "Diagnostics" })
    ).toBeInTheDocument();
    expectNoQueryRun(fetchMock);
  });

  it("renders the focused Ask Data command workspace layout", async () => {
    const fetchMock = stubFetchSequence(
      successResponse(demoManager),
      successResponse(askDataTemplates)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    const templateRegion = await screen.findByRole("region", {
      name: "Template catalog"
    });
    expect(
      within(templateRegion).getByRole("heading", { name: "Template catalog" })
    ).toBeInTheDocument();
    expect(within(templateRegion).getByRole("button", { name: "Licenses" })).toBeInTheDocument();
    expect(within(templateRegion).getByRole("button", { name: "Security" })).toBeInTheDocument();
    expect(
      within(templateRegion).getByRole("button", { name: /Unused paid licenses/i })
    ).toBeInTheDocument();
    expect(
      within(templateRegion).getByRole("button", { name: /Security events/i })
    ).toBeInTheDocument();
    expect(
      within(templateRegion).getByLabelText("Selected template details")
    ).toBeInTheDocument();

    const workspaceRegion = screen.getByRole("region", {
      name: "Ask Data command workspace"
    });
    expect(
      within(workspaceRegion).getByRole("heading", { name: "Ask a question" })
    ).toBeInTheDocument();
    expect(
      within(workspaceRegion).getByRole("region", { name: "Result workspace" })
    ).toBeInTheDocument();
    expect(
      within(workspaceRegion).getAllByText(/Run a selected template or ask a free-form question/i)
        .length
    ).toBeGreaterThan(0);
    expect(within(workspaceRegion).queryByText("Query workspace")).not.toBeInTheDocument();
    expect(within(workspaceRegion).queryByText("Results and context")).not.toBeInTheDocument();

    const insightRegion = screen.getByRole("region", {
      name: "Ask Data insights"
    });
    const insightToggle = within(insightRegion).getByRole("button", {
      name: "Insights & next steps"
    });
    expect(insightToggle).toHaveAttribute("aria-expanded", "false");
    expect(
      within(insightRegion).queryByRole("heading", { name: "Insights" })
    ).not.toBeInTheDocument();
    openInsightsPanel(insightRegion);
    expect(insightToggle).toHaveAttribute("aria-expanded", "true");
    expect(
      within(insightRegion).getByRole("heading", { name: "Insights" })
    ).toBeInTheDocument();
    expect(within(insightRegion).getByText("Suggested Action")).toBeInTheDocument();
    expect(
      within(insightRegion).getByRole("button", { name: "Save as Card" })
    ).toBeDisabled();
    expect(
      within(insightRegion).getByText(/later dashboards\/cards milestone/i)
    ).toBeInTheDocument();
    expect(
      within(insightRegion).getByRole("button", { name: "CSV Export" })
    ).toBeDisabled();
    expect(
      within(insightRegion).getByText(/later export milestone/i)
    ).toBeInTheDocument();
    expect(
      within(insightRegion).getByRole("button", { name: "Preview Action" })
    ).toBeDisabled();
    expect(
      within(insightRegion).getByText(/later actions milestone/i)
    ).toBeInTheDocument();
    expectNoQueryRun(fetchMock);
  });

  it("shows analyst technical navigation without admin navigation", async () => {
    stubFetchSequence(successResponse(demoAnalyst));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    expect(within(nav).getByRole("button", { name: "Ask Data" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Query History" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "SQL / Technical" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Department Dashboards" })).toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Role Requests" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Admin Console" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Users" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Audit" })).not.toBeInTheDocument();
  });

  it("shows admin navigation for demo admin", async () => {
    stubFetchSequence(successResponse(demoAdmin));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    expect(within(nav).getByRole("button", { name: "Ask Data" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Role Requests" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Admin Console" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Users" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Audit" })).toBeInTheDocument();
  });

  it("opens planned workspace pages from the sidebar without real feature behavior", async () => {
    const fetchMock = stubFetchSequence(successResponse(demoAnalyst));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "SQL / Technical" }));

    const workspace = await screen.findByRole("region", {
      name: "SQL / Technical planned workspace"
    });
    expect(
      within(workspace).getByRole("heading", { name: "SQL / Technical" })
    ).toBeInTheDocument();
    expect(within(workspace).getByText("Planned workspace")).toBeInTheDocument();
    expect(
      within(workspace).getByText(/Technical details remain role-gated and contained inside Ask Data result tabs/i)
    ).toBeInTheDocument();
    expect(
      within(workspace).getByRole("button", { name: "Open technical console" })
    ).toBeDisabled();
    expect(
      within(workspace).getByRole("button", { name: "Export technical report" })
    ).toBeDisabled();
    expect(within(workspace).queryByText("Generated SQL")).not.toBeInTheDocument();
    expect(within(workspace).queryByText("Executed SQL")).not.toBeInTheDocument();
    expect(within(workspace).queryByText(/SELECT /i)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("logs out with the stored CSRF token and returns to the demo login screen", async () => {
    const fetchMock = stubFetchSequence(
      errorResponse("UNAUTHORIZED", 401),
      successResponse({
        user: demoManager,
        requires_onboarding: false,
        csrf_token: "csrf-from-login"
      }),
      successResponse({ ok: true })
    );

    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /demo manager/i }));

    expect(
      await screen.findByRole("heading", { name: "Templates" })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(
      await screen.findByRole("heading", { name: "Choose a demo profile" })
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/v1/auth/logout",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({
          "X-CSRF-Token": "csrf-from-login"
        })
      })
    );
  });

  it("shows a logout error and keeps the authenticated app visible when logout fails", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    stubFetchSequence(
      successResponse(demoManager),
      errorResponse("CSRF_TOKEN_INVALID", 403, "Logout failed. Try again.")
    );

    renderApp();

    expect(
      await screen.findByRole("heading", { name: "Templates" })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Logout failed. Try again."
    );
    expect(screen.getByText("demo.manager@queryops.local")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Choose a demo profile" })
    ).not.toBeInTheDocument();
  });

  it("renders the role upgrade request form and current request statuses", async () => {
    const existingRequest = backendRoleRequest({
      id: "request-id",
      requestedRole: "analyst",
      status: "pending",
      reason: "I need SQL-visible access for Sales reviews."
    });
    const fetchMock = stubFetchSequence(
      successResponse(demoUser),
      successResponse([existingRequest])
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Upgrade" }));

    expect(
      await screen.findByRole("heading", { name: "Request Role Upgrade" })
    ).toBeInTheDocument();
    const requestedRoleSelect = screen.getByLabelText("Requested role");
    expect(requestedRoleSelect).toBeInTheDocument();
    expect(within(requestedRoleSelect).getByRole("option", { name: "Manager" })).toBeInTheDocument();
    expect(within(requestedRoleSelect).getByRole("option", { name: "Analyst" })).toBeInTheDocument();
    expect(within(requestedRoleSelect).getByRole("option", { name: "Admin" })).toBeInTheDocument();
    expect(screen.getByLabelText("Reason")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit request" })).toBeInTheDocument();
    expect(screen.getByText("Admin approval is required.")).toBeInTheDocument();
    expect(
      within(screen.getByRole("list")).getByRole("heading", { name: "Analyst" })
    ).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(
      screen.getByText("I need SQL-visible access for Sales reviews.")
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/role-requests/my",
      expect.objectContaining({
        method: "GET",
        credentials: "include"
      })
    );
  });

  it("submits a role upgrade request with the stored CSRF token", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const createdRequest = backendRoleRequest({
      id: "created-request-id",
      requestedRole: "analyst",
      status: "pending",
      reason: "I need SQL-visible access for Sales reviews."
    });
    const fetchMock = stubFetchSequence(
      successResponse(demoUser),
      successResponse([]),
      successResponse(createdRequest)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Upgrade" }));
    await screen.findByRole("heading", { name: "Request Role Upgrade" });

    fireEvent.change(screen.getByLabelText("Requested role"), {
      target: { value: "analyst" }
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "I need SQL-visible access for Sales reviews." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));

    expect(
      await screen.findByText("Role upgrade request submitted.")
    ).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/v1/role-requests",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-from-cookie"
        }),
        body: JSON.stringify({
          requested_role: "analyst",
          reason: "I need SQL-visible access for Sales reviews."
        })
      })
    );
  });

  it("shows role request validation and backend errors", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    stubFetchSequence(
      successResponse(demoUser),
      successResponse([]),
      errorResponse(
        "PENDING_ROLE_REQUEST_EXISTS",
        409,
        "You already have a pending role upgrade request."
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Upgrade" }));
    await screen.findByRole("heading", { name: "Request Role Upgrade" });

    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter a reason for the role upgrade request."
    );

    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "I need broader workspace access." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You already have a pending role upgrade request."
    );
  });

  it("shows a loading state while own role requests are loading", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(successResponse(demoUser))
      .mockReturnValueOnce(new Promise(() => undefined));
    vi.stubGlobal("fetch", fetchMock);

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Upgrade" }));

    expect(await screen.findByText("Loading role requests...")).toBeInTheDocument();
  });

  it("shows an error when own role requests cannot be loaded", async () => {
    stubFetchSequence(
      successResponse(demoUser),
      errorResponse("UNAUTHORIZED", 401, "Authentication is required.")
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Upgrade" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Authentication is required."
    );
  });

  it("hides the current manager role from the upgrade options", async () => {
    stubFetchSequence(successResponse(demoManager), successResponse([]));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Upgrade" }));

    const requestedRoleSelect = await screen.findByLabelText("Requested role");
    expect(
      within(requestedRoleSelect).queryByRole("option", { name: "Manager" })
    ).not.toBeInTheDocument();
    expect(
      within(requestedRoleSelect).getByRole("option", { name: "Analyst" })
    ).toBeInTheDocument();
    expect(
      within(requestedRoleSelect).getByRole("option", { name: "Admin" })
    ).toBeInTheDocument();
  });

  it("only offers admin as an upgrade option for analysts", async () => {
    stubFetchSequence(successResponse(demoAnalyst), successResponse([]));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Upgrade" }));

    const requestedRoleSelect = await screen.findByLabelText("Requested role");
    expect(
      within(requestedRoleSelect).queryByRole("option", { name: "Manager" })
    ).not.toBeInTheDocument();
    expect(
      within(requestedRoleSelect).queryByRole("option", { name: "Analyst" })
    ).not.toBeInTheDocument();
    expect(
      within(requestedRoleSelect).getByRole("option", { name: "Admin" })
    ).toBeInTheDocument();
  });

  it("does not render a submit-able role upgrade form for admins", async () => {
    stubFetchSequence(successResponse(demoAdmin), successResponse([]));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Upgrade" }));

    expect(
      await screen.findByText("Admin already has the highest role.")
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Requested role")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Reason")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit request" })
    ).not.toBeInTheDocument();
  });

  it("loads and renders admin role upgrade requests for admins", async () => {
    const pendingRequest = backendRoleRequest({
      id: "pending-request-id",
      requester: {
        id: "requester-id",
        email: "demo.user@queryops.local",
        fullName: "Demo User"
      },
      requestedRole: "manager",
      status: "pending",
      reason: "I need department-level access for Sales reviews."
    });
    const fetchMock = stubFetchSequence(
      successResponse(demoAdmin),
      successResponse([pendingRequest])
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Requests" }));

    expect(
      await screen.findByRole("heading", { name: "Admin Role Requests" })
    ).toBeInTheDocument();
    expect(screen.getByText("Demo User")).toBeInTheDocument();
    expect(screen.getByText("demo.user@queryops.local")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByLabelText("Decision reason for Demo User")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Approve role request from Demo User" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reject role request from Demo User" })
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/admin/role-requests",
      expect.objectContaining({
        method: "GET",
        credentials: "include"
      })
    );
  });

  it("approves an admin role request with a decision reason and CSRF token", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const pendingRequest = backendRoleRequest({
      id: "pending-request-id",
      requester: {
        id: "requester-id",
        email: "demo.user@queryops.local",
        fullName: "Demo User"
      },
      requestedRole: "manager",
      status: "pending",
      reason: "I need department-level access for Sales reviews."
    });
    const approvedRequest = backendRoleRequest({
      id: "pending-request-id",
      requester: {
        id: "requester-id",
        email: "demo.user@queryops.local",
        fullName: "Demo User"
      },
      requestedRole: "manager",
      status: "approved",
      reason: "I need department-level access for Sales reviews.",
      decisionReason: "Approved for department reporting."
    });
    const fetchMock = stubFetchSequence(
      successResponse(demoAdmin),
      successResponse([pendingRequest]),
      successResponse(approvedRequest)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Requests" }));
    await screen.findByRole("heading", { name: "Admin Role Requests" });

    fireEvent.change(screen.getByLabelText("Decision reason for Demo User"), {
      target: { value: "Approved for department reporting." }
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Approve role request from Demo User" })
    );

    expect(await screen.findByText("Role request approved.")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Approved for department reporting.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve role request from Demo User" })
    ).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/v1/admin/role-requests/pending-request-id/approve",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-from-cookie"
        }),
        body: JSON.stringify({
          decision_reason: "Approved for department reporting."
        })
      })
    );
  });

  it("rejects an admin role request with a decision reason and CSRF token", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const pendingRequest = backendRoleRequest({
      id: "pending-request-id",
      requester: {
        id: "requester-id",
        email: "demo.user@queryops.local",
        fullName: "Demo User"
      },
      requestedRole: "analyst",
      status: "pending",
      reason: "I need SQL-visible access."
    });
    const rejectedRequest = backendRoleRequest({
      id: "pending-request-id",
      requester: {
        id: "requester-id",
        email: "demo.user@queryops.local",
        fullName: "Demo User"
      },
      requestedRole: "analyst",
      status: "rejected",
      reason: "I need SQL-visible access.",
      decisionReason: "Not enough business justification yet."
    });
    const fetchMock = stubFetchSequence(
      successResponse(demoAdmin),
      successResponse([pendingRequest]),
      successResponse(rejectedRequest)
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Requests" }));
    await screen.findByRole("heading", { name: "Admin Role Requests" });

    fireEvent.change(screen.getByLabelText("Decision reason for Demo User"), {
      target: { value: "Not enough business justification yet." }
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Reject role request from Demo User" })
    );

    expect(await screen.findByText("Role request rejected.")).toBeInTheDocument();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("Not enough business justification yet.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/v1/admin/role-requests/pending-request-id/reject",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-from-cookie"
        }),
        body: JSON.stringify({
          decision_reason: "Not enough business justification yet."
        })
      })
    );
  });

  it("shows admin role request load and decision errors", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    const pendingRequest = backendRoleRequest({
      id: "pending-request-id",
      requester: {
        id: "requester-id",
        email: "demo.user@queryops.local",
        fullName: "Demo User"
      },
      requestedRole: "admin",
      status: "pending",
      reason: "I need global administration access."
    });
    stubFetchSequence(
      successResponse(demoAdmin),
      successResponse([pendingRequest]),
      errorResponse(
        "ROLE_REQUEST_ALREADY_PROCESSED",
        409,
        "This role request has already been processed."
      )
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Requests" }));
    await screen.findByRole("heading", { name: "Admin Role Requests" });

    fireEvent.click(
      screen.getByRole("button", { name: "Approve role request from Demo User" })
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter a decision reason before approving or rejecting."
    );

    fireEvent.change(screen.getByLabelText("Decision reason for Demo User"), {
      target: { value: "Approved for administration coverage." }
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Approve role request from Demo User" })
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This role request has already been processed."
    );
  });

  it("shows an error when admin role requests cannot be loaded", async () => {
    stubFetchSequence(
      successResponse(demoAdmin),
      errorResponse("ADMIN_ROLE_REQUESTS_FAILED", 500, "Role requests unavailable.")
    );

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Requests" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Role requests unavailable."
    );
  });

  it("does not expose approve or reject controls for processed role requests", async () => {
    const approvedRequest = backendRoleRequest({
      id: "approved-request-id",
      requester: {
        id: "requester-id",
        email: "demo.user@queryops.local",
        fullName: "Demo User"
      },
      requestedRole: "manager",
      status: "approved",
      reason: "I need department-level access.",
      decisionReason: "Approved for reporting coverage."
    });
    stubFetchSequence(successResponse(demoAdmin), successResponse([approvedRequest]));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Role Requests" }));

    expect(await screen.findByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Approved for reporting coverage.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve role request from Demo User" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reject role request from Demo User" })
    ).not.toBeInTheDocument();
  });
});

function renderApp() {
  render(
    <AuthProvider>
      <App />
    </AuthProvider>
  );
}

function stubSystemTheme(prefersDark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: prefersDark,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn()
    }))
  );
}

function renderAskDataPageWithMutableCsrf(
  user: ReturnType<typeof backendUser>,
  initialCsrfToken: string
) {
  function AskDataHarness() {
    const [csrfToken, setCsrfToken] = useState<string | null>(initialCsrfToken);

    return (
      <>
        <button type="button" onClick={() => setCsrfToken(null)}>
          Drop CSRF
        </button>
        <AskDataPage user={mapBackendUserForAskData(user)} csrfToken={csrfToken} />
      </>
    );
  }

  render(<AskDataHarness />);
}

function mapBackendUserForAskData(user: ReturnType<typeof backendUser>): AuthUser {
  return {
    id: user.id,
    email: user.email,
    fullName: user.full_name,
    role: user.role as AuthUser["role"],
    departmentId: user.department_id,
    department: user.department,
    scopes: user.scopes.map((scope) => ({
      id: scope.id,
      type: scope.type,
      key: scope.key,
      displayName: scope.display_name,
      accessLevel: scope.access_level,
      isDefault: scope.is_default,
      departmentId: scope.department_id
    })),
    status: user.status,
    permissions: user.permissions as AuthUser["permissions"],
    authMode: user.auth_mode
  };
}

async function openAskData() {
  const nav = await screen.findByRole("navigation", {
    name: "Workspace navigation"
  });
  fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));
  await screen.findByRole("heading", { name: "Ask Data" });
  await screen.findByRole("region", { name: "Template catalog" });
}

function expectApprovedTemplatesVisible() {
  const templateRegion = screen.getByRole("region", {
    name: "Template catalog"
  });
  expect(
    within(templateRegion).getByRole("button", { name: /Unused paid licenses/i })
  ).toBeInTheDocument();
  expect(
    within(templateRegion).getByRole("button", { name: /Security events/i })
  ).toBeInTheDocument();
}

function expectFutureControlsDisabled() {
  const insightRegion = screen.getByRole("region", {
    name: "Ask Data insights"
  });
  openInsightsPanel(insightRegion);
  expect(
    within(insightRegion).getByRole("button", { name: "Save as Card" })
  ).toBeDisabled();
  expect(
    within(insightRegion).getByRole("button", { name: "CSV Export" })
  ).toBeDisabled();
  expect(
    within(insightRegion).getByRole("button", { name: "Preview Action" })
  ).toBeDisabled();
}

function openInsightsPanel(insightRegion: HTMLElement) {
  if (within(insightRegion).queryByRole("button", { name: "Save as Card" })) {
    return;
  }

  fireEvent.click(
    within(insightRegion).getByRole("button", { name: "Insights & next steps" })
  );
}

function expectSensitiveTechnicalFieldsHidden(role: string) {
  expect(screen.queryByRole("tab", { name: "SQL" })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
  expect(screen.queryByText("Generated SQL")).not.toBeInTheDocument();
  expect(screen.queryByText("Executed SQL")).not.toBeInTheDocument();
  expect(screen.queryByText("Provider")).not.toBeInTheDocument();
  expect(screen.queryByText("Model")).not.toBeInTheDocument();
  expect(screen.queryByText("Correction attempted")).not.toBeInTheDocument();
  expect(screen.queryByText(`matrix-provider-${role}`)).not.toBeInTheDocument();
  expect(screen.queryByText(`matrix-model-${role}`)).not.toBeInTheDocument();
  expect(screen.queryByText(`matrix-template-${role}`)).not.toBeInTheDocument();
  expect(screen.queryByText(`matrix_resource_${role}`)).not.toBeInTheDocument();
  expect(screen.queryByText("matrix_original_error")).not.toBeInTheDocument();
  expect(screen.queryByText(`SELECT generated_${role}_matrix_sql FROM safe_scope`)).not.toBeInTheDocument();
  expect(screen.queryByText(`SELECT executed_${role}_matrix_sql FROM safe_scope`)).not.toBeInTheDocument();
  expect(screen.queryByText(`SELECT metadata_generated_${role}`)).not.toBeInTheDocument();
  expect(screen.queryByText(`SELECT metadata_executed_${role}`)).not.toBeInTheDocument();
  expect(screen.queryByText(`SELECT validation_${role}`)).not.toBeInTheDocument();
  expect(screen.queryByText(`SELECT correction_${role}`)).not.toBeInTheDocument();
}

function backendUser({
  id,
  email,
  fullName,
  role,
  departmentId,
  departmentName,
  permissions
}: {
  id: string;
  email: string;
  fullName: string;
  role: string;
  departmentId: string;
  departmentName: string;
  permissions: string[];
}) {
  const isAdmin = role === "admin";
  const scopeType = isAdmin ? "global" : "department";
  const scopeKey = isAdmin ? "global" : departmentName.toLowerCase();
  const scopeName = isAdmin ? "Global" : departmentName;

  return {
    id,
    email,
    full_name: fullName,
    role,
    department_id: departmentId,
    department: {
      id: departmentId,
      name: departmentName
    },
    scopes: [
      {
        id: `${scopeKey}-scope-id`,
        type: scopeType,
        key: scopeKey,
        display_name: scopeName,
        access_level: isAdmin || role === "analyst" ? "manage" : "read",
        is_default: true,
        department_id: isAdmin ? null : departmentId
      }
    ],
    status: "active",
    permissions,
    auth_mode: "demo"
  };
}

function backendRoleRequest({
  id,
  requester = {
    id: "user-id",
    email: "demo.user@queryops.local",
    fullName: "Demo User"
  },
  requestedRole,
  status,
  reason,
  decisionReason = null
}: {
  id: string;
  requester?: {
    id: string;
    email: string;
    fullName: string;
  };
  requestedRole: string;
  status: string;
  reason: string;
  decisionReason?: string | null;
}) {
  return {
    id,
    requester: {
      id: requester.id,
      email: requester.email,
      full_name: requester.fullName
    },
    requested_role: requestedRole,
    requested_scope: {
      id: "sales-scope-id",
      type: "department",
      key: "sales",
      display_name: "Sales",
      access_level: "read",
      is_default: true,
      department_id: "sales-id"
    },
    status,
    reason,
    decision_reason: decisionReason,
    decided_by: null,
    decided_at: null,
    created_at: "2026-06-29T12:00:00Z",
    updated_at: "2026-06-29T12:00:00Z"
  };
}

function sensitiveQueryRunResult({
  message,
  role
}: {
  message: string;
  role: string;
}) {
  return backendQueryRunResult({
    queryRunId: `${role}-matrix-run-id`,
    message,
    rowCount: 1,
    durationMs: 25,
    warnings: [`Matrix safe warning for ${role}`],
    metadata: sensitiveQueryMetadata(role),
    generatedSql: `SELECT generated_${role}_matrix_sql FROM safe_scope`,
    executedSql: `SELECT executed_${role}_matrix_sql FROM safe_scope`
  });
}

function sensitiveQueryMetadata(role: string): Record<string, unknown> {
  return {
    provider: `matrix-provider-${role}`,
    model: `matrix-model-${role}`,
    template_id: `matrix-template-${role}`,
    scope_type: role.includes("admin") ? "global" : "department",
    referenced_tables: [`matrix_resource_${role}`],
    clarification_required: false,
    validation: {
      valid: true,
      error_code: null,
      generated_sql: `SELECT validation_${role}`
    },
    execution: {
      status: "succeeded",
      error_code: null,
      row_count: 1,
      duration_ms: 25,
      truncated: false,
      executed_sql: `SELECT metadata_executed_${role}`
    },
    self_correction: {
      attempted: true,
      succeeded: true,
      original_error_code: "matrix_original_error",
      final_error_code: null,
      generated_sql: `SELECT correction_${role}`
    },
    generated_sql: `SELECT metadata_generated_${role}`,
    executed_sql: `SELECT metadata_executed_${role}`
  };
}

function backendQueryTemplate({
  id,
  category,
  title,
  description,
  naturalLanguageQuestion,
  parameters = []
}: {
  id: string;
  category: string;
  title: string;
  description: string;
  naturalLanguageQuestion: string;
  parameters?: Array<{
    name: string;
    data_type: string;
    description: string;
    required: boolean;
    default: string | number | boolean | null;
  }>;
}) {
  return {
    id,
    title,
    description,
    domain: "it_operations",
    category,
    natural_language_question: naturalLanguageQuestion,
    parameters,
    scope_type: "department",
    required_permission: "can_use_query_templates"
  };
}

function backendQueryRunResult({
  queryRunId = "query-run-id",
  status = "succeeded",
  message,
  columns = ["product_name", "unused_count"],
  rows = [
    {
      product_name: "Microsoft 365 E5",
      unused_count: 12
    }
  ],
  rowCount = rows.length,
  durationMs = 42,
  truncated = false,
  warnings = [],
  clarificationRequired = false,
  metadata = {
    template_id: "unused_licenses_department",
    execution: {
      status,
      error_code: null,
      row_count: rowCount,
      duration_ms: durationMs,
      truncated
    }
  },
  generatedSql = null,
  executedSql = null
}: {
  queryRunId?: string | null;
  status?: string;
  message: string;
  columns?: string[];
  rows?: Array<Record<string, unknown>>;
  rowCount?: number;
  durationMs?: number;
  truncated?: boolean;
  warnings?: string[];
  clarificationRequired?: boolean;
  metadata?: Record<string, unknown>;
  generatedSql?: string | null;
  executedSql?: string | null;
}) {
  return {
    query_run_id: queryRunId,
    status,
    columns,
    rows,
    row_count: rowCount,
    duration_ms: durationMs,
    truncated,
    message,
    warnings,
    clarification_required: clarificationRequired,
    metadata,
    generated_sql: generatedSql,
    executed_sql: executedSql
  };
}

function expectNoQueryRun(fetchMock: ReturnType<typeof vi.fn>) {
  expect(
    fetchMock.mock.calls.some(([url]) =>
      String(url).includes("/api/v1/queries/run")
    )
  ).toBe(false);
}

function stubFetchSequence(...responses: Array<ReturnType<typeof jsonResponse>>) {
  const fetchMock = vi.fn();
  for (const response of responses) {
    fetchMock.mockResolvedValueOnce(response);
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function successResponse(data: unknown) {
  return jsonResponse({
    ok: true,
    status: 200,
    payload: {
      data,
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T12:00:00Z"
      }
    }
  });
}

function errorResponse(code: string, status: number, message = "Authentication is required.") {
  return jsonResponse({
    ok: false,
    status,
    payload: {
      error: {
        code,
        message,
        details: {},
        request_id: "request-id"
      }
    }
  });
}

function jsonResponse({
  ok,
  status,
  payload
}: {
  ok: boolean;
  status: number;
  payload: unknown;
}) {
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(payload)
  };
}

function clearCsrfCookie() {
  document.cookie = "qo_csrf=; max-age=0; path=/";
}
