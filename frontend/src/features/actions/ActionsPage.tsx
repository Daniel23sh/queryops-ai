import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { useOwnActionRequests } from "./hooks/useOwnActionRequests";
import { formatActionDate } from "./presentation";
import type { RequesterActionStatusGroup } from "./types";
import { ActionStatusBadge } from "./components/ActionStatusBadge";

const FILTERS: Array<{ value: RequesterActionStatusGroup; label: string }> = [
  { value: "all", label: "My Requests" },
  { value: "pending", label: "Pending" },
  { value: "completed", label: "Completed" },
  { value: "closed", label: "Failed / Expired / Closed" }
];

export function ActionsPage() {
  const [statusGroup, setStatusGroup] = useState<RequesterActionStatusGroup>("all");
  const [page, setPage] = useState(0);
  const { data, reload, status } = useOwnActionRequests({ statusGroup, page });

  return (
    <article className="mx-auto grid w-full max-w-[1120px] gap-5" aria-labelledby="actions-title">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="m-0 text-xs font-bold uppercase tracking-wide text-brand-primary">Requester workspace</p>
          <h1 className="mb-0 mt-1 text-3xl font-bold text-app-text" id="actions-title">Actions</h1>
          <p className="mb-0 mt-2 text-sm leading-6 text-app-subtle">Track action requests you submitted from governed Ask Data results.</p>
        </div>
        <button className="qops-button-secondary" onClick={() => void reload()} type="button"><RefreshCw aria-hidden="true" size={16} />Refresh</button>
      </header>

      {data ? <ActionSummary summary={data.summary} /> : null}
      <div className="flex gap-1 overflow-x-auto rounded-control bg-app-muted p-1" role="tablist" aria-label="Action request filters">
        {FILTERS.map((filter) => (
          <button
            aria-selected={filter.value === statusGroup}
            className={filter.value === statusGroup ? "min-h-11 shrink-0 rounded-control bg-app-surface px-4 text-sm font-bold text-app-text shadow-sm" : "min-h-11 shrink-0 rounded-control px-4 text-sm font-semibold text-app-subtle hover:text-app-text"}
            key={filter.value}
            onClick={() => { setStatusGroup(filter.value); setPage(0); }}
            role="tab"
            type="button"
          >{filter.label}</button>
        ))}
      </div>

      {status === "loading" ? <section className="rounded-card border border-app-border bg-app-surface p-6 text-sm text-app-subtle" role="status">Loading your action requests…</section> : null}
      {status === "error" ? <section className="grid gap-3 rounded-card border border-status-danger/40 bg-status-danger/10 p-5" role="alert"><p className="m-0 text-sm text-app-text">Your action requests could not be loaded.</p><button className="qops-button-secondary justify-self-start" onClick={() => void reload()} type="button">Try again</button></section> : null}
      {status === "success" && data?.items.length === 0 ? <section className="rounded-card border border-dashed border-app-border bg-app-surface p-8 text-center"><h2 className="m-0 text-lg font-bold text-app-text">{statusGroup === "all" ? "No submitted actions yet" : "No requests in this view"}</h2><p className="mb-0 mt-2 text-sm text-app-subtle">Run an action-aware approved template in Ask Data to start a current preview.</p><Link className="qops-button-primary mt-4 inline-flex" to="/ask">Open Ask Data</Link></section> : null}
      {status === "success" && data?.items.length ? (
        <ul className="m-0 grid list-none gap-3 p-0">
          {data.items.map((item) => (
            <li key={item.id}>
              <Link className="grid gap-3 rounded-card border border-app-border bg-app-surface p-4 text-inherit shadow-card transition hover:border-brand-primary/50 focus:shadow-focus sm:grid-cols-[minmax(0,1fr)_auto]" to={`/actions/${encodeURIComponent(item.id)}`}>
                <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="m-0 text-base font-bold text-app-text">{item.title}</h2><ActionStatusBadge status={item.status} /></div><p className="mb-0 mt-2 text-sm text-app-subtle">{item.scope.display_name ?? item.scope.key ?? "Current Scope"} · {item.record_count} records · Priority {item.priority}</p><p className="mb-0 mt-2 text-sm font-semibold text-app-text">Next: {item.next_step}</p></div>
                <dl className="m-0 grid gap-1 text-xs text-app-subtle sm:text-right"><div><dt className="inline font-bold">Submitted </dt><dd className="m-0 inline">{formatActionDate(item.submitted_at ?? item.created_at)}</dd></div><div><dt className="inline font-bold">Updated </dt><dd className="m-0 inline">{formatActionDate(item.updated_at)}</dd></div></dl>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      {data && data.pagination.total > data.pagination.limit ? (
        <nav className="flex items-center justify-between gap-3" aria-label="Action request pagination">
          <button className="qops-button-secondary" disabled={page === 0 || status === "loading"} onClick={() => setPage((value) => Math.max(0, value - 1))} type="button">Previous</button>
          <p className="m-0 text-sm text-app-subtle">Page {page + 1} of {Math.ceil(data.pagination.total / data.pagination.limit)}</p>
          <button className="qops-button-secondary" disabled={(page + 1) * data.pagination.limit >= data.pagination.total || status === "loading"} onClick={() => setPage((value) => value + 1)} type="button">Next</button>
        </nav>
      ) : null}
    </article>
  );
}

export function ActionSummary({ summary }: { summary: { pending: number; completed: number; closed: number } }) {
  return <dl className="m-0 grid gap-3 sm:grid-cols-3"><SummaryMetric label="Pending" value={summary.pending} /><SummaryMetric label="Completed" value={summary.completed} /><SummaryMetric label="Failed / expired / closed" value={summary.closed} /></dl>;
}

function SummaryMetric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-card border border-app-border bg-app-surface p-4 shadow-card"><dt className="text-xs font-bold uppercase tracking-wide text-app-faint">{label}</dt><dd className="m-0 mt-1 text-2xl font-bold text-app-text">{value}</dd></div>;
}
