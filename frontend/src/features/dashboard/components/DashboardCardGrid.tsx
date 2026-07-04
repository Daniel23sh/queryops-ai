import type { Dashboard, DashboardVisibilityScope } from "../types";
import { DashboardCardPreview } from "./DashboardCardPreview";

export function DashboardCardGrid({ dashboard }: { dashboard: Dashboard }) {
  return (
    <article className="dashboard-saved-dashboard">
      <header className="dashboard-saved-dashboard__header">
        <div>
          <p className="eyebrow">{formatVisibilityScope(dashboard.visibility_scope)}</p>
          <h3>{dashboard.title}</h3>
          {dashboard.description ? (
            <p className="dashboard-saved-dashboard__description">
              {dashboard.description}
            </p>
          ) : null}
        </div>
        <span className="dashboard-card-count">
          {dashboard.cards.length} {dashboard.cards.length === 1 ? "card" : "cards"}
        </span>
      </header>

      <div className="dashboard-card-grid">
        {dashboard.cards.map((card) => (
          <DashboardCardPreview key={card.id} card={card} />
        ))}
      </div>
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
