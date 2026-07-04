import { useEffect, useState, type FormEvent } from "react";

import { getMyDashboards } from "../../../api/dashboards";
import { hasPermission } from "../../../auth/permissions";
import type { AuthUser } from "../../../auth/types";
import type { Dashboard } from "../../dashboard/types";
import { useSaveQueryRunAsCard } from "../hooks/useSaveQueryRunAsCard";
import type { QueryRunState } from "../types";
import {
  BODY_TEXT_CLASS,
  ERROR_CARD_CLASS,
  EYEBROW_CLASS,
  INFO_CARD_CLASS,
  INPUT_LABEL_CLASS,
  PANEL_CLASS,
  PANEL_HEADER_CLASS,
  PANEL_TITLE_CLASS,
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
  TEXTAREA_CLASS
} from "./askDataStyles";

type DashboardLoadStatus = "idle" | "loading" | "success" | "error";

const TEXT_INPUT_CLASS =
  "min-h-11 w-full rounded-control border border-app-border bg-app-surface px-3.5 py-2.5 text-sm leading-6 text-app-text outline-none transition placeholder:text-app-faint hover:border-brand-primary focus:border-brand-primary focus:shadow-focus disabled:cursor-not-allowed disabled:opacity-60";

const SELECT_CLASS =
  "min-h-11 w-full rounded-control border border-app-border bg-app-surface px-3.5 py-2.5 text-sm leading-6 text-app-text outline-none transition hover:border-brand-primary focus:border-brand-primary focus:shadow-focus disabled:cursor-not-allowed disabled:opacity-60";

export function SaveAsCardPanel({
  csrfToken,
  queryRunState,
  user
}: {
  csrfToken: string | null;
  queryRunState: QueryRunState;
  user: AuthUser;
}) {
  const canCreateCard = hasPermission(user, "can_create_card");
  const result =
    queryRunState.status === "success" ? queryRunState.result : null;
  const queryRunId = result?.query_run_id ?? null;
  const isSaveableResult =
    Boolean(queryRunId) &&
    result?.status === "succeeded" &&
    result.clarification_required === false;
  const defaultTitle =
    queryRunState.status === "success" && queryRunState.question.trim()
      ? queryRunState.question.trim()
      : "Saved query result";
  const { errorMessage, saveCard, status: saveStatus } =
    useSaveQueryRunAsCard(csrfToken);
  const [dashboardStatus, setDashboardStatus] =
    useState<DashboardLoadStatus>("idle");
  const [dashboardErrorMessage, setDashboardErrorMessage] = useState<
    string | null
  >(null);
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedDashboardId, setSelectedDashboardId] = useState("");
  const [title, setTitle] = useState(defaultTitle);
  const [description, setDescription] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const isSaving = saveStatus === "saving";

  useEffect(() => {
    setTitle(defaultTitle);
    setDescription("");
    setSuccessMessage(null);
    setIsExpanded(false);
    setDashboardStatus("idle");
    setDashboardErrorMessage(null);
    setDashboards([]);
    setSelectedDashboardId("");
  }, [defaultTitle, queryRunId]);

  if (!canCreateCard || !isSaveableResult) {
    return null;
  }

  async function handleChooseDashboard() {
    setIsExpanded(true);
    setDashboardStatus("loading");
    setDashboardErrorMessage(null);
    setSuccessMessage(null);

    try {
      const loadedDashboards = await getMyDashboards();
      const personalDashboards = loadedDashboards.filter(
        (dashboard) =>
          dashboard.visibility_scope === "personal" && !dashboard.is_archived
      );
      setDashboards(personalDashboards);
      setSelectedDashboardId((currentDashboardId) => {
        if (
          personalDashboards.some(
            (dashboard) => dashboard.id === currentDashboardId
          )
        ) {
          return currentDashboardId;
        }

        return personalDashboards[0]?.id ?? "";
      });
      setDashboardStatus("success");
    } catch {
      setDashboards([]);
      setSelectedDashboardId("");
      setDashboardErrorMessage("Personal dashboards could not be loaded.");
      setDashboardStatus("error");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage(null);

    const savedCard = await saveCard({
      dashboardId: selectedDashboardId,
      description,
      queryRunId,
      title
    });

    if (savedCard) {
      setSuccessMessage("Dashboard card saved.");
    }
  }

  return (
    <section className={PANEL_CLASS} aria-label="Save as Card">
      <div className={PANEL_HEADER_CLASS}>
        <p className={EYEBROW_CLASS}>Dashboard cards</p>
        <h2 className={PANEL_TITLE_CLASS}>Save as Card</h2>
        <p className={BODY_TEXT_CLASS}>
          Save this successful result as a table card in one of your personal
          dashboards.
        </p>
      </div>

      {!isExpanded ? (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className={SECONDARY_BUTTON_CLASS}
            onClick={() => void handleChooseDashboard()}
            disabled={dashboardStatus === "loading"}
          >
            {dashboardStatus === "loading"
              ? "Loading dashboards..."
              : "Choose dashboard"}
          </button>
        </div>
      ) : null}

      {dashboardStatus === "loading" ? (
        <p className={INFO_CARD_CLASS} role="status">
          Loading personal dashboards...
        </p>
      ) : null}

      {dashboardStatus === "error" && dashboardErrorMessage ? (
        <p className={ERROR_CARD_CLASS} role="alert">
          {dashboardErrorMessage}
        </p>
      ) : null}

      {dashboardStatus === "success" && dashboards.length === 0 ? (
        <p className={INFO_CARD_CLASS}>
          Create a personal dashboard from My Dashboard before saving cards.
        </p>
      ) : null}

      {dashboardStatus === "success" && dashboards.length > 0 ? (
        <form
          className="grid gap-4"
          onSubmit={(event) => void handleSubmit(event)}
        >
          <label className={INPUT_LABEL_CLASS} htmlFor="save-card-dashboard">
            Target dashboard
            <select
              id="save-card-dashboard"
              className={SELECT_CLASS}
              value={selectedDashboardId}
              disabled={isSaving}
              onChange={(event) => setSelectedDashboardId(event.target.value)}
            >
              {dashboards.map((dashboard) => (
                <option key={dashboard.id} value={dashboard.id}>
                  {dashboard.title}
                </option>
              ))}
            </select>
          </label>

          <label className={INPUT_LABEL_CLASS} htmlFor="save-card-title">
            Card title
            <input
              id="save-card-title"
              className={TEXT_INPUT_CLASS}
              type="text"
              value={title}
              disabled={isSaving}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>

          <label className={INPUT_LABEL_CLASS} htmlFor="save-card-description">
            Description
            <textarea
              id="save-card-description"
              className={TEXTAREA_CLASS}
              rows={3}
              value={description}
              disabled={isSaving}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>

          {errorMessage ? (
            <p className={ERROR_CARD_CLASS} role="alert">
              {errorMessage}
            </p>
          ) : null}

          {successMessage ? (
            <p className={INFO_CARD_CLASS} role="status">
              {successMessage}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              className={PRIMARY_BUTTON_CLASS}
              disabled={isSaving || !selectedDashboardId}
            >
              {isSaving ? "Saving..." : "Save card"}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
