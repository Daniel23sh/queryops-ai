import { X } from "lucide-react";

import type { QueryTemplate } from "../types";

export function SelectedTemplateBadge({
  canClear,
  onClear,
  template
}: {
  canClear: boolean;
  onClear: () => void;
  template: QueryTemplate;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-control border border-brand-primary/40 bg-brand-primary/10 px-3 py-2 text-sm text-app-text">
      <span className="min-w-0 truncate">
        <span className="text-app-faint">Template:</span>{" "}
        <strong>{template.title}</strong>
      </span>
      {canClear ? (
        <button className="ml-auto grid size-8 shrink-0 place-items-center rounded-control hover:bg-app-muted focus:shadow-focus" type="button" onClick={onClear} aria-label="Clear selected template">
          <X aria-hidden="true" size={16} />
        </button>
      ) : null}
    </div>
  );
}
