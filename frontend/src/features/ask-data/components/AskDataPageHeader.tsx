import { History, LayoutTemplate } from "lucide-react";

export function AskDataPageHeader({
  modeLabel,
  onOpenHistory,
  onOpenTemplates,
  scopeLabel
}: {
  modeLabel: string;
  onOpenHistory: () => void;
  onOpenTemplates: () => void;
  scopeLabel: string;
}) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="m-0 text-xs font-bold uppercase tracking-[0.14em] text-brand-primary">
          Governed analytics
        </p>
        <h1 id="workspace-title" className="mb-0 mt-1 text-3xl font-bold tracking-tight text-app-text sm:text-4xl">
          Ask Data
        </h1>
        <p className="mb-0 mt-2 text-sm text-app-subtle">
          <span className="font-semibold text-app-text">{scopeLabel}</span>
          <span aria-hidden="true"> · </span>
          {modeLabel}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button className="qops-button-secondary min-h-11" type="button" onClick={onOpenTemplates}>
          <LayoutTemplate aria-hidden="true" size={18} />
          Templates
        </button>
        <button className="qops-button-secondary min-h-11" type="button" onClick={onOpenHistory}>
          <History aria-hidden="true" size={18} />
          History
        </button>
      </div>
    </header>
  );
}
