import type { ReactNode } from "react";
import { useCallback, useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { evaluationRequestKey, getEvaluationQueries } from "../../../api/evaluation";
import { useEvaluationResource } from "../hooks/useEvaluationResource";
import { formatEvaluationPercent, matchesSelectedRun, safeBreakdownLabel } from "../presentation";
import type {
  EvaluationActualOutcome,
  EvaluationCaseType,
  EvaluationDifficulty,
  EvaluationQueries,
  EvaluationQueryFilters
} from "../types";
import { EvaluationCaseCard } from "./EvaluationCaseDetails";
import { EvaluationChildError } from "./EvaluationCapabilityTab";
import { BreakdownTable, EvaluationStatePanel, MeasurementProgress, MetricCard } from "./EvaluationPrimitives";

const difficulties: EvaluationDifficulty[] = ["easy", "medium", "hard", "security"];
const caseTypes: EvaluationCaseType[] = ["template_query", "free_query", "authorization", "unsafe_sql", "clarification"];
const outcomes: EvaluationActualOutcome[] = ["success", "denied", "unsafe_blocked", "clarification", "execution_failed", "internal_error"];
const pageSizes = [10, 25, 50];

export function EvaluationQueriesTab({ categories, identityKey, onForbidden, onLatest, runId }: {
  categories: string[];
  identityKey: string;
  onForbidden: () => void;
  onLatest: () => void;
  runId: string;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const parsed = parseFilters(searchParams, categories);
  const filters: EvaluationQueryFilters = {
    runId,
    difficulty: parsed.difficulty,
    category: parsed.category,
    caseType: parsed.caseType,
    outcome: parsed.outcome,
    passed: parsed.passed,
    limit: parsed.pageSize,
    offset: (parsed.page - 1) * parsed.pageSize
  };
  const filterKey = JSON.stringify(filters);
  const load = useCallback((signal: AbortSignal) => getEvaluationQueries(filters, signal), [filterKey]);
  const state = useEvaluationResource<EvaluationQueries>({ enabled: !parsed.invalid, load, requestKey: evaluationRequestKey(identityKey, "queries", runId, filterKey) });
  useEffect(() => { if (state.error === "forbidden") onForbidden(); }, [onForbidden, state.error]);

  const updateFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value); else next.delete(key);
    next.delete("page");
    setSearchParams(next);
  };
  const reset = () => setSearchParams(new URLSearchParams("tab=queries"));

  if (parsed.invalid) return <EvaluationStatePanel kind="error" title="The selected filters are not valid" message="Reset the view to supported evaluation filters." actionLabel="Reset filters" onAction={reset} />;

  return (
    <div className="grid gap-6">
      <section className="grid gap-4" aria-labelledby="query-evaluation-title">
        <div><h2 className="m-0 text-xl font-bold text-app-text" id="query-evaluation-title">Query measurements</h2><p className="mb-0 mt-2 max-w-4xl text-sm leading-6 text-app-subtle">Filter the authorized case projection for this exact run. MockLLM gaps remain visible and are not skipped.</p></div>
        <div className="grid gap-3 rounded-card border border-app-border bg-app-surface p-4 sm:grid-cols-2 xl:grid-cols-6" aria-label="Query measurement filters">
          <FilterSelect label="Difficulty" value={parsed.difficulty ?? ""} onChange={(value) => updateFilter("difficulty", value)} options={difficulties.map((value) => [value, safeBreakdownLabel(value)])} />
          <FilterSelect label="Category" value={parsed.category ?? ""} onChange={(value) => updateFilter("category", value)} options={categories.map((value) => [value, safeBreakdownLabel(value)])} />
          <FilterSelect label="Case type" value={parsed.caseType ?? ""} onChange={(value) => updateFilter("case_type", value)} options={caseTypes.map((value) => [value, safeBreakdownLabel(value)])} />
          <FilterSelect label="Actual outcome" value={parsed.outcome ?? ""} onChange={(value) => updateFilter("outcome", value)} options={outcomes.map((value) => [value, safeBreakdownLabel(value)])} />
          <FilterSelect label="Result" value={parsed.passed === undefined ? "" : String(parsed.passed)} onChange={(value) => updateFilter("passed", value)} options={[["true", "Passed"], ["false", "Did not pass"]]} />
          <FilterSelect label="Per page" value={String(parsed.pageSize)} onChange={(value) => updateFilter("page_size", value)} includeAll={false} options={pageSizes.map((value) => [String(value), String(value)])} />
          <button className="qops-button-secondary justify-self-start sm:col-span-2 xl:col-span-6" type="button" onClick={reset}>Reset filters</button>
        </div>
      </section>

      {state.status === "loading" ? <EvaluationStatePanel title="Loading query measurements…" message="Loading the selected authorized case page." /> : null}
      {state.status === "error" ? <EvaluationChildError error={state.error} onLatest={onLatest} onRetry={state.reload} /> : null}
      {state.status === "success" && state.data && !matchesSelectedRun(state.data.run, runId) ? <EvaluationStatePanel kind="error" title="The selected run could not be verified" message="The response did not match the run selected by Overview. No query metrics are shown." actionLabel="Load latest run" onAction={onLatest} /> : null}
      {state.status === "success" && state.data && matchesSelectedRun(state.data.run, runId) ? <QueryResults data={state.data} page={parsed.page} onPage={(page) => { const next = new URLSearchParams(searchParams); if (page <= 1) next.delete("page"); else next.set("page", String(page)); setSearchParams(next); }} /> : null}
    </div>
  );
}

function QueryResults({ data, onPage, page }: { data: EvaluationQueries; onPage: (page: number) => void; page: number }) {
  const maxPage = Math.max(1, Math.ceil(data.pagination.total / data.pagination.limit));
  return <>
    <section className="grid gap-4" aria-label="Filtered query summary">
      <MeasurementProgress label="Filtered visible cases" metrics={data.metrics} />
      <div className="grid gap-3 sm:grid-cols-3"><MetricCard label="Visible results" value={data.pagination.total} detail={`${data.pagination.returned} on this page`} /><MetricCard label="Passed" value={data.metrics.passed_count} detail={`${data.metrics.failed_count} did not pass`} /><MetricCard label="Semantic score" value={formatEvaluationPercent(data.metrics.overall_score)} detail="Selected completed cases" /></div>
    </section>
    <section className="grid gap-4 lg:grid-cols-3" aria-label="Filtered query breakdowns"><BreakdownPanel title="Difficulty"><BreakdownTable caption="Filtered query results by difficulty" items={data.by_difficulty} /></BreakdownPanel><BreakdownPanel title="Category"><BreakdownTable caption="Filtered query results by category" items={data.by_category} /></BreakdownPanel><BreakdownPanel title="Case type"><BreakdownTable caption="Filtered query results by case type" items={data.by_case_type} /></BreakdownPanel></section>
    <section className="grid gap-3" aria-labelledby="query-cases-title"><h3 className="m-0 text-lg font-bold text-app-text" id="query-cases-title">Cases</h3>{data.items.length ? data.items.map((item) => <EvaluationCaseCard item={item} key={item.case_id} />) : <EvaluationStatePanel title="No cases match these filters" message="Change or reset the filters to see another authorized measurement set." />}</section>
    {data.pagination.total ? <nav aria-label="Query measurement pages" className="flex flex-wrap items-center justify-between gap-3"><button className="qops-button-secondary" disabled={page <= 1} onClick={() => onPage(Math.min(page - 1, maxPage))} type="button">Previous</button><span className="text-sm text-app-subtle">Page {page} of {maxPage}</span><button className="qops-button-secondary" disabled={page >= maxPage} onClick={() => onPage(page + 1)} type="button">Next</button></nav> : null}
  </>;
}

function FilterSelect({ includeAll = true, label, onChange, options, value }: { includeAll?: boolean; label: string; onChange: (value: string) => void; options: string[][]; value: string }) {
  return <label className="grid gap-1.5 text-sm font-bold text-app-text">{label}<select className="min-h-11 rounded-control border border-app-border bg-app-surface px-3 py-2 font-normal outline-none focus:border-brand-primary focus:shadow-focus" value={value} onChange={(event) => onChange(event.target.value)}>{includeAll ? <option value="">All</option> : null}{options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}</select></label>;
}

function BreakdownPanel({ children, title }: { children: ReactNode; title: string }) {
  return <section className="min-w-0 rounded-card border border-app-border bg-app-surface p-4"><h3 className="m-0 mb-3 text-base font-bold text-app-text">{title}</h3>{children}</section>;
}

function parseFilters(params: URLSearchParams, categories: string[]) {
  const difficulty = optionalEnum(params.get("difficulty"), difficulties);
  const caseType = optionalEnum(params.get("case_type"), caseTypes);
  const outcome = optionalEnum(params.get("outcome"), outcomes);
  const categoryValue = params.get("category");
  const category = categoryValue && categories.includes(categoryValue) ? categoryValue : undefined;
  const passedValue = params.get("passed");
  const passed = passedValue === "true" ? true : passedValue === "false" ? false : undefined;
  const page = positiveInteger(params.get("page"), 1);
  const pageSize = pageSizes.includes(Number(params.get("page_size"))) ? Number(params.get("page_size")) : 25;
  const invalid = Boolean((params.get("difficulty") && !difficulty) || (params.get("case_type") && !caseType) || (params.get("outcome") && !outcome) || (categoryValue && !category) || (passedValue && passed === undefined) || (params.get("page") && page === 1 && params.get("page") !== "1") || (params.get("page_size") && !pageSizes.includes(Number(params.get("page_size")))));
  return { category, caseType, difficulty, invalid, outcome, page, pageSize, passed };
}

function optionalEnum<T extends string>(value: string | null, values: readonly T[]): T | undefined {
  return value && values.includes(value as T) ? value as T : undefined;
}

function positiveInteger(value: string | null, fallback: number): number {
  if (!value || !/^\d+$/.test(value)) return fallback;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 1 ? parsed : fallback;
}
