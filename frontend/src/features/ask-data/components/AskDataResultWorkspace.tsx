import { AlertTriangle, LoaderCircle } from "lucide-react";

import { inferVisualization, VISUALIZATION_LABELS } from "../../dashboard/visualization";
import type { ReactNode } from "react";
import type { CurrentQueryResult, QueryRequestState, ResultDisplayMode } from "../types";
import { QueryResultToolbar } from "./QueryResultToolbar";
import { QueryResultVisualization } from "./QueryResultVisualization";
import { ResultDetailsDisclosure } from "./ResultDetailsDisclosure";
import { ResultTable } from "./ResultTable";

export function AskDataResultWorkspace({
  actionRecommendation,
  canClarify,
  canExport,
  canSave,
  canViewTechnicalDetails,
  clarificationError,
  clarificationText,
  csrfToken,
  current,
  onClarificationChange,
  onDisplayModeChange,
  onSubmitClarification,
  requestState,
  resultDisplayMode
}: {
  actionRecommendation: ReactNode;
  canClarify: boolean;
  canExport: boolean;
  canSave: boolean;
  canViewTechnicalDetails: boolean;
  clarificationError: string | null;
  clarificationText: string;
  csrfToken: string | null;
  current: CurrentQueryResult | null;
  onClarificationChange: (value: string) => void;
  onDisplayModeChange: (mode: ResultDisplayMode) => void;
  onSubmitClarification: () => void;
  requestState: QueryRequestState;
  resultDisplayMode: ResultDisplayMode;
}) {
  const running = requestState.status === "running";

  return (
    <section className="grid gap-4 rounded-card border border-app-border bg-app-surface p-4 shadow-card sm:p-5" aria-labelledby="result-workspace-title">
      <div className="flex items-center justify-between gap-3">
        <h2 id="result-workspace-title" className="m-0 text-lg font-bold text-app-text">Result</h2>
        {running ? <p className="m-0 inline-flex items-center gap-2 text-sm font-semibold text-app-subtle" role="status"><LoaderCircle className="animate-spin" aria-hidden="true" size={17} />Running</p> : null}
      </div>

      {running ? <p className="m-0 rounded-control border border-brand-primary/30 bg-brand-primary/10 px-3 py-2 text-sm text-app-text" aria-live="polite">Running a governed query under your current scope…</p> : null}

      {!current ? (
        <div className="grid min-h-40 place-items-center rounded-card border border-dashed border-app-border bg-app-muted p-6 text-center text-sm leading-6 text-app-subtle">
          Run an approved template or permitted question to see a result.
        </div>
      ) : (
        <ResultContent
          actionRecommendation={actionRecommendation}
          canClarify={canClarify}
          canExport={canExport}
          canSave={canSave}
          canViewTechnicalDetails={canViewTechnicalDetails}
          clarificationError={clarificationError}
          clarificationText={clarificationText}
          csrfToken={csrfToken}
          current={current}
          onClarificationChange={onClarificationChange}
          onDisplayModeChange={onDisplayModeChange}
          onSubmitClarification={onSubmitClarification}
          requestRunning={running}
          resultDisplayMode={resultDisplayMode}
        />
      )}
    </section>
  );
}

function ResultContent({
  actionRecommendation,
  canClarify,
  canExport,
  canSave,
  canViewTechnicalDetails,
  clarificationError,
  clarificationText,
  csrfToken,
  current,
  onClarificationChange,
  onDisplayModeChange,
  onSubmitClarification,
  requestRunning,
  resultDisplayMode
}: {
  actionRecommendation: ReactNode;
  canClarify: boolean;
  canExport: boolean;
  canSave: boolean;
  canViewTechnicalDetails: boolean;
  clarificationError: string | null;
  clarificationText: string;
  csrfToken: string | null;
  current: CurrentQueryResult;
  onClarificationChange: (value: string) => void;
  onDisplayModeChange: (mode: ResultDisplayMode) => void;
  onSubmitClarification: () => void;
  requestRunning: boolean;
  resultDisplayMode: ResultDisplayMode;
}) {
  const { result } = current;
  const recommendation = inferVisualization({ columns: result.columns, rows: result.rows });
  const visualAvailable = recommendation.recommendedType !== "table";
  const successful = result.status === "succeeded" && !result.clarification_required;
  const hasRows = successful && result.rows.length > 0 && result.columns.length > 0;

  return (
    <div className="grid gap-4">
      <header className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
        <div className="min-w-0">
          <p className="m-0 text-xs font-bold uppercase tracking-wide text-status-success">{humanizeStatus(result.status)}</p>
          <h3 className="mb-0 mt-1 text-base font-bold leading-6 text-app-text">{current.originalQuestion}</h3>
          {current.clarificationResponse ? <p className="mb-0 mt-1 text-sm text-app-subtle"><strong>Clarified:</strong> {current.clarificationResponse}</p> : null}
        </div>
        <dl className="m-0 flex flex-wrap gap-x-4 gap-y-1 text-xs text-app-subtle sm:justify-end">
          <div className="flex gap-1"><dt>Rows</dt><dd className="m-0 font-bold text-app-text">{result.row_count}</dd></div>
          <div className="flex gap-1"><dt>Duration</dt><dd className="m-0 font-bold text-app-text">{formatDuration(result.duration_ms)}</dd></div>
          {result.truncated ? <div><dt className="qops-sr-only">Truncation</dt><dd className="m-0 font-bold text-status-warning">Truncated</dd></div> : null}
          {result.warnings.length ? <div className="flex gap-1"><dt>Warnings</dt><dd className="m-0 font-bold text-status-warning">{result.warnings.length}</dd></div> : null}
        </dl>
      </header>

      {result.warnings.length ? <details className="rounded-control border border-status-warning/40 bg-status-warning/10 px-3 py-2 text-sm text-app-text"><summary className="cursor-pointer font-semibold">{result.warnings.length === 1 ? result.warnings[0] : `${result.warnings.length} query warnings`}</summary>{result.warnings.length > 1 ? <ul className="mb-0 mt-2 pl-5">{result.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul> : null}</details> : null}
      {result.truncated ? <p className="m-0 inline-flex items-center gap-2 text-sm text-status-warning"><AlertTriangle aria-hidden="true" size={16} />The result was truncated by the governed row limit.</p> : null}
      {actionRecommendation}

      {result.clarification_required ? (
        <ClarificationState canClarify={canClarify} csrfToken={csrfToken} error={clarificationError} message={result.message} onChange={onClarificationChange} onSubmit={onSubmitClarification} originalQuestion={current.originalQuestion} running={requestRunning} value={clarificationText} />
      ) : result.status !== "succeeded" ? (
        <div className="rounded-card border border-status-danger/40 bg-status-danger/10 p-4 text-sm leading-6 text-app-text"><strong>Query could not be completed.</strong><p className="mb-0 mt-1">{result.message || "Try refining the question and run it again."}</p></div>
      ) : !hasRows ? (
        <div className="rounded-card border border-app-border bg-app-muted p-5 text-center text-sm text-app-subtle">The query completed successfully but returned no rows.</div>
      ) : (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="inline-flex self-start rounded-control bg-app-muted p-1" role="group" aria-label="Result view">
              {visualAvailable ? <ViewButton active={resultDisplayMode === "visual"} label="Visual" onClick={() => onDisplayModeChange("visual")} /> : null}
              <ViewButton active={resultDisplayMode === "table" || !visualAvailable} label="Table" onClick={() => onDisplayModeChange("table")} />
            </div>
            {visualAvailable ? <p className="m-0 text-xs text-app-faint">Recommended: {VISUALIZATION_LABELS[recommendation.recommendedType]}</p> : <p className="m-0 text-xs text-app-faint">Table is the safest view for this result shape.</p>}
          </div>
          {visualAvailable && resultDisplayMode === "visual" ? <QueryResultVisualization question={current.originalQuestion} result={result} /> : <ResultTable columns={result.columns} rows={result.rows} />}
          <QueryResultToolbar canExport={canExport} canSave={canSave} csrfToken={csrfToken} current={current} />
        </>
      )}

      <ResultDetailsDisclosure canViewTechnicalDetails={canViewTechnicalDetails} current={current} />
    </div>
  );
}

function ClarificationState({ canClarify, csrfToken, error, message, onChange, onSubmit, originalQuestion, running, value }: { canClarify: boolean; csrfToken: string | null; error: string | null; message: string; onChange: (value: string) => void; onSubmit: () => void; originalQuestion: string; running: boolean; value: string }) {
  const available = canClarify && Boolean(csrfToken);
  return <section className="grid gap-3 rounded-card border border-status-warning/40 bg-status-warning/10 p-4" aria-labelledby="clarification-title"><div><p className="m-0 text-xs font-bold uppercase tracking-wide text-status-warning">More detail needed</p><h4 id="clarification-title" className="mb-0 mt-1 text-base font-bold text-app-text">Clarify this question</h4><p className="mb-0 mt-2 text-sm leading-6 text-app-subtle">{message}</p><p className="mb-0 mt-2 text-sm text-app-text"><strong>Original question:</strong> {originalQuestion}</p></div>{available ? <><label className="grid gap-2 text-sm font-bold text-app-text">Clarification<input autoFocus className="min-h-11 rounded-control border border-app-border bg-app-surface px-3 py-2 text-sm outline-none focus:border-brand-primary focus:shadow-focus" value={value} disabled={running} onChange={(event) => onChange(event.target.value)} /></label><button className="qops-button-primary min-h-11 justify-self-start" type="button" disabled={running || !value.trim()} onClick={onSubmit}>{running ? "Submitting…" : "Submit clarification"}</button>{error ? <p className="m-0 text-sm text-status-danger" role="alert">{error}</p> : null}</> : <p className="m-0 text-sm text-app-subtle">Clarification is not available with your current access. Choose another approved template.</p>}</section>;
}

function ViewButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) { return <button className={active ? "min-h-10 min-w-24 rounded-control bg-app-surface px-4 text-sm font-bold text-app-text shadow-sm" : "min-h-10 min-w-24 rounded-control px-4 text-sm font-semibold text-app-subtle hover:text-app-text"} type="button" aria-pressed={active} onClick={onClick}>{label}</button>; }
function formatDuration(value: number) { return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`; }
function humanizeStatus(value: string) { return value.replace(/_/g, " "); }
