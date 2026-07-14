import { useCallback, useEffect, useRef, useState } from "react";

import { getDashboardLibrary } from "../../../api/dashboards";
import type { DashboardLibraryItem } from "../types";

export type DashboardLibraryStatus = "loading" | "success" | "error";

export function useDashboardLibrary() {
  const [dashboards, setDashboards] = useState<DashboardLibraryItem[]>([]);
  const [status, setStatus] = useState<DashboardLibraryStatus>("loading");
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus("loading");

    try {
      const result = await getDashboardLibrary(controller.signal);
      if (controller.signal.aborted) {
        return;
      }
      setDashboards(result);
      setStatus("success");
    } catch {
      if (controller.signal.aborted) {
        return;
      }
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort();
  }, [load]);

  return {
    dashboards,
    errorMessage: "Dashboard library could not be loaded.",
    reload: load,
    status
  };
}
