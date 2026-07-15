import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../../api/client";
import { refreshDashboardCard } from "../../../api/dashboards";
import type { DashboardCardRefreshResult } from "../types";

export type CardRefreshState =
  | { status: "idle" }
  | {
      status: "loading";
      previousResult: DashboardCardRefreshResult | null;
    }
  | { status: "success"; result: DashboardCardRefreshResult }
  | {
      status: "error";
      message: string;
      previousResult: DashboardCardRefreshResult | null;
    };

const PERMISSION_ERROR_CODES = new Set([
  "FORBIDDEN",
  "CARD_NOT_FOUND",
  "CARD_NOT_REFRESHABLE",
  "CARD_REFRESH_NOT_ALLOWED",
  "CSRF_TOKEN_MISSING"
]);

export function useDashboardCardRefresh({
  canRefresh,
  cardId,
  csrfToken
}: {
  canRefresh: boolean;
  cardId: string;
  csrfToken: string | null;
}) {
  const [state, setState] = useState<CardRefreshState>({ status: "idle" });
  const requestInFlight = useRef(false);
  const requestSequence = useRef(0);
  const lastSuccessfulResult = useRef<DashboardCardRefreshResult | null>(null);
  const automaticRefreshCardId = useRef<string | null>(null);
  const activeCardId = useRef(cardId);

  const refresh = useCallback(async () => {
    if (requestInFlight.current || !canRefresh || !csrfToken) {
      return;
    }

    requestInFlight.current = true;
    const requestId = ++requestSequence.current;
    const previousResult = lastSuccessfulResult.current;
    setState({ status: "loading", previousResult });

    try {
      const result = await refreshDashboardCard(cardId, csrfToken);
      if (requestId !== requestSequence.current) return;
      lastSuccessfulResult.current = result;
      setState({ status: "success", result });
    } catch (error: unknown) {
      if (requestId !== requestSequence.current) return;
      setState({
        status: "error",
        message: refreshErrorMessage(error),
        previousResult
      });
    } finally {
      if (requestId === requestSequence.current) requestInFlight.current = false;
    }
  }, [canRefresh, cardId, csrfToken]);

  useEffect(() => {
    if (activeCardId.current === cardId) return;
    activeCardId.current = cardId;
    requestSequence.current += 1;
    requestInFlight.current = false;
    lastSuccessfulResult.current = null;
    automaticRefreshCardId.current = null;
    setState({ status: "idle" });
  }, [cardId]);

  useEffect(() => {
    if (
      !canRefresh ||
      !csrfToken ||
      automaticRefreshCardId.current === cardId
    ) {
      return;
    }

    automaticRefreshCardId.current = cardId;
    void refresh();
  }, [canRefresh, cardId, csrfToken, refresh]);

  const result =
    state.status === "success"
      ? state.result
      : state.status === "loading" || state.status === "error"
        ? state.previousResult
        : null;

  return {
    refresh,
    result,
    state
  };
}

function refreshErrorMessage(error: unknown): string {
  if (error instanceof ApiError && PERMISSION_ERROR_CODES.has(error.code)) {
    return "This card cannot be refreshed with your current permissions.";
  }
  return "Card refresh could not be completed. Try again.";
}
