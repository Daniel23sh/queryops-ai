import { useCallback, useEffect, useRef, useState } from "react";

import { getHomeOverview } from "../../../api/home";
import type { HomeOverview } from "../types";

export type HomeOverviewStatus = "loading" | "success" | "error";

export function useHomeOverview() {
  const [overview, setOverview] = useState<HomeOverview | null>(null);
  const [status, setStatus] = useState<HomeOverviewStatus>("loading");
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus("loading");

    try {
      const result = await getHomeOverview(controller.signal);
      if (controller.signal.aborted) {
        return;
      }
      setOverview(result);
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
    errorMessage: "Home overview could not be loaded.",
    overview,
    reload: load,
    status
  };
}
