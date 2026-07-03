import type { QueryTemplate } from "../types";

export function TemplateCard({
  isSelected,
  onSelect,
  template
}: {
  isSelected: boolean;
  onSelect: () => void;
  template: QueryTemplate;
}) {
  return (
    <button
      type="button"
      className={`qops-focus-ring grid w-full gap-1 rounded-card border p-3 text-left transition hover:border-brand-primary hover:bg-app-surface hover:shadow-sm ${
        isSelected
          ? "border-brand-primary bg-app-surface shadow-sm ring-1 ring-brand-primary/20"
          : "border-app-border bg-app-muted"
      }`}
      aria-pressed={isSelected}
      data-selected={isSelected ? "true" : "false"}
      onClick={onSelect}
    >
      <strong
        className={isSelected ? "text-brand-accent-strong" : "text-app-text"}
      >
        {template.title}
      </strong>
      <p className="m-0 line-clamp-2 text-xs leading-5 text-app-subtle">
        {template.description}
      </p>
    </button>
  );
}
