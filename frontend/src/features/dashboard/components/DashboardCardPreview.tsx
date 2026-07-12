import { useRef, useState } from "react";

import { ApiError, downloadBlob } from "../../../api/client";
import { exportDashboardCardCsv } from "../../../api/exports";
import type { QueryRowValue } from "../../ask-data/types";
import { useDashboardCardRefresh } from "../hooks/useDashboardCardRefresh";
import type { DashboardCard, DashboardCardRefreshResult } from "../types";

type ExportStatus = "idle" | "loading" | "success" | "error";

const EXPORT_PERMISSION_ERRORS = new Set([
  "FORBIDDEN",
  "CARD_NOT_EXPORTABLE",
  "CSV_EXPORT_NOT_ALLOWED",
  "CSRF_TOKEN_MISSING"
]);

export function DashboardCardPreview({
  canExport,
  canRefresh,
  card,
  csrfToken
}: {
  canExport: boolean;
  canRefresh: boolean;
  card: DashboardCard;
  csrfToken: string | null;
}) {
  const { refresh, result, state } = useDashboardCardRefresh({
    canRefresh: canRefresh && card.saved_query_id !== null,
    cardId: card.id,
    csrfToken
  });
  const [exportStatus, setExportStatus] = useState<ExportStatus>("idle");
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const exportInFlight = useRef(false);
  const showExport =
    canExport && card.saved_query_id !== null && csrfToken !== null;

  async function handleExport() {
    if (!csrfToken || exportInFlight.current) {
      return;
    }

    exportInFlight.current = true;
    setExportStatus("loading");
    setExportMessage(null);
    try {
      const download = await exportDashboardCardCsv(card.id, csrfToken, {
        include_headers: true
      });
      downloadBlob(download);
      setExportStatus("success");
      setExportMessage("Card CSV export downloaded.");
    } catch (error: unknown) {
      setExportStatus("error");
      setExportMessage(cardExportErrorMessage(error));
    } finally {
      exportInFlight.current = false;
    }
  }

  return (
    <article className="dashboard-card-preview">
      <div className="dashboard-card-preview__header">
        <h4>{card.title}</h4>
        <span className="dashboard-card-pill">{formatCardType(card.card_type)}</span>
      </div>

      {card.description ? (
        <p className="dashboard-card-preview__description">{card.description}</p>
      ) : null}

      <div className="dashboard-card-preview__actions">
        {canRefresh && card.saved_query_id ? (
          <button
            type="button"
            className="qops-button-secondary qops-focus-ring"
            aria-label={`Refresh ${card.title}`}
            disabled={!csrfToken || state.status === "loading"}
            onClick={() => void refresh()}
          >
            {state.status === "loading" ? "Refreshing card..." : "Refresh"}
          </button>
        ) : null}

        {showExport ? (
          <button
            type="button"
            className="qops-button-secondary qops-focus-ring"
            aria-label={`Export ${card.title} as CSV`}
            disabled={exportStatus === "loading"}
            onClick={() => void handleExport()}
          >
            {exportStatus === "loading"
              ? "Preparing CSV export..."
              : "Export CSV"}
          </button>
        ) : null}
      </div>

      {showExport ? (
        <p className="dashboard-card-preview__notice">
          The exported CSV uses your current access scope and is recorded in the
          audit log.
        </p>
      ) : null}

      {state.status === "loading" ? (
        <p className="dashboard-card-preview__status" role="status" aria-live="polite">
          Refreshing card under your current access scope...
        </p>
      ) : null}

      {state.status === "error" ? (
        <p className="dashboard-card-preview__error" role="alert">
          {state.message}
        </p>
      ) : null}

      {exportStatus === "loading" ? (
        <p className="dashboard-card-preview__status" role="status" aria-live="polite">
          Preparing CSV export...
        </p>
      ) : null}

      {exportStatus === "success" && exportMessage ? (
        <p className="dashboard-card-preview__status" role="status" aria-live="polite">
          {exportMessage}
        </p>
      ) : null}

      {exportStatus === "error" && exportMessage ? (
        <p className="dashboard-card-preview__error" role="alert">
          {exportMessage}
        </p>
      ) : null}

      {result ? <CardResultPreview result={result} /> : null}

      <dl className="dashboard-card-preview__meta" aria-label={`${card.title} metadata`}>
        <div>
          <dt>Order</dt>
          <dd>Order {card.position + 1}</dd>
        </div>
        {result ? (
          <>
            <div>
              <dt>Rows</dt>
              <dd>{result.row_count}</dd>
            </div>
            <div>
              <dt>Last refreshed</dt>
              <dd>
                <time dateTime={result.refreshed_at}>
                  {formatRefreshedAt(result.refreshed_at)}
                </time>
              </dd>
            </div>
          </>
        ) : null}
      </dl>
    </article>
  );
}

function CardResultPreview({ result }: { result: DashboardCardRefreshResult }) {
  const previewRows = result.rows.slice(0, 5);
  const hasTable = result.columns.length > 0 && previewRows.length > 0;

  return (
    <div className="dashboard-card-result" aria-label="Refreshed card result">
      {hasTable ? (
        <div className="dashboard-card-result__table-wrap">
          <table aria-label="Dashboard card results">
            <thead>
              <tr>
                {result.columns.map((column) => (
                  <th scope="col" key={column}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {previewRows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {result.columns.map((column) => (
                    <td key={column}>{formatRowValue(row[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="dashboard-card-preview__status">No rows returned.</p>
      )}

      {result.truncated ? (
        <p className="dashboard-card-preview__warning">
          Preview limited to the first 100 returned rows.
        </p>
      ) : null}

      {result.warnings.length > 0 ? (
        <ul
          className="dashboard-card-preview__warning-list"
          aria-label="Card refresh warnings"
        >
          {result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      {result.rows.length > 5 ? (
        <p className="dashboard-card-preview__notice">
          Showing the first 5 rows in this card preview.
        </p>
      ) : null}
    </div>
  );
}

function formatRowValue(value: QueryRowValue | undefined): string {
  if (value === undefined) {
    return "";
  }
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  try {
    return JSON.stringify(value);
  } catch {
    return "[unavailable]";
  }
}

function formatRefreshedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Recently";
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC"
  }).format(date);
}

function cardExportErrorMessage(error: unknown): string {
  if (error instanceof ApiError && EXPORT_PERMISSION_ERRORS.has(error.code)) {
    return "This card cannot be exported with your current permissions.";
  }
  return "Card CSV export could not be prepared. Try again.";
}

function formatCardType(cardType: string): string {
  return cardType === "table" ? "Table" : cardType;
}
