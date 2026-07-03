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
  "No Query Engine, SQL execution, dashboards, actions, approvals, audit UI, or backend feature is implemented here.";

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
    title: "Templates placeholder",
    summary: "Future approved query templates will appear here.",
    icon: "templates",
    canView: () => true
  },
  {
    id: "my-dashboard",
    label: "My Dashboard",
    title: "My Dashboard placeholder",
    summary: "Future personal dashboard cards will appear here.",
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
    title: "Ask Data placeholder",
    summary: "Future governed data questions will start here.",
    icon: "ask",
    canView: (user) => hasPermission(user, "can_use_query_templates")
  },
  {
    id: "query-history",
    label: "Query History",
    title: "Query History placeholder",
    summary: "Future department query history will appear here.",
    icon: "history",
    canView: (user) => hasPermission(user, "can_view_query_history_department")
  },
  {
    id: "sql-technical",
    label: "SQL / Technical",
    title: "SQL / Technical placeholder",
    summary: "Future SQL-visible technical tools will appear here.",
    icon: "sql",
    canView: (user) => hasPermission(user, "can_view_sql")
  },
  {
    id: "department-dashboards",
    label: "Department Dashboards",
    title: "Department Dashboards placeholder",
    summary: "Future department dashboard management will appear here.",
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
    title: "Admin Console placeholder",
    summary: "Future admin controls will appear here.",
    icon: "admin",
    canView: (user) =>
      hasAnyPermission(user, ["can_manage_users", "can_approve_role_requests"])
  },
  {
    id: "users",
    label: "Users",
    title: "Users placeholder",
    summary: "Future user management will appear here.",
    icon: "users",
    canView: (user) => hasPermission(user, "can_manage_users")
  },
  {
    id: "audit",
    label: "Audit",
    title: "Audit placeholder",
    summary: "Future global audit review will appear here.",
    icon: "audit",
    canView: (user) => hasPermission(user, "can_view_global_audit")
  }
];

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
            <article className="placeholder-panel">
              <p className="placeholder-panel__badge">Placeholder only</p>
              <h1 id="workspace-title">{activeNavItem.title}</h1>
              <p className="subtitle">{activeNavItem.summary}</p>
              <p className="placeholder-panel__scope">{PLACEHOLDER_SCOPE_NOTICE}</p>
            </article>
          )}
        </section>
      </div>
    </main>
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
        ? "Open the current query history workspace placeholder."
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
