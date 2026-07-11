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
  const lastSuccessfulResult = useRef<DashboardCardRefreshResult | null>(null);
  const automaticRefreshCardId = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    if (requestInFlight.current || !canRefresh || !csrfToken) {
      return;
    }

    requestInFlight.current = true;
    const previousResult = lastSuccessfulResult.current;
    setState({ status: "loading", previousResult });

    try {
      const result = await refreshDashboardCard(cardId, csrfToken);
      lastSuccessfulResult.current = result;
      setState({ status: "success", result });
    } catch (error: unknown) {
      setState({
        status: "error",
        message: refreshErrorMessage(error),
        previousResult
      });
    } finally {
      requestInFlight.current = false;
    }
  }, [canRefresh, cardId, csrfToken]);

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
