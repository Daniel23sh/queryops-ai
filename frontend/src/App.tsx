import { useState, type ReactNode } from "react";

import { demoLogin, type DemoLoginResult } from "./api/auth";
import { ApiError } from "./api/client";
import { useAuth } from "./auth/AuthProvider";
import type { AuthUser, PermissionKey } from "./auth/types";

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
  canView: (user: AuthUser) => boolean;
};

const PLACEHOLDER_SCOPE_NOTICE =
  "No Query Engine, SQL execution, dashboards, actions, approvals, audit UI, or backend feature is implemented here.";

const WORKSPACE_NAV_ITEMS: NavItem[] = [
  {
    id: "templates",
    label: "Templates",
    title: "Templates placeholder",
    summary: "Future approved query templates will appear here.",
    canView: () => true
  },
  {
    id: "my-dashboard",
    label: "My Dashboard",
    title: "My Dashboard placeholder",
    summary: "Future personal dashboard cards will appear here.",
    canView: () => true
  },
  {
    id: "ask-data",
    label: "Ask Data",
    title: "Ask Data placeholder",
    summary: "Future governed data questions will start here.",
    canView: (user) => hasPermission(user, "can_run_free_query")
  },
  {
    id: "query-history",
    label: "Query History",
    title: "Query History placeholder",
    summary: "Future department query history will appear here.",
    canView: (user) => hasPermission(user, "can_view_query_history_department")
  },
  {
    id: "sql-technical",
    label: "SQL / Technical",
    title: "SQL / Technical placeholder",
    summary: "Future SQL-visible technical tools will appear here.",
    canView: (user) => hasPermission(user, "can_view_sql")
  },
  {
    id: "department-dashboards",
    label: "Department Dashboards",
    title: "Department Dashboards placeholder",
    summary: "Future department dashboard management will appear here.",
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
    canView: (user) =>
      hasAnyPermission(user, ["can_manage_users", "can_approve_role_requests"])
  },
  {
    id: "users",
    label: "Users",
    title: "Users placeholder",
    summary: "Future user management will appear here.",
    canView: (user) => hasPermission(user, "can_manage_users")
  },
  {
    id: "audit",
    label: "Audit",
    title: "Audit placeholder",
    summary: "Future global audit review will appear here.",
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
        <AuthenticatedWorkspace user={auth.user} onLogout={auth.logout} />
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
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <div className="brand" aria-label="QueryOps AI">
            <span className="brand__name">QueryOps AI</span>
            <span className="brand__phase">Milestone 2 demo auth</span>
          </div>
        </div>
      </header>

      {children}
    </div>
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
  onLogout
}: {
  user: AuthUser;
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
                  {item.label}
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

          <article className="placeholder-panel">
            <p className="placeholder-panel__badge">Placeholder only</p>
            <h1 id="workspace-title">{activeNavItem.title}</h1>
            <p className="subtitle">{activeNavItem.summary}</p>
            <p className="placeholder-panel__scope">{PLACEHOLDER_SCOPE_NOTICE}</p>
          </article>
        </section>
      </div>
    </main>
  );
}

function hasPermission(user: AuthUser, permission: PermissionKey): boolean {
  return user.permissions.includes(permission);
}

function hasAnyPermission(user: AuthUser, permissions: PermissionKey[]): boolean {
  return permissions.some((permission) => hasPermission(user, permission));
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

function formatRole(role: AuthUser["role"]): string {
  if (!role) {
    return "Unassigned";
  }

  return role.charAt(0).toUpperCase() + role.slice(1);
}
