import { Grip } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ApiError, downloadBlob } from "../../../api/client";
import { exportDashboardCardCsv } from "../../../api/exports";
import { useDashboardCardRefresh } from "../hooks/useDashboardCardRefresh";
import type { DashboardBreakpoint, DashboardCardRefreshResult, EditorDashboardCard } from "../types";
import { VISUALIZATION_LABELS } from "../visualization";
import { DashboardVisualization } from "../visualization/DashboardVisualization";
import { CardContextMenu, type CardMenuAction } from "./CardContextMenu";

type ExportState = "idle" | "loading" | "success" | "error";
type MoveDirection = "down" | "left" | "right" | "up";
type PointerDrag = { pointerId: number; x: number; y: number };

export function DashboardEditorCard({
  breakpoint,
  canExport,
  canRefresh,
  canViewSource,
  card,
  csrfToken,
  editMode,
  isFirst,
  isLast,
  onAction,
  onKeyboardMove,
  onMove,
  onResult
}: {
  breakpoint: DashboardBreakpoint;
  canExport: boolean;
  canRefresh: boolean;
  canViewSource: boolean;
  card: EditorDashboardCard;
  csrfToken: string | null;
  editMode: boolean;
  isFirst: boolean;
  isLast: boolean;
  onAction: (action: CardMenuAction, card: EditorDashboardCard) => void;
  onKeyboardMove: (direction: "down" | "left" | "right" | "up") => void;
  onMove: (direction: -1 | 1) => void;
  onResult: (cardId: string, result: DashboardCardRefreshResult) => void;
}) {
  const refreshState = useDashboardCardRefresh({
    canRefresh: canRefresh && card.saved_query_id !== null,
    cardId: card.id,
    csrfToken
  });
  const [exportState, setExportState] = useState<ExportState>("idle");
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const exportInFlight = useRef(false);
  const pointerDrag = useRef<PointerDrag | null>(null);

  useEffect(() => {
    if (refreshState.result) onResult(card.id, refreshState.result);
  }, [card.id, onResult, refreshState.result]);

  async function exportCsv() {
    if (!csrfToken || exportInFlight.current) return;
    exportInFlight.current = true;
    setExportState("loading");
    setExportMessage(null);
    try {
      downloadBlob(await exportDashboardCardCsv(card.id, csrfToken, { include_headers: true }));
      setExportState("success");
      setExportMessage("CSV downloaded. The export used your current access scope.");
    } catch (error: unknown) {
      setExportState("error");
      setExportMessage(error instanceof ApiError && error.status === 403
        ? "This card cannot be exported with your current permissions."
        : "The CSV export could not be prepared. Try again.");
    } finally {
      exportInFlight.current = false;
    }
  }

  function selectAction(action: CardMenuAction) {
    if (action === "refresh") void refreshState.refresh();
    else if (action === "export") void exportCsv();
    else onAction(action, card);
  }

  return (
    <article
      aria-label={`Dashboard card ${card.title}`}
      className="dashboard-editor-card"
      data-editing={editMode}
      onContextMenu={(event) => {
        if ((event.target as Element).closest("[data-card-menu-trigger]")) return;
        event.preventDefault();
        const target = event.currentTarget.querySelector<HTMLButtonElement>("[data-card-menu-trigger]");
        target?.dispatchEvent(new MouseEvent("contextmenu", {
          bubbles: true,
          clientX: event.clientX,
          clientY: event.clientY
        }));
      }}
      onKeyDown={(event) => {
        if (event.shiftKey && event.key === "F10") {
          event.preventDefault();
          event.currentTarget.querySelector<HTMLButtonElement>("[data-card-menu-trigger]")?.click();
        }
      }}
      tabIndex={0}
    >
      <header className="dashboard-editor-card__header">
        <div>
          <h2>{card.title}</h2>
          <span>{VISUALIZATION_LABELS[card.visualization.type]}</span>
        </div>
        <div className="dashboard-editor-card__controls">
          {editMode && breakpoint !== "mobile" ? (
            <button
              aria-description="Drag with a pointer, or use the arrow keys to move this card."
              aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight"
              aria-label={`Drag ${card.title}`}
              className="dashboard-card-drag-handle"
              type="button"
              onPointerCancel={() => {
                pointerDrag.current = null;
              }}
              onPointerDown={(event) => {
                if (!event.isPrimary || event.button !== 0) return;
                event.preventDefault();
                event.stopPropagation();
                pointerDrag.current = {
                  pointerId: event.pointerId,
                  x: event.clientX,
                  y: event.clientY
                };
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerUp={(event) => {
                const start = pointerDrag.current;
                pointerDrag.current = null;
                if (!start || start.pointerId !== event.pointerId) return;
                event.preventDefault();
                event.stopPropagation();
                if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                  event.currentTarget.releasePointerCapture(event.pointerId);
                }
                const direction = pointerDirection(
                  event.clientX - start.x,
                  event.clientY - start.y
                );
                if (direction) onKeyboardMove(direction);
              }}
              onKeyDown={(event) => {
                const direction = keyboardDirection(event.key);
                if (!direction) return;
                event.preventDefault();
                event.stopPropagation();
                onKeyboardMove(direction);
              }}
            >
              <Grip aria-hidden="true" size={18} />
            </button>
          ) : null}
          <CardContextMenu
            canExport={canExport && card.saved_query_id !== null}
            canRefresh={canRefresh && card.saved_query_id !== null}
            canViewSource={canViewSource && card.saved_query_id !== null}
            cardTitle={card.title}
            editMode={editMode}
            onSelect={selectAction}
          />
        </div>
      </header>
      {card.description ? <p className="dashboard-editor-card__description">{card.description}</p> : null}

      <div className="dashboard-editor-card__content">
        {refreshState.result ? (
          <DashboardVisualization config={card.visualization} result={refreshState.result} title={card.title} />
        ) : refreshState.state.status === "loading" ? (
          <p className="dashboard-editor-card__state" role="status">Refreshing under your current access scope…</p>
        ) : (
          <p className="dashboard-editor-card__state">Refresh this card to load its current scoped result.</p>
        )}
      </div>

      {refreshState.state.status === "error" ? (
        <p className="dashboard-editor-card__error" role="alert">{refreshState.state.message}</p>
      ) : null}
      {exportMessage ? (
        <p className={exportState === "error" ? "dashboard-editor-card__error" : "dashboard-editor-card__status"} role={exportState === "error" ? "alert" : "status"}>
          {exportMessage}
        </p>
      ) : null}
      {editMode && breakpoint === "mobile" ? (
        <footer className="dashboard-editor-card__mobile-controls">
          <button disabled={isFirst} onClick={() => onMove(-1)} type="button">Move up</button>
          <button disabled={isLast} onClick={() => onMove(1)} type="button">Move down</button>
          <button onClick={() => onAction("resize", card)} type="button">Size preset</button>
        </footer>
      ) : null}
      {exportState === "loading" ? <span className="qops-sr-only" role="status">Preparing CSV export…</span> : null}
    </article>
  );
}

function keyboardDirection(key: string): MoveDirection | null {
  if (key === "ArrowDown") return "down";
  if (key === "ArrowLeft") return "left";
  if (key === "ArrowRight") return "right";
  if (key === "ArrowUp") return "up";
  return null;
}

function pointerDirection(deltaX: number, deltaY: number): MoveDirection | null {
  if (Math.max(Math.abs(deltaX), Math.abs(deltaY)) < 24) return null;
  if (Math.abs(deltaX) >= Math.abs(deltaY)) return deltaX < 0 ? "left" : "right";
  return deltaY < 0 ? "up" : "down";
}
