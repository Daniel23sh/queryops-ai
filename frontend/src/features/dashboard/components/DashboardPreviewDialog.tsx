import { TableProperties, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { useNavigate } from "react-router-dom";

import { dashboardPath } from "../../../app/routeConfig";
import type { DashboardLibraryItem } from "../types";

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function DashboardPreviewDialog({
  dashboard,
  onClose,
  opener
}: {
  dashboard: DashboardLibraryItem;
  onClose: () => void;
  opener: HTMLButtonElement | null;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)
      );
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      opener?.focus();
    };
  }, [onClose, opener]);

  return (
    <div
      className="dashboard-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        aria-labelledby={titleId}
        aria-modal="true"
        className="dashboard-preview-dialog"
        ref={dialogRef}
        role="dialog"
      >
        <header className="dashboard-preview-dialog__header">
          <div>
            <span className="dashboard-library-card__badges">
              <span className={`dashboard-badge dashboard-badge--${dashboard.relationship}`}>
                {dashboard.relationship === "owned" ? "Owned" : "Shared"}
              </span>
              <span className="dashboard-badge">{dashboard.scope.display_name}</span>
            </span>
            <h2 id={titleId}>{dashboard.title}</h2>
          </div>
          <button
            aria-label="Close dashboard preview"
            className="dashboard-dialog-close qops-focus-ring"
            onClick={onClose}
            ref={closeRef}
            type="button"
          >
            <X aria-hidden="true" size={22} />
          </button>
        </header>
        <div className="dashboard-preview-dialog__body">
          {dashboard.description ? <p>{dashboard.description}</p> : null}
          <dl className="dashboard-preview-dialog__meta">
            {dashboard.owner ? (
              <div>
                <dt>Owner</dt>
                <dd>{dashboard.owner.display_name}</dd>
              </div>
            ) : null}
            <div>
              <dt>Scope</dt>
              <dd>{dashboard.scope.display_name}</dd>
            </div>
            <div>
              <dt>Cards</dt>
              <dd>{dashboard.card_count}</dd>
            </div>
            <div>
              <dt>Last updated</dt>
              <dd>{formatDate(dashboard.updated_at)}</dd>
            </div>
          </dl>
          <div className="dashboard-preview-dialog__cards" aria-label="Card preview">
            {dashboard.preview_cards.slice(0, 4).map((card) => (
              <article key={card.id}>
                <TableProperties aria-hidden="true" size={17} />
                <strong>{card.title}</strong>
                <span className="dashboard-preview-lines" aria-hidden="true">
                  <i />
                  <i />
                </span>
              </article>
            ))}
            {dashboard.preview_cards.length === 0 ? (
              <p className="dashboard-preview-dialog__empty">No saved cards yet.</p>
            ) : null}
          </div>
        </div>
        <footer className="dashboard-preview-dialog__footer">
          <button className="qops-button-secondary qops-focus-ring" onClick={onClose} type="button">
            Close
          </button>
          <button
            className="qops-button-primary qops-focus-ring"
            onClick={() => {
              onClose();
              navigate(dashboardPath(dashboard.id));
            }}
            type="button"
          >
            Open dashboard
          </button>
        </footer>
      </div>
    </div>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Recently"
    : new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(date);
}
