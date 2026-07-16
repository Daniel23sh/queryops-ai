import { useMemo, useRef, useState, type RefObject } from "react";
import { Check, Search } from "lucide-react";

import { AccessibleOverlay } from "../../../components/ui/AccessibleOverlay";
import type { QueryTemplate, TemplateLoadStatus } from "../types";

export function TemplateDrawer({
  error,
  focusTargetRef,
  onClose,
  onSelect,
  selectedTemplateId,
  status,
  templates
}: {
  error: string | null;
  focusTargetRef: RefObject<HTMLElement>;
  onClose: () => void;
  onSelect: (template: QueryTemplate) => void;
  selectedTemplateId: string | null;
  status: TemplateLoadStatus;
  templates: QueryTemplate[];
}) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const searchRef = useRef<HTMLInputElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const categories = useMemo(() => ["All", ...new Set(templates.map((template) => template.category))], [templates]);
  const visibleTemplates = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    return templates.filter((template) => {
      const matchesCategory = category === "All" || template.category === category;
      const haystack = `${template.title} ${template.description} ${template.category} ${template.natural_language_question}`.toLowerCase();
      return matchesCategory && (!normalized || haystack.includes(normalized));
    });
  }, [category, search, templates]);

  function choose(template: QueryTemplate) {
    onSelect(template);
    returnFocusRef.current = focusTargetRef.current;
    onClose();
  }

  return (
    <AccessibleOverlay initialFocusRef={searchRef} kind="drawer" onClose={onClose} returnFocusRef={returnFocusRef} title="Templates" description="Choose an approved question. Selection does not run it automatically.">
      <div className="grid gap-5">
        <label className="relative" htmlFor="template-search">
          <span className="qops-sr-only">Search templates</span>
          <Search className="pointer-events-none absolute left-3 top-3.5 text-app-faint" aria-hidden="true" size={18} />
          <input id="template-search" ref={searchRef} className="min-h-11 w-full rounded-control border border-app-border bg-app-muted py-2 pl-10 pr-3 text-sm text-app-text outline-none focus:border-brand-primary focus:shadow-focus" placeholder="Search templates" value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
        <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Template categories">
          {categories.map((item) => <button key={item} className={item === category ? "qops-button-primary min-h-11 shrink-0" : "qops-button-secondary min-h-11 shrink-0"} type="button" aria-pressed={item === category} onClick={() => setCategory(item)}>{item}</button>)}
        </div>
        {status === "loading" ? <p role="status" className="text-sm text-app-subtle">Loading approved templates…</p> : null}
        {status === "error" ? <p role="alert" className="text-sm text-status-danger">{error ?? "Templates could not be loaded."}</p> : null}
        {status === "loaded" && visibleTemplates.length === 0 ? <p className="rounded-card border border-app-border bg-app-muted p-4 text-sm text-app-subtle">No approved templates match this search.</p> : null}
        <ul className="m-0 grid list-none gap-3 p-0">
          {visibleTemplates.map((template) => {
            const selected = template.id === selectedTemplateId;
            return (
              <li key={template.id} className="grid gap-3 rounded-card border border-app-border bg-app-muted p-4">
                <div>
                  <p className="m-0 text-xs font-bold uppercase tracking-wide text-app-faint">{template.category}</p>
                  <h3 className="mb-0 mt-1 text-base font-bold text-app-text">{template.title}</h3>
                  <p className="mb-0 mt-1 text-sm leading-6 text-app-subtle">{template.description}</p>
                  <p className="mb-0 mt-2 text-sm leading-6 text-app-text">{template.natural_language_question}</p>
                </div>
                <button className="qops-button-secondary min-h-11 justify-self-start" type="button" onClick={() => choose(template)}>
                  {selected ? <Check aria-hidden="true" size={17} /> : null}
                  {selected ? "Selected" : "Use template"}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </AccessibleOverlay>
  );
}
