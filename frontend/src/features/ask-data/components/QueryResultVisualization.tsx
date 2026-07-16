import { DashboardVisualization } from "../../dashboard/visualization/DashboardVisualization";
import {
  inferVisualization,
  recommendedConfig,
  VISUALIZATION_LABELS
} from "../../dashboard/visualization";
import type { QueryRunResult } from "../types";

export function QueryResultVisualization({
  question,
  result
}: {
  question: string;
  result: QueryRunResult;
}) {
  const recommendation = inferVisualization({ columns: result.columns, rows: result.rows });
  if (recommendation.recommendedType === "table") return null;

  return (
    <section className="grid gap-3" aria-label="Query result visualization">
      <p className="m-0 text-sm font-semibold text-app-subtle">
        Recommended: {VISUALIZATION_LABELS[recommendation.recommendedType]}
      </p>
      <div className="min-h-[260px] rounded-card border border-app-border bg-app-muted p-3 sm:min-h-[320px] sm:p-4">
        <DashboardVisualization config={recommendedConfig(recommendation)} result={result} title={question} />
      </div>
    </section>
  );
}
