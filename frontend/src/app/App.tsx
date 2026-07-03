import { useState } from "react";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { AuthUser } from "../auth/types";
import { AskDataPage } from "../features/ask-data";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { RoleRequestsPage } from "../features/role-requests/RoleRequestsPage";
import { RoleUpgradePage } from "../features/role-upgrade/RoleUpgradePage";
import { formatRole } from "../lib/format";
import { LoginPage } from "../pages/LoginPage";
import { PlannedWorkspacePage } from "../pages/PlannedWorkspacePage";
import { AppShell } from "./AppShell";
import { AppSidebar } from "./AppSidebar";
import { WORKSPACE_NAV_ITEMS } from "./navigation";

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
      <LoginPage onLogin={auth.applyLoginResult} />
    </AppShell>
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
        <AppSidebar
          activeNavId={activeNavItem.id}
          items={visibleNavItems}
          onNavigate={setActiveNavId}
        />

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
            <RoleUpgradePage userRole={user.role} csrfToken={csrfToken} />
          ) : activeNavItem.id === "admin-role-requests" ? (
            <RoleRequestsPage csrfToken={csrfToken} />
          ) : (
            <PlannedWorkspacePage item={activeNavItem} user={user} />
          )}
        </section>
      </div>
    </main>
  );
}

function formatLogoutError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Logout failed. Try again.";
}
