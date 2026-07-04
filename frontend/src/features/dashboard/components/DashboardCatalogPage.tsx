import { DashboardCatalogGrid } from "./DashboardCatalogGrid";
import { useDashboardCatalog } from "../hooks/useDashboardCatalog";

export function DashboardCatalogPage() {
  const { dashboards, errorMessage, status } = useDashboardCatalog();

  return (
    <article
      className="dashboard-catalog-page"
      role="region"
      aria-label="Dashboard Catalog"
    >
      <div className="dashboard-catalog-hero">
        <div>
          <p className="eyebrow">Visible dashboards</p>
          <h1 id="dashboard-catalog-title">Dashboard Catalog</h1>
          <p className="subtitle">
            Browse shared dashboards returned by backend visibility rules.
          </p>
        </div>
      </div>

      <section
        className="dashboard-saved-panel"
        aria-labelledby="dashboard-catalog-results-title"
      >
        <div className="dashboard-section__header">
          <p className="eyebrow">Catalog results</p>
          <h2 id="dashboard-catalog-results-title">Visible shared dashboards</h2>
        </div>

        {status === "loading" ? (
          <p className="dashboard-saved-panel__state" aria-live="polite">
            Loading visible dashboards...
          </p>
        ) : null}

        {status === "error" ? (
          <p className="dashboard-saved-panel__state" role="alert">
            {errorMessage ?? "Dashboard catalog could not be loaded."}
          </p>
        ) : null}

        {status === "success" && dashboards.length === 0 ? (
          <p className="dashboard-saved-panel__state">
            No shared dashboards are visible yet.
          </p>
        ) : null}

        {status === "success" && dashboards.length > 0 ? (
          <DashboardCatalogGrid dashboards={dashboards} />
        ) : null}
      </section>
    </article>
  );
}
