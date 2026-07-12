import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../../api/client";
import { updateMyDashboardLayout } from "../../../api/dashboards";
import type { Dashboard, DashboardCard } from "../types";

export type DashboardCardOrderSaveState =
  | { status: "idle" }
  | { status: "saving"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string; canReload: boolean };

const CONFLICT_ERROR_CODE = "DASHBOARD_LAYOUT_CONFLICT";
const SAVE_MESSAGE = "Card order saved.";
const GENERIC_FAILURE_MESSAGE =
  "Card order could not be saved. The previous order was restored.";
const CONFLICT_MESSAGE = "Dashboard cards changed. Reload the dashboard and try again.";

export function useDashboardCardOrder({
  dashboard,
  csrfToken
}: {
  dashboard: Dashboard;
  csrfToken: string | null;
}) {
  const [cards, setCards] = useState(() => sortDashboardCards(dashboard.cards));
  const [saveState, setSaveState] = useState<DashboardCardOrderSaveState>({
    status: "idle"
  });
  const cardsRef = useRef(cards);
  const requestInFlight = useRef(false);
  const serverOrderKey = dashboard.cards
    .map((card) => `${card.id}:${card.position}:${card.updated_at}`)
    .sort()
    .join("|");

  const replaceCards = useCallback((nextCards: DashboardCard[]) => {
    const orderedCards = sortDashboardCards(nextCards);
    cardsRef.current = orderedCards;
    setCards(orderedCards);
  }, []);

  useEffect(() => {
    if (requestInFlight.current) {
      return;
    }

    replaceCards(dashboard.cards);
    setSaveState({ status: "idle" });
  }, [dashboard.id, replaceCards, serverOrderKey]);

  const moveCard = useCallback(
    async (cardId: string, targetIndex: number) => {
      if (requestInFlight.current || !csrfToken) {
        return;
      }

      const previousCards = cardsRef.current;
      const currentIndex = previousCards.findIndex((card) => card.id === cardId);
      if (
        currentIndex < 0 ||
        targetIndex < 0 ||
        targetIndex >= previousCards.length ||
        currentIndex === targetIndex
      ) {
        return;
      }

      const nextCards = normalizeCardPositions(
        moveDashboardCard(previousCards, currentIndex, targetIndex)
      );
      requestInFlight.current = true;
      replaceCards(nextCards);
      setSaveState({ status: "saving", message: "Saving card order..." });

      try {
        const updatedDashboard = await updateMyDashboardLayout(
          {
            items: nextCards.map((card) => ({
              card_id: card.id,
              position: card.position
            }))
          },
          csrfToken
        );
        if (updatedDashboard.id !== dashboard.id) {
          throw new Error("Dashboard layout response did not match the requested dashboard.");
        }

        replaceCards(updatedDashboard.cards);
        setSaveState({ status: "success", message: SAVE_MESSAGE });
      } catch (error: unknown) {
        replaceCards(previousCards);
        if (error instanceof ApiError && error.code === CONFLICT_ERROR_CODE) {
          setSaveState({
            status: "error",
            message: CONFLICT_MESSAGE,
            canReload: true
          });
        } else {
          setSaveState({
            status: "error",
            message: GENERIC_FAILURE_MESSAGE,
            canReload: false
          });
        }
      } finally {
        requestInFlight.current = false;
      }
    },
    [csrfToken, dashboard.id, replaceCards]
  );

  return {
    cards,
    isSaving: saveState.status === "saving",
    moveCard,
    saveState
  };
}

export function sortDashboardCards(cards: DashboardCard[]): DashboardCard[] {
  return [...cards].sort((first, second) => {
    if (first.position !== second.position) {
      return first.position - second.position;
    }
    if (first.created_at !== second.created_at) {
      return first.created_at.localeCompare(second.created_at);
    }
    return first.id.localeCompare(second.id);
  });
}

export function normalizeCardPositions(cards: DashboardCard[]): DashboardCard[] {
  return cards.map((card, position) => ({ ...card, position }));
}

function moveDashboardCard(
  cards: DashboardCard[],
  currentIndex: number,
  targetIndex: number
): DashboardCard[] {
  const nextCards = [...cards];
  const [movedCard] = nextCards.splice(currentIndex, 1);
  nextCards.splice(targetIndex, 0, movedCard);
  return nextCards;
}
