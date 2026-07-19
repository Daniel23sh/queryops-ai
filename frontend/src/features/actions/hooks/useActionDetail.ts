import { useCallback, useEffect, useRef, useState } from "react";

import { getActionDetail } from "../../../api/actions";
import { ApiError } from "../../../api/client";
import type { ActionDetail } from "../types";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function useActionDetail(actionRequestId: string | undefined) {
  const [detail, setDetail] = useState<ActionDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "success" | "not-found" | "error">(
    "loading"
  );
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    if (!actionRequestId || !UUID_PATTERN.test(actionRequestId)) {
      setDetail(null);
      setStatus("not-found");
      return;
    }
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus("loading");
    try {
      const result = await getActionDetail(actionRequestId, controller.signal);
      if (controller.signal.aborted) return;
      setDetail(result);
      setStatus("success");
    } catch (error: unknown) {
      if (controller.signal.aborted) return;
      setDetail(null);
      setStatus(error instanceof ApiError && error.status === 404 ? "not-found" : "error");
    }
  }, [actionRequestId]);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort();
  }, [load]);

  return { detail, reload: load, status };
}
