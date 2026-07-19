import { useState } from "react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { cancelActionRequest } from "../../api/actions";
import { ApiError } from "../../api/client";
import type { AuthUser } from "../../auth/types";
import { ActionRecordList } from "./components/ActionRecordList";
import { ActionStatusBadge } from "./components/ActionStatusBadge";
import { CancelActionDialog } from "./components/CancelActionDialog";
import { useActionDetail } from "./hooks/useActionDetail";
import { actionTitle, formatActionDate } from "./presentation";
import type { ActionDetail, ActionTimelineEvent } from "./types";

export function ActionRequestPage({ user, csrfToken }: { user: AuthUser; csrfToken: string | null }) {
  const { actionRequestId } = useParams();
  const detailState = useActionDetail(actionRequestId);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  if (detailState.status === "loading") return <PageState title="Loading action request…" />;
  if (detailState.status === "not-found") return <PageState title="Action request unavailable" description="This request does not exist or is not available to your account." />;
  if (detailState.status === "error" || !detailState.detail) return <PageState title="Action request could not be loaded" action={<button className="qops-button-secondary" onClick={() => void detailState.reload()} type="button">Try again</button>} />;
  const detail = detailState.detail;
  const requesterOwns = detail.timeline?.some((event) => event.event_type === "action_requested" && event.actor?.id === user.id) ?? false;
  const canCancel = requesterOwns && detail.status === "pending_approval";

  async function confirmCancel() {
    if (!csrfToken || !actionRequestId || cancelBusy || !cancelReason.trim()) return;
    setCancelBusy(true);
    setCancelError(null);
    try {
      await cancelActionRequest(actionRequestId, cancelReason.trim(), csrfToken);
      setCancelOpen(false);
      setCancelReason("");
      await detailState.reload();
    } catch (error: unknown) {
      if (error instanceof ApiError && error.status === 409) {
        setCancelError("The request status changed before cancellation. The latest status has been loaded.");
        await detailState.reload();
      } else {
        setCancelError(error instanceof ApiError ? error.message : "The request could not be cancelled safely.");
      }
    } finally {
      setCancelBusy(false);
    }
  }

  return (
    <article className="mx-auto grid w-full max-w-[960px] gap-5" aria-labelledby="action-request-title">
      <Link className="text-sm font-bold text-brand-primary" to="/actions">← Back to Actions</Link>
      <header className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5 shadow-card sm:grid-cols-[minmax(0,1fr)_auto]">
        <div><p className="m-0 text-xs font-bold uppercase tracking-wide text-brand-primary">Action Request</p><h1 className="mb-0 mt-1 text-2xl font-bold text-app-text" id="action-request-title">{actionTitle(detail.action_type)}</h1><p className="mb-0 mt-2 text-sm text-app-subtle">{detail.scope.display_name ?? detail.scope.key ?? "Current Scope"} · Priority {detail.priority}</p></div>
        <div className="sm:text-right"><ActionStatusBadge status={detail.status} /><p className="mb-0 mt-2 text-xs text-app-subtle">Expires: {formatActionDate(detail.expires_at)}</p></div>
      </header>
      <StatusTracker detail={detail} />
      <DetailSummary detail={detail} />
      <section className="grid gap-4 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="snapshot-title"><h2 className="m-0 text-lg font-bold text-app-text" id="snapshot-title">Preview Snapshot</h2><h3 className="m-0 text-sm font-bold text-app-text">Eligible</h3><ActionRecordList records={detail.preview.eligible_records} emptyMessage="No eligible records remain in this snapshot." /><h3 className="m-0 text-sm font-bold text-app-text">Skipped</h3><ActionRecordList records={detail.preview.skipped_records} emptyMessage="No skipped records." /><h3 className="m-0 text-sm font-bold text-app-text">Requires Admin</h3>{user.role === "manager" ? <p className="m-0 rounded-control bg-app-muted p-3 text-sm text-app-subtle">{detail.preview.override_required_records.length} records require Admin review. Record-level privileged details are hidden.</p> : <ActionRecordList records={detail.preview.override_required_records} emptyMessage="No records require an Admin override." />}</section>
      <ApprovalSection detail={detail} />
      <Timeline events={detail.timeline ?? []} />
      <section className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="controls-title"><h2 className="m-0 text-lg font-bold text-app-text" id="controls-title">Request Controls</h2>{canCancel ? <button className="qops-button-secondary justify-self-start" onClick={() => { setCancelError(null); setCancelOpen(true); }} type="button">Cancel Request</button> : <p className="m-0 text-sm text-app-subtle">This request has no requester action available in its current state.</p>}{detail.status === "expired" && !detail.submitted_at ? <p className="m-0 text-sm text-app-subtle">This draft preview expired. <Link className="font-bold text-brand-primary" to="/ask">Return to Ask Data</Link> and run a current result to create a new preview.</p> : null}</section>
      {cancelOpen ? <CancelActionDialog busy={cancelBusy} error={cancelError} reason={cancelReason} onChange={setCancelReason} onClose={() => { if (!cancelBusy) setCancelOpen(false); }} onConfirm={() => void confirmCancel()} /> : null}
    </article>
  );
}

function DetailSummary({ detail }: { detail: ActionDetail }) {
  const summary = detail.preview.summary;
  const affected = summary.affected_license_assignment_count ?? summary.affected_users_count ?? summary.affected_user_count ?? 0;
  return <section className="grid gap-4 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="summary-title"><h2 className="m-0 text-lg font-bold text-app-text" id="summary-title">Summary</h2><dl className="m-0 grid gap-3 sm:grid-cols-3"><Metric label="Actionable" value={affected} /><Metric label="Skipped" value={summary.skipped_count ?? detail.preview.skipped_records.length} /><Metric label="Requires Admin" value={detail.requires_admin ? "Yes" : "No"} /></dl><p className="m-0 text-sm text-app-subtle"><strong className="text-app-text">Reason:</strong> {detail.reason ?? "No requester reason is available."}</p><p className="m-0 text-xs text-app-faint">Created {formatActionDate(detail.created_at)} · Updated {formatActionDate(detail.updated_at)}</p></section>;
}

function ApprovalSection({ detail }: { detail: ActionDetail }) {
  return <section className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="approval-title"><h2 className="m-0 text-lg font-bold text-app-text" id="approval-title">Approval Status</h2>{detail.approval ? <dl className="m-0 grid gap-2 text-sm sm:grid-cols-3"><Metric label="Status" value={detail.approval.status.replace(/_/g, " ")} /><Metric label="Required approver" value={detail.approval.required_approver_role.replace(/_/g, " ")} /><Metric label="Expires" value={formatActionDate(detail.approval.expires_at)} /></dl> : <p className="m-0 text-sm text-app-subtle">This request has not been submitted for approval.</p>}</section>;
}

function Timeline({ events }: { events: ActionTimelineEvent[] }) {
  return <section className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="timeline-title"><h2 className="m-0 text-lg font-bold text-app-text" id="timeline-title">Timeline</h2>{events.length ? <ol className="m-0 grid gap-3 pl-5">{events.map((event, index) => <li key={`${event.event_type}-${event.created_at}-${index}`}><p className="m-0 text-sm font-bold text-app-text">{event.summary}</p><p className="mb-0 mt-1 text-xs text-app-subtle">{formatActionDate(event.timestamp ?? event.created_at)}{event.actor ? ` · ${event.actor.display_name}` : ""}{event.self_approved ? " · Self-approved" : ""}</p></li>)}</ol> : <p className="m-0 text-sm text-app-subtle">No persisted lifecycle events are available.</p>}</section>;
}

function StatusTracker({ detail }: { detail: ActionDetail }) {
  const eventTypes = new Set((detail.timeline ?? []).map((event) => event.event_type));
  const stages = [
    ["Preview Created", eventTypes.has("action_preview_created")],
    ["Submitted", eventTypes.has("action_requested")],
    ["Pending Approval", eventTypes.has("action_requested")],
    ["Approved", eventTypes.has("action_approved") || eventTypes.has("action_executed")],
    ["Executed", eventTypes.has("action_executed")],
    ["Audited", eventTypes.has("action_executed") || eventTypes.has("action_failed")]
  ] as const;
  return <section className="rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-label="Persisted action status tracker"><ol className="m-0 grid list-none gap-2 p-0 sm:grid-cols-3 lg:grid-cols-6">{stages.map(([label, reached]) => <li className={reached ? "rounded-control border border-status-success/40 bg-status-success/10 p-3 text-xs font-bold text-status-success" : "rounded-control border border-app-border bg-app-muted p-3 text-xs font-semibold text-app-faint"} key={label}>{reached ? "Recorded: " : "Not recorded: "}{label}</li>)}</ol></section>;
}

function Metric({ label, value }: { label: string; value: number | string }) { return <div className="rounded-control bg-app-muted p-3"><dt className="text-xs font-bold text-app-faint">{label}</dt><dd className="m-0 mt-1 font-bold capitalize text-app-text">{value}</dd></div>; }
function PageState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) { return <section className="mx-auto grid w-full max-w-[760px] gap-3 rounded-card border border-app-border bg-app-surface p-8 text-center" role="status"><h1 className="m-0 text-2xl font-bold text-app-text">{title}</h1>{description ? <p className="m-0 text-sm text-app-subtle">{description}</p> : null}{action ? <div>{action}</div> : null}<Link className="text-sm font-bold text-brand-primary" to="/actions">Back to Actions</Link></section>; }
