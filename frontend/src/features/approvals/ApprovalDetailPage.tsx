import { CheckCircle2, Clock3, ShieldAlert, XCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { approveApproval, rejectApproval } from "../../api/approvals";
import { ApiError } from "../../api/client";
import { ActionRecordList } from "../actions/components/ActionRecordList";
import { actionTitle, formatActionDate } from "../actions/presentation";
import { useWorkflowActivity } from "../activity/WorkflowActivityProvider";
import {
  ApprovalDecisionDialog,
  type ApprovalDecisionKind
} from "./components/ApprovalDecisionDialog";
import { useApprovalDetail } from "./hooks/useApprovalDetail";
import type {
  ApprovalDecisionResult,
  ApprovalDetail,
  ApprovalTimelineEvent
} from "./types";

const POLICY_MESSAGES: Record<string, string> = {
  record_count_over_analyst_threshold: "This request exceeds the scoped approval threshold.",
  global_scope_request: "This request requires global approval.",
  mandatory_assignment: "A mandatory assignment requires Admin review.",
  exception_assignment: "An exception assignment requires Admin review.",
  service_account_assignment: "A service-account assignment requires Admin review.",
  cross_scope_target: "A target outside the requested Scope requires Admin review.",
  privileged_user: "A privileged user requires Admin review.",
  open_critical_security_event: "An open critical security event requires Admin review."
};

export function ApprovalDetailPage({
  csrfToken
}: {
  csrfToken: string | null;
}) {
  const { approvalId } = useParams();
  const navigate = useNavigate();
  const activity = useWorkflowActivity();
  const detailState = useApprovalDetail(approvalId);
  const [decisionKind, setDecisionKind] = useState<ApprovalDecisionKind | null>(null);
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionResult, setDecisionResult] = useState<ApprovalDecisionResult | null>(null);
  const [workflowMessage, setWorkflowMessage] = useState<string | null>(null);
  const [decisionLocked, setDecisionLocked] = useState(false);

  if (detailState.status === "loading") return <PageState title="Loading approval…" />;
  if (detailState.status === "not-found") {
    return (
      <PageState
        title="Approval unavailable"
        description="This approval does not exist or is not available to your account."
      />
    );
  }
  if (detailState.status === "error" || !detailState.detail) {
    return (
      <PageState
        title="Approval could not be loaded"
        action={<button className="qops-button-secondary" onClick={() => void detailState.reload()} type="button">Try again</button>}
      />
    );
  }

  const detail = detailState.detail;
  const canApprove = detail.viewer_capabilities.can_approve && !decisionLocked && !decisionResult;
  const canReject = detail.viewer_capabilities.can_reject && !decisionLocked && !decisionResult;

  async function decide() {
    if (!decisionKind || decisionBusy) return;
    const normalizedReason = decisionReason.trim();
    if (!normalizedReason || normalizedReason.length > 1000) {
      setDecisionError("Enter a decision reason between 1 and 1000 characters.");
      return;
    }
    if (!csrfToken) {
      setDecisionError("Your session is missing a CSRF token. Sign in again, then retry.");
      return;
    }

    setDecisionBusy(true);
    setDecisionError(null);
    try {
      const result = decisionKind === "approve"
        ? await approveApproval(detail.approval_id, normalizedReason, csrfToken)
        : await rejectApproval(detail.approval_id, normalizedReason, csrfToken);
      setDecisionResult(result);
      setDecisionLocked(true);
      setDecisionKind(null);
      setDecisionReason("");
      setWorkflowMessage(decisionResultMessage(result));
      await Promise.allSettled([
        activity.refreshAll(),
        detailState.reload({ preserveOnNotFound: true })
      ]);
    } catch (error: unknown) {
      if (!(error instanceof ApiError)) {
        setDecisionError("The decision could not be completed safely. Try again.");
        return;
      }
      if (error.code === "POLICY_OVERRIDE_REQUIRED") {
        setDecisionKind(null);
        await activity.refreshAll();
        const outcome = await detailState.reload({ preserveOnNotFound: true });
        if (outcome === "not-found") {
          navigate("/approvals", {
            replace: true,
            state: {
              workflowMessage: "Current policy now requires an authorized Admin. This approval is no longer available in your queue."
            }
          });
        } else {
          setWorkflowMessage("Current policy now requires an authorized Admin. No action was executed.");
        }
        return;
      }
      if (error.code === "ACTION_ALREADY_PROCESSED") {
        setDecisionKind(null);
        setDecisionLocked(true);
        setWorkflowMessage("Another participant or operation already completed this decision. The latest available state was loaded.");
        await Promise.allSettled([
          activity.refreshAll(),
          detailState.reload({ preserveOnNotFound: true })
        ]);
        return;
      }
      if (error.code === "ACTION_REQUEST_EXPIRED") {
        setDecisionKind(null);
        setDecisionLocked(true);
        setWorkflowMessage("This request expired. The requester must create and submit a new preview.");
        await Promise.allSettled([
          activity.refreshAll(),
          detailState.reload({ preserveOnNotFound: true })
        ]);
        return;
      }
      if (error.code === "APPROVAL_NOT_FOUND" || error.status === 404) {
        navigate("/approvals", {
          replace: true,
          state: { workflowMessage: "This approval is unavailable or your access has changed." }
        });
        return;
      }
      if (error.status === 401 || error.status === 403) {
        setDecisionError("Your session or approval access changed. Sign in again or refresh your access before retrying.");
        return;
      }
      setDecisionError("The decision could not be completed safely. Refresh and try again.");
    } finally {
      setDecisionBusy(false);
    }
  }

  return (
    <article className="mx-auto grid w-full max-w-[1040px] gap-5" aria-labelledby="approval-detail-title">
      <Link className="text-sm font-bold text-brand-primary" to="/approvals">← Back to Approvals</Link>

      <header className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5 shadow-card sm:grid-cols-[minmax(0,1fr)_auto]">
        <div>
          <p className="m-0 text-xs font-bold uppercase tracking-wide text-brand-primary">Approval review</p>
          <h1 className="mb-0 mt-1 text-2xl font-bold text-app-text" id="approval-detail-title">
            {actionTitle(detail.action_type)}
          </h1>
          <p className="mb-0 mt-2 text-sm text-app-subtle">
            Requested by {detail.requester.display_name} · {scopeLabel(detail)} · Priority {detail.priority}
          </p>
        </div>
        <div className="sm:text-right">
          <span className="inline-flex rounded-full border border-status-warning/40 bg-status-warning/10 px-3 py-1 text-xs font-bold capitalize text-status-warning">
            {detail.status}
          </span>
          <p className="mb-0 mt-2 text-xs text-app-subtle">Approval expires {formatActionDate(detail.expires_at)}</p>
        </div>
      </header>

      {workflowMessage ? (
        <p className="m-0 rounded-control border border-status-warning/40 bg-status-warning/10 p-3 text-sm text-app-text" role="status">
          {workflowMessage}
        </p>
      ) : null}

      {decisionResult ? <DecisionResult result={decisionResult} /> : null}
      <ApprovalSummary detail={detail} previewGeneratedAt={detailState.previewGeneratedAt} previewExpiresAt={detailState.previewExpiresAt} />
      <PolicyReview detail={detail} />

      <section className="grid gap-4 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="approval-preview-title">
        <div>
          <h2 className="m-0 text-lg font-bold text-app-text" id="approval-preview-title">Persisted Preview</h2>
          <p className="mb-0 mt-1 text-sm text-app-subtle">Review context only. The server revalidates current records before execution.</p>
        </div>
        <h3 className="m-0 text-sm font-bold text-app-text">Eligible records</h3>
        <ActionRecordList records={detail.preview.eligible_records} emptyMessage="No eligible records are present in this snapshot." />
        <h3 className="m-0 text-sm font-bold text-app-text">Skipped records</h3>
        <ActionRecordList records={detail.preview.skipped_records} emptyMessage="No skipped records are present." />
        <h3 className="m-0 text-sm font-bold text-app-text">Admin-override records</h3>
        <ActionRecordList records={detail.preview.override_required_records} emptyMessage="No records require an Admin override." />
      </section>

      <Timeline events={detail.timeline} />
      <ViewerCapabilities detail={detail} />

      <section className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="approval-controls-title">
        <div>
          <h2 className="m-0 text-lg font-bold text-app-text" id="approval-controls-title">Decision</h2>
          <p className="mb-0 mt-1 text-sm text-app-subtle">Both decisions require a reason. Approval executes synchronously after authoritative revalidation.</p>
        </div>
        {canApprove || canReject ? (
          <div className="flex flex-wrap gap-3">
            {canApprove ? <button className="qops-button-primary" onClick={() => openDecision("approve")} type="button">Approve and Execute</button> : null}
            {canReject ? <button className="qops-button-danger" onClick={() => openDecision("reject")} type="button">Reject Request</button> : null}
          </div>
        ) : (
          <p className="m-0 text-sm text-app-subtle">No decision control is available for your current access and this approval state.</p>
        )}
      </section>

      {decisionKind ? (
        <ApprovalDecisionDialog
          busy={decisionBusy}
          error={decisionError}
          kind={decisionKind}
          onChange={setDecisionReason}
          onClose={() => { if (!decisionBusy) setDecisionKind(null); }}
          onConfirm={() => void decide()}
          reason={decisionReason}
        />
      ) : null}
    </article>
  );

  function openDecision(kind: ApprovalDecisionKind) {
    setDecisionError(null);
    setDecisionReason("");
    setDecisionKind(kind);
  }
}

function ApprovalSummary({
  detail,
  previewGeneratedAt,
  previewExpiresAt
}: {
  detail: ApprovalDetail;
  previewGeneratedAt: string | null;
  previewExpiresAt: string | null;
}) {
  const impact = Object.entries(detail.estimated_impact).filter(([, value]) => value !== null && value !== undefined);
  return (
    <section className="grid gap-4 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="approval-summary-title">
      <h2 className="m-0 text-lg font-bold text-app-text" id="approval-summary-title">Impact Summary</h2>
      <dl className="m-0 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Affected" value={detail.affected_count} />
        <Metric label="Skipped" value={detail.skipped_count} />
        <Metric label="Admin override" value={detail.override_count} />
        <Metric label="Requires Admin" value={detail.requires_admin ? "Yes" : "No"} />
        {impact.map(([key, value]) => <Metric key={key} label={impactLabel(key)} value={impactValue(key, value)} />)}
      </dl>
      <p className="m-0 text-sm text-app-subtle"><strong className="text-app-text">Requester reason:</strong> {detail.reason}</p>
      <div className="grid gap-1 text-xs text-app-faint sm:grid-cols-2">
        <p className="m-0">Preview generated: {formatActionDate(previewGeneratedAt)}</p>
        <p className="m-0">Preview expired: {formatActionDate(previewExpiresAt)}</p>
        <p className="m-0">Approval expires: {formatActionDate(detail.expires_at)}</p>
      </div>
    </section>
  );
}

function PolicyReview({ detail }: { detail: ApprovalDetail }) {
  return (
    <section className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="policy-review-title">
      <div className="flex items-center gap-2">
        {detail.requires_admin ? <ShieldAlert aria-hidden="true" className="text-status-warning" size={19} /> : <CheckCircle2 aria-hidden="true" className="text-status-success" size={19} />}
        <h2 className="m-0 text-lg font-bold text-app-text" id="policy-review-title">Policy Review</h2>
      </div>
      {detail.policy_flags.length ? (
        <ul className="m-0 grid gap-2 pl-5 text-sm text-app-subtle">
          {detail.policy_flags.map((flag, index) => (
            <li key={`${flag.code}-${index}`}>{POLICY_MESSAGES[flag.code] ?? "Additional governed policy review is required."}</li>
          ))}
        </ul>
      ) : <p className="m-0 text-sm text-app-subtle">No additional policy flags were returned.</p>}
    </section>
  );
}

function ViewerCapabilities({ detail }: { detail: ApprovalDetail }) {
  const capabilities = detail.viewer_capabilities;
  return (
    <section className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="viewer-capabilities-title">
      <h2 className="m-0 text-lg font-bold text-app-text" id="viewer-capabilities-title">Your Current Capabilities</h2>
      <ul className="m-0 grid list-none gap-2 p-0 text-sm text-app-subtle sm:grid-cols-2">
        <Capability allowed={capabilities.can_approve} label="Approve this request" />
        <Capability allowed={capabilities.can_reject} label="Reject this request" />
        <Capability allowed={capabilities.can_execute_on_approval} label="Execute synchronously on approval" />
        <Capability allowed={capabilities.self_approval} label="Self-approval permitted" />
      </ul>
    </section>
  );
}

function Capability({ allowed, label }: { allowed: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 rounded-control bg-app-muted p-3">
      {allowed ? <CheckCircle2 aria-hidden="true" className="text-status-success" size={17} /> : <XCircle aria-hidden="true" className="text-app-faint" size={17} />}
      {label}: {allowed ? "Yes" : "No"}
    </li>
  );
}

function Timeline({ events }: { events: ApprovalTimelineEvent[] }) {
  return (
    <section className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="approval-timeline-title">
      <h2 className="m-0 text-lg font-bold text-app-text" id="approval-timeline-title">Persisted Timeline</h2>
      {events.length ? (
        <ol className="m-0 grid gap-3 pl-5">
          {events.map((event, index) => (
            <li key={`${event.event_type}-${event.timestamp}-${index}`}>
              <p className="m-0 text-sm font-bold text-app-text">{event.summary}</p>
              <p className="mb-0 mt-1 text-xs text-app-subtle">
                {formatActionDate(event.timestamp)}{event.actor ? ` · ${event.actor.display_name}` : ""}{event.self_approved ? " · Self-approved" : ""}
              </p>
            </li>
          ))}
        </ol>
      ) : <p className="m-0 text-sm text-app-subtle">No persisted lifecycle events are available.</p>}
    </section>
  );
}

function DecisionResult({ result }: { result: ApprovalDecisionResult }) {
  const failed = result.status === "failed";
  return (
    <section className={`grid gap-2 rounded-card border p-5 ${failed ? "border-status-danger/40 bg-status-danger/10" : "border-status-success/40 bg-status-success/10"}`} role="status">
      <h2 className="m-0 text-lg font-bold text-app-text">{failed ? "Execution did not complete" : "Decision recorded"}</h2>
      <p className="m-0 text-sm text-app-subtle">
        {failed
          ? "The server returned a safe failed result. No technical details are available here."
          : `Authoritative result: ${result.status.replace(/_/g, " ")}.`}
      </p>
      {result.executed_records_count !== undefined ? <p className="m-0 text-sm text-app-subtle">Executed {result.executed_records_count} records · Skipped {result.skipped_records_count ?? 0}</p> : null}
      <Link className="justify-self-start text-sm font-bold text-brand-primary" to={`/actions/${encodeURIComponent(result.action_request_id)}`}>Open resulting Action Request</Link>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return <div className="rounded-control bg-app-muted p-3"><dt className="text-xs font-bold text-app-faint">{label}</dt><dd className="m-0 mt-1 font-bold text-app-text">{value}</dd></div>;
}

function impactLabel(key: string): string {
  if (key === "estimated_monthly_savings") return "Estimated monthly savings";
  if (key === "override_estimated_monthly_savings") return "Override monthly savings";
  return "Estimated impact";
}

function impactValue(key: string, value: string | number | null): string | number {
  if (value === null) return "Not available";
  return key.includes("savings") ? `$${value}` : value;
}

function scopeLabel(detail: ApprovalDetail): string {
  return detail.scope.display_name ?? detail.scope.key ?? "Current Scope";
}

function decisionResultMessage(result: ApprovalDecisionResult): string {
  if (result.status === "failed") return "Approval was recorded, but execution returned a safe failed result.";
  if (result.status === "rejected") return "The request was rejected and no action was executed.";
  return "Approval and synchronous execution completed with the authoritative server result.";
}

function PageState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <section className="mx-auto grid w-full max-w-[760px] gap-3 rounded-card border border-app-border bg-app-surface p-8 text-center" role="status">
      <Clock3 aria-hidden="true" className="mx-auto text-app-faint" size={24} />
      <h1 className="m-0 text-2xl font-bold text-app-text">{title}</h1>
      {description ? <p className="m-0 text-sm text-app-subtle">{description}</p> : null}
      {action ? <div>{action}</div> : null}
      <Link className="text-sm font-bold text-brand-primary" to="/approvals">Back to Approvals</Link>
    </section>
  );
}
