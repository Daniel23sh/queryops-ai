import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../../api/client";

export type EvaluationLoadError =
  | "forbidden"
  | "not_found"
  | "invalid_filter"
  | "unavailable";

type ResourceState<T> = {
  key: string;
  status: "idle" | "loading" | "success" | "error";
  data: T | null;
  error: EvaluationLoadError | null;
};

export function useEvaluationResource<T>({
  enabled = true,
  load,
  requestKey
}: {
  enabled?: boolean;
  load: (signal: AbortSignal) => Promise<T>;
  requestKey: string;
}) {
  const [revision, setRevision] = useState(0);
  const versionedKey = `${requestKey}:${revision}`;
  const [state, setState] = useState<ResourceState<T>>({
    key: versionedKey,
    status: enabled ? "loading" : "idle",
    data: null,
    error: null
  });

  useEffect(() => {
    if (!enabled) {
      setState({ key: versionedKey, status: "idle", data: null, error: null });
      return;
    }

    const controller = new AbortController();
    setState({ key: versionedKey, status: "loading", data: null, error: null });
    void load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setState({ key: versionedKey, status: "success", data, error: null });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            key: versionedKey,
            status: "error",
            data: null,
            error: classifyEvaluationError(error)
          });
        }
      });

    return () => controller.abort();
  }, [enabled, load, versionedKey]);

  const visibleState: ResourceState<T> =
    state.key === versionedKey
      ? state
      : {
          key: versionedKey,
          status: enabled ? "loading" : "idle",
          data: null,
          error: null
        };

  return {
    ...visibleState,
    reload: useCallback(() => setRevision((current) => current + 1), [])
  };
}

function classifyEvaluationError(error: unknown): EvaluationLoadError {
  if (!(error instanceof ApiError)) return "unavailable";
  if (error.status === 403 || error.status === 401) return "forbidden";
  if (error.status === 404) return "not_found";
  if (error.status === 400 || error.status === 422) return "invalid_filter";
  return "unavailable";
}
