import { useCallback, useEffect, useRef, useState } from "react";

import { getMyDashboards } from "../../../api/dashboards";
import type { Dashboard } from "../types";

export type MyDashboardsStatus = "loading" | "success" | "error";

export function useMyDashboards() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [status, setStatus] = useState<MyDashboardsStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const requestGenerationRef = useRef(0);

  const loadDashboards = useCallback(async () => {
    const requestGeneration = ++requestGenerationRef.current;
    setStatus("loading");
    setErrorMessage(null);

    try {
      const loadedDashboards = await getMyDashboards();
      if (requestGeneration !== requestGenerationRef.current) {
        return;
      }

      setDashboards(loadedDashboards);
      setStatus("success");
    } catch {
      if (requestGeneration !== requestGenerationRef.current) {
        return;
      }

      setDashboards([]);
      setErrorMessage("Dashboard cards could not be loaded.");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void loadDashboards();

    return () => {
      requestGenerationRef.current += 1;
    };
  }, [loadDashboards]);

  const reload = useCallback(async () => {
    await loadDashboards();
  }, [loadDashboards]);

  return {
    dashboards,
    errorMessage,
    reload,
    status
  };
}
