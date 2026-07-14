import { Plus, Search } from "lucide-react";

export type DashboardFilter = "all" | "owned" | "shared";
export type DashboardSort = "updated" | "name" | "created";

export function DashboardLibraryToolbar({
  canCreate,
  filter,
  onCreate,
  onFilterChange,
  onSearchChange,
  onSortChange,
  resultCount,
  search,
  sort
}: {
  canCreate: boolean;
  filter: DashboardFilter;
  onCreate: () => void;
  onFilterChange: (filter: DashboardFilter) => void;
  onSearchChange: (search: string) => void;
  onSortChange: (sort: DashboardSort) => void;
  resultCount: number;
  search: string;
  sort: DashboardSort;
}) {
  return (
    <div className="dashboard-library-toolbar">
      <div className="dashboard-library-toolbar__search">
        <Search aria-hidden="true" size={18} />
        <label className="sr-only" htmlFor="dashboard-library-search">
          Search dashboards
        </label>
        <input
          id="dashboard-library-search"
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search dashboards"
          type="search"
          value={search}
        />
      </div>
      <label className="dashboard-library-toolbar__select">
        <span>Show</span>
        <select
          aria-label="Filter dashboards"
          onChange={(event) => onFilterChange(event.target.value as DashboardFilter)}
          value={filter}
        >
          <option value="all">All</option>
          <option value="owned">Owned</option>
          <option value="shared">Shared</option>
        </select>
      </label>
      <label className="dashboard-library-toolbar__select">
        <span>Sort</span>
        <select
          aria-label="Sort dashboards"
          onChange={(event) => onSortChange(event.target.value as DashboardSort)}
          value={sort}
        >
          <option value="updated">Recently updated</option>
          <option value="name">Name</option>
          <option value="created">Created</option>
        </select>
      </label>
      {canCreate ? (
        <button
          className="qops-button-primary qops-focus-ring dashboard-library-toolbar__create"
          onClick={onCreate}
          type="button"
        >
          <Plus aria-hidden="true" size={18} />
          New dashboard
        </button>
      ) : null}
      <p className="sr-only" aria-live="polite">
        {resultCount} {resultCount === 1 ? "dashboard" : "dashboards"} found
      </p>
    </div>
  );
}
