import { RefreshCw, Search } from "lucide-react";
import { useMemo, useRef, useState, type FormEvent, type RefObject } from "react";
import { Link } from "react-router-dom";

import { hasAnyPermission, hasPermission } from "../../auth/permissions";
import type { AuthUser } from "../../auth/types";
import { AccessibleOverlay } from "../../components/ui/AccessibleOverlay";
import { formatActionDate } from "../actions/presentation";
import { APPROVAL_PERMISSION_KEYS } from "../activity/permissions";
import { useAuditLogs } from "./hooks/useAuditLogs";
import type { AuditLogFilters, AuditLogItem } from "./types";

const PAGE_SIZE = 20;

type FilterDraft = { eventType: string; scopeKey: string; fromDate: string; toDate: string };
const EMPTY_FILTERS: FilterDraft = { eventType: "", scopeKey: "", fromDate: "", toDate: "" };

export function AuditPage({ user }: { user: AuthUser }) {
  const [draft, setDraft] = useState<FilterDraft>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<FilterDraft>(EMPTY_FILTERS);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<AuditLogItem | null>(null);
  const detailsButtonRef = useRef<HTMLElement | null>(null);
  const filters = useMemo<AuditLogFilters>(() => ({
    eventType: applied.eventType || undefined,
    scopeKey: applied.scopeKey || undefined,
    fromDate: applied.fromDate ? `${applied.fromDate}T00:00:00.000Z` : undefined,
    toDate: applied.toDate ? `${applied.toDate}T23:59:59.999Z` : undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE
  }), [applied, page]);
  const audit = useAuditLogs(filters);
  const total = audit.data?.pagination.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const canOpenApprovals = hasAnyPermission(user, APPROVAL_PERMISSION_KEYS);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setPage(0);
    setApplied(draft);
  }

  return (
    <article className="mx-auto grid w-full max-w-[1180px] gap-5" aria-labelledby="audit-title">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="m-0 text-xs font-bold uppercase tracking-wide text-brand-primary">Governed activity</p>
          <h1 className="mb-0 mt-1 text-3xl font-bold text-app-text" id="audit-title">Audit</h1>
          <p className="mb-0 mt-2 max-w-3xl text-sm leading-6 text-app-subtle">
            {hasPermission(user, "can_view_global_audit")
              ? "Review globally authorized workflow events and controlled change details."
              : "Review workflow events returned for your currently assigned Scopes."}
          </p>
        </div>
        <button className="qops-button-secondary" disabled={audit.status === "loading"} onClick={() => void audit.reload()} type="button">
          <RefreshCw aria-hidden="true" size={16} /> Refresh
        </button>
      </header>

      <form className="grid gap-3 rounded-card border border-app-border bg-app-surface p-4 md:grid-cols-4" onSubmit={applyFilters}>
        <FilterInput label="Event type" onChange={(value) => setDraft((current) => ({ ...current, eventType: value }))} value={draft.eventType} />
        <FilterInput label="Scope key" onChange={(value) => setDraft((current) => ({ ...current, scopeKey: value }))} value={draft.scopeKey} />
        <FilterInput label="From date" onChange={(value) => setDraft((current) => ({ ...current, fromDate: value }))} type="date" value={draft.fromDate} />
        <FilterInput label="To date" onChange={(value) => setDraft((current) => ({ ...current, toDate: value }))} type="date" value={draft.toDate} />
        <div className="flex flex-wrap gap-2 md:col-span-4">
          <button className="qops-button-primary" type="submit"><Search aria-hidden="true" size={16} /> Apply filters</button>
          <button className="qops-button-secondary" onClick={() => { setDraft(EMPTY_FILTERS); setApplied(EMPTY_FILTERS); setPage(0); }} type="button">Clear</button>
        </div>
      </form>

      {audit.status === "loading" ? <StatePanel message="Loading authorized audit events…" /> : null}
      {audit.status === "error" ? <StatePanel action={() => void audit.reload()} error message="Audit events could not be loaded safely." /> : null}
      {audit.status === "success" && audit.data?.items.length === 0 ? <StatePanel message="No audit events match the current filters." /> : null}
      {audit.status === "success" && audit.data?.items.length ? (
        <AuditResults
          canOpenApprovals={canOpenApprovals}
          items={audit.data.items}
          onSelect={(item, button) => { detailsButtonRef.current = button; setSelected(item); }}
        />
      ) : null}

      {audit.data && total > PAGE_SIZE ? (
        <nav aria-label="Audit pagination" className="flex items-center justify-between gap-3">
          <button className="qops-button-secondary" disabled={page === 0 || audit.status === "loading"} onClick={() => setPage((value) => Math.max(0, value - 1))} type="button">Previous</button>
          <p className="m-0 text-sm text-app-subtle">Page {page + 1} of {pageCount} · {total} events</p>
          <button className="qops-button-secondary" disabled={page + 1 >= pageCount || audit.status === "loading"} onClick={() => setPage((value) => value + 1)} type="button">Next</button>
        </nav>
      ) : null}

      {selected ? (
        <AuditDetails item={selected} onClose={() => setSelected(null)} returnFocusRef={detailsButtonRef} />
      ) : null}
    </article>
  );
}

function AuditResults({ canOpenApprovals, items, onSelect }: { canOpenApprovals: boolean; items: AuditLogItem[]; onSelect: (item: AuditLogItem, button: HTMLButtonElement) => void }) {
  return (
    <>
      <div className="hidden overflow-x-auto rounded-card border border-app-border bg-app-surface md:block">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">Authorized workflow audit events</caption>
          <thead className="bg-app-muted text-xs uppercase tracking-wide text-app-faint"><tr>{["Event", "Actor", "Target", "Scope", "Timestamp", "Severity", "Status", "Details"].map((label) => <th className="px-4 py-3" key={label} scope="col">{label}</th>)}</tr></thead>
          <tbody className="divide-y divide-app-border">{items.map((item) => (
            <tr key={item.id}>
              <td className="px-4 py-4 font-bold text-app-text">{eventLabel(item.event_type)}</td>
              <td className="px-4 py-4 text-app-subtle">{item.actor?.display_name ?? "System"}</td>
              <td className="px-4 py-4"><AuditTarget canOpenApprovals={canOpenApprovals} item={item} /></td>
              <td className="px-4 py-4 text-app-subtle">{item.scope.key ?? item.scope.type ?? "Global"}</td>
              <td className="px-4 py-4 text-app-subtle">{formatActionDate(item.created_at)}</td>
              <td className="px-4 py-4 capitalize text-app-subtle">{item.severity ?? "—"}</td>
              <td className="px-4 py-4 capitalize text-app-subtle">{item.status?.replace(/_/g, " ") ?? "—"}{item.self_approved === true ? " · Self-approved" : ""}</td>
              <td className="px-4 py-4"><DetailsButton item={item} onSelect={onSelect} /></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <ul aria-label="Authorized workflow audit events" className="m-0 grid list-none gap-3 p-0 md:hidden">{items.map((item) => (
        <li className="grid gap-2 rounded-card border border-app-border bg-app-surface p-4" key={item.id}>
          <div className="flex items-start justify-between gap-3"><strong>{eventLabel(item.event_type)}</strong><span className="text-xs capitalize text-app-subtle">{item.severity ?? "Event"}</span></div>
          <p className="m-0 text-sm text-app-subtle">{item.actor?.display_name ?? "System"} · {item.scope.key ?? item.scope.type ?? "Global"}</p>
          <p className="m-0 text-xs text-app-faint">{formatActionDate(item.created_at)} · {item.status?.replace(/_/g, " ") ?? "No status"}</p>
          <div className="flex items-center justify-between gap-3"><AuditTarget canOpenApprovals={canOpenApprovals} item={item} /><DetailsButton item={item} onSelect={onSelect} /></div>
        </li>
      ))}</ul>
    </>
  );
}

function DetailsButton({ item, onSelect }: { item: AuditLogItem; onSelect: (item: AuditLogItem, button: HTMLButtonElement) => void }) {
  return <button className="text-sm font-bold text-brand-primary" onClick={(event) => onSelect(item, event.currentTarget)} type="button">View details</button>;
}

function AuditTarget({ canOpenApprovals, item }: { canOpenApprovals: boolean; item: AuditLogItem }) {
  if (item.action_request_id) return <Link className="font-bold text-brand-primary" to={`/actions/${encodeURIComponent(item.action_request_id)}`}>Action request</Link>;
  if (item.approval_request_id && canOpenApprovals) return <Link className="font-bold text-brand-primary" to={`/approvals/${encodeURIComponent(item.approval_request_id)}`}>Approval</Link>;
  return <span className="text-app-faint">No linked target</span>;
}

function AuditDetails({ item, onClose, returnFocusRef }: { item: AuditLogItem; onClose: () => void; returnFocusRef: RefObject<HTMLElement> }) {
  return (
    <AccessibleOverlay description="Only fields explicitly returned for your current audit permission are shown." kind="drawer" onClose={onClose} returnFocusRef={returnFocusRef} title="Audit event details">
      <dl className="m-0 grid gap-4 text-sm">
        <Detail label="Event" value={eventLabel(item.event_type)} />
        <Detail label="Summary" value={item.summary ?? "No summary returned"} />
        <Detail label="Actor" value={item.actor?.display_name ?? "System"} />
        <Detail label="Scope" value={item.scope.key ?? item.scope.type ?? "Global"} />
        <Detail label="Timestamp" value={formatActionDate(item.created_at)} />
        {item.self_approved !== undefined ? <Detail label="Self-approved" value={item.self_approved ? "Yes" : "No"} /> : null}
        {item.failure_category !== undefined ? <Detail label="Failure category" value={item.failure_category} /> : null}
      </dl>
      {item.before_state !== undefined || item.after_state !== undefined ? (
        <section className="mt-6 grid gap-3" aria-labelledby="audit-changes-title">
          <h3 className="m-0 text-base font-bold" id="audit-changes-title">Changed fields</h3>
          <ChangedFields after={item.after_state ?? null} before={item.before_state ?? null} />
        </section>
      ) : null}
    </AccessibleOverlay>
  );
}

function ChangedFields({ after, before }: { after: Record<string, unknown> | null; before: Record<string, unknown> | null }) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])).sort();
  if (!keys.length) return <p className="m-0 text-sm text-app-subtle">No changed fields were returned.</p>;
  return <dl className="m-0 grid gap-2">{keys.map((key) => <div className="rounded-control bg-app-muted p-3" key={key}><dt className="text-xs font-bold text-app-faint">{safeFieldLabel(key)}</dt><dd className="m-0 mt-1 text-sm text-app-text">{safeStateValue(before?.[key])} → {safeStateValue(after?.[key])}</dd></div>)}</dl>;
}

function safeStateValue(value: unknown): string {
  if (value === null || value === undefined) return "Not set";
  if (["string", "number", "boolean"].includes(typeof value)) return String(value);
  return "Updated";
}

function safeFieldLabel(key: string): string {
  const known: Record<string, string> = {
    status: "Status",
    action_status: "Action status",
    approval_status: "Approval status",
    requires_admin: "Requires Admin",
    account_status: "Account status",
    reclaimed_at: "Reclaimed at",
    reclaimed_by_app_user_id: "Reclaimed by"
  };
  return known[key] ?? "Changed field";
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-bold text-app-faint">{label}</dt><dd className="m-0 mt-1 text-app-text">{value}</dd></div>;
}

function FilterInput({ label, onChange, type = "text", value }: { label: string; onChange: (value: string) => void; type?: "text" | "date"; value: string }) {
  return <label className="grid gap-1 text-sm font-bold text-app-text">{label}<input className="min-h-11 rounded-control border border-app-border bg-app-surface px-3 text-sm outline-none focus:border-brand-primary focus:shadow-focus" onChange={(event) => onChange(event.target.value)} type={type} value={value} /></label>;
}

function StatePanel({ action, error = false, message }: { action?: () => void; error?: boolean; message: string }) {
  return <section className={`grid gap-3 rounded-card border p-5 text-sm ${error ? "border-status-danger/40 bg-status-danger/10" : "border-app-border bg-app-surface"}`} role={error ? "alert" : "status"}><p className="m-0">{message}</p>{action ? <button className="qops-button-secondary justify-self-start" onClick={action} type="button">Try again</button> : null}</section>;
}

function eventLabel(value: string): string {
  return value.split("_").filter(Boolean).map((part) => `${part[0]?.toUpperCase() ?? ""}${part.slice(1)}`).join(" ") || "Workflow event";
}
