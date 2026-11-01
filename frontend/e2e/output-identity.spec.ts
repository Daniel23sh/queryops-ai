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
  const result = await execFileAsync(python, ["-m", "scripts.prepare_output_identity_e2e"], { cwd: backend, env: process.env });
  return JSON.parse(result.stdout);
}

test.describe("Deterministic output identity @m8-primary", () => {
  test.describe.configure({ mode: "serial", retries: 0 });
  test.beforeAll(() => {
    expect(process.env.M8_E2E_DATABASE_DISPOSABLE).toBe("1");
    expect(process.env.M8_E2E_DATABASE_URL).toContain("e2e");
  });

  for (const kind of ["identity", "aggregate"] as const) {
    test(`${kind} retains every value through saved visualization, reload and CSV`, async ({ page }) => {
      const state = await fixture();
      const signedIn = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/demo/login");
      await loginAs(page, "Demo Analyst");
      const csrf = (await (await signedIn).json()).data.csrf_token;
      const headers = { "X-CSRF-Token": csrf };
      const title = `Output ${kind}`;
      const saved = await page.request.post(`${apiBase}/api/v1/query-runs/${state.query_runs[kind]}/save-card`, {
        headers, data: { dashboard_id: state.dashboard_id, title, card_type: "table" }
      });
      expect(saved.status()).toBe(201);
      const cardId = (await saved.json()).data.id;
      const columns = kind === "identity"
        ? ["hostname", "devices__id", "last_seen_at", "directory_users__id"]
        : ["licenses__product_name", "aggregation__product_name"];
      const refreshed = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/v1/cards/${cardId}/refresh`);
      await page.goto(`/dashboards/${state.dashboard_id}`);
      const response = await refreshed;
      expect(response.status()).toBe(200);
      const result = (await response.json()).data;
      expect(result.columns).toEqual(columns);
      expect(result.rows).toHaveLength(2);
      const card = page.getByRole("article", { name: `Dashboard card ${title}`, exact: true });
      if (kind === "identity") {
        expect(result.rows).toEqual(expect.arrayContaining(state.expected_analyst));
        for (const row of state.expected_analyst) {
          await expect(card.getByRole("cell", { name: row.devices__id, exact: true })).toBeVisible();
          await expect(card.getByRole("cell", { name: row.directory_users__id, exact: true })).toHaveCount(2);
        }
      } else {
        await expect(card.locator('[data-visualization="bar"]')).toBeVisible();
        await expect(card.locator(".dashboard-visualization > .qops-sr-only")).toContainText(/Primary measure: Aggregation\s+Product Name/);
        await expect(card.locator(".recharts-bar-rectangle")).toHaveCount(2);
        await expect(card.getByText("=W6b", { exact: true })).toBeVisible();
        const tableMode = await page.request.patch(`${apiBase}/api/v1/cards/${cardId}`, {
          headers, data: { visualization: {
            mode: "manual", type: "table", recommended_type: "bar",
            mapping: { category_column: null, value_columns: [], series_column: null, label_column: null, target_column: null }
          } }
        });
        expect(tableMode.status()).toBe(200);
      }
      const reloaded = page.waitForResponse((candidate) => new URL(candidate.url()).pathname === `/api/v1/cards/${cardId}/refresh`);
      await page.reload();
      expect((await reloaded).status()).toBe(200);
      const table = card.getByRole("table", { name: "Dashboard card results" });
      await expect(table.getByRole("columnheader")).toHaveCount(columns.length);
      expect((await table.getByRole("columnheader").allTextContents()).map((text) => text.replace(/\s+/g, " ").trim())).toEqual(
        kind === "identity" ? ["Hostname", "Devices Id", "Last Seen At", "Directory Users Id"]
          : ["Licenses Product Name", "Aggregation Product Name"]
      );
      await expect(table.getByRole("row")).toHaveCount(3);
      if (kind === "aggregate") {
        await expect(table.getByRole("cell", { name: "=W6b", exact: true })).toBeVisible();
        await expect(table.getByRole("cell", { name: "2", exact: true })).toBeVisible();
      }
      await card.getByRole("button", { name: `Card actions for ${title}` }).click();
      const downloading = page.waitForEvent("download");
      const exporting = page.waitForResponse((candidate) => new URL(candidate.url()).pathname === `/api/v1/cards/${cardId}/export-csv`);
      await page.getByRole("menuitem", { name: "Export CSV", exact: true }).click();
      const download = await downloading;
      expect((await exporting).status()).toBe(200);
      const file = await download.path();
      expect(file).not.toBeNull();
      const csv = await readFile(file!, "utf8");
      expect(csv.split(/\r?\n/)[0]).toBe(columns.join(","));
      expect(csv.trim().split(/\r?\n/)).toHaveLength(3);
      if (kind === "identity") {
        for (const row of state.expected_analyst) {
          expect(csv).toContain(`${row.hostname},${row.devices__id},,${row.directory_users__id}`);
        }
        expect(csv).not.toContain("W6b-Finance-1");
      } else {
        expect(csv).toContain("'=W6b,2");
        expect(csv).toContain("Normal,1");
      }
      expect(await page.evaluate(() => JSON.stringify({ local: localStorage, session: sessionStorage }))).not.toContain("W6b-IT-1");
    });
  }
});
