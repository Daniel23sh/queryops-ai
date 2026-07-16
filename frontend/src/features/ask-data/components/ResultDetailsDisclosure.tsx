import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

import type { CurrentQueryResult, QueryRunState } from "../types";
import { DiagnosticsTab } from "./DiagnosticsTab";
import { SqlTab } from "./SqlTab";

type DetailTab = "summary" | "sql" | "diagnostics";

export function ResultDetailsDisclosure({
  canViewTechnicalDetails,
  current
}: {
  canViewTechnicalDetails: boolean;
  current: CurrentQueryResult;
}) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<DetailTab>("summary");
  const state: QueryRunState = { status: "success", question: current.question, result: current.result };

  useEffect(() => {
    setOpen(false);
    setTab("summary");
  }, [current.generation]);

  return (
    <section className="border-t border-app-border pt-4">
      <button className="flex min-h-11 w-full items-center justify-between rounded-control px-2 text-left text-sm font-bold text-app-text hover:bg-app-muted focus:shadow-focus" type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        Result details
        <ChevronDown aria-hidden="true" className={open ? "rotate-180 transition" : "transition"} size={18} />
      </button>
      {open ? (
        <div className="mt-3 grid gap-3">
          <div className="flex gap-1 overflow-x-auto rounded-control bg-app-muted p-1" role="tablist" aria-label="Result details">
            <DetailButton active={tab === "summary"} label="Summary" onClick={() => setTab("summary")} />
            {canViewTechnicalDetails ? <DetailButton active={tab === "sql"} label="SQL" onClick={() => setTab("sql")} /> : null}
            {canViewTechnicalDetails ? <DetailButton active={tab === "diagnostics"} label="Diagnostics" onClick={() => setTab("diagnostics")} /> : null}
          </div>
          <div role="tabpanel" aria-label={`${capitalize(tab)} details`}>
            {tab === "summary" ? <ResultSummary current={current} /> : null}
            {tab === "sql" && canViewTechnicalDetails ? <SqlTab queryRunState={state} /> : null}
            {tab === "diagnostics" && canViewTechnicalDetails ? <DiagnosticsTab queryRunState={state} /> : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function DetailButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return <button className={active ? "min-h-10 flex-1 rounded-control bg-app-surface px-3 text-sm font-bold text-app-text shadow-sm" : "min-h-10 flex-1 rounded-control px-3 text-sm font-semibold text-app-subtle hover:text-app-text"} type="button" role="tab" aria-selected={active} onClick={onClick}>{label}</button>;
}

function ResultSummary({ current }: { current: CurrentQueryResult }) {
  const { result } = current;
  return (
    <div className="grid gap-3 rounded-card border border-app-border bg-app-muted p-4 text-sm leading-6 text-app-subtle">
      <p className="m-0 text-app-text">{result.message}</p>
      <dl className="m-0 grid gap-2 sm:grid-cols-2">
        <div><dt className="font-bold text-app-faint">Question</dt><dd className="m-0">{current.originalQuestion}</dd></div>
        {current.clarificationResponse ? <div><dt className="font-bold text-app-faint">Clarification</dt><dd className="m-0">{current.clarificationResponse}</dd></div> : null}
        <div><dt className="font-bold text-app-faint">Rows</dt><dd className="m-0">{result.row_count}</dd></div>
        <div><dt className="font-bold text-app-faint">Duration</dt><dd className="m-0">{formatDuration(result.duration_ms)}</dd></div>
      </dl>
      {result.warnings.length ? <p className="m-0">{result.warnings.length} {result.warnings.length === 1 ? "warning" : "warnings"}.{result.truncated ? " Result is truncated." : ""}</p> : result.truncated ? <p className="m-0">Result is truncated.</p> : null}
    </div>
  );
}

function capitalize(value: string) { return value[0].toUpperCase() + value.slice(1); }
function formatDuration(value: number) { return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`; }
