import { useCallback, useEffect, useRef, useState } from "react";

import { listOwnActionRequests } from "../../../api/actions";
import type {
  RequesterActionList,
  RequesterActionStatusGroup
} from "../types";

export function useOwnActionRequests({
  statusGroup,
  page,
  pageSize = 10
}: {
  statusGroup: RequesterActionStatusGroup;
  page: number;
  pageSize?: number;
}) {
  const [data, setData] = useState<RequesterActionList | null>(null);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus("loading");
    try {
      const result = await listOwnActionRequests(
        { statusGroup, limit: pageSize, offset: page * pageSize },
        controller.signal
      );
      if (controller.signal.aborted) return;
      setData(result);
      setStatus("success");
    } catch {
      if (!controller.signal.aborted) setStatus("error");
    }
  }, [page, pageSize, statusGroup]);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort();
  }, [load]);

  return { data, reload: load, status };
}
