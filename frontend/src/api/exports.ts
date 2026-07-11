import { apiDownload } from "./client";
import type { ApiDownloadResult } from "./client";

export type CsvExportRequest = {
  filename?: string;
  include_headers?: boolean;
};

export function exportQueryRunCsv(
  queryRunId: string,
  csrfToken: string,
  payload: CsvExportRequest = {}
): Promise<ApiDownloadResult> {
  return apiDownload(
    `/api/v1/query-runs/${encodeURIComponent(queryRunId)}/export-csv`,
    exportRequestInit(csrfToken, payload),
    "query-result.csv"
  );
}

export function exportDashboardCardCsv(
  cardId: string,
  csrfToken: string,
  payload: CsvExportRequest = {}
): Promise<ApiDownloadResult> {
  return apiDownload(
    `/api/v1/cards/${encodeURIComponent(cardId)}/export-csv`,
    exportRequestInit(csrfToken, payload),
    "dashboard-card.csv"
  );
}

function exportRequestInit(
  csrfToken: string,
  payload: CsvExportRequest
): RequestInit {
  return {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken
    },
    body: JSON.stringify(payload)
  };
}
