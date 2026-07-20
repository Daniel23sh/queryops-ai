import { useCallback, useEffect, useRef, useState } from "react";

import { listPendingApprovals } from "../../../api/approvals";
import type { PendingApprovalList } from "../types";

export function usePendingApprovals({
  page,
  pageSize = 20
}: {
  page: number;
  pageSize?: number;
}) {
  const [data, setData] = useState<PendingApprovalList | null>(null);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus("loading");
    try {
      const result = await listPendingApprovals(
        { limit: pageSize, offset: page * pageSize },
        controller.signal
      );
      if (controller.signal.aborted) return;
      setData(result);
      setStatus("success");
    } catch {
      if (!controller.signal.aborted) setStatus("error");
    }
  }, [page, pageSize]);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort();
  }, [load]);

  return { data, reload: load, status };
}
