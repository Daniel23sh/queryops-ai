import {
  caseTypeLabel,
  failureReasonLabel,
  formatEvaluationPercent,
  outcomeLabel,
  safeBreakdownLabel
} from "../presentation";
import type { EvaluationCaseMetric } from "../types";

export function EvaluationCaseCard({ item }: { item: EvaluationCaseMetric }) {
  return (
    <article className="grid gap-3 rounded-card border border-app-border bg-app-surface p-4 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="m-0 break-all text-base font-bold text-app-text">{item.case_id}</h3>
          <p className="mb-0 mt-1 text-sm text-app-subtle">
            {safeBreakdownLabel(item.difficulty)} · {caseTypeLabel(item.case_type)} · {safeBreakdownLabel(item.category)}
          </p>
        </div>
        <ResultBadge passed={item.passed} />
      </div>
      <dl className="m-0 grid gap-3 text-sm sm:grid-cols-2">
        <Detail label="Score" value={formatEvaluationPercent(item.score)} />
        <Detail label="Expected behavior" value={item.passed ? "Matched" : "Did not match"} />
      </dl>
      {item.technical ? <EvaluationTechnicalDetails item={item} /> : null}
    </article>
  );
}

export function ResultBadge({ passed }: { passed: boolean }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${passed ? "border-status-success/40 bg-status-success/10 text-status-success" : "border-status-danger/40 bg-status-danger/10 text-status-danger"}`}>
      {passed ? "Passed" : "Did not pass"}
    </span>
  );
}

function EvaluationTechnicalDetails({ item }: { item: EvaluationCaseMetric }) {
  const technical = item.technical;
  if (!technical) return null;
  return (
    <details className="rounded-control border border-app-border bg-app-muted p-3">
      <summary className="cursor-pointer font-bold text-app-text">Technical measurement details</summary>
      <dl className="mb-0 mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
        <Detail label="Expected outcome" value={outcomeLabel(technical.expected_outcome)} />
        <Detail label="Actual outcome" value={outcomeLabel(technical.actual_outcome)} />
        <Detail label="Execution" value={technical.query_execution_attempted ? (technical.execution_succeeded ? "Succeeded" : "Did not succeed") : "Not attempted"} />
        <Detail label="Rows" value={`${technical.actual_row_count} actual · ${technical.expected_row_count} expected`} />
        <Detail label="Row differences" value={`${technical.missing_row_count} missing · ${technical.extra_row_count} extra`} />
        <Detail label="Duration" value={`${Math.round(technical.duration_ms)} ms`} />
      </dl>
      {technical.failure_reasons.length ? (
        <div className="mt-3 text-sm">
          <p className="m-0 font-bold text-app-text">Controlled mismatch reasons</p>
          <ul className="mb-0 mt-1 pl-5 text-app-subtle">
            {technical.failure_reasons.map((reason) => <li key={reason}>{failureReasonLabel(reason)}</li>)}
          </ul>
        </div>
      ) : null}
      {technical.error_code ? <p className="mb-0 mt-3 text-sm text-app-subtle">Outcome code: {safeBreakdownLabel(technical.error_code)}</p> : null}
      {technical.referenced_tables !== null ? (
        <div className="mt-3 text-sm">
          <p className="m-0 font-bold text-app-text">Referenced resources</p>
          <p className="mb-0 mt-1 break-words text-app-subtle">{technical.referenced_tables.length ? technical.referenced_tables.map(safeBreakdownLabel).join(", ") : "None"}</p>
        </div>
      ) : null}
    </details>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-bold uppercase tracking-wide text-app-faint">{label}</dt><dd className="m-0 mt-1 text-app-text">{value}</dd></div>;
}
