import type { DashboardCard } from "../types";
import { DashboardCardPreview } from "./DashboardCardPreview";

export function DashboardViewGrid({
  canExportCards,
  canRefreshCards,
  cards,
  csrfToken
}: {
  canExportCards: boolean;
  canRefreshCards: boolean;
  cards: DashboardCard[];
  csrfToken: string | null;
}) {
  if (cards.length === 0) {
    return <p className="dashboard-detail__empty">No cards saved in this dashboard yet.</p>;
  }

  return (
    <div className="dashboard-card-grid dashboard-card-grid--view">
      {cards.map((card) => (
        <DashboardCardPreview
          canExport={canExportCards}
          canRefresh={canRefreshCards}
          card={card}
          csrfToken={csrfToken}
          key={card.id}
        />
      ))}
    </div>
  );
}
