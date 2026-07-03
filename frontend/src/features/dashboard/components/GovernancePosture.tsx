import type { DashboardStatusCard } from "../dashboardModel";

export function GovernancePosture({
  cards
}: {
  cards: DashboardStatusCard[];
}) {
  return (
    <section className="dashboard-section" aria-labelledby="dashboard-governance-title">
      <div className="dashboard-section__header">
        <p className="eyebrow">Governance posture</p>
        <h2 id="dashboard-governance-title">Access status</h2>
      </div>
      <div className="dashboard-posture-grid">
        {cards.map((card) => (
          <article
            key={card.title}
            className="dashboard-status-card"
            data-tone={card.tone}
          >
            <span className="dashboard-status-card__marker" aria-hidden="true" />
            <div>
              <h3>{card.title}</h3>
              <p className="dashboard-status-card__status">{card.status}</p>
              <p className="dashboard-status-card__detail">{card.detail}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
