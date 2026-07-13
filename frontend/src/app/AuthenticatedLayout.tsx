import { useState } from "react";
import { Outlet, useNavigate, type NavigateFunction } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { AuthUser } from "../auth/types";
import { formatRole } from "../lib/format";
import { AppShell } from "./AppShell";
import { AppSidebar } from "./AppSidebar";
import { getVisibleNavItems, type NavItem } from "./navigation";

export type AuthenticatedOutletContext = {
  csrfToken: string | null;
  navigate: NavigateFunction;
  user: AuthUser;
  visibleNavItems: NavItem[];
};

export function AuthenticatedLayout() {
  const auth = useAuth();
  const navigate = useNavigate();
  const user = auth.user as AuthUser;
  const visibleNavItems = getVisibleNavItems(user);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  async function handleLogout() {
    setIsLoggingOut(true);
    setLogoutError(null);

    try {
      await auth.logout();
    } catch (error) {
      setLogoutError(formatLogoutError(error));
      setIsLoggingOut(false);
    }
  }

  return (
    <AppShell>
      <main className="app-main app-main--workspace">
        <div className="workspace-layout">
          <AppSidebar items={visibleNavItems} />

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
                  <dt>Scope</dt>
                  <dd>{getActiveScopeLabel(user)}</dd>
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

            <Outlet
              context={{
                csrfToken: auth.csrfToken,
                navigate,
                user,
                visibleNavItems
              } satisfies AuthenticatedOutletContext}
            />
          </section>
        </div>
      </main>
    </AppShell>
  );
}

function getActiveScopeLabel(user: AuthUser): string {
  return (
    user.scopes.find((scope) => scope.isDefault)?.displayName ??
    user.scopes[0]?.displayName ??
    "No scope assigned"
  );
}

function formatLogoutError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Logout failed. Try again.";
}
