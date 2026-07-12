import type { AuthUser } from "../../auth/types";
import { hasPermission } from "../../auth/permissions";
import type { NavItem } from "../../app/navigation";
import { CreateDashboardPanel } from "./components/CreateDashboardPanel";
import { DashboardHero } from "./components/DashboardHero";
import { DashboardKpiGrid } from "./components/DashboardKpiGrid";
import { DemoActivityPreview } from "./components/DemoActivityPreview";
import { GovernancePosture } from "./components/GovernancePosture";
import { MyDashboardsPanel } from "./components/MyDashboardsPanel";
import { QuickActions } from "./components/QuickActions";
import { buildDashboardModel } from "./dashboardModel";
import { useMyDashboards } from "./hooks/useMyDashboards";

export function DashboardPage({
  csrfToken,
  user,
  visibleNavItems,
  onNavigate
}: {
  csrfToken: string | null;
  user: AuthUser;
  visibleNavItems: NavItem[];
  onNavigate: (navId: string) => void;
}) {
  const model = buildDashboardModel(user, visibleNavItems);
  const myDashboards = useMyDashboards();
  const canRefreshCards =
    hasPermission(user, "can_query_scoped_data") ||
    hasPermission(user, "can_query_global_data");
  const canExportCards = hasPermission(user, "can_export_results");

  return (
    <article className="dashboard-page" role="region" aria-label="My Dashboard">
      <DashboardHero
        departmentLabel={model.departmentLabel}
        roleLabel={model.roleLabel}
      />
      <DashboardKpiGrid cards={model.kpiCards} />
      <MyDashboardsPanel
        canExportCards={canExportCards}
        canRefreshCards={canRefreshCards}
        csrfToken={csrfToken}
        dashboards={myDashboards.dashboards}
        errorMessage={myDashboards.errorMessage}
        onReload={myDashboards.reload}
        status={myDashboards.status}
      />
      <CreateDashboardPanel
        csrfToken={csrfToken}
        onCreated={myDashboards.reload}
        user={user}
      />

      <div className="dashboard-work-grid">
        <QuickActions actions={model.quickActions} onNavigate={onNavigate} />
        <DemoActivityPreview rows={model.activityRows} />
      </div>

      <GovernancePosture cards={model.governanceCards} />

      <section className="dashboard-role-panel" aria-labelledby="dashboard-role-title">
        <p className="eyebrow">What you can do from here</p>
        <h2 id="dashboard-role-title">{model.roleSummary.title}</h2>
        <p>{model.roleSummary.description}</p>
      </section>
    </article>
  );
}
