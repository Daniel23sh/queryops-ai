import type { ReactNode } from "react";

import {
  availabilityLabel,
  formatEvaluationPercent,
  safeBreakdownLabel
} from "../presentation";
import type {
  EvaluationAvailability,
  EvaluationBreakdown,
  EvaluationMetricSummary
} from "../types";

export function AvailabilityBadge({ value }: { value: EvaluationAvailability }) {
  const tone = {
    measured: "border-status-success/40 bg-status-success/10 text-status-success",
    partially_measured: "border-status-warning/40 bg-status-warning/10 text-status-warning",
    not_measured: "border-app-border bg-app-muted text-app-subtle",
    unavailable: "border-status-danger/30 bg-status-danger/10 text-status-danger"
  }[value];
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${tone}`}>
      {availabilityLabel(value)}
    </span>
  );
}

export function EvaluationStatePanel({
  actionLabel = "Try again",
  kind = "status",
  message,
  onAction,
  title
}: {
  actionLabel?: string;
  kind?: "status" | "error";
  message: string;
  onAction?: () => void;
  title: string;
}) {
  return (
    <section
      className={`grid gap-3 rounded-card border p-5 ${
        kind === "error"
          ? "border-status-danger/40 bg-status-danger/10"
          : "border-app-border bg-app-surface"
      }`}
      role={kind === "error" ? "alert" : "status"}
    >
      <h2 className="m-0 text-lg font-bold text-app-text">{title}</h2>
      <p className="m-0 max-w-3xl text-sm leading-6 text-app-subtle">{message}</p>
      {onAction ? (
        <button
          className="qops-button-secondary justify-self-start"
          onClick={onAction}
          type="button"
        >
          {actionLabel}
        </button>
      ) : null}
    </section>
  );
}

export function MetricCard({
  detail,
  label,
  value
}: {
  detail: string;
  label: string;
  value: ReactNode;
}) {
  return (
    <article className="grid gap-2 rounded-card border border-app-border bg-app-surface p-4">
      <p className="m-0 text-xs font-bold uppercase tracking-wide text-app-faint">{label}</p>
      <p className="m-0 text-2xl font-bold text-app-text">{value}</p>
      <p className="m-0 text-xs leading-5 text-app-subtle">{detail}</p>
    </article>
  );
}

export function MeasurementProgress({
  label,
  metrics
}: {
  label: string;
  metrics: EvaluationMetricSummary;
}) {
  const maximum = Math.max(1, metrics.eligible_count);
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-bold text-app-text">{label}</span>
        <span className="text-app-subtle">
          {metrics.completed_count} of {metrics.eligible_count}
        </span>
      </div>
      <progress
        aria-label={`${label}: ${metrics.completed_count} of ${metrics.eligible_count} visible cases completed`}
        className="h-2 w-full accent-brand-primary"
        max={maximum}
        value={Math.min(metrics.completed_count, maximum)}
      />
    </div>
  );
}

export function BreakdownTable({
  caption,
  items
}: {
  caption: string;
  items: EvaluationBreakdown[];
}) {
  if (!items.length) {
    return <p className="m-0 text-sm text-app-subtle">No visible breakdown is available.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-app-border text-xs uppercase tracking-wide text-app-faint">
          <tr>
            <th className="px-3 py-2" scope="col">Group</th>
            <th className="px-3 py-2" scope="col">Completed</th>
            <th className="px-3 py-2" scope="col">Passed</th>
            <th className="px-3 py-2" scope="col">Score</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-app-border">
          {items.map((item) => (
            <tr key={item.key}>
              <th className="px-3 py-3 font-bold text-app-text" scope="row">
                {safeBreakdownLabel(item.key)}
              </th>
              <td className="px-3 py-3 text-app-subtle">
                {item.completed_count} of {item.eligible_count}
              </td>
              <td className="px-3 py-3 text-app-subtle">
                {item.passed_count} passed · {item.failed_count} failed
              </td>
              <td className="px-3 py-3 text-app-subtle">
                {formatEvaluationPercent(item.score)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
