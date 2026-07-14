import { TableProperties } from "lucide-react";
import type { DashboardLibraryItem } from "../types";

export function DashboardLibraryCard({
  dashboard,
  onOpen
}: {
  dashboard: DashboardLibraryItem;
  onOpen: (opener: HTMLButtonElement) => void;
}) {
  return (
    <button
      aria-label={`Preview dashboard ${dashboard.title}`}
      className="dashboard-library-card qops-focus-ring"
      onClick={(event) => onOpen(event.currentTarget)}
      type="button"
    >
      <span className="dashboard-library-card__badges">
        <span className={`dashboard-badge dashboard-badge--${dashboard.relationship}`}>
          {dashboard.relationship === "owned" ? "Owned" : "Shared"}
        </span>
        <span className="dashboard-badge">{dashboard.scope.display_name}</span>
      </span>
      <span className="dashboard-library-card__title">{dashboard.title}</span>
      {dashboard.description ? (
        <span className="dashboard-library-card__description">
          {dashboard.description}
        </span>
      ) : null}
      {dashboard.relationship === "shared" && dashboard.owner ? (
        <span className="dashboard-library-card__owner">
          Shared by {dashboard.owner.display_name}
        </span>
      ) : null}
      <span className="dashboard-library-card__preview" aria-hidden="true">
        {dashboard.preview_cards.length > 0 ? (
          dashboard.preview_cards.slice(0, 4).map((card) => (
            <span className="dashboard-library-card__preview-item" key={card.id}>
              <TableProperties size={14} />
              <span>{card.title}</span>
              <i />
            </span>
          ))
        ) : (
          <span className="dashboard-library-card__preview-empty">No saved cards</span>
        )}
      </span>
      <span className="dashboard-library-card__footer">
        <span>
          {dashboard.card_count} {dashboard.card_count === 1 ? "card" : "cards"}
        </span>
        <time dateTime={dashboard.updated_at}>
          Updated {formatDate(dashboard.updated_at)}
        </time>
      </span>
    </button>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "recently";
  }
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric"
  }).format(date);
}
