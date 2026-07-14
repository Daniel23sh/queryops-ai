import type { DashboardLibraryItem } from "../types";
import { DashboardLibraryCard } from "./DashboardLibraryCard";

export function DashboardLibrarySection({
  dashboards,
  onOpen,
  title
}: {
  dashboards: DashboardLibraryItem[];
  onOpen: (dashboard: DashboardLibraryItem, opener: HTMLButtonElement) => void;
  title: string;
}) {
  return (
    <section className="dashboard-library-section" aria-label={title}>
      <div className="dashboard-library-section__heading">
        <h3>{title}</h3>
        <span>{dashboards.length}</span>
      </div>
      <div className="dashboard-library-grid">
        {dashboards.map((dashboard) => (
          <DashboardLibraryCard
            dashboard={dashboard}
            key={dashboard.id}
            onOpen={(opener) => onOpen(dashboard, opener)}
          />
        ))}
      </div>
    </section>
  );
}
