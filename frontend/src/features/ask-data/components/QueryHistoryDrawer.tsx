import { useRef, type RefObject } from "react";
import { Clock3, RotateCw } from "lucide-react";

import { AccessibleOverlay } from "../../../components/ui/AccessibleOverlay";
import type { QueryHistoryItem, QueryTemplate } from "../types";

export function QueryHistoryDrawer({
  canRunFreeQuery,
  error,
  focusTargetRef,
  items,
  onClose,
  onRunFreeQuestion,
  onRunTemplate,
  onSelectTemplate,
  onUseQuestion,
  running,
  status,
  templates
}: {
  canRunFreeQuery: boolean;
  error: string | null;
  focusTargetRef: RefObject<HTMLElement>;
  items: QueryHistoryItem[];
  onClose: () => void;
  onRunFreeQuestion: (question: string) => void;
  onRunTemplate: (template: QueryTemplate) => void;
  onSelectTemplate: (template: QueryTemplate) => void;
  onUseQuestion: (question: string) => void;
  running: boolean;
  status: "idle" | "loading" | "loaded" | "error";
  templates: QueryTemplate[];
}) {
  const returnFocusRef = useRef<HTMLElement | null>(null);

  function closeAndFocus() {
    returnFocusRef.current = focusTargetRef.current;
    onClose();
  }

  function templateFor(item: QueryHistoryItem) {
    const templateId = item.metadata.template_id;
    return templateId ? templates.find((template) => template.id === templateId) ?? null : null;
  }

  return (
    <AccessibleOverlay kind="drawer" onClose={closeAndFocus} returnFocusRef={returnFocusRef} title="Recent history" description="Your five most recent governed query requests. Rerunning always executes a new query.">
      <div className="grid gap-4">
        {status === "loading" ? <p className="text-sm text-app-subtle" role="status">Loading recent history…</p> : null}
        {status === "error" ? <p className="text-sm text-status-danger" role="alert">{error}</p> : null}
        {status === "loaded" && items.length === 0 ? <p className="rounded-card border border-app-border bg-app-muted p-4 text-sm text-app-subtle">No query history yet.</p> : null}
        <ol className="m-0 grid list-none gap-3 p-0">
          {items.map((item) => {
            const templateId = item.metadata.template_id;
            const template = templateFor(item);
            const canRerun = templateId ? Boolean(template) : canRunFreeQuery;
            return (
              <li key={item.id} className="grid gap-3 rounded-card border border-app-border bg-app-muted p-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-app-faint">
                    <span className="capitalize">{item.status.replace(/_/g, " ")}</span>
                    {templateId ? <span className="rounded-full border border-app-border px-2 py-0.5">Template</span> : null}
                  </div>
                  <p className="mb-0 mt-2 text-sm font-semibold leading-6 text-app-text">{item.natural_language_question}</p>
                  <p className="mb-0 mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-app-faint">
                    <span className="inline-flex items-center gap-1"><Clock3 aria-hidden="true" size={14} />{formatHistoryTime(item.completed_at ?? item.created_at)}</span>
                    {item.row_count !== null ? <span>{item.row_count} {item.row_count === 1 ? "row" : "rows"}</span> : null}
                    {item.duration_ms !== null ? <span>{formatDuration(item.duration_ms)}</span> : null}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {canRerun ? (
                    <button className="qops-button-primary min-h-11" type="button" disabled={running} onClick={() => {
                      closeAndFocus();
                      if (template) onRunTemplate(template);
                      else onRunFreeQuestion(item.natural_language_question);
                    }}><RotateCw aria-hidden="true" size={16} />Run again</button>
                  ) : (
                    <span className="self-center text-xs text-app-faint">{templateId ? "Template is no longer available." : "Free-query access is required to rerun."}</span>
                  )}
                  {canRunFreeQuery ? (
                    <button className="qops-button-secondary min-h-11" type="button" disabled={running} onClick={() => { onUseQuestion(item.natural_language_question); closeAndFocus(); }}>Use question</button>
                  ) : template ? (
                    <button className="qops-button-secondary min-h-11" type="button" disabled={running} onClick={() => { onSelectTemplate(template); closeAndFocus(); }}>Select template</button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </AccessibleOverlay>
  );
}

function formatHistoryTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Recently" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function formatDuration(durationMs: number): string {
  return durationMs < 1000 ? `${durationMs} ms` : `${(durationMs / 1000).toFixed(1)} s`;
}
