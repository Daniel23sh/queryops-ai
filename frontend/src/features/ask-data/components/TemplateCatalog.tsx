import type {
  QueryTemplate,
  QueryTemplateCategory,
  TemplateLoadStatus
} from "../types";
import {
  BODY_TEXT_CLASS,
  ERROR_CARD_CLASS,
  EYEBROW_CLASS,
  INFO_CARD_CLASS,
  MUTED_CARD_CLASS,
  PANEL_CLASS,
  PANEL_HEADER_CLASS,
  PANEL_TITLE_CLASS
} from "./askDataStyles";
import { SelectedTemplateDetails } from "./SelectedTemplateDetails";
import { TemplateCard } from "./TemplateCard";

export function TemplateCatalog({
  categories,
  error,
  onSelectTemplate,
  onRunSelectedTemplate,
  runDisabledReason,
  running,
  selectedTemplate,
  selectedTemplateId,
  status
}: {
  categories: QueryTemplateCategory[];
  error: string | null;
  onSelectTemplate: (templateId: string) => void;
  onRunSelectedTemplate: () => void;
  runDisabledReason: string | null;
  running: boolean;
  selectedTemplate: QueryTemplate | null;
  selectedTemplateId: string | null;
  status: TemplateLoadStatus;
}) {
  const hasTemplates = categories.length > 0;

  return (
    <section
      className={`${PANEL_CLASS} gap-3 xl:sticky xl:top-6`}
      aria-label="Template catalog"
    >
      <div className={PANEL_HEADER_CLASS}>
        <p className={EYEBROW_CLASS}>Approved templates</p>
        <h2 className={PANEL_TITLE_CLASS}>Template catalog</h2>
        <p className={BODY_TEXT_CLASS}>
          Pick a governed starting point. Details stay compact until you run it.
        </p>
      </div>

      {status === "loading" ? (
        <p className={`${INFO_CARD_CLASS} py-3`} role="status">
          <span className="font-bold text-app-text">Loading query templates...</span>
          <span className="block text-app-subtle">
            The approved template catalog is being prepared for this role.
          </span>
        </p>
      ) : null}

      {status === "error" ? (
        <p className={ERROR_CARD_CLASS} role="alert">
          <strong className="block text-state-danger">Template catalog unavailable</strong>
          <span>{error ?? "Query templates could not be loaded."}</span>
        </p>
      ) : null}

      {status === "loaded" && !hasTemplates ? (
        <p className={MUTED_CARD_CLASS}>
          <strong className="text-app-text">No query templates are available yet.</strong>
          <span>Approved templates will appear here when they are published.</span>
        </p>
      ) : null}

      {status === "loaded" && hasTemplates ? (
        <>
          <div
            className="flex gap-2 overflow-x-auto pb-1"
            aria-label="Query template categories"
          >
            {categories.map((group) => (
              <button
                key={group.category}
                type="button"
                className="qops-focus-ring inline-flex min-h-9 shrink-0 items-center rounded-control border border-app-border bg-app-muted px-3 text-xs font-bold text-app-text transition hover:border-brand-primary hover:text-brand-primary"
                onClick={() => onSelectTemplate(group.templates[0].id)}
              >
                {group.category}
              </button>
            ))}
          </div>

          <ul
            className="m-0 grid max-h-[22rem] list-none gap-2 overflow-y-auto p-0 pr-1"
            aria-label="Query templates"
          >
            {categories.flatMap((group) =>
              group.templates.map((template) => (
                <li key={template.id}>
                  <TemplateCard
                    isSelected={template.id === selectedTemplateId}
                    onSelect={() => onSelectTemplate(template.id)}
                    template={template}
                  />
                </li>
              ))
            )}
          </ul>
        </>
      ) : null}

      <SelectedTemplateDetails
        disabledReason={runDisabledReason}
        onRunSelectedTemplate={onRunSelectedTemplate}
        running={running}
        template={selectedTemplate}
      />
    </section>
  );
}
