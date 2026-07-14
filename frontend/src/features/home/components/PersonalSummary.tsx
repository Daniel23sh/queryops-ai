import { Clock3, LayoutDashboard, PanelsTopLeft, SearchCheck } from "lucide-react";

import type { PersonalSummary as PersonalSummaryData } from "../types";

export function PersonalSummary({ summary }: { summary: PersonalSummaryData }) {
  const items = [
    {
      icon: LayoutDashboard,
      label: "Owned dashboards",
      value: summary.owned_dashboard_count
    },
    {
      icon: PanelsTopLeft,
      label: "Shared dashboards",
      value: summary.shared_dashboard_count
    },
    { icon: SearchCheck, label: "Saved cards", value: summary.owned_card_count },
    {
      icon: Clock3,
      label: "Successful queries · 30 days",
      value: summary.successful_queries_last_30_days
    }
  ];

  return (
    <section className="home-section" aria-labelledby="personal-summary-title">
      <div className="home-section__heading">
        <p className="eyebrow">Your workspace</p>
        <h2 id="personal-summary-title">Personal summary</h2>
      </div>
      <div className="home-personal-grid">
        {items.map((item) => (
          <article className="home-summary-card" key={item.label}>
            <item.icon aria-hidden="true" size={18} />
            <span>{item.label}</span>
            <strong>{formatInteger(item.value)}</strong>
          </article>
        ))}
        {summary.pending_own_role_requests > 0 ? (
          <article className="home-summary-card home-summary-card--attention">
            <Clock3 aria-hidden="true" size={18} />
            <span>Pending role requests</span>
            <strong>{formatInteger(summary.pending_own_role_requests)}</strong>
          </article>
        ) : null}
      </div>
    </section>
  );
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}
