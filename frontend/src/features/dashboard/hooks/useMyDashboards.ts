import { useEffect, useState } from "react";

import { getMyDashboards } from "../../../api/dashboards";
import type { Dashboard } from "../types";

export type MyDashboardsStatus = "loading" | "success" | "error";

export function useMyDashboards() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [status, setStatus] = useState<MyDashboardsStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    setStatus("loading");
    setErrorMessage(null);

    getMyDashboards()
      .then((loadedDashboards) => {
        if (!isCurrent) {
          return;
        }

        setDashboards(loadedDashboards);
        setStatus("success");
      })
      .catch(() => {
        if (!isCurrent) {
          return;
        }

        setDashboards([]);
        setErrorMessage("Dashboard cards could not be loaded.");
        setStatus("error");
      });

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
