import { Link, useLocation } from "react-router-dom";

import type { EvaluationTab } from "../types";

const tabs: Array<{ id: EvaluationTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "queries", label: "Queries" },
  { id: "actions", label: "Actions" },
  { id: "security", label: "Security" },
  { id: "dashboards", label: "Dashboards" }
];

export function EvaluationTabs({ activeTab }: { activeTab: EvaluationTab }) {
  const location = useLocation();
  return (
    <nav aria-label="Evaluation sections" className="overflow-x-auto border-b border-app-border">
      <ul className="m-0 flex min-w-max list-none gap-1 p-0">
        {tabs.map((tab) => {
          const query = new URLSearchParams();
          if (tab.id !== "overview") query.set("tab", tab.id);
          const target = `${location.pathname}${query.size ? `?${query}` : ""}`;
          return (
            <li key={tab.id}>
              <Link
                aria-current={activeTab === tab.id ? "page" : undefined}
                className={`inline-flex min-h-11 items-center border-b-2 px-4 text-sm font-bold no-underline outline-none transition focus:shadow-focus ${
                  activeTab === tab.id
                    ? "border-brand-primary text-brand-primary"
                    : "border-transparent text-app-subtle hover:text-app-text"
                }`}
                to={target}
              >
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
