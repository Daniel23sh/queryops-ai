import { formatEvaluationPercent } from "../presentation";
import type { EvaluationReadiness, ReadinessGateStatus, ReadinessVerdict } from "../types";
import { EvaluationStatePanel } from "./EvaluationPrimitives";

const verdictLabels: Record<ReadinessVerdict, string> = {
  ready: "Ready",
  not_ready: "Not ready",
  incomplete: "Incomplete"
};
const gateLabels: Record<ReadinessGateStatus, string> = {
  passed: "Passed",
  failed: "Failed",
  incomplete: "Incomplete"
};
const gateCodes = [
  "qualifying_evidence",
  "deterministic_release_gates",
  "execution_success_rate",
  "result_accuracy",
  "unsafe_query_block_rate",
  "clarification_accuracy",
  "security_case_pass_rate"
] as const;

export function EvaluationReadinessPanel({
  data,
  error,
  loading
}: {
  data: EvaluationReadiness | null;
  error: boolean;
  loading: boolean;
}) {
  if (loading) {
    return <EvaluationStatePanel title="Loading V1 readiness…" message="Checking the latest qualifying full OpenAI evidence against the versioned release policy." />;
  }
  if (error || !data || !isSafeReadiness(data)) {
    return <EvaluationStatePanel kind="error" title="V1 readiness unavailable" message="Readiness evidence could not be validated safely. No pass state is inferred." />;
  }
  const evidenceIsOpenAI = data.provider === "openai";
  const verdict = evidenceIsOpenAI ? data.verdict : "incomplete";
  return (
    <section className="grid gap-4 rounded-card border border-app-border bg-app-surface p-5" aria-labelledby="v1-readiness-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="m-0 text-xs font-bold uppercase tracking-wide text-app-faint">V1 release evidence</p>
          <h2 className="mb-0 mt-1 text-xl font-bold text-app-text" id="v1-readiness-title">V1 readiness: {verdictLabels[verdict]}</h2>
        </div>
        <span className="rounded-full border border-app-border px-3 py-1 text-sm font-bold text-app-text">Status: {verdictLabels[verdict]}</span>
      </div>
      <p className="m-0 max-w-4xl text-sm leading-6 text-app-subtle">
        Readiness combines a qualifying real-provider measurement with deterministic security, PostgreSQL, action, export, frontend, and E2E gates. Provider identity identifies evidence; it never proves readiness.
      </p>
      <dl className="m-0 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Detail label="Policy" value={data.policy_id} />
        <Detail label="Evidence" value={evidenceIsOpenAI && data.model_label ? `OpenAI · ${data.model_label}` : "No qualifying OpenAI evidence"} />
        <Detail label="Dataset version" value={data.dataset_version} />
        <Detail label="Measurement" value={data.completed_count === null ? "Incomplete" : `${data.completed_count}/40 completed`} />
      </dl>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="V1 readiness gates">
        {data.gates.map((gate) => {
          const status = isGateStatus(gate.status) ? gate.status : "incomplete";
          return (
            <article className="rounded-card border border-app-border bg-app-elevated p-4" key={gate.code}>
              <p className="m-0 text-sm font-bold text-app-text">{gate.label}</p>
              <p className="mb-0 mt-2 text-sm text-app-subtle">Status: {gateLabels[status]}</p>
              {typeof gate.actual === "number" ? <p className="mb-0 mt-1 text-xs text-app-faint">Measured {formatEvaluationPercent(gate.actual)}</p> : null}
              {typeof gate.threshold === "number" ? <p className="mb-0 mt-1 text-xs text-app-faint">Threshold {formatEvaluationPercent(gate.threshold)}</p> : null}
            </article>
          );
        })}
      </div>
      <p className="m-0 text-xs leading-5 text-app-faint">Actions and Dashboards are not scored by the frozen 40-case dataset. Their V1 evidence comes from deterministic PostgreSQL and end-to-end release gates. Average latency is informational only.</p>
    </section>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-bold uppercase tracking-wide text-app-faint">{label}</dt><dd className="m-0 mt-1 break-words text-app-text">{value}</dd></div>;
}

function isVerdict(value: string): value is ReadinessVerdict {
  return value === "ready" || value === "not_ready" || value === "incomplete";
}

function isGateStatus(value: string): value is ReadinessGateStatus {
  return value === "passed" || value === "failed" || value === "incomplete";
}

function isSafeReadiness(data: EvaluationReadiness): boolean {
  if (
    data.policy_id !== "queryops-v1-readiness-v1" ||
    !isVerdict(data.verdict) ||
    (data.provider !== null && data.provider !== "openai") ||
    !Array.isArray(data.gates) ||
    data.gates.length !== gateCodes.length ||
    !data.gates.every((gate, index) =>
      gate.code === gateCodes[index] &&
      typeof gate.label === "string" &&
      gate.label.length > 0 &&
      isGateStatus(gate.status) &&
      isBoundedRate(gate.threshold) &&
      isBoundedRate(gate.actual)
    )
  ) {
    return false;
  }
  if (data.provider === null) {
    return data.verdict === "incomplete" && data.model_label === null && data.completed_count === null;
  }
  if (
    typeof data.model_label !== "string" ||
    data.model_label.length === 0 ||
    data.completed_count !== 40
  ) {
    return false;
  }
  const statuses = data.gates.map((gate) => gate.status);
  if (data.verdict === "ready") return statuses.every((status) => status === "passed");
  if (data.verdict === "not_ready") {
    return statuses.includes("failed") && !statuses.includes("incomplete");
  }
  return statuses.includes("incomplete");
}

function isBoundedRate(value: number | null): boolean {
  return value === null || (
    typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1
  );
}
