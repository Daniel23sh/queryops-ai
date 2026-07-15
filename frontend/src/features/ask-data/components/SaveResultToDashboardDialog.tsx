import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { getMyDashboards, saveQueryRunAsCard, updateDashboardCard } from "../../../api/dashboards";
import { AccessibleOverlay } from "../../../components/ui/AccessibleOverlay";
import type { Dashboard } from "../../dashboard/types";
import { inferVisualization, recommendedConfig } from "../../dashboard/visualization";
import type { CurrentQueryResult } from "../types";

type LoadStatus = "loading" | "loaded" | "error";
type SaveStatus = "idle" | "saving" | "complete" | "partial" | "error";

export function SaveResultToDashboardDialog({
  csrfToken,
  current,
  onClose,
  onStatus
}: {
  csrfToken: string | null;
  current: CurrentQueryResult;
  onClose: () => void;
  onStatus: (message: string) => void;
}) {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [selectedDashboardId, setSelectedDashboardId] = useState("");
  const [title, setTitle] = useState(current.originalQuestion);
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const requestRef = useRef(0);
  const selectedDashboard = dashboards.find((dashboard) => dashboard.id === selectedDashboardId) ?? null;
  const saving = saveStatus === "saving";

  useEffect(() => {
    const generation = ++requestRef.current;
    getMyDashboards()
      .then((loaded) => {
        if (requestRef.current !== generation) return;
        const personal = loaded.filter((dashboard) => dashboard.visibility_scope === "personal" && !dashboard.is_archived);
        setDashboards(personal);
        setSelectedDashboardId(personal[0]?.id ?? "");
        setLoadStatus("loaded");
      })
      .catch(() => {
        if (requestRef.current !== generation) return;
        setLoadStatus("error");
      });
    return () => { requestRef.current += 1; };
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const queryRunId = current.result.query_run_id;
    if (saving || !queryRunId || !selectedDashboard || !csrfToken) return;
    const generation = ++requestRef.current;
    setSaveStatus("saving");
    setMessage(null);
    onStatus("Saving result to dashboard…");
    try {
      const card = await saveQueryRunAsCard(queryRunId, {
        dashboard_id: selectedDashboard.id,
        title: title.trim() || current.originalQuestion,
        description: description.trim() || undefined,
        card_type: "table"
      }, csrfToken);
      if (requestRef.current !== generation) return;
      const recommendation = inferVisualization({ columns: current.result.columns, rows: current.result.rows });
      try {
        await updateDashboardCard(card.id, { visualization: recommendedConfig(recommendation) }, csrfToken);
        if (requestRef.current !== generation) return;
        setSaveStatus("complete");
        setMessage(`Saved to ${selectedDashboard.title}`);
        onStatus(`Saved to ${selectedDashboard.title}.`);
      } catch {
        if (requestRef.current !== generation) return;
        setSaveStatus("partial");
        setMessage(`Saved to ${selectedDashboard.title}. The card will use the safe Table view until its visualization is updated.`);
        onStatus("Card saved. Visualization configuration could not be applied.");
      }
    } catch {
      if (requestRef.current !== generation) return;
      setSaveStatus("error");
      setMessage("This result could not be saved. Try again.");
      onStatus("Result could not be saved.");
    }
  }

  const completed = saveStatus === "complete" || saveStatus === "partial";
  return (
    <AccessibleOverlay kind="dialog" closeDisabled={saving} onClose={onClose} title="Save to Dashboard" description="Save this result to one of your personal dashboards." footer={completed ? <><Link className="qops-button-primary" to={`/dashboards/${encodeURIComponent(selectedDashboardId)}`}>Open dashboard</Link><button className="qops-button-secondary" type="button" onClick={onClose}>Done</button></> : undefined}>
      {loadStatus === "loading" ? <p role="status" className="text-sm text-app-subtle">Loading personal dashboards…</p> : null}
      {loadStatus === "error" ? <p role="alert" className="text-sm text-status-danger">Personal dashboards could not be loaded.</p> : null}
      {loadStatus === "loaded" && dashboards.length === 0 ? <div className="grid gap-3 rounded-card border border-app-border bg-app-muted p-4 text-sm text-app-subtle"><p className="m-0">Create a personal dashboard before saving a result.</p><Link className="qops-button-primary justify-self-start" to="/">Go to My Dashboard</Link></div> : null}
      {loadStatus === "loaded" && dashboards.length > 0 && !completed ? (
        <form className="grid gap-4" onSubmit={(event) => void handleSubmit(event)}>
          <Field label="Target dashboard"><select className={CONTROL_CLASS} value={selectedDashboardId} disabled={saving} onChange={(event) => setSelectedDashboardId(event.target.value)}>{dashboards.map((dashboard) => <option key={dashboard.id} value={dashboard.id}>{dashboard.title}</option>)}</select></Field>
          <Field label="Card title"><input className={CONTROL_CLASS} value={title} disabled={saving} onChange={(event) => setTitle(event.target.value)} /></Field>
          <Field label="Description (optional)"><textarea className={`${CONTROL_CLASS} min-h-24 resize-y`} value={description} disabled={saving} onChange={(event) => setDescription(event.target.value)} /></Field>
          {message ? <p className="m-0 text-sm text-status-danger" role="alert">{message}</p> : null}
          <div className="flex justify-end gap-2"><button className="qops-button-secondary" type="button" disabled={saving} onClick={onClose}>Cancel</button><button className="qops-button-primary" type="submit" disabled={saving || !selectedDashboardId || !csrfToken}>{saving ? "Saving…" : "Save"}</button></div>
        </form>
      ) : null}
      {completed && message ? <p className="m-0 rounded-card border border-status-success/40 bg-status-success/10 p-4 text-sm text-app-text" role="status">{message}</p> : null}
    </AccessibleOverlay>
  );
}

function Field({ children, label }: { children: React.ReactNode; label: string }) { return <label className="grid gap-2 text-sm font-bold text-app-text"><span>{label}</span>{children}</label>; }
const CONTROL_CLASS = "min-h-11 w-full rounded-control border border-app-border bg-app-muted px-3 py-2 text-sm text-app-text outline-none focus:border-brand-primary focus:shadow-focus disabled:opacity-60";
