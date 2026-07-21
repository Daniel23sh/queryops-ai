import type { ReactNode } from "react";

import {
  AvailabilityBadge,
  BreakdownTable,
  EvaluationStatePanel,
  MeasurementProgress,
  MetricCard
} from "./EvaluationPrimitives";
import { formatEvaluationDate, formatEvaluationPercent } from "../presentation";
import type { EvaluationOverview } from "../types";

export function EvaluationOverviewTab({ data }: { data: EvaluationOverview }) {
  const { metrics, run } = data;
  const queryCoverage = data.coverage.find((item) => item.capability === "queries");
  return (
    <div className="grid gap-6">
      <section className="grid gap-4" aria-labelledby="evaluation-summary-title">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="m-0 text-xs font-bold uppercase tracking-wide text-app-faint">Latest visible run</p>
            <h2 className="mb-0 mt-1 text-xl font-bold text-app-text" id="evaluation-summary-title">
              MockLLM quality measurement
            </h2>
          </div>
          <AvailabilityBadge value={metrics.availability} />
        </div>
        <p className="m-0 max-w-4xl text-sm leading-6 text-app-subtle">
          These metrics report observed behavior for the deterministic MockLLM dataset. They are measurements, not release thresholds or a quality certification.
        </p>
        <MeasurementProgress label="Visible evaluation coverage" metrics={metrics} />
        {metrics.availability === "partially_measured" ? (
          <EvaluationStatePanel title="Partial measurement" message="Only completed, structurally valid cases are included. Missing cases are visible in the coverage counts and are not treated as zero-score failures." />
        ) : null}
        {metrics.availability === "unavailable" ? (
          <EvaluationStatePanel kind="error" title="Stored measurements are unavailable" message="This run is visible, but its stored measurements cannot be reported safely. No replacement zero score is shown." />
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Completed" value={`${metrics.completed_count}/${metrics.eligible_count}`} detail={`${metrics.selected_count} selected in this run`} />
          <MetricCard label="Passed" value={metrics.passed_count} detail={`${metrics.failed_count} visible cases did not pass`} />
          <MetricCard label="Semantic score" value={formatEvaluationPercent(metrics.overall_score)} detail="Result semantics and expected outcomes" />
          <MetricCard label="Behavior match" value={formatEvaluationPercent(metrics.expected_behavior_match_rate)} detail="Expected behavior matched exactly" />
          <MetricCard label="Security pass rate" value={formatEvaluationPercent(metrics.security_pass_rate)} detail="Visible security-sensitive cases only" />
          <MetricCard label="Query executions" value={metrics.query_execution_succeeded_count} detail={`${metrics.query_execution_failed_count} unexpected execution failures`} />
          <MetricCard label="Query coverage" value={queryCoverage?.measured_case_count ?? 0} detail={queryCoverage ? `${formatEvaluationPercent(queryCoverage.score)} measured score` : "No visible query coverage"} />
          <MetricCard label="Run status" value={run?.status ?? "Unavailable"} detail={`Completed ${formatEvaluationDate(run?.completed_at ?? null)}`} />
        </div>
      </section>

      {run ? (
        <section className="grid gap-3 rounded-card border border-app-border bg-app-surface p-5" aria-labelledby="evaluation-run-title">
          <h2 className="m-0 text-lg font-bold text-app-text" id="evaluation-run-title">Run details</h2>
          <dl className="m-0 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
            <RunDetail label="Provider" value={`${run.provider} · ${run.model_label}`} />
            <RunDetail label="Dataset" value={`${run.dataset_id} · ${run.dataset_version}`} />
            <RunDetail label="Started" value={formatEvaluationDate(run.started_at)} />
            <RunDetail label="Completed" value={formatEvaluationDate(run.completed_at)} />
          </dl>
        </section>
      ) : null}

      <section className="grid gap-5 lg:grid-cols-3" aria-label="Evaluation breakdowns">
        <BreakdownPanel title="By difficulty"><BreakdownTable caption="Evaluation by difficulty" items={data.by_difficulty} /></BreakdownPanel>
        <BreakdownPanel title="By category"><BreakdownTable caption="Evaluation by category" items={data.by_category} /></BreakdownPanel>
        <BreakdownPanel title="By case type"><BreakdownTable caption="Evaluation by case type" items={data.by_case_type} /></BreakdownPanel>
      </section>
    </div>
  );
}

function RunDetail({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-bold uppercase tracking-wide text-app-faint">{label}</dt><dd className="m-0 mt-1 break-words text-app-text">{value}</dd></div>;
}

function BreakdownPanel({ children, title }: { children: ReactNode; title: string }) {
  return <section className="min-w-0 rounded-card border border-app-border bg-app-surface p-4"><h3 className="m-0 mb-3 text-base font-bold text-app-text">{title}</h3>{children}</section>;
}
