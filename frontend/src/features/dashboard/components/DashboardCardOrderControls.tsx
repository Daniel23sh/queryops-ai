import type {
  DraggableAttributes,
  DraggableSyntheticListeners
} from "@dnd-kit/core";

export function DashboardCardOrderControls({
  cardTitle,
  isDisabled,
  isFirst,
  isLast,
  order,
  onMoveDown,
  onMoveUp,
  setActivatorNodeRef,
  handleAttributes,
  handleListeners
}: {
  cardTitle: string;
  isDisabled: boolean;
  isFirst: boolean;
  isLast: boolean;
  order: number;
  onMoveDown: () => void;
  onMoveUp: () => void;
  setActivatorNodeRef: (element: HTMLElement | null) => void;
  handleAttributes: DraggableAttributes;
  handleListeners: DraggableSyntheticListeners;
}) {
  return (
    <div
      className="dashboard-card-order-controls"
      role="group"
      aria-label={`${cardTitle} order controls`}
    >
      <span className="dashboard-card-order-controls__label">Order {order}</span>
      <button
        type="button"
        className="dashboard-card-order-controls__handle qops-focus-ring"
        aria-label={`Reorder ${cardTitle}. Use space then arrow keys to move it.`}
        disabled={isDisabled}
        ref={(element) => setActivatorNodeRef(element)}
        {...handleAttributes}
        {...handleListeners}
      >
        Reorder
      </button>
      <button
        type="button"
        className="dashboard-card-order-controls__button qops-focus-ring"
        aria-label={`Move ${cardTitle} up`}
        disabled={isDisabled || isFirst}
        onClick={onMoveUp}
      >
        Move up
      </button>
      <button
        type="button"
        className="dashboard-card-order-controls__button qops-focus-ring"
        aria-label={`Move ${cardTitle} down`}
        disabled={isDisabled || isLast}
        onClick={onMoveDown}
      >
        Move down
      </button>
    </div>
  );
}
