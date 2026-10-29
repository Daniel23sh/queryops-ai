import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

import { allowExpectedConsoleError, expect, test } from "./fixtures";
import { loginAs } from "./helpers";

const execFileAsync = promisify(execFile);
const apiBase = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
async function fixture(operation: string) {
  const backend = path.resolve(process.cwd(), "../backend");
  const python = process.env.M8_E2E_PYTHON ?? path.join(backend, ".venv/bin/python");
  const result = await execFileAsync(python, ["-m", "scripts.prepare_access_e2e", operation], { cwd: backend, env: process.env });
  return JSON.parse(result.stdout);
}

test.describe("Access & workflow integrity @m8-primary", () => {
  test.describe.configure({ mode: "serial", retries: 0 });
  test.beforeAll(() => {
    expect(process.env.M8_E2E_DATABASE_DISPOSABLE).toBe("1");
    expect(process.env.M8_E2E_DATABASE_URL).toContain("e2e");
  });
  test.afterEach(async () => { await fixture("reset"); });

  test("revocation hides departmental metadata while explicit secondary and global assignments work", async ({ page }) => {
    const ids = await fixture("setup");
    await loginAs(page, "Demo Analyst");
    await page.goto(`/dashboards/${ids.it}`);
    await expect(page.getByRole("heading", { name: "Access integrity it", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Edit", exact: true })).toBeVisible();
    allowExpectedConsoleError(page, (message) => message.text().includes("404") && message.location().url.endsWith(`/api/v1/dashboards/${ids.it}`));
    await fixture("revoke-analyst");
    await page.reload();
    await expect(page.getByRole("heading", { name: "Dashboard not found", exact: true })).toBeVisible();
    await expect(page.getByText("Access integrity it", { exact: true })).toHaveCount(0);
    const detail = await page.request.get(`${apiBase}/api/v1/dashboards/${ids.it}`);
    expect(detail.status()).toBe(404);
    expect(await detail.text()).not.toContain("Access integrity it");
    await fixture("assign-finance");
    await page.goto(`/dashboards/${ids.finance}`);
    await expect(page.getByRole("heading", { name: "Access integrity finance", exact: true })).toBeVisible();
    expect((await page.request.get(`${apiBase}/api/v1/dashboards/${ids.it}`)).status()).toBe(404);
    await fixture("assign-global");
    await page.goto(`/dashboards/${ids.global}`);
    await expect(page.getByRole("heading", { name: "Access integrity global", exact: true })).toBeVisible();
  });

  test("a losing admin decision reloads the winner and the existing requester session gains only approved access", async ({ page, browser }) => {
    const ids = await fixture("setup");
    await fixture("revoke-user");
    await loginAs(page, "Demo User");
    expect((await page.request.get(`${apiBase}/api/v1/dashboards/${ids.sales}`)).status()).toBe(404);
    await page.goto("/profile");
    await page.getByLabel("Requested role").selectOption("analyst");
    await page.getByLabel("Reason", { exact: true }).fill("Controlled scope and workflow review.");
    await page.getByRole("button", { name: "Submit request", exact: true }).click();
    await expect(page.getByText("Role upgrade request submitted.", { exact: true })).toBeVisible();
    const first = await browser.newContext({ baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173" });
    const second = await browser.newContext({ baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173" });
    try {
      const winner = await first.newPage();
      const loser = await second.newPage();
      for (const admin of [winner, loser]) {
        await loginAs(admin, "Demo Admin");
        await admin.goto("/admin/role-requests");
        await admin.getByLabel("Decision reason for Demo User").fill("Reviewed current permissions.");
      }
      await winner.getByRole("button", { name: "Approve role request from Demo User" }).click();
      await expect(winner.getByText("Role request approved.", { exact: true })).toBeVisible();
      await loser.getByRole("button", { name: "Reject role request from Demo User" }).click();
      await expect(loser.getByText("This role request has already been approved.", { exact: true })).toBeVisible();
      await expect(loser.getByRole("alert")).toContainText("The request state changed.");
      await expect(loser.getByText("Role request rejected.", { exact: true })).toHaveCount(0);
      await page.goto(`/dashboards/${ids.sales}`);
      await expect(page.getByRole("heading", { name: "Access integrity sales", exact: true })).toBeVisible();
      expect((await page.request.get(`${apiBase}/api/v1/dashboards/${ids.it}`)).status()).toBe(404);
      const state = await fixture("inspect-user");
      expect(state.role).toBe("analyst");
      expect(state.scopes).toHaveLength(1);
      expect(state.decision_audits).toBe(1);
    } finally {
      await first.close();
      await second.close();
    }
  });
});
