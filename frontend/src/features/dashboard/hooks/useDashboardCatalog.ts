import { useEffect, useState } from "react";

import { getDashboardCatalog } from "../../../api/dashboards";
import type { Dashboard } from "../types";

export type DashboardCatalogStatus = "loading" | "success" | "error";

export function useDashboardCatalog() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [status, setStatus] = useState<DashboardCatalogStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    async function loadCatalog() {
      setStatus("loading");
      setErrorMessage(null);

      try {
        const catalogDashboards = await getDashboardCatalog();
        if (!isCurrent) {
          return;
        }

        setDashboards(catalogDashboards);
        setStatus("success");
      } catch {
        if (!isCurrent) {
          return;
        }

        setDashboards([]);
        setErrorMessage("Dashboard catalog could not be loaded.");
        setStatus("error");
      }
    }

    void loadCatalog();

    return () => {
      isCurrent = false;
    };
  }, []);

  return {
    dashboards,
    errorMessage,
    status
  };
}
