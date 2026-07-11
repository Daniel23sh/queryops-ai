import { useEffect, useRef, useState } from "react";

import { ApiError, downloadBlob } from "../../../api/client";
import { exportQueryRunCsv } from "../../../api/exports";
import { hasPermission } from "../../../auth/permissions";
import type { AuthUser } from "../../../auth/types";
import type { QueryRunState } from "../types";
import {
  BODY_TEXT_CLASS,
  ERROR_CARD_CLASS,
  INFO_CARD_CLASS,
  PANEL_CLASS,
  SECONDARY_BUTTON_CLASS
} from "./askDataStyles";

type ExportStatus = "idle" | "loading" | "success" | "error";

const PERMISSION_ERROR_CODES = new Set([
  "FORBIDDEN",
  "CSV_EXPORT_NOT_ALLOWED",
  "QUERY_RUN_NOT_EXPORTABLE",
  "CSRF_TOKEN_MISSING"
]);

export function QueryResultExportButton({
  csrfToken,
  queryRunState,
  user
}: {
  csrfToken: string | null;
  queryRunState: QueryRunState;
  user: AuthUser;
}) {
  const [status, setStatus] = useState<ExportStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const requestInFlight = useRef(false);
  const result =
    queryRunState.status === "success" ? queryRunState.result : null;
  const queryRunId = result?.query_run_id ?? null;
  const isExportableResult =
    queryRunState.status === "success" &&
    result?.status === "succeeded" &&
    Boolean(queryRunId) &&
    result?.clarification_required === false;
  const canExport = hasPermission(user, "can_export_results");
  const requestContext = useRef({ queryRunId, generation: 0 });
  if (requestContext.current.queryRunId !== queryRunId) {
    requestContext.current = {
      queryRunId,
      generation: requestContext.current.generation + 1
    };
  }

  useEffect(() => {
    requestInFlight.current = false;
    setStatus("idle");
    setMessage(null);
  }, [queryRunId]);

  if (!canExport || !isExportableResult || !queryRunId) {
    return null;
  }
  const exportQueryRunId = queryRunId;

  async function handleExport() {
    if (requestInFlight.current || !csrfToken) {
      return;
    }

    requestInFlight.current = true;
    const requestGeneration = requestContext.current.generation;
    setStatus("loading");
    setMessage(null);

    const requestIsCurrent = () =>
      requestContext.current.queryRunId === exportQueryRunId &&
      requestContext.current.generation === requestGeneration;

    try {
      const download = await exportQueryRunCsv(exportQueryRunId, csrfToken, {
        include_headers: true
      });
      if (!requestIsCurrent()) {
        return;
      }
      downloadBlob(download);
      setStatus("success");
      setMessage("CSV export downloaded.");
    } catch (error: unknown) {
      if (!requestIsCurrent()) {
        return;
      }
      setStatus("error");
      setMessage(exportErrorMessage(error));
    } finally {
      if (requestIsCurrent()) {
        requestInFlight.current = false;
      }
    }
  }

  return (
    <section className={PANEL_CLASS} aria-label="Query result export">
      <div className="grid gap-2">
        <h2 className="m-0 text-base font-bold text-app-text">Export result</h2>
        <p className={BODY_TEXT_CLASS} id="query-export-scope-warning">
          Exports contain only data visible in your current access scope. CSV
          exports are audited.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={SECONDARY_BUTTON_CLASS}
          aria-describedby="query-export-scope-warning"
          disabled={!csrfToken || status === "loading"}
          onClick={() => void handleExport()}
        >
          {status === "loading" ? "Preparing CSV export..." : "Export CSV"}
        </button>
        {!csrfToken ? (
          <p className={BODY_TEXT_CLASS}>
            Refresh your session before exporting this result.
          </p>
        ) : null}
      </div>

      {status === "loading" ? (
        <p className={INFO_CARD_CLASS} role="status" aria-live="polite">
          Preparing CSV export...
        </p>
      ) : null}

      {status === "success" && message ? (
        <p className={INFO_CARD_CLASS} role="status" aria-live="polite">
          {message}
        </p>
      ) : null}

      {status === "error" && message ? (
        <p className={ERROR_CARD_CLASS} role="alert">
          {message}
        </p>
      ) : null}
    </section>
  );
}

function exportErrorMessage(error: unknown): string {
  if (error instanceof ApiError && PERMISSION_ERROR_CODES.has(error.code)) {
    return "This result cannot be exported with your current permissions.";
  }

  return "CSV export could not be prepared. Try again.";
}
