import { Navigate, Outlet, Route, Routes, useOutletContext } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { AskDataPage } from "../features/ask-data";
import { ActionsPage } from "../features/actions/ActionsPage";
import { ActionRequestPage } from "../features/actions/ActionRequestPage";
import { DashboardDetailPage } from "../features/dashboard/DashboardDetailPage";
import { HomePage } from "../features/home/HomePage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { RoleRequestsPage } from "../features/role-requests/RoleRequestsPage";
import { LoginPage } from "../pages/LoginPage";
import {
  AuthenticatedLayout,
  type AuthenticatedOutletContext
} from "./AuthenticatedLayout";
import { AppShell } from "./AppShell";
import { PermissionRoute } from "./PermissionRoute";
import { APP_ROUTES } from "./routeConfig";

export function AppRoutes() {
  return (
    <Routes>
      <Route path={APP_ROUTES.login} element={<LoginRoute />} />
      <Route element={<AuthenticatedRoute />}>
        <Route element={<AuthenticatedLayout />}>
          <Route index element={<DashboardRoute />} />
          <Route path={APP_ROUTES.dashboard} element={<DashboardDetailRoute />} />
          <Route
            path={APP_ROUTES.ask}
            element={
              <PermissionRoute permission="can_use_query_templates">
                <AskDataRoute />
              </PermissionRoute>
            }
          />
          <Route
            path={APP_ROUTES.actions}
            element={
              <PermissionRoute permission="can_request_action">
                <ActionsRoute />
              </PermissionRoute>
            }
          />
          <Route
            path={APP_ROUTES.actionRequest}
            element={
              <PermissionRoute permission="can_request_action">
                <ActionRequestRoute />
              </PermissionRoute>
            }
          />
          <Route path={APP_ROUTES.profile} element={<ProfileRoute />} />
          <Route
            path={APP_ROUTES.adminRoleRequests}
            element={
              <PermissionRoute permission="can_approve_role_requests">
                <AdminRoleRequestsRoute />
              </PermissionRoute>
            }
          />
          <Route path="*" element={<Navigate to={APP_ROUTES.home} replace />} />
        </Route>
      </Route>
    </Routes>
  );
}

function AuthenticatedRoute() {
  const auth = useAuth();

  if (auth.status === "loading") {
    return <AuthLoadingPage />;
  }

  if (auth.status !== "authenticated" || !auth.user) {
    return <Navigate to={APP_ROUTES.login} replace />;
  }

  return <Outlet />;
}

function LoginRoute() {
  const auth = useAuth();

  if (auth.status === "loading") {
    return <AuthLoadingPage />;
  }

  if (auth.status === "authenticated" && auth.user) {
    return <Navigate to={APP_ROUTES.home} replace />;
  }

  return (
    <AppShell>
      <LoginPage onLogin={auth.applyLoginResult} />
    </AppShell>
  );
}

function AuthLoadingPage() {
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

function DashboardRoute() {
  const { csrfToken, user } = useOutletContext<AuthenticatedOutletContext>();

  return <HomePage csrfToken={csrfToken} user={user} />;
}

function DashboardDetailRoute() {
  const { csrfToken, user } = useOutletContext<AuthenticatedOutletContext>();
  return <DashboardDetailPage csrfToken={csrfToken} user={user} />;
}

function AskDataRoute() {
  const { csrfToken, user } = useOutletContext<AuthenticatedOutletContext>();
  return <AskDataPage user={user} csrfToken={csrfToken} />;
}

function ActionsRoute() {
  return <ActionsPage />;
}

function ActionRequestRoute() {
  const { csrfToken, user } = useOutletContext<AuthenticatedOutletContext>();
  return <ActionRequestPage csrfToken={csrfToken} user={user} />;
}

function ProfileRoute() {
  const { csrfToken, user } = useOutletContext<AuthenticatedOutletContext>();
  return <ProfilePage user={user} csrfToken={csrfToken} />;
}

function AdminRoleRequestsRoute() {
  const { csrfToken } = useOutletContext<AuthenticatedOutletContext>();
  return <RoleRequestsPage csrfToken={csrfToken} />;
}
