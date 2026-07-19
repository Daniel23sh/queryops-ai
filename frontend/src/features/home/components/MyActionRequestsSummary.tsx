import { Link } from "react-router-dom";

import { ActionSummary } from "../../actions/ActionsPage";
import { useActionRequestSummary } from "../hooks/useActionRequestSummary";

export function MyActionRequestsSummary() {
  const actions = useActionRequestSummary(true);
  return (
    <section className="grid gap-4" aria-labelledby="my-action-requests-title">
      <div className="flex items-end justify-between gap-3"><div><p className="m-0 text-xs font-bold uppercase tracking-wide text-brand-primary">Governed actions</p><h2 className="mb-0 mt-1 text-xl font-bold text-app-text" id="my-action-requests-title">My Action Requests</h2></div><Link className="text-sm font-bold text-brand-primary" to="/actions">View Actions</Link></div>
      {actions.status === "loading" ? <p className="m-0 rounded-card border border-app-border bg-app-surface p-4 text-sm text-app-subtle" role="status">Loading action summary…</p> : null}
      {actions.status === "error" ? <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-status-danger/40 bg-status-danger/10 p-4" role="alert"><p className="m-0 text-sm text-app-text">Action counts are temporarily unavailable. The rest of Home remains available.</p><button className="qops-button-secondary" onClick={() => void actions.reload()} type="button">Try again</button></div> : null}
      {actions.summary ? <ActionSummary summary={actions.summary} /> : null}
    </section>
  );
}
