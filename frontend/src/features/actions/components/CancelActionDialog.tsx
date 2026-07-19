import { useRef } from "react";

import { AccessibleOverlay } from "../../../components/ui/AccessibleOverlay";

export function CancelActionDialog({
  busy,
  error,
  reason,
  onChange,
  onClose,
  onConfirm
}: {
  busy: boolean;
  error: string | null;
  reason: string;
  onChange: (value: string) => void;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  return (
    <AccessibleOverlay
      closeDisabled={busy}
      description="Cancellation is terminal and does not execute the requested action."
      footer={<><button className="qops-button-secondary" disabled={busy} onClick={onClose} type="button">Keep Request</button><button className="qops-button-primary" disabled={busy || !reason.trim()} onClick={onConfirm} type="button">{busy ? "Cancelling…" : "Cancel Request"}</button></>}
      initialFocusRef={inputRef}
      kind="dialog"
      onClose={onClose}
      title="Cancel this action request?"
    >
      <label className="grid gap-2 text-sm font-bold text-app-text">Cancellation reason<textarea ref={inputRef} className="min-h-28 rounded-control border border-app-border bg-app-surface p-3 text-sm outline-none focus:border-brand-primary focus:shadow-focus" disabled={busy} maxLength={1000} onChange={(event) => onChange(event.target.value)} value={reason} /></label>
      {error ? <p className="mb-0 mt-3 text-sm text-status-danger" role="alert">{error}</p> : null}
    </AccessibleOverlay>
  );
}
