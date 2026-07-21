import { useCallback, useEffect } from "react";

import { evaluationRequestKey, getEvaluationActions, getEvaluationDashboards } from "../../../api/evaluation";
import { useEvaluationResource } from "../hooks/useEvaluationResource";
import { AvailabilityBadge, EvaluationStatePanel, MetricCard } from "./EvaluationPrimitives";
import { formatEvaluationPercent, matchesSelectedRun } from "../presentation";
import type { EvaluationCapability } from "../types";

export function EvaluationCapabilityTab({ capability, identityKey, onForbidden, onLatest, runId }: {
  capability: "actions" | "dashboards";
  identityKey: string;
  onForbidden: () => void;
  onLatest: () => void;
  runId: string;
}) {
  const load = useCallback((signal: AbortSignal) => capability === "actions" ? getEvaluationActions(runId, signal) : getEvaluationDashboards(runId, signal), [capability, runId]);
  const state = useEvaluationResource<EvaluationCapability>({ load, requestKey: evaluationRequestKey(identityKey, capability, runId) });
  useEffect(() => { if (state.error === "forbidden") onForbidden(); }, [onForbidden, state.error]);

  if (state.status === "loading") return <EvaluationStatePanel title={`Loading ${capability} measurement…`} message="Loading the authorized projection for this run." />;
  if (state.status === "error") return <EvaluationChildError error={state.error} onLatest={onLatest} onRetry={state.reload} />;
  if (!state.data) return null;
  if (!matchesSelectedRun(state.data.run, runId)) return <EvaluationStatePanel kind="error" title="The selected run could not be verified" message="The response did not match the run selected by Overview. No capability metrics are shown." actionLabel="Load latest run" onAction={onLatest} />;
  const title = capability === "actions" ? "Action evaluation" : "Dashboard evaluation";
  return (
    <section className="grid gap-5" aria-labelledby={`${capability}-evaluation-title`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="m-0 text-xl font-bold text-app-text" id={`${capability}-evaluation-title`}>{title}</h2><p className="mb-0 mt-2 max-w-3xl text-sm leading-6 text-app-subtle">This M9 dataset does not measure {capability}. No score is inferred from zero eligible cases.</p></div>
        <AvailabilityBadge value={state.data.availability} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <MetricCard label="Measured cases" value={state.data.measured_cases} detail="Eligible cases in the selected run" />
        <MetricCard label="Score" value={formatEvaluationPercent(state.data.score)} detail="Unavailable until this capability has an approved evaluation contract" />
      </div>
      <EvaluationStatePanel title="Not measured in this dataset" message={`The selected evaluation run contains no ${capability} cases. This is an explicit coverage boundary, not a passing or failing result.`} />
    </section>
  );
}

export function EvaluationChildError({ error, onLatest, onRetry }: { error: "forbidden" | "not_found" | "invalid_filter" | "unavailable" | null; onLatest: () => void; onRetry: () => void }) {
  if (error === "not_found") return <EvaluationStatePanel kind="error" title="This run is no longer available" message="Return to the latest visible evaluation run and try again." actionLabel="Load latest run" onAction={onLatest} />;
  if (error === "invalid_filter") return <EvaluationStatePanel kind="error" title="The selected filters are not valid" message="Reset the filters to a supported combination." />;
  if (error === "forbidden") return <EvaluationStatePanel kind="error" title="Evaluation access changed" message="Your current access no longer permits this evaluation view." />;
  return <EvaluationStatePanel kind="error" title="Evaluation metrics are temporarily unavailable" message="No stored details from the previous request are shown. Try again when the service is available." onAction={onRetry} />;
}
