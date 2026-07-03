import type { QueryRunState } from "../types";
import { safeSqlText } from "../utils/diagnostics";
import {
  BODY_TEXT_CLASS,
  MUTED_CARD_CLASS,
  SMALL_PANEL_TITLE_CLASS
} from "./askDataStyles";

export function SqlTab({ queryRunState }: { queryRunState: QueryRunState }) {
  if (queryRunState.status === "idle") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
        <p className={BODY_TEXT_CLASS}>Run a query to inspect SQL for this role.</p>
      </div>
    );
  }

  if (queryRunState.status === "running") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
        <p className={BODY_TEXT_CLASS}>
          SQL will be available after the query finishes, if the backend returns it.
        </p>
      </div>
    );
  }

  if (queryRunState.status === "error") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
        <p className={BODY_TEXT_CLASS}>
          SQL is not available because the latest request ended with a safe error state.
        </p>
      </div>
    );
  }

  const generatedSql = safeSqlText(queryRunState.result.generated_sql);
  const executedSql = safeSqlText(queryRunState.result.executed_sql);

  if (!generatedSql && !executedSql) {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
        <p className={BODY_TEXT_CLASS}>SQL is not available for this query result.</p>
      </div>
    );
  }

  return (
    <div className={`${MUTED_CARD_CLASS} font-mono`}>
      <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
      <p className={BODY_TEXT_CLASS}>
        SQL is visible only for roles with SQL access. Generated SQL is the
        provider output; executed SQL is the validated SQL sent to the query
        executor.
      </p>
      {generatedSql ? <SqlBlock label="Generated SQL" sql={generatedSql} /> : null}
      {executedSql ? <SqlBlock label="Executed SQL" sql={executedSql} /> : null}
    </div>
  );
}

function SqlBlock({ label, sql }: { label: string; sql: string }) {
  return (
    <section className="grid gap-2" aria-label={label}>
      <h4 className="m-0 text-sm font-bold text-app-text">{label}</h4>
      <pre className="m-0 overflow-x-auto whitespace-pre-wrap rounded-card border border-app-border bg-app-surface p-3 font-mono text-xs leading-6 text-app-text">
        <code>{sql}</code>
      </pre>
    </section>
  );
}
