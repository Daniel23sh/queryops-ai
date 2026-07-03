import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { demoLogin, type DemoLoginResult } from "./api/auth";
import { ApiError } from "./api/client";
import {
  approveRoleRequest,
  createRoleRequest,
  getAdminRoleRequests,
  getMyRoleRequests,
  rejectRoleRequest,
  type RoleRequest,
  type RoleRequestStatus,
  type RoleUpgradeTarget
} from "./api/roleRequests";
import { useAuth } from "./auth/AuthProvider";
import type { AuthUser, PermissionKey } from "./auth/types";
import { AskDataPage } from "./features/ask-data";

type DemoProfile = {
  label: string;
  email: string;
  roleLabel: string;
  department: string;
  summary: string;
};

const DEMO_PROFILES: DemoProfile[] = [
  {
    label: "Demo Admin",
    email: "demo.admin@queryops.local",
    roleLabel: "Admin",
    department: "IT",
    summary: "Global administration profile for seeded demo data."
  },
  {
    label: "Demo Analyst",
    email: "demo.analyst@queryops.local",
    roleLabel: "Analyst",
    department: "IT",
    summary: "Technical department profile with SQL-visible permissions."
  },
  {
    label: "Demo Manager",
    email: "demo.manager@queryops.local",
    roleLabel: "Manager",
    department: "Finance",
    summary: "Department business profile for free-query access."
  },
  {
    label: "Demo User",
    email: "demo.user@queryops.local",
    roleLabel: "User",
    department: "Sales",
    summary: "Limited read-only profile for approved templates."
  }
];

type NavItem = {
  id: string;
  label: string;
  title: string;
  summary: string;
  icon: NavIconName;
  canView: (user: AuthUser) => boolean;
};

type AdminDecisionAction = "approve" | "reject";
type ThemeMode = "light" | "dark";
type PlannedWorkspaceCard = {
  title: string;
  status: string;
  description: string;
  tone?: "blue" | "green" | "warning" | "muted";
};
type PlannedWorkspaceAction = {
  label: string;
  description: string;
};
type PlannedWorkspaceContent = {
  summary: string;
  cards: PlannedWorkspaceCard[];
  actions: PlannedWorkspaceAction[];
};
type NavIconName =
  | "templates"
  | "dashboard"
  | "upgrade"
  | "requests"
  | "ask"
  | "history"
  | "sql"
  | "department"
  | "admin"
  | "users"
  | "audit";

const THEME_STORAGE_KEY = "queryops-theme";

const PLACEHOLDER_SCOPE_NOTICE =
  "Visual preview only. This page does not run queries, create dashboards, export files, execute actions, approve requests, or call any additional backend APIs.";

const ROLE_UPGRADE_OPTIONS: Array<{ value: RoleUpgradeTarget; label: string }> = [
  { value: "manager", label: "Manager" },
  { value: "analyst", label: "Analyst" },
  { value: "admin", label: "Admin" }
];

const ROLE_UPGRADE_ORDER: RoleUpgradeTarget[] = ["manager", "analyst", "admin"];

const WORKSPACE_NAV_ITEMS: NavItem[] = [
  {
    id: "templates",
    label: "Templates",
    title: "Templates",
    summary:
      "Approved query templates are available from Ask Data while standalone template management waits for a later milestone.",
    icon: "templates",
    canView: () => true
  },
  {
    id: "my-dashboard",
    label: "My Dashboard",
    title: "QueryOps Command Center",
    summary: "Role-aware governed analytics overview.",
    icon: "dashboard",
    canView: () => true
  },
  {
    id: "role-upgrade",
    label: "Role Upgrade",
    title: "Request Role Upgrade",
    summary: "Request a role change and track admin approval status.",
    icon: "upgrade",
    canView: () => true
  },
  {
    id: "admin-role-requests",
    label: "Role Requests",
    title: "Admin Role Requests",
    summary: "Review role upgrade requests and record role-only decisions.",
    icon: "requests",
    canView: (user) => hasPermission(user, "can_approve_role_requests")
  },
  {
    id: "ask-data",
    label: "Ask Data",
    title: "Ask Data",
    summary: "Run governed template and permitted free-form questions.",
    icon: "ask",
    canView: (user) => hasPermission(user, "can_use_query_templates")
  },
  {
    id: "query-history",
    label: "Query History",
    title: "Query History",
    summary:
      "History navigation is role-gated; the dedicated history UI remains future work.",
    icon: "history",
    canView: (user) => hasPermission(user, "can_view_query_history_department")
  },
  {
    id: "sql-technical",
    label: "SQL / Technical",
    title: "SQL / Technical",
    summary:
      "Technical details stay role-gated and contained inside Ask Data result tabs.",
    icon: "sql",
    canView: (user) => hasPermission(user, "can_view_sql")
  },
  {
    id: "department-dashboards",
    label: "Department Dashboards",
    title: "Department Dashboards",
    summary:
      "Department dashboard management is planned for a later milestone without card persistence in this PR.",
    icon: "department",
    canView: (user) =>
      hasAnyPermission(user, [
        "can_create_department_dashboard",
        "can_manage_department_dashboard"
      ])
  },
  {
    id: "admin-console",
    label: "Admin Console",
    title: "Admin Console",
    summary:
      "Administrative controls are staged intentionally; Role Requests remains the active admin workflow.",
    icon: "admin",
    canView: (user) =>
      hasAnyPermission(user, ["can_manage_users", "can_approve_role_requests"])
  },
  {
    id: "users",
    label: "Users",
    title: "Users",
    summary:
      "User management UI is planned later; demo identity context remains read-only here.",
    icon: "users",
    canView: (user) => hasPermission(user, "can_manage_users")
  },
  {
    id: "audit",
    label: "Audit",
    title: "Audit",
    summary:
      "Audit review is planned for a later milestone while backend governance remains the source of truth.",
    icon: "audit",
    canView: (user) => hasPermission(user, "can_view_global_audit")
  }
];

const PLANNED_WORKSPACE_CONTENT: Record<string, PlannedWorkspaceContent> = {
  templates: {
    summary:
      "Approved query templates are available from Ask Data while standalone template management waits for a later milestone.",
    cards: [
      {
        title: "Catalog source",
        status: "Ask Data",
        description: "The approved template catalog is already reachable from Ask Data.",
        tone: "blue"
      },
      {
        title: "Template defaults",
        status: "Backend-owned",
        description: "Template runs continue to use existing backend defaults and validation.",
        tone: "green"
      },
      {
        title: "Management UI",
        status: "Future milestone",
        description: "Creating or editing templates is intentionally outside this PR.",
        tone: "muted"
      }
    ],
    actions: [
      {
        label: "Create template",
        description: "Template authoring is not implemented in this checkpoint."
      },
      {
        label: "Manage catalog",
        description: "Catalog administration remains future work."
      }
    ]
  },
  "query-history": {
    summary:
      "Query history navigation is reserved for roles with history visibility; this screen remains a safe visual preview until the history UI is wired.",
    cards: [
      {
        title: "History access",
        status: "Role-gated",
        description: "Only permitted roles can reach this workspace entry.",
        tone: "blue"
      },
      {
        title: "Scope history",
        status: "Future view",
        description: "Dedicated own, department, and scope history screens are not added here.",
        tone: "muted"
      },
      {
        title: "Exports",
        status: "Disabled",
        description: "CSV and report export behavior remains outside Milestone 5 PR6.",
        tone: "warning"
      }
    ],
    actions: [
      {
        label: "Open history timeline",
        description: "History timelines are not wired in this visual checkpoint."
      },
      {
        label: "Export query history",
        description: "Export behavior is intentionally disabled."
      }
    ]
  },
  "sql-technical": {
    summary:
      "Technical details remain role-gated and contained inside Ask Data result tabs for Analyst and Admin users.",
    cards: [
      {
        title: "Technical tab policy",
        status: "Ask Data only",
        description: "Technical labels stay tied to Ask Data result tabs instead of a standalone console.",
        tone: "blue"
      },
      {
        title: "Diagnostics posture",
        status: "Structured and safe",
        description: "Diagnostics views remain filtered by the existing Ask Data presentation.",
        tone: "green"
      },
      {
        title: "Standalone tooling",
        status: "Not implemented",
        description: "This page does not run SQL tools, previews, exports, or debug actions.",
        tone: "muted"
      }
    ],
    actions: [
      {
        label: "Open technical console",
        description: "Standalone technical tooling is not part of this milestone."
      },
      {
        label: "Export technical report",
        description: "Technical export behavior remains future work."
      }
    ]
  },
  "department-dashboards": {
    summary:
      "Department dashboard management is planned for a later milestone. This preview shows the governance shape without saved-card behavior.",
    cards: [
      {
        title: "Department cards",
        status: "Future persistence",
        description: "Saving cards to department dashboards is intentionally disabled.",
        tone: "blue"
      },
      {
        title: "Sharing model",
        status: "Governed",
        description: "Dashboard visibility will follow role and scope policy when implemented.",
        tone: "green"
      },
      {
        title: "Layout controls",
        status: "Not wired",
        description: "Drag, pin, and layout persistence are reserved for later milestones.",
        tone: "muted"
      }
    ],
    actions: [
      {
        label: "Create dashboard",
        description: "Dashboard creation is not implemented in this PR."
      },
      {
        label: "Save dashboard card",
        description: "Saved-card behavior remains future work."
      }
    ]
  },
  "admin-console": {
    summary:
      "Administrative controls are staged intentionally. Role Requests remains the active admin workflow in this milestone.",
    cards: [
      {
        title: "Role requests",
        status: "Live workflow",
        description: "Use the existing Role Requests page for role-only admin decisions.",
        tone: "green"
      },
      {
        title: "Permission controls",
        status: "Planned",
        description: "Policy editing and permission management are not added here.",
        tone: "muted"
      },
      {
        title: "Admin actions",
        status: "Disabled",
        description: "No operational action preview or execution controls are introduced.",
        tone: "warning"
      }
    ],
    actions: [
      {
        label: "Edit permissions",
        description: "Permission editing remains future work."
      },
      {
        label: "Run admin action",
        description: "Admin actions are not implemented in this checkpoint."
      }
    ]
  },
  users: {
    summary:
      "User management is planned for a later milestone. Demo identity context remains read-only from this page.",
    cards: [
      {
        title: "Demo identities",
        status: "Read-only context",
        description: "Current user identity is shown in the workspace header only.",
        tone: "blue"
      },
      {
        title: "Role changes",
        status: "Request workflow",
        description: "Role changes continue through the existing request and review flow.",
        tone: "green"
      },
      {
        title: "Account controls",
        status: "Not implemented",
        description: "Invites, disables, and user edits are outside this PR.",
        tone: "muted"
      }
    ],
    actions: [
      {
        label: "Invite user",
        description: "User invitations are not wired in demo auth."
      },
      {
        label: "Disable user",
        description: "Account mutation controls remain future work."
      }
    ]
  },
  audit: {
    summary:
      "Audit review is planned for later milestones. Backend governance remains the source of truth while this screen stays inert.",
    cards: [
      {
        title: "Audit timeline",
        status: "Future view",
        description: "A dedicated audit timeline is not added in this visual checkpoint.",
        tone: "blue"
      },
      {
        title: "Security posture",
        status: "Backend governed",
        description: "This page does not change audit, auth, role, or query behavior.",
        tone: "green"
      },
      {
        title: "Audit exports",
        status: "Disabled",
        description: "Audit export behavior remains outside the approved scope.",
        tone: "warning"
      }
    ],
    actions: [
      {
        label: "Open audit timeline",
        description: "Audit timelines are not wired in this PR."
      },
      {
        label: "Export audit",
        description: "Audit export remains future work."
      }
    ]
  }
};

export default function App() {
  const auth = useAuth();

  if (auth.status === "loading") {
    return (
      <AppShell>
        <main className="app-main app-main--centered" aria-live="polite">
          <section className="loading-panel" aria-label="Loading authentication state">
            <p className="eyebrow">Demo auth</p>
            <h1>Checking your session...</h1>
            <p className="subtitle">
              QueryOps AI is checking whether your demo session is still valid.
            </p>
          </section>
        </main>
      </AppShell>
    );
  }

  if (auth.status === "authenticated" && auth.user) {
    return (
      <AppShell>
        <AuthenticatedWorkspace
          user={auth.user}
          csrfToken={auth.csrfToken}
          onLogout={auth.logout}
        />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <DemoLoginScreen onLogin={auth.applyLoginResult} />
    </AppShell>
  );
}

function AppShell({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeMode>(() => getInitialTheme());

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <div className="brand" aria-label="QueryOps AI">
            <span className="brand__mark" aria-hidden="true">
              Q
            </span>
            <span className="brand__copy">
              <span className="brand__name">QueryOps AI</span>
              <span className="brand__phase">Governed data workspace</span>
            </span>
          </div>
          <div className="app-header__actions" aria-label="Application controls">
            <span className="app-status-pill">Demo environment</span>
            <ThemeToggle
              theme={theme}
              onToggle={() =>
                setTheme((currentTheme) =>
                  currentTheme === "dark" ? "light" : "dark"
                )
              }
            />
          </div>
        </div>
      </header>

      {children}
    </div>
  );
}

function ThemeToggle({
  theme,
  onToggle
}: {
  theme: ThemeMode;
  onToggle: () => void;
}) {
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={isDark}
      onClick={onToggle}
    >
      <span className="theme-toggle__track" aria-hidden="true">
        <span className="theme-toggle__thumb" />
      </span>
      <span className="theme-toggle__label">{isDark ? "Dark" : "Light"}</span>
    </button>
  );
}

function DemoLoginScreen({
  onLogin
}: {
  onLogin: (result: DemoLoginResult) => void;
}) {
  const [submittingEmail, setSubmittingEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isSubmitting = submittingEmail !== null;

  async function handleLogin(profile: DemoProfile) {
    setError(null);
    setSubmittingEmail(profile.email);

    try {
      const result = await demoLogin(profile.email);
      onLogin(result);
    } catch (loginError) {
      setError(formatLoginError(loginError));
    } finally {
      setSubmittingEmail(null);
    }
  }

  return (
    <main className="app-main">
      <section className="login-layout" aria-labelledby="login-title">
        <div className="login-copy">
          <p className="eyebrow">Local demo mode</p>
          <h1 id="login-title">Choose a demo profile</h1>
          <p className="subtitle">
            Sign in as one of the seeded QueryOps users to review the current auth
            foundation. The browser will store the backend session cookie.
          </p>
        </div>

        <div className="demo-profile-grid" aria-label="Demo profiles">
          {DEMO_PROFILES.map((profile) => {
            const isCurrentProfile = submittingEmail === profile.email;

            return (
              <button
                key={profile.email}
                type="button"
                className="demo-profile-card"
                aria-label={profile.label}
                disabled={isSubmitting}
                onClick={() => void handleLogin(profile)}
              >
                <span className="demo-profile-card__role">{profile.label}</span>
                <span className="demo-profile-card__email">{profile.email}</span>
                <span className="demo-profile-card__meta">
                  {profile.roleLabel} / {profile.department}
                </span>
                <span className="demo-profile-card__summary">{profile.summary}</span>
                <span className="demo-profile-card__action">
                  {isCurrentProfile ? "Signing in..." : "Sign in"}
                </span>
              </button>
            );
          })}
        </div>

        {error ? (
          <p className="login-error" role="alert">
            {error}
          </p>
        ) : null}
      </section>
    </main>
  );
}

function AuthenticatedWorkspace({
  user,
  csrfToken,
  onLogout
}: {
  user: AuthUser;
  csrfToken: string | null;
  onLogout: () => Promise<void>;
}) {
  const visibleNavItems = WORKSPACE_NAV_ITEMS.filter((item) => item.canView(user));
  const [activeNavId, setActiveNavId] = useState(visibleNavItems[0]?.id ?? "templates");
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const activeNavItem =
    visibleNavItems.find((item) => item.id === activeNavId) ?? visibleNavItems[0];

  async function handleLogout() {
    setIsLoggingOut(true);
    setLogoutError(null);

    try {
      await onLogout();
    } catch (error) {
      setLogoutError(formatLogoutError(error));
      setIsLoggingOut(false);
    }
  }

  return (
    <main className="app-main app-main--workspace">
      <div className="workspace-layout">
        <aside className="workspace-sidebar" aria-label="Workspace">
          <nav className="workspace-nav" aria-label="Workspace navigation">
            {visibleNavItems.map((item) => {
              const isActive = item.id === activeNavItem.id;

              return (
                <button
                  key={item.id}
                  type="button"
                  className="workspace-nav__item"
                  aria-current={isActive ? "page" : undefined}
                  data-active={isActive ? "true" : "false"}
                  onClick={() => setActiveNavId(item.id)}
                >
                  <span
                    className="workspace-nav__icon"
                    data-icon={item.icon}
                    aria-hidden="true"
                  />
                  <span className="workspace-nav__label">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </aside>

        <section className="workspace-content" aria-labelledby="workspace-title">
          <div className="workspace-topbar">
            <dl className="identity-grid" aria-label="Current user">
              <div>
                <dt>Email</dt>
                <dd>{user.email}</dd>
              </div>
              <div>
                <dt>Role</dt>
                <dd>{formatRole(user.role)}</dd>
              </div>
              <div>
                <dt>Department</dt>
                <dd>{user.department?.name ?? "No department assigned"}</dd>
              </div>
              <div>
                <dt>Auth mode</dt>
                <dd>{user.authMode}</dd>
              </div>
            </dl>

            <div className="workspace-actions" aria-label="Session actions">
              <button
                type="button"
                className="logout-button"
                disabled={isLoggingOut}
                onClick={() => void handleLogout()}
              >
                {isLoggingOut ? "Logging out..." : "Log out"}
              </button>
            </div>
          </div>

          {logoutError ? (
            <p className="logout-error" role="alert">
              {logoutError}
            </p>
          ) : null}

          {activeNavItem.id === "ask-data" ? (
            <AskDataPage user={user} csrfToken={csrfToken} />
          ) : activeNavItem.id === "my-dashboard" ? (
            <DashboardPage
              user={user}
              visibleNavItems={visibleNavItems}
              onNavigate={setActiveNavId}
            />
          ) : activeNavItem.id === "role-upgrade" ? (
            <RoleUpgradePanel userRole={user.role} csrfToken={csrfToken} />
          ) : activeNavItem.id === "admin-role-requests" ? (
            <AdminRoleRequestsPanel csrfToken={csrfToken} />
          ) : (
            <PlannedWorkspacePage item={activeNavItem} user={user} />
          )}
        </section>
      </div>
    </main>
  );
}

function PlannedWorkspacePage({ item, user }: { item: NavItem; user: AuthUser }) {
  const content =
    PLANNED_WORKSPACE_CONTENT[item.id] ??
    ({
      summary: item.summary,
      cards: [
        {
          title: "Workspace status",
          status: "Planned",
          description: "This workspace is intentionally visual-only for this PR.",
          tone: "muted"
        }
      ],
      actions: [
        {
          label: "Open workspace",
          description: "This control is disabled until the feature is implemented."
        }
      ]
    } satisfies PlannedWorkspaceContent);
  const roleLabel = formatRole(user.role);
  const departmentLabel = user.department?.name ?? "No department assigned";

  return (
    <article
      className="placeholder-panel"
      role="region"
      aria-label={`${item.label} planned workspace`}
    >
      <section className="placeholder-panel__hero" aria-labelledby="workspace-title">
        <div className="placeholder-panel__copy">
          <p className="placeholder-panel__badge">Planned workspace</p>
          <h1 id="workspace-title">{item.title}</h1>
          <p className="subtitle">{content.summary}</p>
        </div>
        <div className="placeholder-panel__chips" aria-label="Workspace context">
          <span>Role: {roleLabel}</span>
          <span>Scope: {departmentLabel}</span>
          <span>Demo environment</span>
        </div>
      </section>

      <section className="placeholder-panel__card-grid" aria-label={`${item.label} status`}>
        {content.cards.map((card) => (
          <article
            key={card.title}
            className="placeholder-status-card"
            data-tone={card.tone ?? "blue"}
          >
            <p className="placeholder-status-card__label">{card.title}</p>
            <h2>{card.status}</h2>
            <p>{card.description}</p>
          </article>
        ))}
      </section>

      <div className="placeholder-panel__work-grid">
        <section className="placeholder-panel__notice" aria-labelledby={`${item.id}-guardrail-title`}>
          <p className="eyebrow">Scope guardrail</p>
          <h2 id={`${item.id}-guardrail-title`}>Visual preview only</h2>
          <p>{PLACEHOLDER_SCOPE_NOTICE}</p>
        </section>

        <section className="placeholder-panel__actions" aria-labelledby={`${item.id}-actions-title`}>
          <div>
            <p className="eyebrow">Future controls</p>
            <h2 id={`${item.id}-actions-title`}>Intentionally disabled</h2>
          </div>
          <div className="placeholder-action-list">
            {content.actions.map((action) => (
              <button
                key={action.label}
                type="button"
                className="placeholder-action-button"
                aria-label={action.label}
                disabled
              >
                <span>{action.label}</span>
                <small>{action.description}</small>
              </button>
            ))}
          </div>
        </section>
      </div>
    </article>
  );
}

function DashboardPage({
  user,
  visibleNavItems,
  onNavigate
}: {
  user: AuthUser;
  visibleNavItems: NavItem[];
  onNavigate: (navId: string) => void;
}) {
  const roleLabel = formatRole(user.role);
  const departmentLabel = user.department?.name ?? "No department assigned";
  const hasTemplateAccess = hasPermission(user, "can_use_query_templates");
  const hasFreeQueryAccess = hasPermission(user, "can_run_free_query");
  const hasTechnicalVisibility = hasPermission(user, "can_view_sql");
  const hasGlobalScope = hasPermission(user, "can_query_global_data");
  const queryAccessLabel = hasFreeQueryAccess
    ? "Free-query access"
    : "Template-only access";
  const sqlVisibilityLabel = hasTechnicalVisibility
    ? "SQL visible in Ask Data"
    : "SQL hidden";
  const diagnosticsVisibilityLabel = hasTechnicalVisibility
    ? "Diagnostics visible in Ask Data"
    : "Diagnostics hidden";
  const currentScopeLabel =
    user.role === "admin" && hasGlobalScope ? "Global scope" : departmentLabel;
  const technicalSummary = hasTechnicalVisibility
    ? "Technical tabs visible"
    : "Business view";
  const roleSummary = getDashboardRoleSummary(user.role, hasFreeQueryAccess, hasTechnicalVisibility);

  function canNavigateTo(navId: string): boolean {
    return visibleNavItems.some((item) => item.id === navId);
  }

  const quickActions = [
    {
      label: "Open Ask Data",
      description: "Start with approved templates or a permitted governed question.",
      navId: "ask-data",
      disabled: !canNavigateTo("ask-data"),
      isPrimary: true
    },
    {
      label: "Review query history",
      description: canNavigateTo("query-history")
        ? "Open the planned query history workspace."
        : "Available only to roles with query history visibility.",
      navId: "query-history",
      disabled: !canNavigateTo("query-history"),
      isPrimary: false
    },
    {
      label: "Request role upgrade",
      description: "Use the existing role request workflow when more access is needed.",
      navId: "role-upgrade",
      disabled: !canNavigateTo("role-upgrade"),
      isPrimary: false
    },
    {
      label: "Save dashboard card",
      description: "Future saved-card behavior is intentionally disabled in this PR.",
      navId: null,
      disabled: true,
      isPrimary: false
    }
  ];

  const kpiCards = [
    {
      label: "Approved templates",
      value: hasTemplateAccess ? "Available" : "Hidden",
      detail: hasTemplateAccess
        ? "The template catalog is available from Ask Data."
        : "The template catalog is not visible for this role.",
      tone: "blue"
    },
    {
      label: "Query access mode",
      value: queryAccessLabel,
      detail: hasFreeQueryAccess
        ? "This role can ask permitted free-form questions."
        : "This role runs approved templates only.",
      tone: hasFreeQueryAccess ? "green" : "blue"
    },
    {
      label: "Technical visibility",
      value: technicalSummary,
      detail: hasTechnicalVisibility
        ? "Technical tabs stay contained in Ask Data."
        : "Technical views remain hidden for this role.",
      tone: hasTechnicalVisibility ? "green" : "muted"
    },
    {
      label: "Current scope",
      value: currentScopeLabel,
      detail: hasGlobalScope
        ? "Admin demo permissions include global query scope."
        : "Workspace context follows the signed-in department.",
      tone: hasGlobalScope ? "warning" : "blue"
    }
  ];

  const governanceCards = [
    {
      title: "Template governance",
      status: hasTemplateAccess ? "Approved catalog enabled" : "Catalog hidden",
      detail: hasTemplateAccess
        ? "Approved templates remain the safest entry point for repeat questions."
        : "This role does not have template catalog visibility.",
      tone: "blue"
    },
    {
      title: "Free-question access",
      status: hasFreeQueryAccess ? "Free questions enabled" : "Templates required",
      detail: hasFreeQueryAccess
        ? "Free questions still run through backend validation and authorization."
        : "Approved templates are the safe starting point for this role.",
      tone: hasFreeQueryAccess ? "green" : "muted"
    },
    {
      title: "SQL visibility",
      status: sqlVisibilityLabel,
      detail: hasTechnicalVisibility
        ? "SQL is available only inside the Ask Data technical tab."
        : "SQL tabs and SQL content remain hidden for this role.",
      tone: hasTechnicalVisibility ? "green" : "muted"
    },
    {
      title: "Diagnostics visibility",
      status: diagnosticsVisibilityLabel,
      detail: hasTechnicalVisibility
        ? "Safe technical diagnostics stay inside Ask Data."
        : "Technical diagnostics remain hidden for this role.",
      tone: hasTechnicalVisibility ? "green" : "muted"
    },
    {
      title: "Scope enforcement",
      status: "Backend enforced",
      detail: "Frontend status mirrors permissions; backend authorization remains the source of truth.",
      tone: "blue"
    }
  ];

  const activityRows = [
    {
      title: "Demo workspace loaded",
      meta: `${roleLabel} profile / ${departmentLabel}`,
      status: "Preview"
    },
    {
      title: "Ask Data entry point",
      meta: hasTemplateAccess
        ? "Approved template access is visible in navigation."
        : "Ask Data is hidden for this role.",
      status: hasTemplateAccess ? "Ready" : "Hidden"
    },
    {
      title: "Technical controls",
      meta: hasTechnicalVisibility
        ? "Technical visibility is summarized here, with details kept in Ask Data."
        : "Technical views are not exposed to this role.",
      status: hasTechnicalVisibility ? "Role-gated" : "Restricted"
    }
  ];

  return (
    <article className="dashboard-page" role="region" aria-label="My Dashboard">
      <section className="dashboard-hero" aria-labelledby="workspace-title">
        <div className="dashboard-hero__copy">
          <p className="eyebrow">My Dashboard</p>
          <h1 id="workspace-title">QueryOps Command Center</h1>
          <p className="subtitle">
            A role-aware overview of governed analytics access for this demo
            workspace. The dashboard summarizes current permissions without adding
            new backend behavior.
          </p>
        </div>
        <div className="dashboard-chip-row" aria-label="Workspace context">
          <span className="dashboard-chip">
            Role <strong>{roleLabel}</strong>
          </span>
          <span className="dashboard-chip">Scope: {departmentLabel}</span>
          <span className="dashboard-chip">Demo environment</span>
        </div>
      </section>

      <section className="dashboard-kpi-grid" aria-label="Dashboard status">
        {kpiCards.map((card) => (
          <div key={card.label} className="dashboard-kpi-card" data-tone={card.tone}>
            <p className="dashboard-kpi-card__label">{card.label}</p>
            <p className="dashboard-kpi-card__value">{card.value}</p>
            <p className="dashboard-kpi-card__detail">{card.detail}</p>
          </div>
        ))}
      </section>

      <div className="dashboard-work-grid">
        <section className="dashboard-section" aria-labelledby="dashboard-actions-title">
          <div className="dashboard-section__header">
            <p className="eyebrow">Recommended next steps</p>
            <h2 id="dashboard-actions-title">Move through the workspace</h2>
          </div>
          <div className="dashboard-actions-grid">
            {quickActions.map((action) => (
              <button
                key={action.label}
                type="button"
                className="dashboard-action-button"
                aria-label={action.label}
                data-primary={action.isPrimary ? "true" : "false"}
                disabled={action.disabled}
                onClick={() => {
                  if (action.navId) {
                    onNavigate(action.navId);
                  }
                }}
              >
                <span className="dashboard-action-button__label">{action.label}</span>
                <span className="dashboard-action-button__description">
                  {action.description}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="dashboard-section" aria-labelledby="dashboard-activity-title">
          <div className="dashboard-section__header">
            <p className="eyebrow">Workspace preview</p>
            <h2 id="dashboard-activity-title">Demo activity preview</h2>
          </div>
          <ul className="dashboard-activity-list">
            {activityRows.map((row) => (
              <li key={row.title} className="dashboard-activity-item">
                <div>
                  <h3>{row.title}</h3>
                  <p>{row.meta}</p>
                </div>
                <span className="dashboard-status-pill">{row.status}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="dashboard-section" aria-labelledby="dashboard-governance-title">
        <div className="dashboard-section__header">
          <p className="eyebrow">Governance posture</p>
          <h2 id="dashboard-governance-title">Access status</h2>
        </div>
        <div className="dashboard-posture-grid">
          {governanceCards.map((card) => (
            <article
              key={card.title}
              className="dashboard-status-card"
              data-tone={card.tone}
            >
              <span className="dashboard-status-card__marker" aria-hidden="true" />
              <div>
                <h3>{card.title}</h3>
                <p className="dashboard-status-card__status">{card.status}</p>
                <p className="dashboard-status-card__detail">{card.detail}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="dashboard-role-panel" aria-labelledby="dashboard-role-title">
        <p className="eyebrow">What you can do from here</p>
        <h2 id="dashboard-role-title">{roleSummary.title}</h2>
        <p>{roleSummary.description}</p>
      </section>
    </article>
  );
}

function RoleUpgradePanel({
  userRole,
  csrfToken
}: {
  userRole: AuthUser["role"];
  csrfToken: string | null;
}) {
  const roleUpgradeOptions = getRoleUpgradeOptions(userRole);
  const hasRoleUpgradeOptions = roleUpgradeOptions.length > 0;
  const [requestedRole, setRequestedRole] =
    useState<RoleUpgradeTarget>(roleUpgradeOptions[0]?.value ?? "manager");
  const [reason, setReason] = useState("");
  const [roleRequests, setRoleRequests] = useState<RoleRequest[]>([]);
  const [isLoadingRequests, setIsLoadingRequests] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;
    setIsLoadingRequests(true);
    setLoadError(null);

    getMyRoleRequests()
      .then((requests) => {
        if (!isCurrent) {
          return;
        }
        setRoleRequests(requests);
        setIsLoadingRequests(false);
      })
      .catch((error) => {
        if (!isCurrent) {
          return;
        }
        setLoadError(formatRoleRequestError(error, "Role requests could not be loaded."));
        setIsLoadingRequests(false);
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    setSuccessMessage(null);

    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setSubmitError("Enter a reason for the role upgrade request.");
      return;
    }

    if (!csrfToken) {
      setSubmitError("Refresh your session before submitting a role upgrade request.");
      return;
    }

    if (!hasRoleUpgradeOptions) {
      setSubmitError("No role upgrade target is available for your current role.");
      return;
    }

    setIsSubmitting(true);
    try {
      const createdRequest = await createRoleRequest(
        requestedRole,
        trimmedReason,
        csrfToken
      );
      setRoleRequests((requests) => [
        createdRequest,
        ...requests.filter((request) => request.id !== createdRequest.id)
      ]);
      setReason("");
      setSuccessMessage("Role upgrade request submitted.");
    } catch (error) {
      setSubmitError(formatRoleRequestError(error, "Role upgrade request failed."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <article className="role-upgrade-panel">
      <div className="role-upgrade-panel__header">
        <p className="eyebrow">Role upgrade</p>
        <h1 id="workspace-title">Request Role Upgrade</h1>
        <p className="subtitle">
          Choose the role you need and explain the access change. Admin approval is
          required.
        </p>
        <div className="role-upgrade-panel__chips" aria-label="Role request safeguards">
          <span>Existing workflow</span>
          <span>Admin reviewed</span>
          <span>No automatic access</span>
        </div>
      </div>

      {hasRoleUpgradeOptions ? (
        <form className="role-request-form" onSubmit={(event) => void handleSubmit(event)}>
          <div className="form-field">
            <label htmlFor="requested-role">Requested role</label>
            <select
              id="requested-role"
              value={requestedRole}
              onChange={(event) =>
                setRequestedRole(event.target.value as RoleUpgradeTarget)
              }
            >
              {roleUpgradeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-field">
            <label htmlFor="role-request-reason">Reason</label>
            <textarea
              id="role-request-reason"
              rows={4}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>

          <p className="role-request-note">Admin approval is required.</p>

          {submitError ? (
            <p className="form-message form-message--error" role="alert">
              {submitError}
            </p>
          ) : null}

          {successMessage ? (
            <p className="form-message form-message--success" role="status">
              {successMessage}
            </p>
          ) : null}

          <button
            type="submit"
            className="primary-action-button"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Submitting..." : "Submit request"}
          </button>
        </form>
      ) : (
        <p className="role-request-note">Admin already has the highest role.</p>
      )}

      <section className="role-request-status" aria-labelledby="role-request-status-title">
        <div className="role-request-status__header">
          <h2 id="role-request-status-title">My role requests</h2>
        </div>

        {isLoadingRequests ? (
          <p className="status-copy">Loading role requests...</p>
        ) : null}

        {loadError ? (
          <p className="form-message form-message--error" role="alert">
            {loadError}
          </p>
        ) : null}

        {!isLoadingRequests && !loadError && roleRequests.length === 0 ? (
          <p className="status-copy">No role upgrade requests yet.</p>
        ) : null}

        {!isLoadingRequests && !loadError && roleRequests.length > 0 ? (
          <ul className="role-request-list">
            {roleRequests.map((request) => (
              <li key={request.id} className="role-request-list__item">
                <div>
                  <h3>{formatRole(request.requestedRole)}</h3>
                  <p>{request.reason ?? "No reason provided."}</p>
                </div>
                <span
                  className="role-request-status-badge"
                  data-status={request.status}
                >
                  {formatRequestStatus(request.status)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </article>
  );
}

function AdminRoleRequestsPanel({ csrfToken }: { csrfToken: string | null }) {
  const [roleRequests, setRoleRequests] = useState<RoleRequest[]>([]);
  const [decisionReasons, setDecisionReasons] = useState<Record<string, string>>({});
  const [isLoadingRequests, setIsLoadingRequests] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [processingDecision, setProcessingDecision] = useState<{
    requestId: string;
    action: AdminDecisionAction;
  } | null>(null);

  useEffect(() => {
    let isCurrent = true;
    setIsLoadingRequests(true);
    setLoadError(null);

    getAdminRoleRequests()
      .then((requests) => {
        if (!isCurrent) {
          return;
        }
        setRoleRequests(requests);
        setIsLoadingRequests(false);
      })
      .catch((error) => {
        if (!isCurrent) {
          return;
        }
        setLoadError(formatRoleRequestError(error, "Admin role requests could not be loaded."));
        setIsLoadingRequests(false);
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  async function handleDecision(request: RoleRequest, action: AdminDecisionAction) {
    const decisionReason = (decisionReasons[request.id] ?? "").trim();
    setDecisionError(null);
    setSuccessMessage(null);

    if (!decisionReason) {
      setDecisionError("Enter a decision reason before approving or rejecting.");
      return;
    }

    if (!csrfToken) {
      setDecisionError("Refresh your session before reviewing role requests.");
      return;
    }

    setProcessingDecision({ requestId: request.id, action });

    try {
      const updatedRequest =
        action === "approve"
          ? await approveRoleRequest(request.id, decisionReason, csrfToken)
          : await rejectRoleRequest(request.id, decisionReason, csrfToken);

      setRoleRequests((requests) =>
        requests.map((existingRequest) =>
          existingRequest.id === updatedRequest.id ? updatedRequest : existingRequest
        )
      );
      setDecisionReasons((currentReasons) => ({
        ...currentReasons,
        [request.id]: ""
      }));
      setSuccessMessage(
        action === "approve" ? "Role request approved." : "Role request rejected."
      );
    } catch (error) {
      setDecisionError(
        formatRoleRequestError(error, `Role request ${action} failed.`)
      );
    } finally {
      setProcessingDecision(null);
    }
  }

  return (
    <article className="role-upgrade-panel admin-role-requests-panel">
      <div className="role-upgrade-panel__header">
        <p className="eyebrow">Role upgrade review</p>
        <h1 id="workspace-title">Admin Role Requests</h1>
        <p className="subtitle">
          Review role upgrade requests only. Approving a request changes the
          requester's role after their next auth refresh.
        </p>
        <div className="role-upgrade-panel__chips" aria-label="Admin review safeguards">
          <span>Existing approval flow</span>
          <span>Role-only decision</span>
          <span>No policy changes</span>
        </div>
      </div>

      {isLoadingRequests ? (
        <p className="status-copy">Loading admin role requests...</p>
      ) : null}

      {loadError ? (
        <p className="form-message form-message--error" role="alert">
          {loadError}
        </p>
      ) : null}

      {decisionError ? (
        <p className="form-message form-message--error" role="alert">
          {decisionError}
        </p>
      ) : null}

      {successMessage ? (
        <p className="form-message form-message--success" role="status">
          {successMessage}
        </p>
      ) : null}

      {!isLoadingRequests && !loadError && roleRequests.length === 0 ? (
        <p className="status-copy">No role upgrade requests to review.</p>
      ) : null}

      {!isLoadingRequests && !loadError && roleRequests.length > 0 ? (
        <ul className="role-request-list admin-role-request-list">
          {roleRequests.map((request) => {
            const requesterName = request.requester?.fullName ?? "Unknown requester";
            const requesterEmail = request.requester?.email ?? "No requester email";
            const decisionReasonId = `decision-reason-${request.id}`;
            const isPending = request.status === "pending";
            const isApproving =
              processingDecision?.requestId === request.id &&
              processingDecision.action === "approve";
            const isRejecting =
              processingDecision?.requestId === request.id &&
              processingDecision.action === "reject";
            const isProcessing = processingDecision !== null;

            return (
              <li key={request.id} className="admin-role-request-list__item">
                <div className="admin-role-request-card__summary">
                  <div>
                    <h2>{requesterName}</h2>
                    <p>{requesterEmail}</p>
                  </div>
                  <span
                    className="role-request-status-badge"
                    data-status={request.status}
                  >
                    {formatRequestStatus(request.status)}
                  </span>
                </div>

                <dl className="admin-role-request-details">
                  <div>
                    <dt>Requested role</dt>
                    <dd>{formatRole(request.requestedRole)}</dd>
                  </div>
                  <div>
                    <dt>Reason</dt>
                    <dd>{request.reason ?? "No reason provided."}</dd>
                  </div>
                  {request.decisionReason ? (
                    <div>
                      <dt>Decision reason</dt>
                      <dd>{request.decisionReason}</dd>
                    </div>
                  ) : null}
                </dl>

                {isPending ? (
                  <div className="admin-role-request-decision">
                    <div className="form-field">
                      <label htmlFor={decisionReasonId}>
                        Decision reason for {requesterName}
                      </label>
                      <textarea
                        id={decisionReasonId}
                        rows={3}
                        value={decisionReasons[request.id] ?? ""}
                        onChange={(event) =>
                          setDecisionReasons((currentReasons) => ({
                            ...currentReasons,
                            [request.id]: event.target.value
                          }))
                        }
                      />
                    </div>

                    <div className="admin-role-request-actions">
                      <button
                        type="button"
                        className="primary-action-button"
                        aria-label={`Approve role request from ${requesterName}`}
                        disabled={isProcessing}
                        onClick={() => void handleDecision(request, "approve")}
                      >
                        {isApproving ? "Approving..." : "Approve request"}
                      </button>
                      <button
                        type="button"
                        className="secondary-danger-button"
                        aria-label={`Reject role request from ${requesterName}`}
                        disabled={isProcessing}
                        onClick={() => void handleDecision(request, "reject")}
                      >
                        {isRejecting ? "Rejecting..." : "Reject request"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="status-copy">
                    This role request has already been {request.status}.
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
    </article>
  );
}

function hasPermission(user: AuthUser, permission: PermissionKey): boolean {
  return user.permissions.includes(permission);
}

function hasAnyPermission(user: AuthUser, permissions: PermissionKey[]): boolean {
  return permissions.some((permission) => hasPermission(user, permission));
}

function getRoleUpgradeOptions(
  currentRole: AuthUser["role"]
): Array<{ value: RoleUpgradeTarget; label: string }> {
  if (currentRole === null || currentRole === "user") {
    return ROLE_UPGRADE_OPTIONS;
  }

  const currentRoleIndex = ROLE_UPGRADE_ORDER.indexOf(currentRole);
  if (currentRoleIndex === -1) {
    return ROLE_UPGRADE_OPTIONS;
  }

  return ROLE_UPGRADE_OPTIONS.filter(
    (option) => ROLE_UPGRADE_ORDER.indexOf(option.value) > currentRoleIndex
  );
}

function formatLoginError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Demo login is unavailable right now.";
}

function formatLogoutError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Logout failed. Try again.";
}

function formatRoleRequestError(error: unknown, fallbackMessage: string): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return fallbackMessage;
}

function formatRole(role: AuthUser["role"]): string {
  if (!role) {
    return "Unassigned";
  }

  return role.charAt(0).toUpperCase() + role.slice(1);
}

function getDashboardRoleSummary(
  role: AuthUser["role"],
  hasFreeQueryAccess: boolean,
  hasTechnicalVisibility: boolean
): { title: string; description: string } {
  if (role === "admin") {
    return {
      title: "Admin governance view",
      description:
        "Admins can move into Ask Data, review technical tabs there, and use the existing admin navigation without any dashboard-side execution controls."
    };
  }

  if (hasTechnicalVisibility) {
    return {
      title: "Analyst technical view",
      description:
        "Analysts can ask governed questions and review technical tabs inside Ask Data while this dashboard stays focused on safe status and navigation."
    };
  }

  if (hasFreeQueryAccess) {
    return {
      title: "Manager analytics view",
      description:
        "Managers can open Ask Data for approved templates or permitted free questions. SQL and diagnostics remain hidden from this dashboard and from manager views."
    };
  }

  return {
    title: "Template-only workspace",
    description:
      "Use approved templates as the safe starting point for this role. Free questions, SQL visibility, and diagnostics stay unavailable unless a role upgrade is approved."
  };
}

function formatRequestStatus(status: RoleRequestStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function getInitialTheme(): ThemeMode {
  const storedTheme = getStoredTheme();
  if (storedTheme) {
    return storedTheme;
  }

  if (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  ) {
    return "dark";
  }

  return "light";
}

function getStoredTheme(): ThemeMode | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    return storedTheme === "light" || storedTheme === "dark" ? storedTheme : null;
  } catch {
    return null;
  }
}

function applyTheme(theme: ThemeMode) {
  if (typeof document === "undefined") {
    return;
  }

  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.dataset.theme = theme;

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Theme persistence is a convenience; the visual theme still applies.
  }
}
