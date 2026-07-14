import { useCallback, useMemo, useState } from "react";

import type { DashboardLibraryStatus } from "../hooks/useDashboardLibrary";
import type { DashboardLibraryItem } from "../types";
import {
  DashboardLibraryToolbar,
  type DashboardFilter,
  type DashboardSort
} from "./DashboardLibraryToolbar";
import { DashboardLibrarySection } from "./DashboardLibrarySection";
import { DashboardPreviewDialog } from "./DashboardPreviewDialog";

type PreviewState = {
  dashboard: DashboardLibraryItem;
  opener: HTMLButtonElement;
} | null;

export function DashboardLibrary({
  canCreate,
  dashboards,
  errorMessage,
  onCreate,
  onReload,
  status
}: {
  canCreate: boolean;
  dashboards: DashboardLibraryItem[];
  errorMessage: string;
  onCreate: () => void;
  onReload: () => Promise<void>;
  status: DashboardLibraryStatus;
}) {
  const [filter, setFilter] = useState<DashboardFilter>("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<DashboardSort>("updated");
  const [preview, setPreview] = useState<PreviewState>(null);
  const closePreview = useCallback(() => setPreview(null), []);
  const visibleDashboards = useMemo(
    () => filterAndSortDashboards(dashboards, filter, search, sort),
    [dashboards, filter, search, sort]
  );
  const owned = visibleDashboards.filter((item) => item.relationship === "owned");
  const shared = visibleDashboards.filter((item) => item.relationship === "shared");

  return (
    <section className="dashboard-library home-section" aria-labelledby="dashboard-library-title">
      <div className="home-section__heading home-section__heading--split">
        <div>
          <p className="eyebrow">Saved views</p>
          <h2 id="dashboard-library-title">My dashboards</h2>
        </div>
        <span className="dashboard-library__count">
          {dashboards.length} {dashboards.length === 1 ? "dashboard" : "dashboards"}
        </span>
      </div>

      <DashboardLibraryToolbar
        canCreate={canCreate}
        filter={filter}
        onCreate={onCreate}
        onFilterChange={setFilter}
        onSearchChange={setSearch}
        onSortChange={setSort}
        resultCount={visibleDashboards.length}
        search={search}
        sort={sort}
      />

      {status === "loading" && dashboards.length === 0 ? (
        <p className="dashboard-library__state" aria-live="polite">
          Loading dashboard library...
        </p>
      ) : null}
      {status === "error" ? (
        <div className="dashboard-library__state" role="alert">
          <p>{errorMessage}</p>
          <button
            className="qops-button-secondary qops-focus-ring"
            onClick={() => void onReload()}
            type="button"
          >
            Try again
          </button>
        </div>
      ) : null}

      {status !== "loading" &&
        status !== "error" &&
        visibleDashboards.length === 0 ? (
        <div className="dashboard-library__state">
          <p>
            {dashboards.length === 0
              ? "No dashboards are available yet."
              : "No dashboards match this search and filter."}
          </p>
        </div>
      ) : null}

      {visibleDashboards.length > 0 ? (
        <div className="dashboard-library__sections">
          {filter === "all" ? (
            <>
              {owned.length > 0 ? (
                <DashboardLibrarySection
                  dashboards={owned}
                  onOpen={(dashboard, opener) => setPreview({ dashboard, opener })}
                  title="Owned by me"
                />
              ) : null}
              {shared.length > 0 ? (
                <DashboardLibrarySection
                  dashboards={shared}
                  onOpen={(dashboard, opener) => setPreview({ dashboard, opener })}
                  title="Shared with me"
                />
              ) : null}
            </>
          ) : (
            <DashboardLibrarySection
              dashboards={visibleDashboards}
              onOpen={(dashboard, opener) => setPreview({ dashboard, opener })}
              title={filter === "owned" ? "Owned by me" : "Shared with me"}
            />
          )}
        </div>
      ) : null}

      {preview ? (
        <DashboardPreviewDialog
          dashboard={preview.dashboard}
          onClose={closePreview}
          opener={preview.opener}
        />
      ) : null}
    </section>
  );
}

export function filterAndSortDashboards(
  dashboards: DashboardLibraryItem[],
  filter: DashboardFilter,
  search: string,
  sort: DashboardSort
): DashboardLibraryItem[] {
  const query = search.trim().toLocaleLowerCase();
  return dashboards
    .filter((dashboard) => filter === "all" || dashboard.relationship === filter)
    .filter((dashboard) => {
      if (!query) {
        return true;
      }
      return `${dashboard.title} ${dashboard.description ?? ""}`
        .toLocaleLowerCase()
        .includes(query);
    })
    .sort((left, right) => {
      if (sort === "name") {
        return left.title.localeCompare(right.title) || left.id.localeCompare(right.id);
      }
      const field = sort === "created" ? "created_at" : "updated_at";
      const timeDifference = dateValue(right[field]) - dateValue(left[field]);
      return (
        timeDifference ||
        left.title.localeCompare(right.title) ||
        left.id.localeCompare(right.id)
      );
    });
}

function dateValue(value: string): number {
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}
