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
    "can_request_action",
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
    "can_request_action",
    "can_approve_scoped_action",
    "can_view_scope_audit",
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
    "can_manage_users",
    "can_request_action",
    "can_approve_global_action",
    "can_approve_policy_override",
    "can_self_approve_admin_action",
    "can_view_global_audit"
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
    "GET /api/v1/home/overview": successResponse(backendHomeOverview(user)),
    "GET /api/v1/dashboards/library": successResponse([]),
    "GET /api/v1/notifications": successResponse(backendNotificationList()),
    ...(user.permissions.includes("can_request_action")
      ? { "GET /api/v1/actions": successResponse(backendActionList()) }
      : {}),
    ...(user.permissions.some((permission) => [
      "can_approve_scoped_action",
      "can_approve_global_action",
      "can_approve_policy_override"
    ].includes(permission))
      ? { "GET /api/v1/approvals/pending": successResponse(backendPendingApprovalList()) }
      : {}),
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
  title = "Open tickets",
  position = 0
}: {
  id?: string;
  dashboardId?: string;
  title?: string;
  position?: number;
} = {}) {
  return {
    id,
    dashboard_id: dashboardId,
    saved_query_id: "saved-query-id",
    title,
    description: "Current scoped result.",
    card_type: "table",
    position,
    layout: editorLayout(position),
    visualization: editorVisualization(),
    allowed_sizes: editorAllowedSizes(),
    created_at: "2026-07-13T12:00:00Z",
    updated_at: "2026-07-13T12:00:00Z"
  };
}

export function backendHomeOverview(user: BackendUser = demoManager) {
  const isPersonal = user.role === "user";
  const isGlobal = user.role === "admin";
  return {
    mode: isPersonal ? "personal" : isGlobal ? "global" : "scoped",
    scope: {
      type: isGlobal ? "global" : "department",
      display_name: user.scopes[0]?.display_name ?? "Personal",
      scope_count: 1
    },
    personal_summary: {
      owned_dashboard_count: 0,
      shared_dashboard_count: 0,
      owned_card_count: 0,
      successful_queries_last_30_days: 0,
      pending_own_role_requests: 0
    },
    operational_metrics: isPersonal
      ? null
      : {
          active_human_users: 84,
          device_total: 117,
          compliant_device_count: 109,
          device_compliance_rate: 93.16,
          monthly_license_cost_usd: 18432.5,
          unused_license_assignments: 18,
          open_support_tickets: 11,
          security_events_last_30_days: 7
        },
    admin_metrics: isGlobal
      ? {
          active_app_users: 4,
          pending_role_requests: 1,
          app_audit_events_last_7_days: null
        }
      : null
  };
}

export function backendPendingApprovalList(items: Array<Record<string, unknown>> = []) {
  return {
    items,
    pagination: { limit: 20, offset: 0, returned: items.length, total: items.length }
  };
}

export function backendApprovalDetail({
  canApprove = true,
  policyFlags = [{ code: "record_count_over_analyst_threshold", reason: "Internal policy text" }],
  status = "pending"
}: {
  canApprove?: boolean;
  policyFlags?: Array<{ code: string; reason: string }>;
  status?: string;
} = {}) {
  const action = backendActionDetail();
  return {
    approval_id: "00000000-0000-4000-8000-000000000701",
    action_request_id: action.action_request_id,
    action_type: action.action_type,
    requester: {
      id: "00000000-0000-4000-8000-000000000102",
      display_name: "Demo Manager"
    },
    reason: action.reason,
    priority: action.priority,
    scope: action.scope,
    preview: action.preview,
    expires_at: action.expires_at,
    affected_count: 1,
    skipped_count: 0,
    override_count: 1,
    estimated_impact: { estimated_monthly_savings: "25.00" },
    policy_flags: policyFlags,
    requires_admin: true,
    status,
    timeline: [
      {
        event_type: "action_requested",
        timestamp: "2026-07-19T12:01:00Z",
        actor: { id: "00000000-0000-4000-8000-000000000102", display_name: "Demo Manager" },
        summary: "Action requested",
        status: "pending_approval"
      }
    ],
    viewer_capabilities: {
      can_approve: canApprove,
      can_reject: canApprove,
      can_execute_on_approval: canApprove,
      self_approval: false,
      reason: canApprove ? null : "Not currently eligible"
    }
  };
}

export function backendNotificationList(items: Array<Record<string, unknown>> = [], unreadCount = 0) {
  return {
    items,
    pagination: { limit: 10, offset: 0, returned: items.length, total: items.length },
    unread_count: unreadCount
  };
}

export function backendDashboardLibraryItem({
  id = "dashboard-id",
  title = "Operations review",
  relationship = "owned",
  cardCount = 1,
  description = "Saved operational questions.",
  createdAt = "2026-07-12T12:00:00Z",
  updatedAt = "2026-07-13T12:00:00Z"
}: {
  id?: string;
  title?: string;
  relationship?: "owned" | "shared";
  cardCount?: number;
  description?: string | null;
  createdAt?: string;
  updatedAt?: string;
} = {}) {
  return {
    id,
    title,
    description,
    visibility_scope: relationship === "owned" ? "personal" : "department",
    relationship,
    owner: {
      id: relationship === "owned" ? "current-user" : "other-user",
      display_name: relationship === "owned" ? "Demo Manager" : "Demo Analyst"
    },
    scope: {
      type: relationship === "owned" ? "personal" : "department",
      display_name: relationship === "owned" ? "Personal" : "Finance"
    },
    card_count: cardCount,
    preview_cards: Array.from({ length: Math.min(cardCount, 4) }, (_, index) => ({
      id: `${id}-card-${index}`,
      title: `Card ${index + 1}`,
      card_type: "table",
      position: index
    })),
    created_at: createdAt,
    updated_at: updatedAt
  };
}

export function backendDashboardDetail({
  id = "dashboard-id",
  relationship = "owned",
  visibilityScope = "personal",
  cards = []
}: {
  id?: string;
  relationship?: "owned" | "shared";
  visibilityScope?: "personal" | "department" | "global";
  cards?: Array<Record<string, unknown>>;
} = {}) {
  return {
    ...backendDashboardLibraryItem({ id, relationship, cardCount: cards.length }),
    visibility_scope: visibilityScope,
    scope: {
      type: visibilityScope,
      display_name:
        visibilityScope === "personal"
          ? "Personal"
          : visibilityScope === "global"
            ? "Global"
            : "Finance"
    },
    layout_version: 1,
    capabilities: {
      can_manage: relationship === "owned",
      can_duplicate: true,
      can_refresh_cards: true,
      can_export_cards: relationship === "owned",
      can_view_source: relationship === "owned",
      can_create_cards: relationship === "owned"
    },
    cards: cards.map((card, index) => ({
      ...card,
      layout: card.layout && typeof card.layout === "object" ? card.layout : editorLayout(index),
      visualization: card.visualization && typeof card.visualization === "object" ? card.visualization : editorVisualization(),
      allowed_sizes: card.allowed_sizes && typeof card.allowed_sizes === "object" ? card.allowed_sizes : editorAllowedSizes(),
      position: typeof card.position === "number" ? card.position : index
    }))
  };
}

function editorLayout(position: number) {
  return {
    version: 1,
    desktop: { x: (position % 2) * 6, y: Math.floor(position / 2) * 3, w: 6, h: 3 },
    tablet: { x: 0, y: position * 3, w: 6, h: 3 },
    mobile: { x: 0, y: position * 3, w: 1, h: 3 }
  };
}

function editorVisualization() {
  return {
    mode: "auto",
    type: "table",
    recommended_type: "table",
    mapping: {
      category_column: null,
      value_columns: [],
      series_column: null,
      label_column: null,
      target_column: null
    }
  };
}

function editorAllowedSizes() {
  return {
    desktop: [
      { w: 4, h: 2 }, { w: 4, h: 3 }, { w: 4, h: 4 },
      { w: 6, h: 2 }, { w: 6, h: 3 }, { w: 6, h: 4 },
      { w: 8, h: 2 }, { w: 8, h: 3 }, { w: 8, h: 4 },
      { w: 12, h: 2 }, { w: 12, h: 3 }, { w: 12, h: 4 }
    ],
    tablet: [
      { w: 3, h: 2 }, { w: 3, h: 3 }, { w: 3, h: 4 },
      { w: 4, h: 2 }, { w: 4, h: 3 }, { w: 4, h: 4 },
      { w: 6, h: 2 }, { w: 6, h: 3 }, { w: 6, h: 4 }
    ],
    mobile: [{ w: 1, h: 2 }, { w: 1, h: 3 }, { w: 1, h: 4 }]
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
    required_permission: "can_use_query_templates",
    can_suggest_action: false
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
    executed_sql: executedSql,
    suggested_actions: []
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
  const roleIds = {
    user: "00000000-0000-4000-8000-000000000101",
    manager: "00000000-0000-4000-8000-000000000102",
    analyst: "00000000-0000-4000-8000-000000000103",
    admin: "00000000-0000-4000-8000-000000000104"
  };
  const scopeIds = {
    sales: "00000000-0000-4000-8000-000000000201",
    finance: "00000000-0000-4000-8000-000000000202",
    it: "00000000-0000-4000-8000-000000000203",
    global: "00000000-0000-4000-8000-000000000204"
  };
  const departmentIds = {
    sales: "00000000-0000-4000-8000-000000000301",
    finance: "00000000-0000-4000-8000-000000000302",
    it: "00000000-0000-4000-8000-000000000303",
    global: null
  };
  const scopeId = scopeIds[scopeKey as keyof typeof scopeIds];
  const departmentId = departmentIds[scopeKey as keyof typeof departmentIds];

  return {
    id: roleIds[role],
    email: `demo.${role}@queryops.local`,
    full_name: `Demo ${role.charAt(0).toUpperCase()}${role.slice(1)}`,
    role,
    department_id: departmentId,
    department: isAdmin ? null : { id: departmentId, name: scopeName },
    scopes: [
      {
        id: scopeId,
        type: isAdmin ? "global" : "department",
        key: scopeKey,
        display_name: scopeName,
        access_level: isAdmin || role === "analyst" ? "manage" : "read",
        is_default: true,
        department_id: departmentId
      }
    ],
    status: "active",
    permissions,
    auth_mode: "demo"
  };
}

export function backendActionList() {
  return {
    items: [],
    summary: { pending: 0, completed: 0, closed: 0 },
    pagination: { limit: 25, offset: 0, returned: 0, total: 0 }
  };
}

export function backendActionListItem({
  id = "00000000-0000-4000-8000-000000000501",
  status = "pending_approval",
  priority = "high"
}: {
  id?: string;
  status?: string;
  priority?: "normal" | "high" | "urgent";
} = {}) {
  return {
    id,
    action_request_id: id,
    action_type: "reclaim_unused_license",
    title: "Reclaim unused licenses",
    status,
    priority,
    scope: {
      id: "00000000-0000-4000-8000-000000000202",
      type: "department",
      key: "finance",
      display_name: "Finance"
    },
    record_count: 1,
    skipped_count: 0,
    requires_admin: false,
    created_at: "2026-07-19T12:00:00Z",
    submitted_at: "2026-07-19T12:01:00Z",
    updated_at: "2026-07-19T12:01:00Z",
    expires_at: "2026-07-20T12:01:00Z",
    next_step: "Waiting for approval"
  };
}

export function backendActionDetail({
  id = "00000000-0000-4000-8000-000000000501",
  status = "pending_approval",
  requesterId = "00000000-0000-4000-8000-000000000102",
  expired = false
}: {
  id?: string;
  status?: string;
  requesterId?: string;
  expired?: boolean;
} = {}) {
  return {
    id,
    action_request_id: id,
    action_type: "reclaim_unused_license",
    status,
    priority: "high",
    scope: {
      id: "00000000-0000-4000-8000-000000000202",
      type: "department",
      key: "finance",
      display_name: "Finance"
    },
    preview: {
      summary: {
        affected_license_assignment_count: 1,
        normal_eligible_count: 1,
        skipped_count: 0,
        override_required_count: 1,
        high_confidence_count: 1,
        estimated_monthly_savings: "25.00"
      },
      eligible_records: [safeLicenseRecord("00000000-0000-4000-8000-000000000601")],
      skipped_records: [],
      override_required_records: [
        {
          ...safeLicenseRecord("00000000-0000-4000-8000-000000000602"),
          reason: "Admin review is required."
        }
      ],
      exclusions_by_reason: [],
      policy_flags: [{ code: "review_required", reason: "Approval is required." }]
    },
    generated_at: "2026-07-19T12:00:00Z",
    preview_expires_at: expired ? "2026-07-18T12:30:00Z" : "2099-07-19T12:30:00Z",
    expires_at: expired ? "2026-07-18T12:30:00Z" : "2099-07-20T12:00:00Z",
    requires_admin: true,
    is_expired: expired,
    reason: "Review this current governed result.",
    submitted_at: status === "draft_preview" ? null : "2026-07-19T12:01:00Z",
    created_at: "2026-07-19T12:00:00Z",
    updated_at: "2026-07-19T12:01:00Z",
    approval:
      status === "draft_preview"
        ? null
        : {
            id: "00000000-0000-4000-8000-000000000701",
            status: "pending",
            required_approver_role: "admin",
            created_at: "2026-07-19T12:01:00Z",
            expires_at: "2099-07-20T12:00:00Z"
          },
    timeline:
      status === "draft_preview"
        ? [timelineEvent("action_preview_created", "Preview created", requesterId)]
        : [
            timelineEvent("action_preview_created", "Preview created", requesterId),
            timelineEvent("action_requested", "Action requested", requesterId)
          ]
  };
}

export function backendActionQueryResult() {
  const result = backendQueryResult();
  return {
    ...result,
    query_run_id: "00000000-0000-4000-8000-000000000401",
    columns: ["id", "product_name"],
    rows: [
      {
        id: "00000000-0000-4000-8000-000000000601",
        product_name: "Microsoft 365 E5"
      }
    ],
    suggested_actions: [
      {
        action_type: "reclaim_unused_license",
        label: "Preview license reclaim",
        selector_kind: "license_assignment",
        result_identifier_column: "id"
      }
    ]
  };
}

function safeLicenseRecord(id: string) {
  return {
    record_type: "license_assignment",
    record_id: id,
    license_assignment_id: id,
    scope: {
      id: "00000000-0000-4000-8000-000000000202",
      type: "department",
      key: "finance"
    },
    user_display_label: "Governed user 1",
    license_product: "Microsoft 365 E5",
    license_vendor: "Microsoft",
    last_used_at: null,
    monthly_cost_usd: "25.00",
    reason_code: "no_recorded_usage",
    reason: "No license usage is recorded.",
    high_confidence: true
  };
}

function timelineEvent(eventType: string, summary: string, actorId: string) {
  return {
    event_type: eventType,
    status: "pending_approval",
    summary,
    timestamp: "2026-07-19T12:01:00Z",
    created_at: "2026-07-19T12:01:00Z",
    actor: { id: actorId, display_name: "Demo Manager" }
  };
}

function jsonResponse(status: number, payload: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(payload)
  };
}
