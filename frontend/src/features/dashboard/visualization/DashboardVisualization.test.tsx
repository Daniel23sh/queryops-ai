import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DashboardCardRefreshResult, VisualizationConfig } from "../types";
import { DashboardVisualization } from "./DashboardVisualization";

describe("DashboardVisualization", () => {
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
