import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { AuthProvider } from "../auth/AuthProvider";

const manager = backendUser({
  role: "manager",
  permissions: [
    "can_use_query_templates",
    "can_run_free_query",
    "can_query_scoped_data",
    "can_create_personal_dashboard"
  ]
});

const admin = backendUser({
  role: "admin",
  permissions: [
    "can_use_query_templates",
    "can_query_global_data",
    "can_create_personal_dashboard",
    "can_approve_role_requests"
  ]
});

afterEach(() => {
  window.history.replaceState({}, "", "/");
  document.cookie = "qo_csrf=; max-age=0; path=/";
  vi.unstubAllGlobals();
});

describe("application routing", () => {
  it("redirects an unauthenticated protected route to login", async () => {
    installApiMock({ authenticatedUser: null });

    renderApp("/ask");

    expect(
      await screen.findByRole("heading", { name: "Choose a demo profile" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
  });

  it("redirects a successful login to My Dashboard", async () => {
    installApiMock({ authenticatedUser: null, loginUser: manager });

    renderApp("/login");
    fireEvent.click(await screen.findByRole("button", { name: /demo manager/i }));

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("redirects an authenticated login route to My Dashboard", async () => {
    installApiMock({ authenticatedUser: manager });

    renderApp("/login");

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("renders Ask Data from a direct URL", async () => {
    installApiMock({ authenticatedUser: manager });

    renderApp("/ask");

    expect(await screen.findByRole("heading", { name: "Ask Data" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/ask");
  });

  it("renders Profile from a direct URL", async () => {
    installApiMock({ authenticatedUser: manager });

    renderApp("/profile");

    expect(
      await screen.findByRole("heading", { name: "Request Role Upgrade" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/profile");
  });

  it("renders Role Requests for a user with its permission", async () => {
    installApiMock({ authenticatedUser: admin });

    renderApp("/admin/role-requests");

    expect(
      await screen.findByRole("heading", { name: "Admin Role Requests" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/admin/role-requests");
  });

  it("redirects a direct unauthorized Admin route without rendering it", async () => {
    installApiMock({ authenticatedUser: manager });

    renderApp("/admin/role-requests");

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Admin Role Requests" })
    ).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("redirects an unknown authenticated route to My Dashboard", async () => {
    installApiMock({ authenticatedUser: manager });

    renderApp("/not-a-real-route");

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("uses links so Browser Back and Forward restore routed screens", async () => {
    installApiMock({ authenticatedUser: manager });

    renderApp("/");
    fireEvent.click(await screen.findByRole("link", { name: "Ask Data" }));
    expect(await screen.findByRole("heading", { name: "Ask Data" })).toBeInTheDocument();

    window.history.back();
    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(await screen.findByRole("region", { name: "My Dashboard" })).toBeInTheDocument();

    window.history.forward();
    await waitFor(() => expect(window.location.pathname).toBe("/ask"));
    expect(await screen.findByRole("heading", { name: "Ask Data" })).toBeInTheDocument();
  });
});

function renderApp(path: string) {
  window.history.replaceState({}, "", path);
  render(
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  );
}

function installApiMock({
  authenticatedUser,
  loginUser
}: {
  authenticatedUser: ReturnType<typeof backendUser> | null;
  loginUser?: ReturnType<typeof backendUser>;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/api/v1/auth/me")) {
        return authenticatedUser
          ? successResponse(authenticatedUser)
          : errorResponse("UNAUTHORIZED", 401);
      }

      if (url.endsWith("/api/v1/demo/login") && loginUser) {
        return successResponse({
          user: loginUser,
          requires_onboarding: false,
          csrf_token: "csrf-from-login"
        });
      }

      if (
        url.endsWith("/api/v1/dashboards/my") ||
        url.endsWith("/api/v1/query-templates") ||
        url.endsWith("/api/v1/role-requests/my") ||
        url.endsWith("/api/v1/admin/role-requests")
      ) {
        return successResponse([]);
      }

      throw new Error(`Unexpected request: ${url}`);
    })
  );
}

function backendUser({ role, permissions }: { role: string; permissions: string[] }) {
  const isAdmin = role === "admin";
  return {
    id: `${role}-id`,
    email: `demo.${role}@queryops.local`,
    full_name: `Demo ${role}`,
    role,
    department_id: "scope-id",
    department: { id: "scope-id", name: isAdmin ? "IT" : "Finance" },
    scopes: [
      {
        id: `${role}-scope-id`,
        type: isAdmin ? "global" : "department",
        key: isAdmin ? "global" : "finance",
        display_name: isAdmin ? "Global" : "Finance",
        access_level: isAdmin ? "manage" : "read",
        is_default: true,
        department_id: isAdmin ? null : "scope-id"
      }
    ],
    status: "active",
    permissions,
    auth_mode: "demo"
  };
}

function successResponse(data: unknown) {
  return jsonResponse(200, {
    data,
    meta: { request_id: "request-id", timestamp: "2026-07-13T12:00:00Z" }
  });
}

function errorResponse(code: string, status: number) {
  return jsonResponse(status, {
    error: {
      code,
      message: "Authentication is required.",
      details: {},
      request_id: "request-id"
    }
  });
}

function jsonResponse(status: number, payload: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(payload)
  };
}
