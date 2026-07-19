import { ShieldCheck } from "lucide-react";

import type { ActionResolution } from "../types";

export function ActionRecommendationCard({
  resolution,
  scopeLabel,
  onPreview
}: {
  resolution: Exclude<ActionResolution, { status: "hidden" }>;
  scopeLabel: string;
  onPreview: (resolution: Extract<ActionResolution, { status: "available" }>) => void;
}) {
  return (
    <aside className="grid gap-3 rounded-card border border-brand-primary/30 bg-brand-primary/10 p-4" aria-label="Suggested action">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-control bg-brand-primary text-white">
          <ShieldCheck aria-hidden="true" size={20} />
        </span>
        <div className="min-w-0">
          <p className="m-0 text-xs font-bold uppercase tracking-wide text-brand-primary">Suggested action</p>
          <h4 className="mb-0 mt-1 text-base font-bold text-app-text">
            {resolution.status === "available"
              ? resolution.suggestion.label
              : "Action preview unavailable"}
          </h4>
        </div>
      </div>
      {resolution.status === "available" ? (
        <>
          <p className="m-0 text-sm leading-6 text-app-subtle">
            Preview {resolution.targetCount} visible-result {resolution.targetCount === 1 ? "target" : "targets"} in {scopeLabel}. Approval and current-state revalidation are required before any change.
          </p>
          <button
            className="qops-button-primary min-h-11 justify-self-start"
            onClick={() => onPreview(resolution)}
            type="button"
          >
            Preview Action
          </button>
        </>
      ) : (
        <p className="m-0 text-sm leading-6 text-app-subtle">{resolution.reason}</p>
      )}
    </aside>
  );
}
