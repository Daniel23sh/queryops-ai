import { useState } from "react";

import {
  BODY_TEXT_CLASS,
  FUTURE_OPERATION_PLACEHOLDERS,
  SECONDARY_BUTTON_CLASS
} from "./askDataStyles";

export function InsightsPanel() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <section
      className="rounded-card border border-app-border bg-app-muted p-1"
      aria-label="Ask Data insights"
    >
      <button
        type="button"
        className="qops-focus-ring flex min-h-12 w-full items-center justify-between gap-3 rounded-control border border-transparent bg-transparent px-3 py-2 text-left text-sm font-bold text-app-text transition hover:border-app-border hover:bg-app-surface"
        aria-expanded={isOpen}
        aria-label="Insights & next steps"
        onClick={() => setIsOpen((currentValue) => !currentValue)}
      >
        <span>Insights & next steps</span>
        <span className="text-xs font-bold uppercase text-app-faint" aria-hidden="true">
          {isOpen ? "Close" : "Open"}
        </span>
      </button>

      {isOpen ? (
        <div className="grid gap-3 px-3 pb-3 pt-1">
          <div className="grid gap-1 rounded-card border border-app-border bg-app-surface p-3">
            <h3 className="m-0 text-sm font-bold tracking-normal text-app-text">
              Insights
            </h3>
            <p className={BODY_TEXT_CLASS}>
              Result interpretation, assumptions, and visualization guidance stay
              close to the result workspace without occupying a permanent column.
            </p>
          </div>

          <div className="grid gap-1 rounded-card border border-app-border bg-app-surface p-3">
            <h3 className="m-0 text-sm font-bold tracking-normal text-app-text">
              Suggested Action
            </h3>
            <p className={BODY_TEXT_CLASS}>
              Operational recommendations remain disabled until the actions
              milestone defines preview, approval, and audit behavior.
            </p>
          </div>

          <div
            className="grid gap-2 sm:grid-cols-3"
            aria-label="Future operational controls"
          >
            {FUTURE_OPERATION_PLACEHOLDERS.map((placeholder) => (
              <div
                className="grid gap-2 rounded-card border border-app-border bg-app-surface p-3"
                key={placeholder.label}
              >
                <button
                  type="button"
                  className={`${SECONDARY_BUTTON_CLASS} w-full`}
                  disabled
                >
                  {placeholder.label}
                </button>
                <div>
                  <strong className="mb-1 block text-xs font-bold text-app-text">
                    {placeholder.milestone}
                  </strong>
                  <p className="m-0 text-xs leading-5 text-app-subtle">
                    {placeholder.summary}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
