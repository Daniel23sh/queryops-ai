import { useEffect, useRef, useState } from "react";

import { getQueryHistory } from "../../../api/queries";
import type { QueryHistoryItem } from "../types";

type HistoryStatus = "idle" | "loading" | "loaded" | "error";

export function useRecentQueryHistory({
  isOpen,
  refreshGeneration
}: {
  isOpen: boolean;
  refreshGeneration: number;
}) {
  const [items, setItems] = useState<QueryHistoryItem[]>([]);
  const [status, setStatus] = useState<HistoryStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);

  useEffect(() => {
    if (!isOpen) return;
    const generation = ++requestGeneration.current;
    setStatus("loading");
    setError(null);
    getQueryHistory({ limit: 5, offset: 0, include_sql: false })
      .then((history) => {
        if (requestGeneration.current !== generation) return;
        setItems(history.slice(0, 5));
        setStatus("loaded");
      })
      .catch(() => {
        if (requestGeneration.current !== generation) return;
        setItems([]);
        setError("Recent query history could not be loaded.");
        setStatus("error");
      });
    return () => {
      requestGeneration.current += 1;
    };
  }, [isOpen, refreshGeneration]);

  return { error, items, status };
}
