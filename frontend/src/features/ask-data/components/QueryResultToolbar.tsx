import { useEffect, useRef, useState } from "react";
import { Download, Save } from "lucide-react";

import { ApiError, downloadBlob } from "../../../api/client";
import { exportQueryRunCsv } from "../../../api/exports";
import type { CurrentQueryResult } from "../types";
import { SaveResultToDashboardDialog } from "./SaveResultToDashboardDialog";

const PERMISSION_ERROR_CODES = new Set(["FORBIDDEN", "CSV_EXPORT_NOT_ALLOWED", "QUERY_RUN_NOT_EXPORTABLE", "CSRF_TOKEN_MISSING"]);

export function QueryResultToolbar({
  canExport,
  canSave,
  csrfToken,
  current
}: {
  canExport: boolean;
  canSave: boolean;
  csrfToken: string | null;
  current: CurrentQueryResult;
}) {
  const [exporting, setExporting] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [status, setStatus] = useState("");
  const requestGeneration = useRef(0);
  const queryRunId = current.result.query_run_id;

  useEffect(() => {
    requestGeneration.current += 1;
    setExporting(false);
    setSaveOpen(false);
    setStatus("");
  }, [current.generation]);

  async function handleExport() {
    if (exporting || !queryRunId || !csrfToken) return;
    const generation = ++requestGeneration.current;
    setExporting(true);
    setStatus("Preparing CSV export…");
    try {
      const download = await exportQueryRunCsv(queryRunId, csrfToken, { include_headers: true });
      if (requestGeneration.current !== generation) return;
      downloadBlob(download);
      setStatus("CSV export downloaded. Exports are audited.");
    } catch (error) {
      if (requestGeneration.current !== generation) return;
      setStatus(error instanceof ApiError && PERMISSION_ERROR_CODES.has(error.code)
        ? "This result cannot be exported with your current permissions."
        : "CSV export could not be prepared. Try again.");
    } finally {
      if (requestGeneration.current === generation) setExporting(false);
    }
  }

  if (!canExport && !canSave) return null;

  return (
    <>
      <div className="flex flex-col gap-2 border-t border-app-border pt-4 sm:flex-row sm:items-center sm:justify-between" aria-label="Result actions">
        <div className="flex flex-wrap gap-2">
          {canSave ? <button className="qops-button-primary min-h-11" type="button" disabled={!csrfToken} onClick={() => setSaveOpen(true)}><Save aria-hidden="true" size={17} />Save to Dashboard</button> : null}
          {canExport ? <button className="qops-button-secondary min-h-11" type="button" aria-description="Exports use your current scope and are audited." disabled={exporting || !csrfToken} onClick={() => void handleExport()}><Download aria-hidden="true" size={17} />{exporting ? "Preparing…" : "Export CSV"}</button> : null}
        </div>
        <p className="m-0 text-xs leading-5 text-app-subtle" aria-live="polite">{status}</p>
      </div>
      {saveOpen ? <SaveResultToDashboardDialog csrfToken={csrfToken} current={current} onClose={() => setSaveOpen(false)} onStatus={setStatus} /> : null}
    </>
  );
}
