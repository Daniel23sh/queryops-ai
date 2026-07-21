import { useCallback, useEffect } from "react";

import { evaluationRequestKey, getEvaluationSecurity } from "../../../api/evaluation";
import { useEvaluationResource } from "../hooks/useEvaluationResource";
import { formatEvaluationPercent } from "../presentation";
import type { EvaluationSecurity } from "../types";
import { EvaluationCaseCard } from "./EvaluationCaseDetails";
import { BreakdownTable, EvaluationStatePanel, MeasurementProgress, MetricCard } from "./EvaluationPrimitives";
import { EvaluationChildError } from "./EvaluationCapabilityTab";

export function EvaluationSecurityTab({ identityKey, onForbidden, onLatest, runId }: { identityKey: string; onForbidden: () => void; onLatest: () => void; runId: string }) {
  const load = useCallback((signal: AbortSignal) => getEvaluationSecurity(runId, signal), [runId]);
  const state = useEvaluationResource<EvaluationSecurity>({ load, requestKey: evaluationRequestKey(identityKey, "security", runId) });
  useEffect(() => { if (state.error === "forbidden") onForbidden(); }, [onForbidden, state.error]);
  if (state.status === "loading") return <EvaluationStatePanel title="Loading security measurements…" message="Loading the authorized security-case projection." />;
  if (state.status === "error") return <EvaluationChildError error={state.error} onLatest={onLatest} onRetry={state.reload} />;
  if (!state.data) return null;
  const { metrics } = state.data;
  return (
    <div className="grid gap-6">
      <section className="grid gap-4" aria-labelledby="security-evaluation-title">
        <div><h2 className="m-0 text-xl font-bold text-app-text" id="security-evaluation-title">Security behavior</h2><p className="mb-0 mt-2 max-w-4xl text-sm leading-6 text-app-subtle">A passing case means the exact expected denial, clarification, or unsafe-query block was observed. These results do not constitute a security certification.</p></div>
        <MeasurementProgress label="Visible security cases" metrics={metrics} />
        <div className="grid gap-3 sm:grid-cols-3">
          <MetricCard label="Passed" value={`${metrics.passed_count}/${metrics.completed_count}`} detail={`${metrics.failed_count} exact behavior mismatches remain visible`} />
          <MetricCard label="Pass rate" value={formatEvaluationPercent(metrics.security_pass_rate)} detail="Completed security-sensitive cases" />
          <MetricCard label="Expected behavior" value={formatEvaluationPercent(metrics.expected_behavior_match_rate)} detail="Exact outcome classification match" />
        </div>
      </section>
      <section className="rounded-card border border-app-border bg-app-surface p-4"><h3 className="m-0 mb-3 text-base font-bold text-app-text">By expected behavior</h3><BreakdownTable caption="Security results by expected behavior" items={state.data.by_expected_behavior} /></section>
      <section className="grid gap-3" aria-labelledby="security-cases-title"><h3 className="m-0 text-lg font-bold text-app-text" id="security-cases-title">Security cases</h3>{state.data.items.length ? state.data.items.map((item) => <EvaluationCaseCard item={item} key={item.case_id} />) : <EvaluationStatePanel title="No visible security cases" message="The selected run has no security-case results in your authorized projection." />}</section>
    </div>
  );
}
