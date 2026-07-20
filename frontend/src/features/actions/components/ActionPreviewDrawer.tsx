import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";

import type { Role } from "../../../auth/types";
import { AccessibleOverlay } from "../../../components/ui/AccessibleOverlay";
import { actionTitle } from "../presentation";
import { previewExpired, type ActionPreviewFlow } from "../hooks/useActionPreviewFlow";
import { ActionRecordList } from "./ActionRecordList";

type PreviewTab = "eligible" | "skipped" | "admin" | "policy";

export function ActionPreviewDrawer({
  flow,
  role,
  onClose,
  onReasonChange,
  onRecreate,
  onSubmit
}: {
  flow: ActionPreviewFlow;
  role: Role | null;
  onClose: () => void;
  onReasonChange: (reason: string) => void;
  onRecreate: () => void;
  onSubmit: () => void;
}) {
  const [tab, setTab] = useState<PreviewTab>("eligible");
  const [now, setNow] = useState(Date.now());
  const busy = flow.phase === "creating" || flow.phase === "submitting";
  const expired = flow.preview ? previewExpired(flow.preview, now) : false;

  useEffect(() => {
    if (!flow.preview || expired) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [expired, flow.preview]);

  const preview = flow.preview;
  const footer = (
    <>
      <button className="qops-button-secondary" disabled={busy} onClick={onClose} type="button">Close</button>
      {expired ? (
        <button className="qops-button-primary" disabled={busy} onClick={onRecreate} type="button">Create new preview</button>
      ) : (
        <button
          className="qops-button-primary"
          disabled={busy || !preview || !flow.reason.trim()}
          onClick={onSubmit}
          type="button"
        >
          {flow.phase === "submitting" ? "Submitting…" : "Submit for Approval"}
        </button>
      )}
    </>
  );

  return (
    <AccessibleOverlay
      closeDisabled={busy}
      description={`${preview?.scope.display_name ?? preview?.scope.key ?? "Current Scope"} · ${expiryLabel(preview?.preview_expires_at ?? null, now)}`}
      footer={footer}
      kind="drawer"
      onClose={onClose}
      title={actionTitle(flow.resolution.suggestion.action_type)}
    >
      {flow.phase === "creating" ? (
        <p className="m-0 inline-flex items-center gap-2 text-sm text-app-subtle" role="status">
          <LoaderCircle className="animate-spin" aria-hidden="true" size={18} />Creating a current, governed preview…
        </p>
      ) : null}
      {flow.phase === "preview-error" ? (
        <div className="grid gap-3" role="alert">
          <p className="m-0 text-sm text-status-danger">{flow.error}</p>
          <button className="qops-button-secondary justify-self-start" onClick={onRecreate} type="button">Try again</button>
        </div>
      ) : null}
      {preview ? (
        <div className="grid gap-5">
          <PreviewSummary flow={flow} />
          {expired ? <p className="m-0 rounded-control border border-status-warning/40 bg-status-warning/10 p-3 text-sm text-app-text" role="status">This preview has expired. Create a new preview from the still-current result before submitting.</p> : null}
          <div className="flex gap-1 overflow-x-auto rounded-control bg-app-muted p-1" role="tablist" aria-label="Action preview sections">
            <Tab active={tab === "eligible"} label="Eligible" onClick={() => setTab("eligible")} />
            <Tab active={tab === "skipped"} label="Skipped" onClick={() => setTab("skipped")} />
            <Tab active={tab === "admin"} label="Requires Admin" onClick={() => setTab("admin")} />
            <Tab active={tab === "policy"} label="Policy Details" onClick={() => setTab("policy")} />
          </div>
          <div role="tabpanel" aria-label={`${tab} action preview`}>
            {tab === "eligible" ? <ActionRecordList records={preview.preview.eligible_records} emptyMessage="No records are currently eligible." /> : null}
            {tab === "skipped" ? <ActionRecordList records={preview.preview.skipped_records} emptyMessage="No records were skipped." /> : null}
            {tab === "admin" ? (
              role === "manager" ? (
                <p className="m-0 rounded-control bg-app-muted p-3 text-sm text-app-subtle">{preview.preview.override_required_records.length} records require Admin review. Record-level privileged details are hidden.</p>
              ) : (
                <ActionRecordList records={preview.preview.override_required_records} emptyMessage="No records require an Admin override." />
              )
            ) : null}
            {tab === "policy" ? <PolicyDetails flow={flow} /> : null}
          </div>
          <label className="grid gap-2 text-sm font-bold text-app-text">
            Request reason
            <textarea
              className="min-h-24 rounded-control border border-app-border bg-app-surface p-3 text-sm outline-none focus:border-brand-primary focus:shadow-focus"
              disabled={busy || expired}
              maxLength={1000}
              onChange={(event) => onReasonChange(event.target.value)}
              value={flow.reason}
            />
          </label>
          {flow.phase === "submit-error" ? <p className="m-0 text-sm text-status-danger" role="alert">{flow.error}</p> : null}
          <div className="rounded-control border border-app-border bg-app-muted p-3 text-xs leading-5 text-app-subtle">
            Approval executes synchronously after records are revalidated. Newly ineligible records may be skipped. Every change is audited. V1 does not provide an automatic rollback action.
          </div>
        </div>
      ) : null}
    </AccessibleOverlay>
  );
}

function PreviewSummary({ flow }: { flow: ActionPreviewFlow }) {
  const detail = flow.preview;
  if (!detail) return null;
  const summary = detail.preview.summary;
  const affected = summary.affected_license_assignment_count ?? summary.affected_users_count ?? summary.affected_user_count ?? 0;
  return (
    <dl className="m-0 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Metric label="Actionable" value={affected} />
      <Metric label="Skipped" value={summary.skipped_count ?? detail.preview.skipped_records.length} />
      <Metric label="Admin review" value={summary.override_required_count ?? detail.preview.override_required_records.length} />
      <Metric label="Requires Admin" value={detail.requires_admin ? "Yes" : "No"} />
      {summary.high_confidence_count !== undefined ? <Metric label="High confidence" value={summary.high_confidence_count} /> : null}
      {summary.estimated_monthly_savings ? <Metric label="Est. monthly savings" value={`$${summary.estimated_monthly_savings}`} /> : null}
    </dl>
  );
}

function PolicyDetails({ flow }: { flow: ActionPreviewFlow }) {
  const detail = flow.preview;
  if (!detail) return null;
  return (
    <div className="grid gap-3 text-sm text-app-subtle">
      <p className="m-0">{detail.requires_admin ? "Admin approval is required." : "An eligible Analyst or Admin must approve this request."}</p>
      {detail.preview.policy_flags.length ? <ul className="m-0 pl-5">{detail.preview.policy_flags.map((flag) => <li key={flag.code}>{flag.reason}</li>)}</ul> : <p className="m-0">No additional policy flags were returned.</p>}
      {detail.policy_details ? <p className="m-0">Cross-scope: {detail.policy_details.crosses_scopes ? "Yes" : "No"}. Threshold exceeded: {detail.policy_details.record_count_over_analyst_threshold ? "Yes" : "No"}.</p> : null}
    </div>
  );
}

function Tab({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return <button className={active ? "min-h-10 shrink-0 rounded-control bg-app-surface px-3 text-sm font-bold text-app-text shadow-sm" : "min-h-10 shrink-0 rounded-control px-3 text-sm font-semibold text-app-subtle"} onClick={onClick} role="tab" aria-selected={active} type="button">{label}</button>;
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return <div className="rounded-control bg-app-muted p-3"><dt className="text-xs font-bold text-app-faint">{label}</dt><dd className="m-0 mt-1 text-lg font-bold text-app-text">{value}</dd></div>;
}

function expiryLabel(value: string | null, now: number): string {
  if (!value) return "Expired";
  const remaining = new Date(value).getTime() - now;
  if (!Number.isFinite(remaining) || remaining <= 0) return "Expired";
  const minutes = Math.ceil(remaining / 60_000);
  return `Expires in ${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}
