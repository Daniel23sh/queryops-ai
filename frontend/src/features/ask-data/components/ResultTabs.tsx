import type { AskDataResultTab } from "../types";

export function ResultTabs({
  activeTab,
  canViewTechnicalDetails,
  onSelectTab
}: {
  activeTab: AskDataResultTab;
  canViewTechnicalDetails: boolean;
  onSelectTab: (tab: AskDataResultTab) => void;
}) {
  const tabs: { id: AskDataResultTab; label: string; technicalOnly?: boolean }[] = [
    { id: "results", label: "Results" },
    { id: "summary", label: "Summary" },
    { id: "sql", label: "SQL", technicalOnly: true },
    { id: "diagnostics", label: "Diagnostics", technicalOnly: true }
  ];

  return (
    <div
      className="grid grid-cols-2 gap-2 rounded-card border border-app-border bg-app-muted p-1 sm:flex sm:flex-wrap"
      role="tablist"
      aria-label="Ask Data result views"
    >
      {tabs
        .filter((tab) => !tab.technicalOnly || canViewTechnicalDetails)
        .map((tab) => (
          <button
            key={tab.id}
            id={`ask-data-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`ask-data-tab-panel-${tab.id}`}
            className={`qops-focus-ring inline-flex min-h-11 items-center justify-center rounded-control border px-3.5 text-sm font-bold transition sm:w-auto ${
              activeTab === tab.id
                ? "border-app-border bg-app-surface text-app-text shadow-sm"
                : "border-transparent bg-transparent text-app-subtle hover:bg-app-surface hover:text-brand-primary"
            }`}
            onClick={() => onSelectTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
    </div>
  );
}
