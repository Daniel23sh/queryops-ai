import { LogOut, Moon, Sun } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import type { AuthScope, AuthUser } from "../../auth/types";
import { formatRole } from "../../lib/format";
import { useTheme } from "../../app/useTheme";
import { RoleUpgradeSection } from "../role-upgrade/RoleUpgradePage";

export function ProfilePage({
  csrfToken,
  user
}: {
  csrfToken: string | null;
  user: AuthUser;
}) {
  const auth = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const activeScope = getActiveScope(user.scopes);

  async function handleLogout() {
    setIsLoggingOut(true);
    setLogoutError(null);

    try {
      await auth.logout();
    } catch (error) {
      setLogoutError(
        error instanceof ApiError ? error.message : "Logout failed. Try again."
      );
      setIsLoggingOut(false);
    }
  }

  return (
    <article className="profile-page" aria-labelledby="profile-title">
      <header className="profile-page__header">
        <div>
          <p className="eyebrow">Account</p>
          <h1 id="profile-title">Profile</h1>
          <p className="subtitle">
            Review your identity, assigned scopes, appearance, and access requests.
          </p>
        </div>
      </header>

      <section className="profile-section" aria-labelledby="profile-identity-title">
        <div className="profile-section__header">
          <h2 id="profile-identity-title">Identity</h2>
        </div>
        <dl className="profile-detail-grid">
          <ProfileDetail label="Full name" value={user.fullName} />
          <ProfileDetail label="Email" value={user.email} />
          <ProfileDetail label="Role" value={formatRole(user.role)} />
          <ProfileDetail label="Auth mode" value={formatAuthMode(user.authMode)} />
          <ProfileDetail
            label="Active scope"
            value={activeScope?.displayName ?? "Not assigned"}
          />
        </dl>
      </section>

      <section className="profile-section" aria-labelledby="profile-scopes-title">
        <div className="profile-section__header">
          <h2 id="profile-scopes-title">Assigned scopes</h2>
          <p>Scope assignments are enforced by the backend.</p>
        </div>

        {user.scopes.length > 0 ? (
          <ul className="profile-scope-list">
            {user.scopes.map((scope) => (
              <li key={scope.id}>
                <div>
                  <strong>{scope.displayName}</strong>
                  <span>{formatScopeType(scope.type)}</span>
                </div>
                <div className="profile-scope-list__badges">
                  {scope.isDefault ? <span>Default / active</span> : null}
                  {scope.accessLevel ? <span>{formatScopeType(scope.accessLevel)}</span> : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="profile-empty-state">No scopes are assigned.</p>
        )}
      </section>

      <section className="profile-section" aria-labelledby="profile-appearance-title">
        <div className="profile-section__header">
          <h2 id="profile-appearance-title">Appearance</h2>
          <p>Choose the product theme stored for this browser.</p>
        </div>
        <button
          type="button"
          className="profile-theme-button"
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          onClick={toggleTheme}
        >
          <span className="profile-theme-button__icon" aria-hidden="true">
            {theme === "dark" ? <Moon size={20} /> : <Sun size={20} />}
          </span>
          <span>
            <strong>{theme === "dark" ? "Dark" : "Light"}</strong>
            <small>Switch to {theme === "dark" ? "light" : "dark"} mode</small>
          </span>
        </button>
      </section>

      {user.role !== "admin" ? (
        <RoleUpgradeSection csrfToken={csrfToken} userRole={user.role} />
      ) : null}

      <section className="profile-section" aria-labelledby="profile-session-title">
        <div className="profile-section__header">
          <h2 id="profile-session-title">Session</h2>
        </div>
        {logoutError ? (
          <p className="form-message form-message--error" role="alert">
            {logoutError}
          </p>
        ) : null}
        <button
          type="button"
          className="profile-logout-button"
          disabled={isLoggingOut}
          onClick={() => void handleLogout()}
        >
          <LogOut aria-hidden="true" size={18} />
          {isLoggingOut ? "Logging out..." : "Log out"}
        </button>
      </section>
    </article>
  );
}

function ProfileDetail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function getActiveScope(scopes: AuthScope[]): AuthScope | null {
  return scopes.find((scope) => scope.isDefault) ?? scopes[0] ?? null;
}

function formatAuthMode(authMode: string): string {
  return authMode
    .split(/[_-]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ") || "Unknown";
}

function formatScopeType(value: string): string {
  return value
    .split(/[_-]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
