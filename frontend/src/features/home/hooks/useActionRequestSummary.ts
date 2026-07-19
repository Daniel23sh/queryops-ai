import { useCallback, useEffect, useRef, useState } from "react";

import { listOwnActionRequests } from "../../../api/actions";
import type { RequesterActionList } from "../../actions/types";

export function useActionRequestSummary(enabled: boolean) {
  const [summary, setSummary] = useState<RequesterActionList["summary"] | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">(
    enabled ? "loading" : "idle"
  );
  const requestRef = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    if (!enabled) return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus("loading");
    try {
      const result = await listOwnActionRequests({ limit: 1 }, controller.signal);
      if (controller.signal.aborted) return;
      setSummary(result.summary);
      setStatus("success");
    } catch {
      if (!controller.signal.aborted) setStatus("error");
    }
  }, [enabled]);
  useEffect(() => {
    void load();
    return () => requestRef.current?.abort();
  }, [load]);
  return { reload: load, status, summary };
}
