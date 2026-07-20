import { useRef } from "react";

import { AccessibleOverlay } from "../../../components/ui/AccessibleOverlay";

export type ApprovalDecisionKind = "approve" | "reject";

export function ApprovalDecisionDialog({
  busy,
  error,
  kind,
  onChange,
  onClose,
  onConfirm,
  reason
}: {
  busy: boolean;
  error: string | null;
  kind: ApprovalDecisionKind;
  onChange: (value: string) => void;
  onClose: () => void;
  onConfirm: () => void;
  reason: string;
}) {
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const approving = kind === "approve";
  const title = approving ? "Approve and Execute" : "Reject Request";
  const busyLabel = approving ? "Approving and executing…" : "Rejecting request…";

  return (
    <AccessibleOverlay
      closeDisabled={busy}
      description={
        approving
          ? "Approval revalidates current records and executes synchronously in one governed operation."
          : "Rejection closes this approval without executing the action."
      }
      footer={
        <>
          <button className="qops-button-secondary" disabled={busy} onClick={onClose} type="button">
            Cancel
          </button>
          <button
            className={approving ? "qops-button-primary" : "qops-button-danger"}
            disabled={busy || reason.trim().length < 1 || reason.trim().length > 1000}
            onClick={onConfirm}
            type="button"
          >
            {busy ? busyLabel : title}
          </button>
        </>
      }
      initialFocusRef={reasonRef}
      kind="dialog"
      onClose={onClose}
      title={title}
    >
      <div className="grid gap-4">
        <label className="grid gap-2 text-sm font-bold text-app-text">
          Decision reason
          <textarea
            ref={reasonRef}
            aria-describedby="approval-decision-help"
            className="min-h-28 rounded-control border border-app-border bg-app-surface p-3 text-sm outline-none focus:border-brand-primary focus:shadow-focus"
            disabled={busy}
            maxLength={1000}
            onChange={(event) => onChange(event.target.value)}
            required
            value={reason}
          />
        </label>
        <p className="m-0 text-xs text-app-faint" id="approval-decision-help">
          Required · 1–1000 characters · {reason.length}/1000
        </p>
        {error ? <p className="m-0 text-sm text-status-danger" role="alert">{error}</p> : null}
        {busy ? <p className="m-0 text-sm font-semibold text-app-text" role="status">{busyLabel}</p> : null}
      </div>
    </AccessibleOverlay>
  );
}
