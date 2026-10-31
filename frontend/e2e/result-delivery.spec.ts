import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import { expect, test } from "./fixtures";
import { loginAs } from "./helpers";

const execFileAsync = promisify(execFile);
const apiBase = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function fixture() {
  const backend = path.resolve(process.cwd(), "../backend");
  const python = process.env.M8_E2E_PYTHON ?? path.join(backend, ".venv/bin/python");
  const result = await execFileAsync(python, ["-m", "scripts.prepare_delivery_e2e"], { cwd: backend, env: process.env });
  return JSON.parse(result.stdout);
}

test.describe("Bounded result delivery @m8-primary", () => {
  test.describe.configure({ mode: "serial", retries: 0 });
  test.beforeAll(() => {
    expect(process.env.M8_E2E_DATABASE_DISPOSABLE).toBe("1");
    expect(process.env.M8_E2E_DATABASE_URL).toContain("e2e");
  });

  for (const [source, cardCount, cardState, csvCount, csvState] of [
    ["below_cap", 99, "complete", 99, "complete"],
    ["at_cap", 100, "safety_limited", 100, "safety_limited"],
    ["above_cap", 100, "safety_limited", 100, "safety_limited"],
    ["top_100", 100, "complete", 100, "complete"],
    ["top_500", 100, "safety_limited", 500, "complete"],
    ["clamped", 100, "safety_limited", 500, "safety_limited"],
    ["legacy", 100, "unknown", 100, "unknown"],
    ["table_11", 11, "complete", 11, "complete"]
  ] as const) {
    test(`${source} retains delivery provenance through saved Card, table and CSV`, async ({ page }) => {
      const ids = await fixture();
      if (source === "table_11") await page.setViewportSize({ width: 390, height: 844 });
      const signedIn = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/demo/login");
      await loginAs(page, "Demo Analyst");
      const csrf = (await (await signedIn).json()).data.csrf_token;
      const saved = await page.request.post(`${apiBase}/api/v1/query-runs/${ids.query_runs[source]}/save-card`, {
        headers: { "X-CSRF-Token": csrf },
        data: { dashboard_id: ids.dashboard_id, title: `Delivery ${source}`, card_type: "table" }
      });
      expect(saved.status()).toBe(201);
      const cardId = (await saved.json()).data.id;
      const tableMode = await page.request.patch(`${apiBase}/api/v1/cards/${cardId}`, {
        headers: { "X-CSRF-Token": csrf },
        data: { visualization: {
          mode: "manual", type: "table", recommended_type: "table",
          mapping: { category_column: null, value_columns: [], series_column: null, label_column: null, target_column: null }
        } }
      });
      expect(tableMode.status()).toBe(200);
      const refreshed = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/v1/cards/${cardId}/refresh`);
      await page.goto(`/dashboards/${ids.dashboard_id}`);
      const refresh = await refreshed;
      expect(refresh.status()).toBe(200);
      const data = (await refresh.json()).data;
      expect(data.delivery_completeness).toBe(cardState);
      expect(data.row_count).toBe(cardCount);
      if (source === "at_cap" || source === "above_cap") expect(data.truncated).toBe(false);
      const card = page.getByRole("article", { name: `Dashboard card Delivery ${source}`, exact: true });
      if (cardState === "safety_limited") await expect(card.getByText(/Partial result: a safety limit may have omitted rows/)).toBeVisible();
      else if (cardState === "unknown") await expect(card.getByText(/Result completeness is unknown/)).toBeVisible();
      else await expect(card.getByText(/Partial result|completeness is unknown/)).toHaveCount(0);
      await expect(card.getByText(`Showing 10 of ${cardCount} returned rows.`, { exact: true })).toBeVisible();
      await card.getByRole("button", { name: `Show all ${cardCount} returned rows` }).click();
      await expect(card.getByRole("table").getByRole("row")).toHaveCount(cardCount + 1);
      const lastRow = card.getByRole("cell", { name: `Delivery ${String(cardCount).padStart(4, "0")}`, exact: true });
      await lastRow.scrollIntoViewIfNeeded();
      await expect(lastRow).toBeVisible();
      await card.getByRole("button", { name: `Card actions for Delivery ${source}` }).click();
      const downloading = page.waitForEvent("download");
      const exporting = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/v1/cards/${cardId}/export-csv`);
      await page.getByRole("menuitem", { name: "Export CSV", exact: true }).click();
      const download = await downloading;
      const exported = await exporting;
      expect(exported.status()).toBe(200);
      expect(exported.headers()["x-queryops-delivery-completeness"]).toBe(csvState);
      expect(exported.headers()["x-queryops-returned-row-count"]).toBe(String(csvCount));
      const suffix = csvState === "safety_limited" ? "-partial.csv" : csvState === "unknown" ? "-completeness-unknown.csv" : ".csv";
      expect(download.suggestedFilename()).toBe(`card-${cardId}${suffix}`);
      const file = await download.path();
      expect(file).not.toBeNull();
      const contents = await readFile(file!, "utf8");
      expect(contents.trim().split(/\r?\n/)).toHaveLength(csvCount + 1);
      expect(contents.split(/\r?\n/)[0]).toBe("product_name,monthly_cost_usd");
      expect(contents).not.toContain("completeness");
      await expect(card.getByRole("status")).toContainText(`${csvCount} rows returned.`);
      await expect(card.getByRole("status")).toContainText(csvState === "safety_limited" ? "Partial CSV downloaded." : csvState === "unknown" ? "completeness could not be established" : "CSV export downloaded.");
    });
  }
});
