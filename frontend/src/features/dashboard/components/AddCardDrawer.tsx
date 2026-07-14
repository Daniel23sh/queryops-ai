import { Clock3, FilePlus2, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  refreshDashboardCard,
  saveQueryRunAsCard,
  updateDashboardCard
} from "../../../api/dashboards";
import { getQueryHistory, runQuery } from "../../../api/queries";
import { listQueryTemplates } from "../../../api/queryTemplates";
import type { QueryHistoryItem, QueryTemplate } from "../../ask-data/types";
import { inferVisualization, recommendedConfig } from "../visualization";

type Stage = "idle" | "query" | "save" | "refresh" | "visualization" | "success";

export function AddCardDrawer({
  csrfToken,
  dashboardId,
  onClose,
  onDashboardReload
}: {
  csrfToken: string;
  dashboardId: string;
  onClose: () => void;
  onDashboardReload: (message: string) => Promise<void>;
}) {
  const [templates, setTemplates] = useState<QueryTemplate[]>([]);
  const [recent, setRecent] = useState<QueryHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [tab, setTab] = useState<"templates" | "recent">("templates");
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState(false);
  const inFlight = useRef(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    let active = true;
    Promise.all([
      listQueryTemplates(),
      getQueryHistory({ limit: 20, offset: 0, include_sql: false })
    ]).then(([nextTemplates, history]) => {
      if (!active) return;
      setTemplates(nextTemplates);
      setRecent(history.filter((item) => item.status === "succeeded" && item.can_save_as_card === true));
      setLoading(false);
    }).catch(() => {
      if (!active) return;
      setLoadError(true); setLoading(false);
    });
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !inFlight.current) { onClose(); return; }
      if (event.key !== "Tab" || !drawerRef.current) return;
      const focusable = Array.from(drawerRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'));
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (!first || !last) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", escape);
    return () => {
      active = false;
      document.removeEventListener("keydown", escape);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  const normalizedSearch = search.trim().toLocaleLowerCase();
  const visibleTemplates = useMemo(() => templates.filter((template) =>
    !normalizedSearch || `${template.title} ${template.description} ${template.category}`.toLocaleLowerCase().includes(normalizedSearch)
  ), [normalizedSearch, templates]);
  const visibleRecent = useMemo(() => recent.filter((item) =>
    !normalizedSearch || item.natural_language_question.toLocaleLowerCase().includes(normalizedSearch)
  ), [normalizedSearch, recent]);

  async function addTemplate(template: QueryTemplate) {
    if (inFlight.current || created) return;
    inFlight.current = true; setError(null); setStage("query");
    try {
      const result = await runQuery({ question: template.natural_language_question, template_id: template.id }, csrfToken);
      if (result.status !== "succeeded" || !result.query_run_id) throw new StageError("query");
      await saveAndConfigure(result.query_run_id, template.title);
    } catch (caught: unknown) {
      handleStageError(caught, stage === "idle" ? "query" : stage);
    } finally { inFlight.current = false; }
  }

  async function addRecent(item: QueryHistoryItem) {
    if (inFlight.current || created) return;
    inFlight.current = true; setError(null);
    try { await saveAndConfigure(item.id, item.natural_language_question); }
    catch (caught: unknown) { handleStageError(caught, stage === "idle" ? "save" : stage); }
    finally { inFlight.current = false; }
  }

  async function saveAndConfigure(queryRunId: string, title: string) {
    setStage("save");
    let card;
    try {
      card = await saveQueryRunAsCard(queryRunId, { dashboard_id: dashboardId, title }, csrfToken);
    } catch { throw new StageError("save"); }
    setCreated(true);
    await onDashboardReload("Card added. Loading its current scoped result…");

    setStage("refresh");
    let result;
    try { result = await refreshDashboardCard(card.id, csrfToken); }
    catch { throw new StageError("refresh"); }

    setStage("visualization");
    try {
      const recommendation = inferVisualization({ columns: result.columns, rows: result.rows });
      await updateDashboardCard(card.id, { visualization: recommendedConfig(recommendation) }, csrfToken);
    } catch { throw new StageError("visualization"); }

    setStage("success");
    await onDashboardReload("Card added with its recommended visualization.");
    onClose();
  }

  function handleStageError(caught: unknown, fallback: Stage) {
    const failed = caught instanceof StageError ? caught.stage : fallback;
    setStage(failed);
    setError(failed === "query" ? "The template query could not be completed. No card was created."
      : failed === "save" ? "The query succeeded, but it could not be saved as a card. The query remains in your history."
        : failed === "refresh" ? "The card was added, but its first scoped refresh failed. Close this panel and refresh the card from its menu."
          : "The card was added and refreshed, but its recommended visualization could not be saved. It remains safely available as a Table."
    );
  }

  return (
    <div className="dashboard-add-card-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !inFlight.current) onClose(); }}>
      <aside aria-labelledby="add-card-title" aria-modal="true" className="dashboard-add-card" ref={drawerRef} role="dialog">
        <header>
          <div><p className="eyebrow">Dashboard editor</p><h2 id="add-card-title">Add Card</h2><p>Use a governed query source. Result rows stay in memory and are never stored in card configuration.</p></div>
          <button aria-label="Close Add Card" className="dashboard-dialog-close" disabled={inFlight.current} onClick={onClose} ref={closeRef} type="button"><X aria-hidden="true" size={20} /></button>
        </header>
        <div className="dashboard-add-card__body">
          <div className="dashboard-add-card__tabs" role="tablist">
            <button aria-selected={tab === "templates"} onClick={() => setTab("templates")} role="tab" type="button"><FilePlus2 aria-hidden="true" size={16} />Approved templates</button>
            <button aria-selected={tab === "recent"} onClick={() => setTab("recent")} role="tab" type="button"><Clock3 aria-hidden="true" size={16} />Recent results</button>
          </div>
          <label className="dashboard-add-card__search"><Search aria-hidden="true" size={17} /><span className="qops-sr-only">Search Add Card sources</span><input onChange={(event) => setSearch(event.target.value)} placeholder="Search sources" type="search" value={search} /></label>
          {loading ? <p role="status">Loading governed card sources…</p> : loadError ? <p role="alert">Card sources could not be loaded. Try reopening Add Card.</p> : (
            <div className="dashboard-add-card__list">
              {tab === "templates" ? visibleTemplates.map((template) => (
                <article key={template.id}><div><span>{template.category}</span><h3>{template.title}</h3><p>{template.description}</p></div><button disabled={inFlight.current || created} onClick={() => void addTemplate(template)} type="button">{stage === "query" && inFlight.current ? "Running…" : "Run and add"}</button></article>
              )) : visibleRecent.map((item) => (
                <article key={item.id}><div><span>{formatDate(item.completed_at ?? item.created_at)}</span><h3>{item.natural_language_question}</h3><p>{item.row_count} returned {item.row_count === 1 ? "row" : "rows"}</p></div><button disabled={inFlight.current || created} onClick={() => void addRecent(item)} type="button">{stage === "save" && inFlight.current ? "Adding…" : "Add result"}</button></article>
              ))}
              {(tab === "templates" ? visibleTemplates : visibleRecent).length === 0 ? <p>No eligible sources match this search.</p> : null}
            </div>
          )}
          {inFlight.current ? <p className="dashboard-add-card__stage" role="status">{stageLabel(stage)}</p> : null}
          {error ? <div className="dashboard-add-card__error" role="alert"><p>{error}</p>{created ? <button className="qops-button-primary" onClick={onClose} type="button">Return to dashboard</button> : null}</div> : null}
        </div>
      </aside>
    </div>
  );
}

class StageError extends Error {
  constructor(readonly stage: Stage) { super(stage); }
}
function stageLabel(stage: Stage) {
  return stage === "query" ? "Running the approved query…" : stage === "save" ? "Saving the successful query as a card…" : stage === "refresh" ? "Refreshing under your current access scope…" : "Choosing and saving the recommended visualization…";
}
function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Recent" : new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(date);
}
