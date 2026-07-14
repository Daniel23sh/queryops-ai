import { useCallback, useState } from "react";

import { hasPermission } from "../../auth/permissions";
import type { AuthUser } from "../../auth/types";
import { CreateDashboardDialog } from "../dashboard/components/CreateDashboardDialog";
import { DashboardLibrary } from "../dashboard/components/DashboardLibrary";
import { useDashboardLibrary } from "../dashboard/hooks/useDashboardLibrary";
import { AdminMetrics } from "./components/AdminMetrics";
import { HomeHeader } from "./components/HomeHeader";
import { OperationalMetrics } from "./components/OperationalMetrics";
import { PersonalSummary } from "./components/PersonalSummary";
import { useHomeOverview } from "./hooks/useHomeOverview";

export function HomePage({
  csrfToken,
  user
}: {
  csrfToken: string | null;
  user: AuthUser;
}) {
  const overview = useHomeOverview();
  const library = useDashboardLibrary();
  const [createOpen, setCreateOpen] = useState(false);
  const [createOpener, setCreateOpener] = useState<HTMLElement | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const canCreate = hasPermission(user, "can_create_personal_dashboard");
  const closeCreate = useCallback(() => setCreateOpen(false), []);
  const handleCreated = useCallback(
    async (title: string) => {
      await Promise.allSettled([overview.reload(), library.reload()]);
      setSuccessMessage(`${title} was created.`);
    },
    [library.reload, overview.reload]
  );

  return (
    <article className="home-page" aria-labelledby="home-title" role="region">
      <HomeHeader
        canUseAskData={hasPermission(user, "can_use_query_templates")}
        scope={overview.overview?.scope ?? null}
        user={user}
      />

      {successMessage ? (
        <p className="home-success-status" role="status">
          {successMessage}
        </p>
      ) : null}

      {overview.status === "loading" && !overview.overview ? (
        <section className="home-overview-state" aria-live="polite">
          Loading your Home overview...
        </section>
      ) : null}
      {overview.status === "error" ? (
        <section className="home-overview-state" role="alert">
          <p>{overview.errorMessage}</p>
          <button
            className="qops-button-secondary qops-focus-ring"
            onClick={() => void overview.reload()}
            type="button"
          >
            Try again
          </button>
        </section>
      ) : null}

      {overview.overview ? (
        <>
          <PersonalSummary summary={overview.overview.personal_summary} />
          {overview.overview.operational_metrics ? (
            <OperationalMetrics
              metrics={overview.overview.operational_metrics}
              scope={overview.overview.scope}
            />
          ) : null}
          {overview.overview.admin_metrics ? (
            <AdminMetrics metrics={overview.overview.admin_metrics} />
          ) : null}
        </>
      ) : null}

      <DashboardLibrary
        canCreate={canCreate}
        dashboards={library.dashboards}
        errorMessage={library.errorMessage}
        onCreate={() => {
          setSuccessMessage(null);
          setCreateOpener(
            document.activeElement instanceof HTMLElement
              ? document.activeElement
              : null
          );
          setCreateOpen(true);
        }}
        onReload={library.reload}
        status={library.status}
      />

      {createOpen ? (
        <CreateDashboardDialog
          csrfToken={csrfToken}
          onClose={closeCreate}
          onCreated={handleCreated}
          opener={createOpener}
        />
      ) : null}
    </article>
  );
}
