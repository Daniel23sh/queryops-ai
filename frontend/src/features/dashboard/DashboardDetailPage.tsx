import { ArrowLeft, Edit3, Plus, RotateCcw, Save, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  archiveDashboard,
  duplicateDashboard,
  duplicateDashboardCard,
  getDashboardCardSource,
  removeDashboardCard,
  updateDashboard,
  updateDashboardCard,
  updateDashboardEditorLayout
} from "../../api/dashboards";
import { APP_ROUTES, dashboardPath } from "../../app/routeConfig";
import type { AuthUser } from "../../auth/types";
import { DashboardActionMenu, type DashboardMenuAction } from "./components/DashboardActionMenu";
import { AddCardDrawer } from "./components/AddCardDrawer";
import type { CardMenuAction } from "./components/CardContextMenu";
import { DashboardEditorGrid } from "./components/DashboardEditorGrid";
import { EditorDialog } from "./components/EditorDialog";
import { useDashboardDetail } from "./hooks/useDashboardDetail";
import { DashboardVisualization } from "./visualization/DashboardVisualization";
import type {
  CardSource,
  DashboardBreakpoint,
  DashboardCardLayout,
  DashboardCardRefreshResult,
  EditorDashboardCard,
  VisualizationConfig
} from "./types";
import {
  inferVisualization,
  manualConfig,
  recommendedConfig,
  VISUALIZATION_LABELS
} from "./visualization";

type EditorMode = "view" | "edit";
type DialogState =
  | { kind: "dashboard-rename" }
  | { kind: "dashboard-archive" }
  | { kind: "card-rename"; card: EditorDashboardCard }
  | { kind: "card-visualization"; card: EditorDashboardCard }
  | { kind: "card-resize"; card: EditorDashboardCard; breakpoint: DashboardBreakpoint }
  | { kind: "card-remove"; card: EditorDashboardCard }
  | { kind: "card-source"; card: EditorDashboardCard }
  | null;

export function DashboardDetailPage({
  csrfToken
}: {
  csrfToken: string | null;
  user: AuthUser;
}) {
  const { dashboardId } = useParams<{ dashboardId: string }>();
  const detail = useDashboardDetail(dashboardId);
  const navigate = useNavigate();
  const [mode, setMode] = useState<EditorMode>("view");
  const [draftLayouts, setDraftLayouts] = useState<Record<string, DashboardCardLayout>>({});
  const [serverLayouts, setServerLayouts] = useState<Record<string, DashboardCardLayout>>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [addCardOpen, setAddCardOpen] = useState(false);
  const [results, setResults] = useState<Record<string, DashboardCardRefreshResult>>({});
  const [source, setSource] = useState<{ loading: boolean; data: CardSource | null; error: string | null }>({ loading: false, data: null, error: null });
  const sourceRequestRef = useRef<AbortController | null>(null);
  const dashboard = detail.dashboard;
  const effectiveLayouts = useMemo(
    () => dashboard
      ? Object.fromEntries(dashboard.cards.map((card) => [card.id, draftLayouts[card.id] ?? cloneLayout(card.layout)]))
      : {},
    [dashboard, draftLayouts]
  );

  useEffect(() => {
    if (!dashboard) return;
    const next = Object.fromEntries(dashboard.cards.map((card) => [card.id, cloneLayout(card.layout)]));
    setServerLayouts(next);
    setDraftLayouts(next);
    setDirty(false);
    setConflict(false);
  }, [dashboard]);

  useEffect(() => {
    sourceRequestRef.current?.abort();
    setMode("view");
    setDialog(null);
    setAddCardOpen(false);
    setResults({});
    setStatus(null);
    setError(null);
  }, [dashboardId]);

  useEffect(() => () => sourceRequestRef.current?.abort(), []);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const links = (event: MouseEvent) => {
      const anchor = (event.target as Element).closest("a[href]");
      if (anchor && !window.confirm("Discard unsaved dashboard layout changes?")) event.preventDefault();
    };
    const historyNavigation = () => {
      if (!window.confirm("Discard unsaved dashboard layout changes?")) window.history.forward();
      else setDirty(false);
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", links, true);
    window.addEventListener("popstate", historyNavigation);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", links, true);
      window.removeEventListener("popstate", historyNavigation);
    };
  }, [dirty]);

  const onResult = useCallback((cardId: string, result: DashboardCardRefreshResult) => {
    setResults((current) => current[cardId] === result ? current : { ...current, [cardId]: result });
  }, []);

  const updateDraft = useCallback((next: Record<string, DashboardCardLayout>) => {
    setDraftLayouts(next);
    setDirty(layoutFingerprint(next) !== layoutFingerprint(serverLayouts));
    setConflict(false);
  }, [serverLayouts]);
  const closeAddCard = useCallback(() => setAddCardOpen(false), []);

  if (detail.status === "loading" && !dashboard) {
    return <section className="dashboard-detail dashboard-detail--state" aria-live="polite">Loading dashboard…</section>;
  }
  if (detail.status === "not-found") return <DashboardUnavailable title="Dashboard not found" />;
  if (detail.status === "error" || !dashboard) {
    return <DashboardUnavailable onRetry={() => void detail.reload()} title="Dashboard unavailable" />;
  }

  async function saveLayout() {
    if (!dashboard || !csrfToken || saving) return;
    setSaving(true); setError(null); setStatus(null);
    try {
      await updateDashboardEditorLayout(dashboard.id, {
        expected_layout_version: dashboard.layout_version,
        items: dashboard.cards.map((card) => ({
          card_id: card.id,
          desktop: { ...draftLayouts[card.id].desktop },
          tablet: { ...draftLayouts[card.id].tablet },
          mobile: { ...draftLayouts[card.id].mobile }
        }))
      }, csrfToken);
      setStatus("Dashboard layout saved.");
      setDirty(false);
      setMode("view");
      await detail.reload();
    } catch (caught: unknown) {
      if (caught instanceof ApiError && caught.code === "DASHBOARD_LAYOUT_CONFLICT") {
        setConflict(true);
        setError("This dashboard changed in another session. Your draft is still here; reload the latest layout before editing again.");
      } else setError("Dashboard changes could not be saved. Try again.");
    } finally { setSaving(false); }
  }

  function cancelEditing() {
    setDraftLayouts(cloneLayouts(serverLayouts));
    setDirty(false); setConflict(false); setError(null); setMode("view");
  }

  function openCardAction(action: CardMenuAction, card: EditorDashboardCard, breakpoint: DashboardBreakpoint) {
    if (action === "duplicate") { void duplicateCard(card); return; }
    if (action === "source") { setDialog({ kind: "card-source", card }); void loadSource(card); return; }
    const kind = action === "rename" ? "card-rename"
      : action === "visualization" ? "card-visualization"
        : action === "resize" ? "card-resize"
          : action === "remove" ? "card-remove"
            : null;
    if (kind === "card-resize") setDialog({ kind, card, breakpoint });
    else if (kind) setDialog({ kind, card } as DialogState);
  }

  async function duplicateCard(card: EditorDashboardCard) {
    if (!csrfToken) return;
    setError(null);
    try {
      await duplicateDashboardCard(card.id, csrfToken);
      setStatus(`${card.title} duplicated.`);
      await detail.reload();
    } catch { setError("The card could not be duplicated. Try again."); }
  }

  async function loadSource(card: EditorDashboardCard) {
    sourceRequestRef.current?.abort();
    const controller = new AbortController();
    sourceRequestRef.current = controller;
    setSource({ loading: true, data: null, error: null });
    try {
      const data = await getDashboardCardSource(card.id, controller.signal);
      if (!controller.signal.aborted) setSource({ loading: false, data, error: null });
    } catch {
      if (!controller.signal.aborted) setSource({ loading: false, data: null, error: "Source is unavailable with your current access." });
    }
  }

  function closeSourceDialog() {
    sourceRequestRef.current?.abort();
    setDialog(null);
  }

  async function dashboardAction(action: DashboardMenuAction) {
    if (!csrfToken) return;
    if (action === "rename") setDialog({ kind: "dashboard-rename" });
    else if (action === "archive") setDialog({ kind: "dashboard-archive" });
    else {
      setError(null);
      try {
        const copy = await duplicateDashboard(dashboard!.id, csrfToken);
        navigate(dashboardPath(copy.id));
      } catch { setError("The dashboard could not be duplicated. Try again."); }
    }
  }

  function applySize(card: EditorDashboardCard, breakpoint: DashboardBreakpoint, w: number, h: number) {
    const next = cloneLayouts(draftLayouts);
    next[card.id][breakpoint] = { ...next[card.id][breakpoint], w, h };
    repack(next, dashboard!.cards, breakpoint);
    updateDraft(next);
    setDialog(null);
  }

  return (
    <article className="dashboard-detail dashboard-editor" aria-labelledby="dashboard-detail-title">
      <Link className="dashboard-detail__back qops-focus-ring" to={APP_ROUTES.home}><ArrowLeft aria-hidden="true" size={17} />Back to My Dashboard</Link>
      <header className="dashboard-detail__header dashboard-editor__header">
        <div>
          <span className="dashboard-library-card__badges">
            <span className={`dashboard-badge dashboard-badge--${dashboard.relationship}`}>{dashboard.relationship === "owned" ? "Owned" : "Shared"}</span>
            <span className="dashboard-badge">{dashboard.scope.display_name}</span>
          </span>
          <h1 id="dashboard-detail-title">{dashboard.title}</h1>
          {dashboard.description ? <p>{dashboard.description}</p> : null}
          <p className="dashboard-detail__meta">{dashboard.owner ? `Owner: ${dashboard.owner.display_name} · ` : ""}{dashboard.card_count} {dashboard.card_count === 1 ? "card" : "cards"} · Updated {formatDate(dashboard.updated_at)}</p>
        </div>
        <div className="dashboard-editor__header-actions">
          {dashboard.capabilities.can_manage ? (
            <div className="dashboard-editor__mode" aria-label="Dashboard mode" role="group">
              <button aria-pressed={mode === "view"} onClick={() => mode === "edit" ? cancelEditing() : setMode("view")} type="button">View</button>
              <button aria-pressed={mode === "edit"} onClick={() => { setMode("edit"); setStatus(null); }} type="button"><Edit3 aria-hidden="true" size={16} />Edit</button>
            </div>
          ) : null}
          <DashboardActionMenu canDuplicate={dashboard.capabilities.can_duplicate} canManage={dashboard.capabilities.can_manage} onSelect={(action) => void dashboardAction(action)} />
        </div>
      </header>

      {mode === "edit" ? (
        <div className="dashboard-editor__toolbar" aria-label="Dashboard editing controls">
          <div><strong>Edit dashboard</strong><span>{dirty ? "Unsaved layout changes" : "No unsaved layout changes"}</span></div>
          <div>
            {dashboard.capabilities.can_create_cards ? <button className="qops-button-secondary" onClick={() => setAddCardOpen(true)} type="button"><Plus aria-hidden="true" size={17} />Add Card</button> : null}
            <button className="qops-button-secondary" disabled={saving} onClick={cancelEditing} type="button"><X aria-hidden="true" size={17} />Cancel</button>
            <button className="qops-button-primary" disabled={!dirty || saving || !csrfToken} onClick={() => void saveLayout()} type="button"><Save aria-hidden="true" size={17} />{saving ? "Saving…" : "Save changes"}</button>
          </div>
        </div>
      ) : null}

      {conflict ? <div className="dashboard-editor__conflict" role="alert"><p>{error}</p><button className="qops-button-secondary" onClick={() => { setDirty(false); void detail.reload(); }} type="button"><RotateCcw aria-hidden="true" size={16} />Reload latest layout</button></div> : error ? <p className="dashboard-editor__error" role="alert">{error}</p> : null}
      {status ? <p className="dashboard-editor__status" role="status">{status}</p> : null}

      <DashboardEditorGrid
        canExport={dashboard.capabilities.can_export_cards}
        canRefresh={dashboard.capabilities.can_refresh_cards}
        canViewSource={dashboard.capabilities.can_view_source}
        cards={dashboard.cards}
        csrfToken={csrfToken}
        editMode={mode === "edit"}
        layouts={effectiveLayouts}
        onAction={openCardAction}
        onLayoutsChange={updateDraft}
        onResult={onResult}
      />

      {dialog?.kind === "dashboard-rename" ? <RenameDashboardDialog dashboard={dashboard} onClose={() => setDialog(null)} onSaved={async (title, description) => { if (!csrfToken) return; await updateDashboard(dashboard.id, { title, description }, csrfToken); setDialog(null); setStatus("Dashboard renamed."); await detail.reload(); }} /> : null}
      {dialog?.kind === "dashboard-archive" ? <ConfirmDialog confirmLabel="Archive dashboard" description="This removes the dashboard from active views. Its saved cards and query history are preserved." onClose={() => setDialog(null)} onConfirm={async () => { if (!csrfToken) return; await archiveDashboard(dashboard.id, csrfToken); setDirty(false); navigate(APP_ROUTES.home); }} title="Archive dashboard?" /> : null}
      {dialog?.kind === "card-rename" ? <RenameCardDialog card={dialog.card} onClose={() => setDialog(null)} onSaved={async (title, description) => { if (!csrfToken) return; await updateDashboardCard(dialog.card.id, { title, description }, csrfToken); setDialog(null); setStatus("Card updated."); await detail.reload(); }} /> : null}
      {dialog?.kind === "card-remove" ? <ConfirmDialog confirmLabel="Remove card" description="Only this dashboard card will be removed. The saved query and all query-run history are preserved." onClose={() => setDialog(null)} onConfirm={async () => { if (!csrfToken) return; await removeDashboardCard(dialog.card.id, csrfToken); setDialog(null); setStatus("Card removed; query history was preserved."); await detail.reload(); }} title={`Remove ${dialog.card.title}?`} /> : null}
      {dialog?.kind === "card-source" ? <SourceDialog card={dialog.card} onClose={closeSourceDialog} source={source} /> : null}
      {dialog?.kind === "card-resize" ? <ResizeDialog breakpoint={dialog.breakpoint} card={dialog.card} onClose={() => setDialog(null)} onSelect={(w, h) => applySize(dialog.card, dialog.breakpoint, w, h)} /> : null}
      {dialog?.kind === "card-visualization" ? <VisualizationDialog card={dialog.card} onClose={() => setDialog(null)} onSave={async (visualization) => { if (!csrfToken) return; await updateDashboardCard(dialog.card.id, { visualization }, csrfToken); setDialog(null); setStatus("Visualization preference saved."); await detail.reload(); }} result={results[dialog.card.id] ?? null} /> : null}
      {addCardOpen && csrfToken ? <AddCardDrawer csrfToken={csrfToken} dashboardId={dashboard.id} onClose={closeAddCard} onDashboardReload={async (message) => { setStatus(message); await detail.reload(); }} /> : null}
    </article>
  );
}

function RenameDashboardDialog({ dashboard, onClose, onSaved }: { dashboard: { title: string; description: string | null }; onClose: () => void; onSaved: (title: string, description: string | null) => Promise<void> }) {
  return <RenameDialog description={dashboard.description} entity="dashboard" onClose={onClose} onSaved={onSaved} title={dashboard.title} />;
}
function RenameCardDialog({ card, onClose, onSaved }: { card: EditorDashboardCard; onClose: () => void; onSaved: (title: string, description: string | null) => Promise<void> }) {
  return <RenameDialog description={card.description} entity="card" onClose={onClose} onSaved={onSaved} title={card.title} />;
}
function RenameDialog({ description: initialDescription, entity, onClose, onSaved, title: initialTitle }: { description: string | null; entity: "card" | "dashboard"; onClose: () => void; onSaved: (title: string, description: string | null) => Promise<void>; title: string }) {
  const [title, setTitle] = useState(initialTitle); const [description, setDescription] = useState(initialDescription ?? ""); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  return <EditorDialog footer={<><button className="qops-button-secondary" onClick={onClose} type="button">Cancel</button><button className="qops-button-primary" disabled={busy || !title.trim()} form={`rename-${entity}`} type="submit">{busy ? "Saving…" : "Save"}</button></>} onClose={onClose} title={`Rename ${entity}`}>
    <form className="dashboard-editor-form" id={`rename-${entity}`} onSubmit={(event) => { event.preventDefault(); if (!title.trim() || busy) return; setBusy(true); setError(null); void onSaved(title.trim(), description.trim() || null).catch(() => { setBusy(false); setError(`The ${entity} could not be updated.`); }); }}>
      <label>Title<input autoComplete="off" maxLength={255} onChange={(event) => setTitle(event.target.value)} required value={title} /></label>
      <label>Description<textarea maxLength={2000} onChange={(event) => setDescription(event.target.value)} rows={4} value={description} /></label>
      {error ? <p role="alert">{error}</p> : null}
    </form>
  </EditorDialog>;
}
function ConfirmDialog({ confirmLabel, description, onClose, onConfirm, title }: { confirmLabel: string; description: string; onClose: () => void; onConfirm: () => Promise<void>; title: string }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  return <EditorDialog description={description} footer={<><button className="qops-button-secondary" onClick={onClose} type="button">Cancel</button><button className="qops-button-danger" disabled={busy} onClick={() => { setBusy(true); setError(null); void onConfirm().catch(() => { setBusy(false); setError("The change could not be completed."); }); }} type="button">{busy ? "Working…" : confirmLabel}</button></>} onClose={onClose} title={title}>{error ? <p role="alert">{error}</p> : <p>This action does not delete saved queries or query-run history.</p>}</EditorDialog>;
}
function SourceDialog({ card, onClose, source }: { card: EditorDashboardCard; onClose: () => void; source: { loading: boolean; data: CardSource | null; error: string | null } }) {
  return <EditorDialog footer={<button className="qops-button-primary" onClick={onClose} type="button">Close</button>} onClose={onClose} title={`Source for ${card.title}`}>
    {source.loading ? <p role="status">Loading permitted source…</p> : source.error ? <p role="alert">{source.error}</p> : source.data ? <div className="dashboard-source"><section><h3>Original question</h3><p>{source.data.question}</p></section><section><h3>SQL</h3><pre><code>{source.data.sql}</code></pre></section></div> : null}
  </EditorDialog>;
}
function ResizeDialog({ breakpoint, card, onClose, onSelect }: { breakpoint: DashboardBreakpoint; card: EditorDashboardCard; onClose: () => void; onSelect: (w: number, h: number) => void }) {
  return <EditorDialog onClose={onClose} title={`Resize ${card.title}`}><p>Choose an allowed {breakpoint} size. Mobile always remains one column wide.</p><div className="dashboard-size-presets">{card.allowed_sizes[breakpoint].map((size) => <button key={`${size.w}x${size.h}`} onClick={() => onSelect(size.w, size.h)} type="button">{breakpoint === "mobile" ? `Height ${size.h}` : `${size.w} × ${size.h}`}</button>)}</div></EditorDialog>;
}
function VisualizationDialog({ card, onClose, onSave, result }: { card: EditorDashboardCard; onClose: () => void; onSave: (config: VisualizationConfig) => Promise<void>; result: DashboardCardRefreshResult | null }) {
  const recommendation = useMemo(() => result ? inferVisualization({ columns: result.columns, rows: result.rows, currentConfig: card.visualization }) : null, [card.visualization, result]);
  const [selected, setSelected] = useState(card.visualization.type); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const compatible = recommendation?.compatibleTypes ?? [card.visualization.type, "table" as const];
  const save = (config: VisualizationConfig) => { setBusy(true); setError(null); void onSave(config).catch(() => { setBusy(false); setError("The visualization preference could not be saved."); }); };
  return <EditorDialog footer={<><button className="qops-button-secondary" onClick={onClose} type="button">Cancel</button>{recommendation ? <button className="qops-button-primary" disabled={busy} onClick={() => save(manualConfig(selected, recommendation))} type="button">Save visualization</button> : null}</>} onClose={onClose} title={`Visualization for ${card.title}`}>
    {recommendation ? <><p><strong>Recommended:</strong> {VISUALIZATION_LABELS[recommendation.recommendedType]}. {recommendation.reason}</p><fieldset className="dashboard-visualization-options"><legend>Compatible visualizations</legend>{compatible.map((type) => <label key={type}><input checked={selected === type} name="visualization" onChange={() => setSelected(type)} type="radio" />{VISUALIZATION_LABELS[type]}</label>)}</fieldset><div className="dashboard-visualization-dialog__preview" aria-label="Visualization preview"><DashboardVisualization config={manualConfig(selected, recommendation)} result={result!} title={`Preview of ${card.title}`} /></div><button className="qops-button-secondary" disabled={busy} onClick={() => save(recommendedConfig(recommendation))} type="button"><RotateCcw aria-hidden="true" size={16} />Reset to recommended</button></> : <p>Refresh this card before choosing a compatible visualization.</p>}
    {error ? <p role="alert">{error}</p> : null}
  </EditorDialog>;
}
function DashboardUnavailable({ onRetry, title }: { onRetry?: () => void; title: string }) {
  return <section className="dashboard-detail dashboard-detail--state"><h1>{title}</h1><p>This dashboard is unavailable or is not visible in your current scope.</p><div>{onRetry ? <button className="qops-button-secondary" onClick={onRetry} type="button">Try again</button> : null}<Link className="qops-button-primary" to={APP_ROUTES.home}>Back to My Dashboard</Link></div></section>;
}
function cloneLayout(layout: DashboardCardLayout): DashboardCardLayout { return { version: 1, desktop: { ...layout.desktop }, tablet: { ...layout.tablet }, mobile: { ...layout.mobile } }; }
function cloneLayouts(layouts: Record<string, DashboardCardLayout>) { return Object.fromEntries(Object.entries(layouts).map(([id, layout]) => [id, cloneLayout(layout)])); }
function layoutFingerprint(layouts: Record<string, DashboardCardLayout>): string { return JSON.stringify(Object.entries(layouts).sort(([left], [right]) => left.localeCompare(right))); }
function repack(layouts: Record<string, DashboardCardLayout>, cards: EditorDashboardCard[], breakpoint: DashboardBreakpoint) {
  const columns = breakpoint === "desktop" ? 12 : breakpoint === "tablet" ? 6 : 1;
  const ordered = [...cards].sort((left, right) => layouts[left.id][breakpoint].y - layouts[right.id][breakpoint].y || layouts[left.id][breakpoint].x - layouts[right.id][breakpoint].x);
  let x = 0; let y = 0; let rowHeight = 0;
  for (const card of ordered) {
    const item = layouts[card.id][breakpoint];
    if (x + item.w > columns) { x = 0; y += rowHeight; rowHeight = 0; }
    layouts[card.id][breakpoint] = { ...item, x, y };
    x += item.w; rowHeight = Math.max(rowHeight, item.h);
    if (breakpoint === "mobile") { x = 0; y += item.h; rowHeight = 0; }
  }
}
function formatDate(value: string): string { const date = new Date(value); return Number.isNaN(date.getTime()) ? "recently" : new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(date); }
