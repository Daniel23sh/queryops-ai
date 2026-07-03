import type { QueryResultRow, QueryRunResult, QueryRunState } from "../types";
import { firstRowColumns } from "../utils/formatResultValue";
import {
  buildVisualizationSuggestion,
  runningQueryMessage
} from "../utils/resultSummary";
import {
  BODY_TEXT_CLASS,
  ERROR_CARD_CLASS,
  INFO_CARD_CLASS,
  SMALL_PANEL_TITLE_CLASS,
  WARNING_CARD_CLASS
} from "./askDataStyles";
import { ClarificationPanel } from "./ClarificationPanel";
import { ResultTable } from "./ResultTable";

export function ResultsTab({
  canClarify,
  clarificationDisabledReason,
  clarificationQuestion,
  onClarificationQuestionChange,
  onSubmitClarification,
  queryRunState
}: {
  canClarify: boolean;
  clarificationDisabledReason: string | null;
  clarificationQuestion: string;
  onClarificationQuestionChange: (question: string) => void;
  onSubmitClarification: () => void;
  queryRunState: QueryRunState;
}) {
  return (
    <>
      {queryRunState.status === "idle" ? (
        <div
          className="grid min-h-64 place-items-center rounded-card border border-dashed border-app-border bg-app-muted p-6 text-center"
          aria-label="Empty result workspace"
        >
          <div className="max-w-md">
            <h3 className="m-0 text-base font-bold text-app-text">Ready for a query</h3>
            <p className="mt-2 text-sm leading-6 text-app-subtle">
              Choose an approved template or ask a governed question. Results,
              warnings, and clarification prompts will appear here.
            </p>
          </div>
        </div>
      ) : null}

      {queryRunState.status === "running" ? (
        <p className={`${INFO_CARD_CLASS} min-h-32 place-content-center`} role="status">
          <span className="font-bold text-app-text">
            {runningQueryMessage(queryRunState.mode)}
          </span>
          <span className="block text-app-subtle">
            Results will appear here when the query finishes.
          </span>
        </p>
      ) : null}

      {queryRunState.status === "error" ? (
        <p className={ERROR_CARD_CLASS} role="alert">
          <strong className="block text-state-danger">Request failed</strong>
          <span>{queryRunState.message}</span>
        </p>
      ) : null}

      {queryRunState.status === "success" ? (
        <QueryResultSummary
          canClarify={canClarify}
          clarificationDisabledReason={clarificationDisabledReason}
          clarificationQuestion={clarificationQuestion}
          onClarificationQuestionChange={onClarificationQuestionChange}
          onSubmitClarification={onSubmitClarification}
          question={queryRunState.question}
          result={queryRunState.result}
        />
      ) : null}
    </>
  );
}

function QueryResultSummary({
  canClarify,
  clarificationDisabledReason,
  clarificationQuestion,
  onClarificationQuestionChange,
  onSubmitClarification,
  question,
  result
}: {
  canClarify: boolean;
  clarificationDisabledReason: string | null;
  clarificationQuestion: string;
  onClarificationQuestionChange: (question: string) => void;
  onSubmitClarification: () => void;
  question: string;
  result: QueryRunResult;
}) {
  const columns = result.columns.length > 0 ? result.columns : firstRowColumns(result.rows);
  const hasRows = result.rows.length > 0 && columns.length > 0;

  if (result.clarification_required) {
    return (
      <ClarificationPanel
        canClarify={canClarify}
        disabledReason={clarificationDisabledReason}
        message={result.message}
        onQuestionChange={onClarificationQuestionChange}
        onSubmit={onSubmitClarification}
        question={clarificationQuestion}
      />
    );
  }

  return (
    <div
      className="grid gap-4 rounded-card border border-app-border bg-app-surface p-4 text-sm leading-6 text-app-subtle shadow-sm"
      aria-label="Query result summary"
    >
      <h3 className={SMALL_PANEL_TITLE_CLASS}>Query result</h3>
      <p className={BODY_TEXT_CLASS}>{result.message}</p>
      <p className={BODY_TEXT_CLASS}>Question: {question}</p>
      <dl className="m-0 grid gap-2.5 md:grid-cols-3">
        <div className="grid gap-1 rounded-card border border-app-border bg-app-muted p-3">
          <dt className="text-xs font-bold uppercase text-app-faint">Status</dt>
          <dd className="m-0 font-bold text-app-text">Status: {result.status}</dd>
        </div>
        <div className="grid gap-1 rounded-card border border-app-border bg-app-muted p-3">
          <dt className="text-xs font-bold uppercase text-app-faint">Rows</dt>
          <dd className="m-0 font-bold text-app-text">{result.row_count}</dd>
        </div>
        <div className="grid gap-1 rounded-card border border-app-border bg-app-muted p-3">
          <dt className="text-xs font-bold uppercase text-app-faint">Duration</dt>
          <dd className="m-0 font-bold text-app-text">{result.duration_ms} ms</dd>
        </div>
      </dl>

      {result.truncated || result.warnings.length > 0 ? (
        <div className="grid gap-2.5">
          {result.truncated ? (
            <p className={`${WARNING_CARD_CLASS} grid gap-1`}>
              <strong className="text-sm text-app-text">Results truncated</strong>
              <span>Only the returned rows are shown in this preview.</span>
            </p>
          ) : null}
          {result.warnings.length > 0 ? (
            <div
              className={`${WARNING_CARD_CLASS} grid gap-2`}
              aria-label="Query warnings"
            >
              <h4 className="m-0 text-sm font-bold text-app-text">Warnings</h4>
              <ul className="m-0 grid gap-1.5 pl-5">
                {result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <VisualizationSuggestion columns={columns} rows={result.rows} />

      {hasRows ? (
        <ResultTable columns={columns} rows={result.rows} />
      ) : (
        <p className={`${WARNING_CARD_CLASS} m-0`}>No rows returned.</p>
      )}
    </div>
  );
}

function VisualizationSuggestion({
  columns,
  rows
}: {
  columns: string[];
  rows: QueryResultRow[];
}) {
  return (
    <div
      className="grid gap-1.5 rounded-card border border-app-border bg-app-muted px-3.5 py-3 text-sm leading-6 text-app-subtle"
      aria-label="Visualization suggestion"
    >
      <h4 className="m-0 text-sm font-bold text-app-text">
        Visualization suggestion
      </h4>
      <p className="m-0">{buildVisualizationSuggestion(columns, rows)}</p>
    </div>
  );
}
