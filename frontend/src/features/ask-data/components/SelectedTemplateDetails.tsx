import type { QueryTemplate } from "../types";
import {
  BODY_TEXT_CLASS,
  PRIMARY_BUTTON_CLASS,
  SESSION_MESSAGE_CLASS
} from "./askDataStyles";

export function SelectedTemplateDetails({
  disabledReason,
  onRunSelectedTemplate,
  running,
  template
}: {
  disabledReason: string | null;
  onRunSelectedTemplate: () => void;
  running: boolean;
  template: QueryTemplate | null;
}) {
  const canRunTemplate = template !== null && disabledReason === null && !running;

  return (
    <div
      className="grid gap-3 rounded-card border border-app-border bg-app-muted p-3.5 text-sm leading-6 text-app-subtle"
      aria-label="Selected template details"
    >
      <h3 className="m-0 text-sm font-bold tracking-normal text-app-text">
        Selected template details
      </h3>
      {template ? (
        <>
          <div className="grid gap-1">
            <strong className="text-app-text">{template.title}</strong>
            <p className="m-0 text-xs leading-5 text-app-subtle">
              {template.description}
            </p>
          </div>
          <p className="m-0 rounded-card border border-app-border bg-app-surface px-3 py-2 text-xs leading-5 text-app-subtle">
            {template.natural_language_question}
          </p>
          {template.parameters.length > 0 ? (
            <p className="m-0 border-l-4 border-brand-primary pl-3 text-xs leading-5 text-app-subtle">
              Custom parameters are not supported yet; backend template defaults
              will be used.
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              className={`${PRIMARY_BUTTON_CLASS} w-full`}
              disabled={!canRunTemplate}
              onClick={onRunSelectedTemplate}
            >
              {running ? "Running template..." : "Run selected template"}
            </button>
          </div>
          {disabledReason ? (
            <p className={SESSION_MESSAGE_CLASS}>{disabledReason}</p>
          ) : null}
        </>
      ) : (
        <p className={BODY_TEXT_CLASS}>
          Select a template to view its default question and scope.
        </p>
      )}
    </div>
  );
}
