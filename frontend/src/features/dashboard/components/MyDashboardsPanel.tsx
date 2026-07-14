import type { MyDashboardsStatus } from "../hooks/useMyDashboards";
import type { Dashboard } from "../types";
import { DashboardCardGrid } from "./DashboardCardGrid";

const EMPTY_DASHBOARD_MESSAGE =
  "No dashboards or saved cards yet. Run a query in Ask Data and save it to a dashboard.";

export function MyDashboardsPanel({
  canExportCards,
  canRefreshCards,
  csrfToken,
  dashboards,
  errorMessage,
  onReload,
  status
}: {
  canExportCards: boolean;
  canRefreshCards: boolean;
  csrfToken: string | null;
  dashboards: Dashboard[];
  errorMessage: string | null;
  onReload: () => Promise<void>;
  status: MyDashboardsStatus;
}) {
  return (
    <section
      className="dashboard-saved-panel"
      aria-labelledby="dashboard-saved-cards-title"
    >
      <div className="dashboard-section__header">
        <p className="eyebrow">Saved views</p>
        <h2 id="dashboard-saved-cards-title">Your dashboards</h2>
      </div>

      {status === "loading" ? (
        <p className="dashboard-saved-panel__state" aria-live="polite">
          Loading your saved dashboard cards...
        </p>
      ) : null}

      {status === "error" ? (
        <div className="dashboard-saved-panel__state" role="alert">
          <p>{errorMessage ?? "Dashboard cards could not be loaded."}</p>
          <button
            type="button"
            className="qops-button-secondary qops-focus-ring"
            onClick={() => void onReload()}
          >
            Try again
          </button>
        </div>
      ) : null}

      {status === "success" && dashboards.length === 0 ? (
        <p className="dashboard-saved-panel__state">{EMPTY_DASHBOARD_MESSAGE}</p>
      ) : null}

      {status === "success" && dashboards.length > 0 ? (
        <div className="dashboard-saved-list">
          {dashboards.map((dashboard) => (
            <DashboardCardGrid
              key={dashboard.id}
              canExportCards={canExportCards}
              canRefreshCards={canRefreshCards}
              csrfToken={csrfToken}
              dashboard={dashboard}
              onReload={onReload}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}
