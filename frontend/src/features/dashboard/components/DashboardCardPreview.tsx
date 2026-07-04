import type { DashboardCard } from "../types";

export function DashboardCardPreview({ card }: { card: DashboardCard }) {
  return (
    <article className="dashboard-card-preview">
      <div className="dashboard-card-preview__header">
        <h4>{card.title}</h4>
        <span className="dashboard-card-pill">{formatCardType(card.card_type)}</span>
      </div>

      {card.description ? (
        <p className="dashboard-card-preview__description">{card.description}</p>
      ) : null}

      <dl className="dashboard-card-preview__meta" aria-label={`${card.title} metadata`}>
        <div>
          <dt>Position</dt>
          <dd>Position {card.position}</dd>
        </div>
      </dl>
    </article>
  );
}

function formatCardType(cardType: string): string {
  if (cardType === "table") {
    return "Table";
  }

  return cardType;
}
