import { ArrowRight, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { hasAnyPermission, hasPermission } from "../../../auth/permissions";
import type { AuthUser } from "../../../auth/types";
import { actionTitle, formatActionDate } from "../../actions/presentation";
import { APPROVAL_PERMISSION_KEYS, AUDIT_PERMISSION_KEYS } from "../../activity/permissions";
import { useWorkflowActivity } from "../../activity/WorkflowActivityProvider";

export function WorkflowSummary({ user }: { user: AuthUser }) {
  const activity = useWorkflowActivity();
  const canApprove = hasAnyPermission(user, APPROVAL_PERMISSION_KEYS);
  const canViewAudit = hasAnyPermission(user, AUDIT_PERMISSION_KEYS);
  if (!canApprove && !canViewAudit) return null;

  return (
    <section className="grid gap-4 rounded-card border border-app-border bg-app-surface p-5 shadow-card" aria-labelledby="workflow-summary-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="m-0 text-xs font-bold uppercase tracking-wide text-brand-primary">Governed workflows</p>
          <h2 className="mb-0 mt-1 text-lg font-bold text-app-text" id="workflow-summary-title">Approval activity</h2>
        </div>
        <div className="flex flex-wrap gap-3">
          {canApprove ? <Link className="text-sm font-bold text-brand-primary" to="/approvals">Open Approvals <ArrowRight aria-hidden="true" className="inline" size={15} /></Link> : null}
          {canViewAudit ? <Link className="text-sm font-bold text-brand-primary" to="/audit">Open {hasPermission(user, "can_view_global_audit") ? "global" : "scoped"} Audit <ArrowRight aria-hidden="true" className="inline" size={15} /></Link> : null}
        </div>
      </div>
      {canApprove ? (
        <>
          {activity.pendingStatus === "loading" ? <p className="m-0 text-sm text-app-subtle" role="status">Loading pending approvals…</p> : null}
          {activity.pendingStatus === "error" ? <p className="m-0 text-sm text-app-subtle">Pending approvals are temporarily unavailable.</p> : null}
          {activity.pendingStatus === "success" ? <p className="m-0 text-sm text-app-subtle"><strong className="text-app-text">{activity.pendingApprovalCount}</strong> action requests are currently waiting for your decision.</p> : null}
          {activity.pendingApprovals.length ? (
            <ul className="m-0 grid list-none gap-2 p-0">{activity.pendingApprovals.map((approval) => (
              <li className="flex flex-col gap-2 rounded-control bg-app-muted p-3 sm:flex-row sm:items-center sm:justify-between" key={approval.approval_id}>
                <div>
                  <Link className="text-sm font-bold text-brand-primary" to={`/approvals/${encodeURIComponent(approval.approval_id)}`}>{actionTitle(approval.action_type)}</Link>
                  <p className="mb-0 mt-1 text-xs text-app-subtle">{approval.requester.display_name} · expires {formatActionDate(approval.expires_at)}</p>
                </div>
                {hasPermission(user, "can_view_global_audit") && approval.requires_admin ? <span className="inline-flex items-center gap-1 text-xs font-bold text-status-warning"><ShieldAlert aria-hidden="true" size={14} /> Admin required</span> : null}
              </li>
            ))}</ul>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
