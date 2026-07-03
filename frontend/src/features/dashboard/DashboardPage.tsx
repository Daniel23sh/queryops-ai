import type { AuthUser } from "../../auth/types";
import type { NavItem } from "../../app/navigation";
import { DashboardHero } from "./components/DashboardHero";
import { DashboardKpiGrid } from "./components/DashboardKpiGrid";
import { DemoActivityPreview } from "./components/DemoActivityPreview";
import { GovernancePosture } from "./components/GovernancePosture";
import { QuickActions } from "./components/QuickActions";
import { buildDashboardModel } from "./dashboardModel";

export function DashboardPage({
  user,
  visibleNavItems,
  onNavigate
}: {
  user: AuthUser;
  visibleNavItems: NavItem[];
  onNavigate: (navId: string) => void;
}) {
  const model = buildDashboardModel(user, visibleNavItems);

  return (
    <article className="dashboard-page" role="region" aria-label="My Dashboard">
      <DashboardHero
        departmentLabel={model.departmentLabel}
        roleLabel={model.roleLabel}
      />
      <DashboardKpiGrid cards={model.kpiCards} />

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
