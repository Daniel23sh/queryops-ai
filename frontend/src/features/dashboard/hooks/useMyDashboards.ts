import { useCallback, useEffect, useState } from "react";

import { getMyDashboards } from "../../../api/dashboards";
import type { Dashboard } from "../types";

export type MyDashboardsStatus = "loading" | "success" | "error";

export function useMyDashboards() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [status, setStatus] = useState<MyDashboardsStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadDashboards = useCallback(async (isCurrent: () => boolean) => {
    setStatus("loading");
    setErrorMessage(null);

    try {
      const loadedDashboards = await getMyDashboards();
      if (!isCurrent()) {
        return;
      }

      setDashboards(loadedDashboards);
      setStatus("success");
    } catch {
      if (!isCurrent()) {
        return;
      }

      setDashboards([]);
      setErrorMessage("Dashboard cards could not be loaded.");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    let isCurrent = true;

    void loadDashboards(() => isCurrent);

    return () => {
      isCurrent = false;
    };
  }, [loadDashboards]);

  const reload = useCallback(async () => {
    await loadDashboards(() => true);
  }, [loadDashboards]);

  return {
    dashboards,
    errorMessage,
    reload,
    status
  };
}
