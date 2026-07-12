import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import type { DashboardCard } from "../types";
import { DashboardCardOrderControls } from "./DashboardCardOrderControls";
import { DashboardCardPreview } from "./DashboardCardPreview";

export function SortableDashboardCard({
  canExport,
  canRefresh,
  card,
  csrfToken,
  index,
  isReorderDisabled,
  onMoveCard,
  showOrderControls,
  totalCards
}: {
  canExport: boolean;
  canRefresh: boolean;
  card: DashboardCard;
  csrfToken: string | null;
  index: number;
  isReorderDisabled: boolean;
  onMoveCard: (cardId: string, targetIndex: number) => void;
  showOrderControls: boolean;
  totalCards: number;
}) {
  const {
    attributes,
    isDragging,
    listeners,
    setActivatorNodeRef,
    setNodeRef,
    transform,
    transition
  } = useSortable({ id: card.id, disabled: isReorderDisabled });

  return (
    <div
      className="dashboard-sortable-card"
      data-dragging={isDragging ? "true" : "false"}
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition
      }}
    >
      {showOrderControls ? (
        <DashboardCardOrderControls
          cardTitle={card.title}
          handleAttributes={attributes}
          handleListeners={listeners}
          isDisabled={isReorderDisabled}
          isFirst={index === 0}
          isLast={index === totalCards - 1}
          onMoveDown={() => onMoveCard(card.id, index + 1)}
          onMoveUp={() => onMoveCard(card.id, index - 1)}
          order={index + 1}
          setActivatorNodeRef={setActivatorNodeRef}
        />
      ) : null}
      <DashboardCardPreview
        canExport={canExport}
        canRefresh={canRefresh}
        card={card}
        csrfToken={csrfToken}
      />
    </div>
  );
}
