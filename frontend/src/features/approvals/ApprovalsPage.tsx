import { RefreshCw, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { actionTitle, formatActionDate } from "../actions/presentation";
import type { PendingApprovalItem } from "./types";
import { usePendingApprovals } from "./hooks/usePendingApprovals";

const PAGE_SIZE = 20;

export function ApprovalsPage() {
  const [page, setPage] = useState(0);
  const { data, reload, status } = usePendingApprovals({ page, pageSize: PAGE_SIZE });
  const location = useLocation();
  const navigate = useNavigate();
  const routeMessage = workflowMessage(location.state);

  useEffect(() => {
    if (routeMessage) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, navigate, routeMessage]);

  const pageCount = data ? Math.max(1, Math.ceil(data.pagination.total / PAGE_SIZE)) : 1;

  return (
    <article
      className="mx-auto grid w-full max-w-[1180px] gap-5"
      aria-labelledby="approvals-title"
    >
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="m-0 text-xs font-bold uppercase tracking-wide text-brand-primary">
            Decision workspace
          </p>
          <h1 className="mb-0 mt-1 text-3xl font-bold text-app-text" id="approvals-title">
            Approvals
          </h1>
          <p className="mb-0 mt-2 max-w-3xl text-sm leading-6 text-app-subtle">
            Review only action requests that the backend currently authorizes you to decide.
          </p>
        </div>
        <button
          className="qops-button-secondary"
          disabled={status === "loading"}
          onClick={() => void reload()}
          type="button"
        >
          <RefreshCw aria-hidden="true" size={16} />
          Refresh
        </button>
      </header>

      {routeMessage ? (
        <p
          className="m-0 rounded-control border border-status-warning/40 bg-status-warning/10 p-3 text-sm text-app-text"
          role="status"
        >
          {routeMessage}
        </p>
      ) : null}

      {status === "loading" ? (
        <section
          className="rounded-card border border-app-border bg-app-surface p-6 text-sm text-app-subtle"
          role="status"
        >
          Loading approvals waiting for your decision…
        </section>
      ) : null}

      {status === "error" ? (
        <section
          className="grid gap-3 rounded-card border border-status-danger/40 bg-status-danger/10 p-5"
          role="alert"
        >
          <p className="m-0 text-sm text-app-text">
            Pending approvals could not be loaded safely.
          </p>
          <button
            className="qops-button-secondary justify-self-start"
            onClick={() => void reload()}
            type="button"
          >
            Try again
          </button>
        </section>
      ) : null}

      {status === "success" && data?.items.length === 0 ? (
        <section className="rounded-card border border-dashed border-app-border bg-app-surface p-8 text-center">
          <h2 className="m-0 text-lg font-bold text-app-text">No pending approvals</h2>
          <p className="mb-0 mt-2 text-sm text-app-subtle">
            You have no action requests waiting for your approval.
          </p>
        </section>
      ) : null}

      {status === "success" && data?.items.length ? (
        <ApprovalResults items={data.items} />
      ) : null}

      {data && data.pagination.total > PAGE_SIZE ? (
        <nav className="flex items-center justify-between gap-3" aria-label="Approval pagination">
          <button
            className="qops-button-secondary"
            disabled={page === 0 || status === "loading"}
            onClick={() => setPage((value) => Math.max(0, value - 1))}
            type="button"
          >
            Previous
          </button>
          <p className="m-0 text-sm text-app-subtle">
            Page {page + 1} of {pageCount} · {data.pagination.total} approvals
          </p>
          <button
            className="qops-button-secondary"
            disabled={page + 1 >= pageCount || status === "loading"}
            onClick={() => setPage((value) => value + 1)}
            type="button"
          >
            Next
          </button>
        </nav>
      ) : null}
    </article>
  );
}

function ApprovalResults({ items }: { items: PendingApprovalItem[] }) {
  return (
    <>
      <div className="hidden overflow-x-auto rounded-card border border-app-border bg-app-surface md:block">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">Action requests waiting for your approval</caption>
          <thead className="bg-app-muted text-xs uppercase tracking-wide text-app-faint">
            <tr>
              {[
                "Priority",
                "Action",
                "Requester",
                "Scope",
                "Records",
                "Policy",
                "Expiration",
                "Status"
              ].map((label) => (
                <th className="px-4 py-3 font-bold" key={label} scope="col">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-app-border">
            {items.map((item) => (
              <tr key={item.approval_id}>
                <td className="px-4 py-4"><Priority value={item.priority} /></td>
                <td className="px-4 py-4 font-bold">
                  <Link className="text-brand-primary" to={approvalPath(item.approval_id)}>
                    {actionTitle(item.action_type)}
                  </Link>
                </td>
                <td className="px-4 py-4 text-app-subtle">{item.requester.display_name}</td>
                <td className="px-4 py-4 text-app-subtle">{scopeLabel(item)}</td>
                <td className="px-4 py-4 text-app-subtle">
                  {item.affected_count} affected
                  {item.skipped_count ? ` · ${item.skipped_count} skipped` : ""}
                </td>
                <td className="px-4 py-4"><AdminRequirement item={item} /></td>
                <td className="px-4 py-4 text-app-subtle">{expirationLabel(item.expires_at)}</td>
                <td className="px-4 py-4"><ApprovalStatus status={item.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="m-0 grid list-none gap-3 p-0 md:hidden" aria-label="Pending approvals">
        {items.map((item) => (
          <li className="rounded-card border border-app-border bg-app-surface p-4 shadow-card" key={item.approval_id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Priority value={item.priority} />
              <ApprovalStatus status={item.status} />
            </div>
            <h2 className="mb-0 mt-3 text-base font-bold text-app-text">
              <Link className="text-brand-primary" to={approvalPath(item.approval_id)}>
                {actionTitle(item.action_type)}
              </Link>
            </h2>
            <p className="mb-0 mt-2 text-sm text-app-subtle">
              {item.requester.display_name} · {scopeLabel(item)}
            </p>
            <p className="mb-0 mt-2 text-sm text-app-subtle">
              {item.affected_count} affected
              {item.skipped_count ? ` · ${item.skipped_count} skipped` : ""} · {expirationLabel(item.expires_at)}
            </p>
            {item.requires_admin ? <div className="mt-3"><AdminRequirement item={item} /></div> : null}
          </li>
        ))}
      </ul>
    </>
  );
}

function Priority({ value }: { value: PendingApprovalItem["priority"] }) {
  const tone = value === "urgent"
    ? "border-status-danger/40 bg-status-danger/10 text-status-danger"
    : value === "high"
      ? "border-status-warning/40 bg-status-warning/10 text-status-warning"
      : "border-app-border bg-app-muted text-app-subtle";
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold capitalize ${tone}`}>
      {value}
    </span>
  );
}

function ApprovalStatus({ status }: { status: PendingApprovalItem["status"] }) {
  return (
    <span className="inline-flex rounded-full border border-status-warning/40 bg-status-warning/10 px-2.5 py-1 text-xs font-bold capitalize text-status-warning">
      {status}
    </span>
  );
}

function AdminRequirement({ item }: { item: PendingApprovalItem }) {
  if (!item.requires_admin) return <span className="text-xs text-app-faint">Standard review</span>;
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-status-warning/40 bg-status-warning/10 px-2.5 py-1 text-xs font-bold text-status-warning">
      <ShieldAlert aria-hidden="true" size={14} />
      Admin required{item.override_count ? ` · ${item.override_count}` : ""}
    </span>
  );
}

function scopeLabel(item: PendingApprovalItem): string {
  return item.scope.display_name ?? item.scope.key ?? "Current Scope";
}

function expirationLabel(value: string | null): string {
  if (!value) return "Expiration unavailable";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "Expiration unavailable";
  const remaining = timestamp - Date.now();
  if (remaining <= 0) return "Expired";
  const hours = Math.ceil(remaining / 3_600_000);
  if (hours <= 48) return `Expires in ${hours} ${hours === 1 ? "hour" : "hours"}`;
  return `Expires ${formatActionDate(value)}`;
}

function approvalPath(approvalId: string): string {
  return `/approvals/${encodeURIComponent(approvalId)}`;
}

function workflowMessage(state: unknown): string | null {
  if (!state || typeof state !== "object") return null;
  const message = (state as { workflowMessage?: unknown }).workflowMessage;
  return typeof message === "string" ? message : null;
}
