import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../../api/client";
import { getDashboardDetail } from "../../../api/dashboards";
import type { DashboardDetail } from "../types";

export type DashboardDetailStatus = "loading" | "success" | "not-found" | "error";

export function useDashboardDetail(dashboardId: string | undefined) {
  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);
  const [status, setStatus] = useState<DashboardDetailStatus>("loading");
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    if (!dashboardId) {
      setDashboard(null);
      setStatus("not-found");
      return;
    }

    const controller = new AbortController();
    requestRef.current = controller;
    setStatus("loading");
    try {
      const result = await getDashboardDetail(dashboardId, controller.signal);
      if (controller.signal.aborted) {
        return;
      }
      setDashboard(result);
      setStatus("success");
    } catch (error: unknown) {
      if (controller.signal.aborted) {
        return;
      }
      setDashboard(null);
      setStatus(
        error instanceof ApiError &&
          (error.status === 404 || error.code === "DASHBOARD_NOT_FOUND")
          ? "not-found"
          : "error"
      );
    }
  }, [dashboardId]);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort();
  }, [load]);

  return { dashboard, reload: load, status };
}
