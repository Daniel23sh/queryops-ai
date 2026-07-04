import { useState } from "react";

import { saveQueryRunAsCard } from "../../../api/dashboards";
import type { DashboardCard } from "../../dashboard/types";

export type SaveQueryRunAsCardStatus = "idle" | "saving" | "success" | "error";

export function useSaveQueryRunAsCard(csrfToken: string | null) {
  const [status, setStatus] = useState<SaveQueryRunAsCardStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function saveCard({
    dashboardId,
    description,
    queryRunId,
    title
  }: {
    dashboardId: string;
    description?: string;
    queryRunId: string | null;
    title?: string;
  }): Promise<DashboardCard | null> {
    const trimmedQueryRunId = queryRunId?.trim() ?? "";
    const trimmedDashboardId = dashboardId.trim();
    const trimmedTitle = title?.trim() ?? "";
    const trimmedDescription = description?.trim() ?? "";

    setErrorMessage(null);

    if (!trimmedQueryRunId) {
      setStatus("error");
      setErrorMessage("Run a successful query before saving a card.");
      return null;
    }

    if (!trimmedDashboardId) {
      setStatus("error");
      setErrorMessage("Choose a dashboard before saving a card.");
      return null;
    }

    if (!csrfToken) {
      setStatus("error");
      setErrorMessage("Refresh your session before saving a card.");
      return null;
    }

    setStatus("saving");

    try {
      const savedCard = await saveQueryRunAsCard(
        trimmedQueryRunId,
        {
          dashboard_id: trimmedDashboardId,
          title: trimmedTitle || undefined,
          description: trimmedDescription || undefined,
          card_type: "table"
        },
        csrfToken
      );
      setStatus("success");
      return savedCard;
    } catch {
      setStatus("error");
      setErrorMessage("Dashboard card could not be saved.");
      return null;
    }
  }

  return {
    errorMessage,
    saveCard,
    status
  };
}
