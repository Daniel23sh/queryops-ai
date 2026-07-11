import type { Dashboard, DashboardVisibilityScope } from "../types";
import { DashboardCardPreview } from "./DashboardCardPreview";

export function DashboardCatalogItem({ dashboard }: { dashboard: Dashboard }) {
  return (
    <article className="dashboard-catalog-item">
      <header className="dashboard-catalog-item__header">
        <div>
          <p className="eyebrow">{formatVisibilityScope(dashboard.visibility_scope)}</p>
          <h2>{dashboard.title}</h2>
          {dashboard.description ? (
            <p className="dashboard-catalog-item__description">
              {dashboard.description}
            </p>
          ) : null}
        </div>
        <span className="dashboard-card-count">
          {dashboard.cards.length} {dashboard.cards.length === 1 ? "card" : "cards"}
        </span>
      </header>

      <dl className="dashboard-catalog-item__meta" aria-label={`${dashboard.title} catalog metadata`}>
        <div>
          <dt>Scope</dt>
          <dd>{formatVisibilityScope(dashboard.visibility_scope)}</dd>
        </div>
        {dashboard.department_id ? (
          <div>
            <dt>Department</dt>
            <dd>Department: {dashboard.department_id}</dd>
          </div>
        ) : null}
      </dl>

      {dashboard.cards.length > 0 ? (
        <div className="dashboard-card-grid">
          {dashboard.cards.map((card) => (
            <DashboardCardPreview
              canExport={false}
              canRefresh={false}
              card={card}
              csrfToken={null}
              key={card.id}
            />
          ))}
        </div>
      ) : (
        <p className="dashboard-saved-panel__state">
          No cards are published in this dashboard yet.
        </p>
      )}
    </article>
  );
}

function formatVisibilityScope(scope: DashboardVisibilityScope): string {
  if (scope === "department") {
    return "Department";
  }

  if (scope === "global") {
    return "Global";
  }

  return "Personal";
}
