import { ArrowLeft, ListRestart } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { APP_ROUTES } from "../../app/routeConfig";
import { hasPermission } from "../../auth/permissions";
import type { AuthUser } from "../../auth/types";
import { DashboardCardGrid } from "./components/DashboardCardGrid";
import { DashboardViewGrid } from "./components/DashboardViewGrid";
import { useDashboardDetail } from "./hooks/useDashboardDetail";
import type { Dashboard, DashboardDetail } from "./types";

export function DashboardDetailPage({
  csrfToken,
  user
}: {
  csrfToken: string | null;
  user: AuthUser;
}) {
  const { dashboardId } = useParams<{ dashboardId: string }>();
  const detail = useDashboardDetail(dashboardId);
  const [arranging, setArranging] = useState(false);
  useEffect(() => setArranging(false), [dashboardId]);

  if (detail.status === "loading" && !detail.dashboard) {
    return (
      <section className="dashboard-detail dashboard-detail--state" aria-live="polite">
        Loading dashboard...
      </section>
    );
  }

  if (detail.status === "not-found") {
    return <DashboardUnavailable title="Dashboard not found" />;
  }
  if (detail.status === "error" || !detail.dashboard) {
    return (
      <DashboardUnavailable
        onRetry={() => void detail.reload()}
        title="Dashboard unavailable"
      />
    );
  }

  const dashboard = detail.dashboard;
  const canRefreshCards =
    hasPermission(user, "can_query_scoped_data") ||
    hasPermission(user, "can_query_global_data");
  const canExportCards = hasPermission(user, "can_export_results");
  const canArrange =
    dashboard.relationship === "owned" &&
    dashboard.visibility_scope === "personal" &&
    dashboard.cards.length > 1;

  return (
    <article className="dashboard-detail" aria-labelledby="dashboard-detail-title">
      <Link className="dashboard-detail__back qops-focus-ring" to={APP_ROUTES.home}>
        <ArrowLeft aria-hidden="true" size={17} />
        Back to My Dashboard
      </Link>
      <header className="dashboard-detail__header">
        <div>
          <span className="dashboard-library-card__badges">
            <span className={`dashboard-badge dashboard-badge--${dashboard.relationship}`}>
              {dashboard.relationship === "owned" ? "Owned" : "Shared"}
            </span>
            <span className="dashboard-badge">{dashboard.scope.display_name}</span>
          </span>
          <h1 id="dashboard-detail-title">{dashboard.title}</h1>
          {dashboard.description ? <p>{dashboard.description}</p> : null}
          <p className="dashboard-detail__meta">
            {dashboard.owner ? `Owner: ${dashboard.owner.display_name} · ` : ""}
            {dashboard.card_count} {dashboard.card_count === 1 ? "card" : "cards"} ·
            Updated {formatDate(dashboard.updated_at)}
          </p>
        </div>
        {canArrange ? (
          <button
            className={arranging ? "qops-button-primary qops-focus-ring" : "qops-button-secondary qops-focus-ring"}
            onClick={() => {
              if (arranging) {
                void detail.reload();
              }
              setArranging((value) => !value);
            }}
            type="button"
          >
            <ListRestart aria-hidden="true" size={17} />
            {arranging ? "Done arranging" : "Arrange cards"}
          </button>
        ) : null}
      </header>

      {arranging ? (
        <section className="dashboard-detail__arrange" aria-label="Arrange dashboard cards">
          <p>
            Drag cards, use the keyboard, or use Move up and Move down. Card size and
            visualization are unchanged.
          </p>
          <DashboardCardGrid
            canExportCards={canExportCards}
            canRefreshCards={canRefreshCards}
            csrfToken={csrfToken}
            dashboard={legacyDashboard(dashboard)}
            onReload={detail.reload}
            showDashboardHeader={false}
          />
        </section>
      ) : (
        <DashboardViewGrid
          canExportCards={canExportCards}
          canRefreshCards={canRefreshCards}
          cards={dashboard.cards}
          csrfToken={csrfToken}
        />
      )}
    </article>
  );
}

function DashboardUnavailable({
  onRetry,
  title
}: {
  onRetry?: () => void;
  title: string;
}) {
  return (
    <section className="dashboard-detail dashboard-detail--state">
      <h1>{title}</h1>
      <p>This dashboard is unavailable or is not visible in your current scope.</p>
      <div>
        {onRetry ? (
          <button className="qops-button-secondary qops-focus-ring" onClick={onRetry} type="button">
            Try again
          </button>
        ) : null}
        <Link className="qops-button-primary qops-focus-ring" to={APP_ROUTES.home}>
          Back to My Dashboard
        </Link>
      </div>
    </section>
  );
}

function legacyDashboard(detail: DashboardDetail): Dashboard {
  return {
    id: detail.id,
    title: detail.title,
    description: detail.description,
    visibility_scope: detail.visibility_scope,
    department_id: null,
    is_archived: false,
    created_at: detail.created_at,
    updated_at: detail.updated_at,
    cards: detail.cards
  };
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "recently"
    : new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(date);
}
