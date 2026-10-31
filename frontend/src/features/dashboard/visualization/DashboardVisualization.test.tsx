import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DashboardCardRefreshResult, VisualizationConfig } from "../types";
import { DashboardVisualization } from "./DashboardVisualization";

describe("DashboardVisualization", () => {
  it("discloses the actual table preview and makes row 11 accessible", () => {
    const rows = Array.from({ length: 24 }, (_, index) => ({ item: `Item ${index + 1}` }));
    render(<DashboardVisualization config={config("table", "manual")} result={result(["item"], rows)} title="Items" />);
    expect(screen.getByText("Showing 10 of 24 returned rows.")).toBeInTheDocument();
    expect(screen.queryByText("Item 11")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show all 24 returned rows" }));
    expect(screen.getByText("Item 11")).toBeInTheDocument();
    expect(screen.getByText("Item 24")).toBeInTheDocument();
    expect(screen.getByText("Showing all 24 returned rows.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show fewer rows" }));
    expect(screen.queryByText("Item 11")).not.toBeInTheDocument();
  });

  it("keeps all returned table rows accessible beyond the chart-only limit", () => {
    const rows = Array.from({ length: 100 }, (_, index) => ({ item: `Item ${index + 1}` }));
    render(<DashboardVisualization config={config("table", "manual")} result={result(["item"], rows)} title="Items" />);
    fireEvent.click(screen.getByRole("button", { name: "Show all 100 returned rows" }));
    expect(screen.getByText("Item 100")).toBeInTheDocument();
  });

  it("discloses safety-limited delivery even when SQL truncation is false", () => {
    const delivery = { ...result(["item"], [{ item: "Only delivered item" }]), delivery_completeness: "safety_limited" as const };
    render(<DashboardVisualization config={config("table", "manual")} result={delivery} title="Items" />);
    expect(screen.getByText(/Partial result: a safety limit may have omitted rows/i)).toBeInTheDocument();
    expect(screen.queryByText(/Showing 10 of/)).not.toBeInTheDocument();
  });

  it("does not claim completeness for a legacy response without delivery metadata", () => {
    render(<DashboardVisualization config={config("table", "manual")} result={result(["item"], [{ item: "Legacy" }])} title="Items" />);
    expect(screen.getByText(/Result completeness is unknown/i)).toBeInTheDocument();
  });

  it("does not mark an explicitly complete bounded result as partial", () => {
    const delivery = { ...result(["item"], [{ item: "Top result" }]), delivery_completeness: "complete" as const };
    render(<DashboardVisualization config={config("table", "manual")} result={delivery} title="Top item" />);
    expect(screen.queryByText(/Partial result|completeness is unknown/)).not.toBeInTheDocument();
  });

  it("renders an accessible empty state", () => {
    render(<DashboardVisualization config={config("table")} result={result([], [])} title="Empty card" />);
    expect(screen.getByText("No result rows are available for this card.")).toBeInTheDocument();
  });

  it("renders structured table content without interpreting unsafe strings as HTML", () => {
    render(<DashboardVisualization
      config={config("table", "manual")}
      result={result(["service", "status"], [{ service: "<img src=x onerror=alert(1)>", status: "healthy" }])}
      title="Service status"
    />);
    expect(screen.getByRole("table", { name: "Dashboard card results" })).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText(/Service status: table visualization with 1 row/i)).toHaveClass("qops-sr-only");
  });

  it("preserves an incompatible manual choice while rendering the safe Table fallback", () => {
    render(<DashboardVisualization
      config={config("line", "manual")}
      result={result(["department", "device_count"], [{ department: "IT", device_count: 3 }])}
      title="Devices"
    />);
    expect(screen.getByRole("status")).toHaveTextContent(/saved visualization is not compatible/i);
    expect(screen.getByRole("table", { name: "Dashboard card results" })).toBeInTheDocument();
  });

  it("renders a KPI with a screen-reader summary", () => {
    render(<DashboardVisualization config={config("kpi")} result={result(["active_users"], [{ active_users: 84 }])} title="Active users" />);
    expect(screen.getByText("84")).toBeInTheDocument();
    expect(screen.getByText(/Active users: KPI visualization with 1 row/i)).toBeInTheDocument();
  });
});

function config(type: VisualizationConfig["type"], mode: VisualizationConfig["mode"] = "auto"): VisualizationConfig {
  return { mode, type, recommended_type: type, mapping: { category_column: null, value_columns: type === "kpi" ? ["active_users"] : [], series_column: null, label_column: null, target_column: null } };
}
function result(columns: string[], rows: Array<Record<string, string | number>>): DashboardCardRefreshResult {
  return { card_id: "card", dashboard_id: "dashboard", saved_query_id: "saved", query_run_id: "run", status: "succeeded", columns, rows, row_count: rows.length, duration_ms: 2, truncated: false, refreshed_at: "2026-07-14T12:00:00Z", message: "Done", warnings: [] };
}
