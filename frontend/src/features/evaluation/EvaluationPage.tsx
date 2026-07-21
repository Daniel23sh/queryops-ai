import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { evaluationRequestKey, getEvaluationOverview } from "../../api/evaluation";
import { hasPermission } from "../../auth/permissions";
import type { AuthUser } from "../../auth/types";
import { EvaluationCapabilityTab } from "./components/EvaluationCapabilityTab";
import { EvaluationOverviewTab } from "./components/EvaluationOverviewTab";
import { EvaluationQueriesTab } from "./components/EvaluationQueriesTab";
import { EvaluationSecurityTab } from "./components/EvaluationSecurityTab";
import { EvaluationStatePanel } from "./components/EvaluationPrimitives";
import { EvaluationTabs } from "./components/EvaluationTabs";
import { useEvaluationResource } from "./hooks/useEvaluationResource";
import { evaluationIdentityKey } from "./identity";
import type { EvaluationOverview, EvaluationTab } from "./types";

const validTabs: EvaluationTab[] = ["overview", "queries", "actions", "security", "dashboards"];

export function EvaluationPage({ user }: { user: AuthUser }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const identityKey = useMemo(() => evaluationIdentityKey(user), [user]);
  const [accessRevokedFor, setAccessRevokedFor] = useState<string | null>(null);
  const requestedTab = searchParams.get("tab");
  const activeTab = validTabs.includes(requestedTab as EvaluationTab) ? requestedTab as EvaluationTab : "overview";
  const loadOverview = useCallback((signal: AbortSignal) => getEvaluationOverview(undefined, signal), []);
  const overview = useEvaluationResource<EvaluationOverview>({
    load: loadOverview,
    requestKey: evaluationRequestKey(identityKey, "overview", null)
  });

  useEffect(() => {
    if (requestedTab && !validTabs.includes(requestedTab as EvaluationTab)) {
      setSearchParams(new URLSearchParams(), { replace: true });
    }
  }, [requestedTab, setSearchParams]);
  useEffect(() => {
    if (overview.error === "forbidden") setAccessRevokedFor(identityKey);
  }, [identityKey, overview.error]);

  const accessRevoked = accessRevokedFor === identityKey;
  const denyCurrentProjection = useCallback(() => setAccessRevokedFor(identityKey), [identityKey]);
  const loadLatest = useCallback(() => {
    setAccessRevokedFor(null);
    navigate("/evaluation", { replace: true });
    overview.reload();
  }, [navigate, overview.reload]);

  return (
    <div className="grid gap-6">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="m-0 text-xs font-bold uppercase tracking-wide text-brand-primary">Quality measurement</p>
          <h1 className="mb-0 mt-1 text-3xl font-bold tracking-tight text-app-text">Evaluation</h1>
          <p className="mb-0 mt-2 max-w-4xl text-sm leading-6 text-app-subtle">Review the latest supported stored evaluation through your {projectionLabel(user)}. This workspace is read-only and cannot start or rerun evaluation.</p>
        </div>
        {overview.data?.run && !accessRevoked ? <p className="m-0 text-xs text-app-faint">Run {overview.data.run.id}</p> : null}
      </header>

      <EvaluationTabs activeTab={activeTab} />

      {accessRevoked ? <EvaluationStatePanel kind="error" title="Evaluation access changed" message="Your current identity, permissions, or scope no longer permits this evaluation projection. Previously loaded metrics have been removed." /> : null}
      {!accessRevoked && overview.status === "loading" ? <EvaluationStatePanel title="Loading evaluation overview…" message="Selecting the latest run visible to your current access context." /> : null}
      {!accessRevoked && overview.status === "error" ? <OverviewError error={overview.error} onRetry={overview.reload} /> : null}
      {!accessRevoked && overview.status === "success" && overview.data && !overview.data.run ? <EvaluationStatePanel title="No visible evaluation run" message="No completed or in-progress evaluation run is available to your current access context. Run history and arbitrary run lookup are not available in this workspace." /> : null}
      {!accessRevoked && overview.status === "success" && overview.data?.run ? (
        <EvaluationTabContent
          activeTab={activeTab}
          identityKey={identityKey}
          onForbidden={denyCurrentProjection}
          onLatest={loadLatest}
          overview={overview.data}
          runId={overview.data.run.id}
        />
      ) : null}
    </div>
  );
}

function EvaluationTabContent({ activeTab, identityKey, onForbidden, onLatest, overview, runId }: {
  activeTab: EvaluationTab;
  identityKey: string;
  onForbidden: () => void;
  onLatest: () => void;
  overview: EvaluationOverview;
  runId: string;
}) {
  if (activeTab === "overview") return <EvaluationOverviewTab data={overview} />;
  if (activeTab === "queries") return <EvaluationQueriesTab categories={overview.by_category.map((item) => item.key)} identityKey={identityKey} onForbidden={onForbidden} onLatest={onLatest} runId={runId} />;
  if (activeTab === "security") return <EvaluationSecurityTab identityKey={identityKey} onForbidden={onForbidden} onLatest={onLatest} runId={runId} />;
  return <EvaluationCapabilityTab capability={activeTab} identityKey={identityKey} onForbidden={onForbidden} onLatest={onLatest} runId={runId} />;
}

function OverviewError({ error, onRetry }: { error: "forbidden" | "not_found" | "invalid_filter" | "unavailable" | null; onRetry: () => void }) {
  if (error === "forbidden") return null;
  if (error === "not_found") return <EvaluationStatePanel title="No visible evaluation run" message="The latest run is not available to your current access context." />;
  return <EvaluationStatePanel kind="error" title="Evaluation metrics are temporarily unavailable" message="No stored details from a previous identity or request are shown. Try again when the service is available." onAction={onRetry} />;
}

function projectionLabel(user: AuthUser): string {
  if (hasPermission(user, "can_view_global_evaluation")) return "global evaluation projection";
  if (hasPermission(user, "can_view_scope_evaluation")) return "assigned-scope evaluation projection";
  return "department evaluation projection";
}
