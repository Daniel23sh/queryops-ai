import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { APP_ROUTES } from "../../app/routeConfig";
import { hasPermission } from "../../auth/permissions";
import type { AuthUser } from "../../auth/types";
import { formatRole } from "../../lib/format";
import { CreateDashboardPanel } from "./components/CreateDashboardPanel";
import { MyDashboardsPanel } from "./components/MyDashboardsPanel";
import { useMyDashboards } from "./hooks/useMyDashboards";

export function DashboardPage({
  csrfToken,
  user
}: {
  csrfToken: string | null;
  user: AuthUser;
}) {
  const myDashboards = useMyDashboards();
  const canCreatePersonalDashboard = hasPermission(
    user,
    "can_create_personal_dashboard"
  );
  const canUseAskData = hasPermission(user, "can_use_query_templates");
  const canRefreshCards =
    hasPermission(user, "can_query_scoped_data") ||
    hasPermission(user, "can_query_global_data");
  const canExportCards = hasPermission(user, "can_export_results");
  const activeScope =
    user.scopes.find((scope) => scope.isDefault)?.displayName ??
    user.scopes[0]?.displayName ??
    "Not assigned";

  return (
    <article
      className="dashboard-page"
      role="region"
      aria-labelledby="dashboard-title"
    >
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1 id="dashboard-title">My Dashboard</h1>
          <p className="dashboard-header__context">
            {formatRole(user.role)} <span aria-hidden="true">·</span> Scope: {activeScope}
          </p>
        </div>

        {canUseAskData ? (
          <Link
            className="dashboard-ask-link"
            to={APP_ROUTES.ask}
            aria-label="Open Ask Data"
          >
            Ask Data
            <ArrowRight aria-hidden="true" size={18} />
          </Link>
        ) : null}
      </header>

      <MyDashboardsPanel
        canExportCards={canExportCards}
        canRefreshCards={canRefreshCards}
        csrfToken={csrfToken}
        dashboards={myDashboards.dashboards}
        errorMessage={myDashboards.errorMessage}
        onReload={myDashboards.reload}
        status={myDashboards.status}
      />

      {canCreatePersonalDashboard ? (
        <CreateDashboardPanel
          csrfToken={csrfToken}
          onCreated={myDashboards.reload}
        />
      ) : null}
    </article>
  );
}
