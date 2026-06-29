import { useState, type ReactNode } from "react";

import { demoLogin, type DemoLoginResult } from "./api/auth";
import { ApiError } from "./api/client";
import { useAuth } from "./auth/AuthProvider";
import type { AuthUser } from "./auth/types";

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
        <AuthenticatedPlaceholder user={auth.user} />
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

function AuthenticatedPlaceholder({ user }: { user: AuthUser }) {
  return (
    <main className="app-main">
      <section className="workspace-placeholder" aria-labelledby="workspace-title">
        <div className="workspace-placeholder__copy">
          <p className="eyebrow">Signed in</p>
          <h1 id="workspace-title">Authenticated workspace placeholder</h1>
          <p className="subtitle">
            This is the minimal authenticated app area for the demo auth checkpoint.
            Role-based navigation is intentionally left for the next checkpoint.
          </p>
        </div>

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
      </section>
    </main>
  );
}

function formatLoginError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Demo login is unavailable right now.";
}

function formatRole(role: AuthUser["role"]): string {
  if (!role) {
    return "Unassigned";
  }

  return role.charAt(0).toUpperCase() + role.slice(1);
}
