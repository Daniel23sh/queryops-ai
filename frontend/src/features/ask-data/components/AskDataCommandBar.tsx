import { forwardRef, type KeyboardEvent } from "react";
import { Play, Search } from "lucide-react";

import type { QueryRequestState, QueryTemplate } from "../types";
import { SelectedTemplateBadge } from "./SelectedTemplateBadge";

export const AskDataCommandBar = forwardRef<
  HTMLDivElement,
  {
    canRunFreeQuery: boolean;
    composerText: string;
    csrfToken: string | null;
    onChange: (value: string) => void;
    onChooseTemplate: () => void;
    onClearTemplate: () => void;
    onRun: () => void;
    requestState: QueryRequestState;
    selectedTemplate: QueryTemplate | null;
  }
>(function AskDataCommandBar(
  {
    canRunFreeQuery,
    composerText,
    csrfToken,
    onChange,
    onChooseTemplate,
    onClearTemplate,
    onRun,
    requestState,
    selectedTemplate
  },
  ref
) {
  const running = requestState.status === "running";
  const canRun = Boolean(csrfToken && selectedTemplate) || Boolean(csrfToken && canRunFreeQuery && composerText.trim());

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canRun && !running) onRun();
    }
  }

  return (
    <section ref={ref} tabIndex={-1} className="rounded-card border border-app-border bg-app-surface p-4 shadow-card outline-none sm:p-5" aria-label="Ask Data command">
      <div className="grid gap-3">
        {selectedTemplate ? (
          <SelectedTemplateBadge template={selectedTemplate} canClear={canRunFreeQuery} onClear={onClearTemplate} />
        ) : null}

        {canRunFreeQuery ? (
          <label className="grid gap-2" htmlFor="ask-data-question">
            <span className="qops-sr-only">Question</span>
            <textarea
              id="ask-data-question"
              className="min-h-28 w-full resize-y rounded-card border border-app-border bg-app-muted px-4 py-3 text-base leading-7 text-app-text outline-none transition placeholder:text-app-faint hover:border-brand-primary focus:border-brand-primary focus:shadow-focus disabled:cursor-wait disabled:opacity-70"
              disabled={running}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about the data you can access…"
              value={composerText}
            />
          </label>
        ) : selectedTemplate ? (
          <div className="rounded-card border border-app-border bg-app-muted px-4 py-3 text-base leading-7 text-app-text" aria-label="Approved template question">
            {selectedTemplate.natural_language_question}
          </div>
        ) : (
          <button className="flex min-h-28 w-full items-center justify-center gap-2 rounded-card border border-dashed border-app-border bg-app-muted px-4 text-base font-bold text-app-text hover:border-brand-primary focus:shadow-focus" type="button" onClick={onChooseTemplate}>
            <Search aria-hidden="true" size={20} />
            Choose a template
          </button>
        )}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="m-0 text-xs leading-5 text-app-faint">
            {selectedTemplate
              ? `Template question · ${canRunFreeQuery ? "Enter to run" : "approved question"}`
              : canRunFreeQuery
                ? "Free question · Enter to run · Shift+Enter for a new line"
                : "Choose an approved template"}
          </p>
          <div className="flex flex-wrap justify-end gap-2">
            {canRunFreeQuery ? (
              <button className="qops-button-secondary min-h-11" type="button" onClick={onChooseTemplate} disabled={running}>
                Templates
              </button>
            ) : null}
            <button className="qops-button-primary min-h-11" type="button" onClick={onRun} disabled={!canRun || running}>
              <Play aria-hidden="true" size={18} />
              {running ? "Running…" : "Run"}
            </button>
          </div>
        </div>
        {!csrfToken ? <p className="m-0 text-sm text-status-danger" role="alert">Refresh your session before running a query.</p> : null}
        {requestState.status === "error" ? <p className="m-0 rounded-control border border-status-danger/40 bg-status-danger/10 px-3 py-2 text-sm text-app-text" role="alert">{requestState.message}</p> : null}
      </div>
    </section>
  );
});
