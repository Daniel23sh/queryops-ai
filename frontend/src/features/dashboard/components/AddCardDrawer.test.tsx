import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { refreshDashboardCard, saveQueryRunAsCard, updateDashboardCard } from "../../../api/dashboards";
import { getQueryHistory, runQuery } from "../../../api/queries";
import { listQueryTemplates } from "../../../api/queryTemplates";
import { AddCardDrawer } from "./AddCardDrawer";

vi.mock("../../../api/dashboards", () => ({ refreshDashboardCard: vi.fn(), saveQueryRunAsCard: vi.fn(), updateDashboardCard: vi.fn() }));
vi.mock("../../../api/queries", () => ({ getQueryHistory: vi.fn(), runQuery: vi.fn() }));
vi.mock("../../../api/queryTemplates", () => ({ listQueryTemplates: vi.fn() }));

afterEach(() => { vi.clearAllMocks(); document.body.style.overflow = ""; });

describe("AddCardDrawer", () => {
  it("runs, saves, refreshes, infers, and persists an approved template exactly once", async () => {
    vi.mocked(listQueryTemplates).mockResolvedValue([template()]);
    vi.mocked(getQueryHistory).mockResolvedValue([]);
    vi.mocked(runQuery).mockResolvedValue(queryResult());
    vi.mocked(saveQueryRunAsCard).mockResolvedValue({ id: "new-card" } as never);
    vi.mocked(refreshDashboardCard).mockResolvedValue(refreshResult());
    vi.mocked(updateDashboardCard).mockResolvedValue({} as never);
    const onClose = vi.fn(); const reload = vi.fn().mockResolvedValue(undefined);
    render(<AddCardDrawer csrfToken="csrf" dashboardId="dashboard" onClose={onClose} onDashboardReload={reload} />);

    const addButton = await screen.findByRole("button", { name: "Run and add" });
    fireEvent.click(addButton);
    expect(addButton).toBeDisabled();

    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(runQuery).toHaveBeenCalledOnce();
    expect(saveQueryRunAsCard).toHaveBeenCalledWith("query-run", expect.objectContaining({ dashboard_id: "dashboard" }), "csrf");
    expect(refreshDashboardCard).toHaveBeenCalledWith("new-card", "csrf");
    expect(updateDashboardCard).toHaveBeenCalledWith("new-card", expect.objectContaining({ visualization: expect.objectContaining({ mode: "auto", type: "bar" }) }), "csrf");
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("shows only eligible recent successful results and never renders SQL", async () => {
    vi.mocked(listQueryTemplates).mockResolvedValue([]);
    vi.mocked(getQueryHistory).mockResolvedValue([
      history("eligible", true),
      { ...history("already-saved", false), executed_sql: "SELECT private" }
    ]);
    vi.mocked(saveQueryRunAsCard).mockResolvedValue({ id: "new-card" } as never);
    vi.mocked(refreshDashboardCard).mockResolvedValue(refreshResult());
    vi.mocked(updateDashboardCard).mockResolvedValue({} as never);
    render(<AddCardDrawer csrfToken="csrf" dashboardId="dashboard" onClose={vi.fn()} onDashboardReload={vi.fn().mockResolvedValue(undefined)} />);

    fireEvent.click(await screen.findByRole("tab", { name: "Recent results" }));
    expect(screen.getByText("Question eligible")).toBeInTheDocument();
    expect(screen.queryByText("Question already-saved")).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT private/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add result" }));
    await waitFor(() => expect(saveQueryRunAsCard).toHaveBeenCalledWith("eligible", expect.any(Object), "csrf"));
    expect(runQuery).not.toHaveBeenCalled();
  });

  it("distinguishes a save failure after a successful query", async () => {
    vi.mocked(listQueryTemplates).mockResolvedValue([template()]);
    vi.mocked(getQueryHistory).mockResolvedValue([]);
    vi.mocked(runQuery).mockResolvedValue(queryResult());
    vi.mocked(saveQueryRunAsCard).mockRejectedValue(new Error("no"));
    render(<AddCardDrawer csrfToken="csrf" dashboardId="dashboard" onClose={vi.fn()} onDashboardReload={vi.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(await screen.findByRole("button", { name: "Run and add" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/query succeeded, but it could not be saved/i);
    expect(refreshDashboardCard).not.toHaveBeenCalled();
  });
});

function template() { return { id: "template", title: "Devices by scope", description: "Counts devices.", domain: "it", category: "Devices", natural_language_question: "Count devices by scope.", parameters: [], scope_type: "department", required_permission: "can_use_query_templates", can_suggest_action: false }; }
function queryResult() { return { query_run_id: "query-run", status: "succeeded" as const, columns: ["department", "device_count"], rows: [{ department: "IT", device_count: 3 }], row_count: 1, duration_ms: 2, truncated: false, message: "Done", warnings: [], clarification_required: false, metadata: {}, suggested_actions: [] }; }
function refreshResult() { return { card_id: "new-card", dashboard_id: "dashboard", saved_query_id: "saved", query_run_id: "refresh", status: "succeeded" as const, columns: ["department", "device_count"], rows: [{ department: "IT", device_count: 3 }, { department: "Sales", device_count: 5 }], row_count: 2, duration_ms: 2, truncated: false, refreshed_at: "2026-07-14T12:00:00Z", message: "Done", warnings: [] }; }
function history(id: string, canSave: boolean) { return { id, status: "succeeded" as const, natural_language_question: `Question ${id}`, row_count: 2, duration_ms: 2, error_message: null, created_at: "2026-07-14T12:00:00Z", started_at: null, completed_at: "2026-07-14T12:00:01Z", metadata: {}, can_save_as_card: canSave }; }
