import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";

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
    "can_view_department_data",
    "can_create_personal_dashboard",
    "can_request_action",
    "can_view_department_evaluation"
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
    "can_view_department_data",
    "can_create_personal_dashboard",
    "can_request_action",
    "can_view_department_evaluation",
    "can_view_sql",
    "can_create_card",
    "can_create_department_dashboard",
    "can_manage_department_dashboard",
    "can_view_query_history_department",
    "can_view_department_audit",
    "can_approve_department_action"
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
    "can_query_global_data",
    "can_query_product_tables",
    "can_view_own_data",
    "can_view_department_data",
    "can_view_global_data",
    "can_view_sql",
    "can_view_query_history_department",
    "can_star_dashboard",
    "can_create_personal_dashboard",
    "can_create_department_dashboard",
    "can_create_global_dashboard",
    "can_manage_department_dashboard",
    "can_manage_global_dashboard",
    "can_create_card",
    "can_request_action",
    "can_approve_department_action",
    "can_approve_global_action",
    "can_approve_policy_override",
    "can_self_approve_admin_action",
    "can_manage_users",
    "can_disable_app_user",
    "can_downgrade_user_role",
    "can_approve_role_requests",
    "can_view_department_audit",
    "can_view_global_audit",
    "can_view_department_evaluation",
    "can_view_global_evaluation"
  ]
});

afterEach(() => {
  clearCsrfCookie();
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

  it("logs in as the selected demo user and renders the authenticated placeholder", async () => {
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
      await screen.findByRole("heading", { name: "Templates placeholder" })
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
      await screen.findByRole("heading", { name: "Templates placeholder" })
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Choose a demo profile" })).not.toBeInTheDocument();
    });
  });

  it("shows only common navigation for demo user", async () => {
    stubFetchSequence(successResponse(demoUser));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    expect(within(nav).getByRole("button", { name: "Templates" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "My Dashboard" })).toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Ask Data" })).not.toBeInTheDocument();
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
    expect(within(nav).queryByRole("button", { name: "Admin Console" })).not.toBeInTheDocument();
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
    expect(within(nav).getByRole("button", { name: "Admin Console" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Users" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Audit" })).toBeInTheDocument();
  });

  it("opens placeholder sections from the sidebar without real feature behavior", async () => {
    stubFetchSequence(successResponse(demoAnalyst));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "SQL / Technical" }));

    expect(
      await screen.findByRole("heading", { name: "SQL / Technical placeholder" })
    ).toBeInTheDocument();
    expect(screen.getByText("Placeholder only")).toBeInTheDocument();
    expect(
      screen.getByText(/No Query Engine, SQL execution, dashboards, actions, approvals, audit UI, or backend feature is implemented here/i)
    ).toBeInTheDocument();
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
      await screen.findByRole("heading", { name: "Templates placeholder" })
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
      await screen.findByRole("heading", { name: "Templates placeholder" })
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
});

function renderApp() {
  render(
    <AuthProvider>
      <App />
    </AuthProvider>
  );
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
    status: "active",
    permissions,
    auth_mode: "demo"
  };
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
