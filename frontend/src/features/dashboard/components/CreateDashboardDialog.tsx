import { X } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { useCreateDashboard } from "../hooks/useCreateDashboard";

export function CreateDashboardDialog({
  csrfToken,
  onClose,
  onCreated,
  opener
}: {
  csrfToken: string | null;
  onClose: () => void;
  onCreated: (title: string) => Promise<void>;
  opener: HTMLElement | null;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const isSavingRef = useRef(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const { createPersonalDashboard, errorMessage, status } =
    useCreateDashboard(csrfToken);
  const isSaving = status === "saving";
  isSavingRef.current = isSaving;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    titleInputRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSavingRef.current) {
        event.preventDefault();
        onClose();
      }
      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }
      const items = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [href]'
        )
      );
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      opener?.focus();
    };
  }, [onClose, opener]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createPersonalDashboard({ title, description });
    if (!created) {
      return;
    }
    await onCreated(created.title);
    onClose();
  }

  return (
    <div
      className="dashboard-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSaving) {
          onClose();
        }
      }}
    >
      <div
        aria-labelledby={titleId}
        aria-modal="true"
        className="dashboard-create-dialog"
        ref={dialogRef}
        role="dialog"
      >
        <header>
          <div>
            <p className="eyebrow">Personal dashboard</p>
            <h2 id={titleId}>New dashboard</h2>
          </div>
          <button
            aria-label="Close new dashboard dialog"
            className="dashboard-dialog-close qops-focus-ring"
            disabled={isSaving}
            onClick={onClose}
            type="button"
          >
            <X aria-hidden="true" size={22} />
          </button>
        </header>
        <form onSubmit={(event) => void handleSubmit(event)}>
          <div className="form-field">
            <label htmlFor="new-dashboard-title">Dashboard title</label>
            <input
              disabled={isSaving}
              id="new-dashboard-title"
              onChange={(event) => setTitle(event.target.value)}
              ref={titleInputRef}
              type="text"
              value={title}
            />
          </div>
          <div className="form-field">
            <label htmlFor="new-dashboard-description">Description (optional)</label>
            <textarea
              disabled={isSaving}
              id="new-dashboard-description"
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              value={description}
            />
          </div>
          <p className="dashboard-create-dialog__visibility">
            Visibility: Personal
          </p>
          {errorMessage ? (
            <p className="form-message form-message--error" role="alert">
              {errorMessage}
            </p>
          ) : null}
          <footer>
            <button
              className="qops-button-secondary qops-focus-ring"
              disabled={isSaving}
              onClick={onClose}
              type="button"
            >
              Cancel
            </button>
            <button
              className="qops-button-primary qops-focus-ring"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? "Creating..." : "Create dashboard"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
