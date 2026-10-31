import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

import { expect, test } from "./fixtures";
import { loginAs } from "./helpers";

const execFileAsync = promisify(execFile);
const apiBase = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const endpoints = ["overview", "queries", "security", "actions", "dashboards"];

async function fixture(state: "empty" | "hidden" | "visible"): Promise<Record<string, string>> {
  const backend = path.resolve(process.cwd(), "../backend");
  const python = process.env.M8_E2E_PYTHON ?? path.join(backend, ".venv/bin/python");
  const result = await execFileAsync(python, ["-m", "scripts.prepare_evaluation_e2e", state], { cwd: backend, env: process.env });
  return JSON.parse(result.stdout);
}

test.describe("PostgreSQL scoped Evaluation @m8-primary", () => {
  test.describe.configure({ mode: "serial", retries: 0 });
  test.beforeAll(() => {
    expect(process.env.M8_E2E_DATABASE_DISPOSABLE).toBe("1");
    expect(process.env.M8_E2E_DATABASE_URL).toContain("e2e");
  });
  test.afterEach(async () => { await fixture("empty"); });

  for (const profile of ["Demo Manager", "Demo Analyst", "Demo Admin"] as const) {
    for (const state of ["empty", "hidden", "visible"] as const) {
      test(`${profile} reads ${state} persisted measurements without API mocks`, async ({ page }) => {
        const ids = await fixture(state);
        await loginAs(page, profile);
        const visible = state === "visible" || (state === "hidden" && profile === "Demo Admin");
        const overviewResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/evaluation/overview");
        await page.goto("/evaluation");
        expect((await overviewResponse).status()).toBe(200);
        if (!visible) {
          await expect(page.getByRole("heading", { name: "No visible evaluation run", exact: true })).toBeVisible();
        } else {
          await expect(page.getByRole("heading", { name: "MockLLM quality measurement", exact: true })).toBeVisible();
          await page.getByRole("navigation", { name: "Evaluation sections" }).getByRole("link", { name: "Queries", exact: true }).click();
          const caseId = profile === "Demo Admin" ? "itops-security-001" : profile === "Demo Manager" ? "itops-security-002" : "itops-security-003";
          await expect(page.getByText(caseId, { exact: true })).toBeVisible();
          if (profile === "Demo Manager") await expect(page.getByText("Technical measurement details", { exact: true })).toHaveCount(0);
          else await expect(page.getByText("Technical measurement details", { exact: true })).toBeVisible();
          await page.getByRole("navigation", { name: "Evaluation sections" }).getByRole("link", { name: "Security", exact: true }).click();
          await expect(page.getByText(caseId, { exact: true })).toBeVisible();
        }
        for (const endpoint of endpoints) {
          const response = await page.request.get(`${apiBase}/api/v1/evaluation/${endpoint}`);
          expect(response.status()).toBe(200);
          const text = await response.text();
          const data = (await response.json()).data;
          if (visible) {
            expect(data.run.id).toBe(profile === "Demo Admin" ? ids.hidden : ids.visible);
            if (data.metrics) {
              expect(data.metrics.completed_count).toBe(1);
              expect(data.metrics.selected_count).toBe(1);
            }
          } else {
            expect(data.run).toBeNull();
            if (data.metrics) expect(data.metrics.completed_count).toBe(0);
          }
          expect(text).not.toContain("9001");
          expect(text).not.toContain('"summary"');
          expect(text).not.toContain('"comparison_evidence"');
          if (profile !== "Demo Admin" && ids.hidden) {
            expect(text).not.toContain(ids.hidden);
            const hidden = await page.request.get(`${apiBase}/api/v1/evaluation/${endpoint}?run_id=${ids.hidden}`);
            expect(hidden.status()).toBe(404);
            expect(await hidden.text()).not.toContain(ids.hidden);
          }
        }
      });
    }
  }
});
