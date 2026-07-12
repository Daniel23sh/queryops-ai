import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent
} from "@dnd-kit/core";
import {
  rectSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates
} from "@dnd-kit/sortable";

import { useDashboardCardOrder } from "../hooks/useDashboardCardOrder";
import type { Dashboard, DashboardVisibilityScope } from "../types";
import { SortableDashboardCard } from "./SortableDashboardCard";

export function DashboardCardGrid({
  canExportCards,
  canRefreshCards,
  csrfToken,
  dashboard,
  onReload
}: {
  canExportCards: boolean;
  canRefreshCards: boolean;
  csrfToken: string | null;
  dashboard: Dashboard;
  onReload: () => Promise<void>;
}) {
  const { cards, isSaving, moveCard, saveState } = useDashboardCardOrder({
    dashboard,
    csrfToken
  });
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 }
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates
    })
  );
  const reorderDisabled = isSaving || csrfToken === null;
  const canReorder = cards.length > 1;

  function handleDragEnd(event: DragEndEvent) {
    const activeCardId = String(event.active.id);
    const overCardId = event.over ? String(event.over.id) : null;
    if (!overCardId || activeCardId === overCardId || reorderDisabled) {
      return;
    }

    const targetIndex = cards.findIndex((card) => card.id === overCardId);
    if (targetIndex >= 0) {
      void moveCard(activeCardId, targetIndex);
    }
  }

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
          {cards.length} {cards.length === 1 ? "card" : "cards"}
        </span>
      </header>

      {cards.length > 0 ? (
        <DndContext
          accessibility={{
            announcements: {
              onDragCancel: ({ active }) => `${cardTitle(active.id)} was returned to its original order.`,
              onDragEnd: ({ active, over }) =>
                over
                  ? `${cardTitle(active.id)} was moved to the position of ${cardTitle(over.id)}.`
                  : `${cardTitle(active.id)} was not moved.`,
              onDragOver: ({ active, over }) =>
                over
                  ? `${cardTitle(active.id)} is over ${cardTitle(over.id)}.`
                  : undefined,
              onDragStart: ({ active }) => `Picked up ${cardTitle(active.id)}.`
            },
            screenReaderInstructions: {
              draggable:
                "Press space to pick up a card. Use arrow keys to move it, then press space to drop it."
            }
          }}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
          sensors={sensors}
        >
          <SortableContext
            disabled={!canReorder || reorderDisabled}
            items={cards.map((card) => card.id)}
            strategy={rectSortingStrategy}
          >
            <div className="dashboard-card-grid">
              {cards.map((card, index) => (
                <SortableDashboardCard
                  key={card.id}
                  canExport={canExportCards}
                  canRefresh={canRefreshCards}
                  card={card}
                  csrfToken={csrfToken}
                  index={index}
                  isReorderDisabled={!canReorder || reorderDisabled}
                  onMoveCard={(cardId, targetIndex) => void moveCard(cardId, targetIndex)}
                  showOrderControls={canReorder}
                  totalCards={cards.length}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      ) : (
        <p className="dashboard-saved-panel__state">
          No cards saved in this dashboard yet.
        </p>
      )}

      {saveState.status === "saving" || saveState.status === "success" ? (
        <p className="dashboard-card-order-status" aria-live="polite" role="status">
          {saveState.message}
        </p>
      ) : null}

      {saveState.status === "error" ? (
        <div className="dashboard-card-order-error" role="alert">
          <p>{saveState.message}</p>
          {saveState.canReload ? (
            <button
              type="button"
              className="qops-button-secondary qops-focus-ring"
              onClick={() => void onReload()}
            >
              Reload dashboard
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  );

  function cardTitle(cardId: string | number) {
    return cards.find((card) => card.id === String(cardId))?.title ?? "Dashboard card";
  }
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
