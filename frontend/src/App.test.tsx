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

  it("renders the Ask Data page shell from workspace navigation", async () => {
    const fetchMock = stubFetchSequence(successResponse(demoManager));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    expect(
      await screen.findByRole("heading", { name: "Ask Data" })
    ).toBeInTheDocument();
    expect(screen.getByText("Static UI shell")).toBeInTheDocument();
    expect(
      screen.getAllByText(/Query integration comes in the next PR/i).length
    ).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renders template-only Ask Data mode for demo user without extra API calls", async () => {
    const fetchMock = stubFetchSequence(successResponse(demoUser));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    expect(
      await screen.findByRole("heading", { name: "Ask Data" })
    ).toBeInTheDocument();
    expect(screen.getByText("Template-only mode")).toBeInTheDocument();
    expect(
      screen.getByText(/Use approved templates when query integration arrives/i)
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/free query/i)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renders the static Ask Data split workspace layout", async () => {
    const fetchMock = stubFetchSequence(successResponse(demoManager));

    renderApp();

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    fireEvent.click(within(nav).getByRole("button", { name: "Ask Data" }));

    const templateRegion = await screen.findByRole("region", {
      name: "Ask Data templates"
    });
    expect(
      within(templateRegion).getByRole("heading", { name: "Templates" })
    ).toBeInTheDocument();
    expect(within(templateRegion).getByText("Unused licenses")).toBeInTheDocument();
    expect(within(templateRegion).getByText("Inactive users")).toBeInTheDocument();
    expect(within(templateRegion).getByText("Security events")).toBeInTheDocument();

    const workspaceRegion = screen.getByRole("region", {
      name: "Ask Data workspace"
    });
    expect(
      within(workspaceRegion).getByRole("heading", { name: "Question composer" })
    ).toBeInTheDocument();
    expect(within(workspaceRegion).getByText("Result placeholder")).toBeInTheDocument();
    expect(
      within(workspaceRegion).getByText(/Query integration comes in the next PR/i)
    ).toBeInTheDocument();

    const insightRegion = screen.getByRole("region", {
      name: "Ask Data insights"
    });
    expect(
      within(insightRegion).getByRole("heading", { name: "Explanation" })
    ).toBeInTheDocument();
    expect(within(insightRegion).getByText("Suggested Action")).toBeInTheDocument();
    expect(within(insightRegion).getByText("Future status")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
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
