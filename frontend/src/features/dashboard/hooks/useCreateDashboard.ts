import { useState } from "react";

import { createDashboard } from "../../../api/dashboards";
import type { Dashboard } from "../types";

export type CreateDashboardStatus = "idle" | "saving" | "success" | "error";

export function useCreateDashboard(csrfToken: string | null) {
  const [status, setStatus] = useState<CreateDashboardStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function createPersonalDashboard({
    description,
    title
  }: {
    description: string;
    title: string;
  }): Promise<Dashboard | null> {
    const trimmedTitle = title.trim();
    const trimmedDescription = description.trim();

    setErrorMessage(null);

    if (!trimmedTitle) {
      setStatus("error");
      setErrorMessage("Enter a dashboard title.");
      return null;
    }

    if (!csrfToken) {
      setStatus("error");
      setErrorMessage("Refresh your session before creating a dashboard.");
      return null;
    }

    setStatus("saving");

    try {
      const createdDashboard = await createDashboard(
        {
          title: trimmedTitle,
          description: trimmedDescription || undefined,
          visibility_scope: "personal"
        },
        csrfToken
      );
      setStatus("success");
      return createdDashboard;
    } catch {
      setStatus("error");
      setErrorMessage("Dashboard could not be created.");
      return null;
    }
  }

  return {
    createPersonalDashboard,
    errorMessage,
    status
  };
}
