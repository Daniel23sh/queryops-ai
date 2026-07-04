import type { MyDashboardsStatus } from "../hooks/useMyDashboards";
import type { Dashboard } from "../types";
import { DashboardCardGrid } from "./DashboardCardGrid";

const EMPTY_DASHBOARD_MESSAGE =
  "No saved dashboard cards yet. Run a query in Ask Data and save it as a card once Save as Card is enabled.";

export function MyDashboardsPanel({
  dashboards,
  errorMessage,
  status
}: {
  dashboards: Dashboard[];
  errorMessage: string | null;
  status: MyDashboardsStatus;
}) {
  const dashboardsWithCards = dashboards.filter((dashboard) => dashboard.cards.length > 0);

  return (
    <section
      className="dashboard-saved-panel"
      aria-labelledby="dashboard-saved-cards-title"
    >
      <div className="dashboard-section__header">
        <p className="eyebrow">Saved views</p>
        <h2 id="dashboard-saved-cards-title">Saved dashboard cards</h2>
      </div>

      {status === "loading" ? (
        <p className="dashboard-saved-panel__state" aria-live="polite">
          Loading your saved dashboard cards...
        </p>
      ) : null}

      {status === "error" ? (
        <p className="dashboard-saved-panel__state" role="alert">
          {errorMessage ?? "Dashboard cards could not be loaded."}
        </p>
      ) : null}

      {status === "success" && dashboardsWithCards.length === 0 ? (
        <p className="dashboard-saved-panel__state">{EMPTY_DASHBOARD_MESSAGE}</p>
      ) : null}

      {status === "success" && dashboardsWithCards.length > 0 ? (
        <div className="dashboard-saved-list">
          {dashboardsWithCards.map((dashboard) => (
            <DashboardCardGrid key={dashboard.id} dashboard={dashboard} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
