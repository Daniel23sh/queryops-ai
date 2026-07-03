import type { DashboardKpiCard } from "../dashboardModel";

export function DashboardKpiGrid({ cards }: { cards: DashboardKpiCard[] }) {
  return (
    <section className="dashboard-kpi-grid" aria-label="Dashboard status">
      {cards.map((card) => (
        <div key={card.label} className="dashboard-kpi-card" data-tone={card.tone}>
          <p className="dashboard-kpi-card__label">{card.label}</p>
          <p className="dashboard-kpi-card__value">{card.value}</p>
          <p className="dashboard-kpi-card__detail">{card.detail}</p>
        </div>
      ))}
    </section>
  );
}
