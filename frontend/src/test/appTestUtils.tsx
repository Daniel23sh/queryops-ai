import { render, type RenderResult } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";

import App from "../App";
import { ThemeProvider } from "../app/ThemeProvider";
import { AuthProvider } from "../auth/AuthProvider";

export const demoUser = backendUser({
  role: "user",
  scopeName: "Sales",
  permissions: ["can_use_query_templates", "can_star_dashboard", "can_view_own_data"]
});

export const demoManager = backendUser({
  role: "manager",
  scopeName: "Finance",
  permissions: [
    "can_use_query_templates",
    "can_run_free_query",
    "can_query_scoped_data",
    "can_view_scoped_data",
    "can_create_personal_dashboard",
    "can_star_dashboard",
    "can_view_own_data"
  ]
});

export const demoAnalyst = backendUser({
  role: "analyst",
  scopeName: "IT",
  permissions: [
    "can_use_query_templates",
    "can_run_free_query",
    "can_query_scoped_data",
    "can_view_scoped_data",
    "can_create_personal_dashboard",
    "can_create_card",
    "can_export_results",
    "can_view_sql",
    "can_star_dashboard",
    "can_view_own_data"
  ]
});

export const demoAdmin = backendUser({
  role: "admin",
  scopeName: "Global",
  permissions: [
    "can_use_query_templates",
    "can_run_free_query",
    "can_query_global_data",
    "can_view_global_data",
    "can_create_personal_dashboard",
    "can_create_card",
    "can_export_results",
    "can_view_sql",
    "can_approve_role_requests",
    "can_manage_users"
  ]
});

export type BackendUser = ReturnType<typeof backendUser>;
type MockResponse = ReturnType<typeof jsonResponse>;
type MockResult = MockResponse | Promise<MockResponse>;
type MockResolver = MockResult | (() => MockResult);
export type ApiRoutes = Record<string, MockResolver | MockResolver[]>;

export function renderAppAt(path = "/"): RenderResult {
  window.history.replaceState({}, "", path);
  return render(
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export function installApiMock(routes: ApiRoutes) {
  const queues = new Map(
    Object.entries(routes).map(([key, value]) => [key, Array.isArray(value) ? [...value] : [value]])
  );
  const fetchMock = vi.fn(
    (input: string | URL | Request, init?: RequestInit): Promise<MockResponse> => {
      const requestUrl = new URL(String(input), "http://localhost");
      const requestMethod = (
        init?.method ?? (input instanceof Request ? input.method : "GET")
      ).toUpperCase();
      const routeKey = `${requestMethod} ${requestUrl.pathname}`;
      const queue = queues.get(routeKey) ?? queues.get(requestUrl.pathname);
      const resolver = queue?.shift();

      if (!resolver) {
        return Promise.reject(new Error(`Unexpected request: ${routeKey}`));
      }

      const result = typeof resolver === "function" ? resolver() : resolver;
      return Promise.resolve(result);
    }
  );

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function authenticatedRoutes(
  user: BackendUser,
  routes: ApiRoutes = {}
): ApiRoutes {
  return {
    "GET /api/v1/auth/me": successResponse(user),
    ...routes
  };
}

export function successResponse(data: unknown) {
  return jsonResponse(200, {
    data,
    meta: {
      request_id: "request-id",
      timestamp: "2026-07-13T12:00:00Z"
    }
  });
}

export function errorResponse(
  code: string,
  status: number,
  message = "Authentication is required."
) {
  return jsonResponse(status, {
    error: {
      code,
      message,
      details: {},
      request_id: "request-id"
    }
  });
}

export function pendingResponse(): Promise<MockResponse> {
  return new Promise(() => undefined);
}

export function resetAppTestState() {
  document.cookie = "qo_csrf=; max-age=0; path=/";
  document.body.style.overflow = "";
  document.documentElement.classList.remove("dark");
  document.documentElement.removeAttribute("data-theme");
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
}

export function setCsrfCookie(value: string) {
  document.cookie = `qo_csrf=${encodeURIComponent(value)}; path=/`;
}

export function backendDashboard({
  id = "dashboard-id",
  title = "Operations review",
  cards = []
}: {
  id?: string;
  title?: string;
  cards?: Array<Record<string, unknown>>;
} = {}) {
  return {
    id,
    title,
    description: "Saved operational questions.",
    visibility_scope: "personal",
    department_id: null,
    is_archived: false,
    created_at: "2026-07-13T12:00:00Z",
    updated_at: "2026-07-13T12:00:00Z",
    cards
  };
}

export function backendDashboardCard({
  id = "card-id",
  dashboardId = "dashboard-id",
  title = "Open tickets"
}: {
  id?: string;
  dashboardId?: string;
  title?: string;
} = {}) {
  return {
    id,
    dashboard_id: dashboardId,
    saved_query_id: "saved-query-id",
    title,
    description: "Current scoped result.",
    card_type: "table",
    position: 0,
    layout: null,
    config: null,
    created_at: "2026-07-13T12:00:00Z",
    updated_at: "2026-07-13T12:00:00Z"
  };
}

export function backendQueryTemplate() {
  return {
    id: "unused_licenses_scope",
    title: "Unused paid licenses",
    description: "Find reclaimable paid licenses in the active scope.",
    domain: "it_operations",
    category: "Licenses",
    natural_language_question: "Show unused paid licenses in my scope.",
    parameters: [],
    scope_type: "department",
    required_permission: "can_use_query_templates"
  };
}

export function backendQueryResult({
  generatedSql = null,
  executedSql = null
}: {
  generatedSql?: string | null;
  executedSql?: string | null;
} = {}) {
  return {
    query_run_id: "query-run-id",
    status: "succeeded",
    columns: ["product_name", "unused_count"],
    rows: [{ product_name: "Microsoft 365 E5", unused_count: 12 }],
    row_count: 1,
    duration_ms: 42,
    truncated: false,
    message: "Found one reclaim opportunity.",
    warnings: [],
    clarification_required: false,
    metadata: {
      provider: "mock",
      model: "deterministic",
      template_id: "unused_licenses_scope",
      execution: {
        status: "succeeded",
        row_count: 1,
        duration_ms: 42,
        truncated: false
      }
    },
    generated_sql: generatedSql,
    executed_sql: executedSql
  };
}

export function backendRoleRequest({
  id = "role-request-id",
  status = "pending",
  requestedRole = "manager"
}: {
  id?: string;
  status?: string;
  requestedRole?: string;
} = {}) {
  return {
    id,
    requester: {
      id: "user-id",
      email: "demo.user@queryops.local",
      full_name: "Demo User"
    },
    requested_role: requestedRole,
    requested_scope: null,
    status,
    reason: "I need broader reporting access.",
    decision_reason: null,
    decided_by: null,
    decided_at: null,
    created_at: "2026-07-13T12:00:00Z",
    updated_at: "2026-07-13T12:00:00Z"
  };
}

function backendUser({
  role,
  scopeName,
  permissions
}: {
  role: "user" | "manager" | "analyst" | "admin";
  scopeName: string;
  permissions: string[];
}) {
  const isAdmin = role === "admin";
  const scopeKey = scopeName.toLowerCase();

  return {
    id: `${role}-id`,
    email: `demo.${role}@queryops.local`,
    full_name: `Demo ${role.charAt(0).toUpperCase()}${role.slice(1)}`,
    role,
    department_id: isAdmin ? null : `${scopeKey}-id`,
    department: isAdmin ? null : { id: `${scopeKey}-id`, name: scopeName },
    scopes: [
      {
        id: `${scopeKey}-scope-id`,
        type: isAdmin ? "global" : "department",
        key: scopeKey,
        display_name: scopeName,
        access_level: isAdmin || role === "analyst" ? "manage" : "read",
        is_default: true,
        department_id: isAdmin ? null : `${scopeKey}-id`
      }
    ],
    status: "active",
    permissions,
    auth_mode: "demo"
  };
}

function jsonResponse(status: number, payload: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(payload)
  };
}
