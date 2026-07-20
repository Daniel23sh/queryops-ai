import { useCallback, useEffect, useRef, useState } from "react";

import { listAuditLogs } from "../../../api/audit";
import type { AuditLogFilters, AuditLogList } from "../types";

type AuditStatus = "loading" | "success" | "error";

export function useAuditLogs(filters: AuditLogFilters) {
  const [data, setData] = useState<AuditLogList | null>(null);
  const [status, setStatus] = useState<AuditStatus>("loading");
  const requestRef = useRef<AbortController | null>(null);
  const filterKey = JSON.stringify(filters);

  const reload = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus("loading");
    try {
      const result = await listAuditLogs(filters, controller.signal);
      if (controller.signal.aborted) return;
      setData(result);
      setStatus("success");
    } catch {
      if (controller.signal.aborted) return;
      setStatus("error");
    }
  }, [filterKey]);

  useEffect(() => {
    void reload();
    return () => requestRef.current?.abort();
  }, [reload]);

  return { data, reload, status };
}
