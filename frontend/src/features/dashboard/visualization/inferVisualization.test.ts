import { describe, expect, it } from "vitest";

import type { VisualizationConfig } from "../types";
import { inferVisualization, manualConfig, nearestAllowedSize } from ".";

describe("inferVisualization", () => {
  it("recommends KPI for one numeric result", () => {
    const result = inferVisualization({ columns: ["active_users"], rows: [{ active_users: 84 }] });
    expect(result.recommendedType).toBe("kpi");
    expect(result.compatibleTypes).toContain("table");
  });

  it("reserves gauges for clear bounded semantics", () => {
    const gauge = inferVisualization({ columns: ["compliance_rate"], rows: [{ compliance_rate: 93.16 }] });
    const arbitrary = inferVisualization({ columns: ["license_cost"], rows: [{ license_cost: 18432 }] });
    expect(gauge.recommendedType).toBe("semicircle_gauge");
    expect(arbitrary.recommendedType).toBe("kpi");
  });

  it("recommends line for temporal values and exposes area compatibility", () => {
    const result = inferVisualization({
      columns: ["created_month", "ticket_count"],
      rows: [
        { created_month: "2026-01-01", ticket_count: 2 },
        { created_month: "2026-02-01", ticket_count: 5 }
      ]
    });
    expect(result.recommendedType).toBe("line");
    expect(result.compatibleTypes).toEqual(expect.arrayContaining(["line", "area", "table"]));
  });

  it("uses area only for volume-like time-series semantics", () => {
    const result = inferVisualization({
      columns: ["period_date", "traffic_volume"],
      rows: [
        { period_date: "2026-01-01", traffic_volume: 10 },
        { period_date: "2026-01-02", traffic_volume: 14 }
      ]
    });
    expect(result.recommendedType).toBe("area");
  });

  it("defaults ordinary category comparisons to bar", () => {
    const result = inferVisualization({
      columns: ["department", "device_count"],
      rows: [{ department: "IT", device_count: 3 }, { department: "Sales", device_count: 5 }]
    });
    expect(result.recommendedType).toBe("bar");
    expect(result.compatibleTypes).not.toContain("donut");
  });

  it("recommends stacked bars for bounded category and series dimensions", () => {
    const result = inferVisualization({
      columns: ["department", "device_type", "device_count"],
      rows: [
        { department: "IT", device_type: "Laptop", device_count: 3 },
        { department: "IT", device_type: "Phone", device_count: 2 },
        { department: "Sales", device_type: "Laptop", device_count: 4 }
      ]
    });
    expect(result.recommendedType).toBe("stacked_bar");
  });

  it("builds a type-specific mapping for manual stacked-bar selection", () => {
    const result = inferVisualization({
      columns: ["priority", "status", "ticket_count"],
      rows: [
        { priority: "high", status: "open", ticket_count: 3 },
        { priority: "high", status: "in_progress", ticket_count: 2 }
      ]
    });

    expect(result.recommendedType).toBe("bar");
    expect(result.compatibleTypes).toContain("stacked_bar");
    expect(manualConfig("stacked_bar", result).mapping).toMatchObject({
      category_column: "priority",
      series_column: "status",
      value_columns: ["ticket_count"]
    });
  });

  it("allows donut only for bounded, non-negative part-to-whole data", () => {
    const allowed = inferVisualization({
      columns: ["department", "license_share"],
      rows: [{ department: "IT", license_share: 40 }, { department: "Sales", license_share: 60 }]
    });
    const negative = inferVisualization({
      columns: ["department", "license_share"],
      rows: [{ department: "IT", license_share: -4 }, { department: "Sales", license_share: 104 }]
    });
    expect(allowed.recommendedType).toBe("donut");
    expect(negative.compatibleTypes).not.toContain("donut");
  });

  it("recommends status list for small status-like results", () => {
    const result = inferVisualization({
      columns: ["service", "health_status"],
      rows: [{ service: "Email", health_status: "healthy" }, { service: "VPN", health_status: "degraded" }]
    });
    expect(result.recommendedType).toBe("status_list");
  });

  it("falls back to table for null, mixed, and large category data", () => {
    expect(inferVisualization({ columns: ["value"], rows: [{ value: null }] }).recommendedType).toBe("table");
    expect(inferVisualization({ columns: ["value"], rows: [{ value: 1 }, { value: "two" }] }).recommendedType).toBe("table");
    const rows = Array.from({ length: 30 }, (_, index) => ({ category: `C${index}`, value: index }));
    expect(inferVisualization({ columns: ["category", "value"], rows }).recommendedType).toBe("table");
  });

  it("treats numeric identifier columns as categories", () => {
    const result = inferVisualization({ columns: ["device_id"], rows: [{ device_id: 1001 }] });
    expect(result.recommendedType).toBe("table");
    expect(result.profiles[0].kind).toBe("categorical");
  });

  it("preserves compatible manual types and safely renders table for incompatible ones", () => {
    const compatible = inferVisualization({
      columns: ["department", "count"],
      rows: [{ department: "IT", count: 2 }],
      currentConfig: config("bar")
    });
    const incompatible = inferVisualization({
      columns: ["active_users"],
      rows: [{ active_users: 2 }],
      currentConfig: config("line")
    });
    expect(compatible.renderType).toBe("bar");
    expect(incompatible.renderType).toBe("table");
    expect(incompatible.warning).toMatch(/saved visualization/i);
  });

  it("snaps resize candidates to stable size presets", () => {
    expect(nearestAllowedSize("table", "desktop", { w: 7, h: 4 })).toEqual({ w: 6, h: 4 });
    expect(nearestAllowedSize("kpi", "mobile", { w: 1, h: 9 })).toEqual({ w: 1, h: 2 });
  });
});

function config(type: VisualizationConfig["type"]): VisualizationConfig {
  return {
    mode: "manual",
    type,
    recommended_type: "table",
    mapping: {
      category_column: null,
      value_columns: [],
      series_column: null,
      label_column: null,
      target_column: null
    }
  };
}
