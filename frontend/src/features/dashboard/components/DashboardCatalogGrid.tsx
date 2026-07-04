import type { Dashboard } from "../types";
import { DashboardCatalogItem } from "./DashboardCatalogItem";

export function DashboardCatalogGrid({ dashboards }: { dashboards: Dashboard[] }) {
  return (
    <div className="dashboard-catalog-grid">
      {dashboards.map((dashboard) => (
        <DashboardCatalogItem dashboard={dashboard} key={dashboard.id} />
      ))}
    </div>
  );
}
