import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import type { Dialog, Page } from "@playwright/test";

import { allowExpectedConsoleError, expect, test } from "./fixtures";
import { loginAs } from "./helpers";

const execFileAsync = promisify(execFile);
const apiBase = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
type Item = { x: number; y: number; w: number; h: number };
type Card = { id: string; title: string; layout: { desktop: Item; tablet: Item; mobile: Item } };
type Detail = { layout_version: number; cards: Card[] };
type Fixture = { dashboard_id: string; query_runs: Record<string, string> };
const emptyMapping = { category_column: null, value_columns: [], series_column: null, label_column: null, target_column: null };

async function prepare(page: Page) {
  const backend = path.resolve(process.cwd(), "../backend");
  const python = process.env.M8_E2E_PYTHON ?? path.join(backend, ".venv/bin/python");
  const result = await execFileAsync(python, ["-m", "scripts.prepare_dashboard_integrity_e2e"], { cwd: backend, env: process.env });
  const ids = JSON.parse(result.stdout) as Fixture;
  const signedIn = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/demo/login");
  await loginAs(page, "Demo Analyst");
  const csrf = (await (await signedIn).json()).data.csrf_token as string;
  return { ids, csrf };
}

async function addCard(page: Page, ids: Fixture, csrf: string, source: string, type: string) {
  const saved = await page.request.post(`${apiBase}/api/v1/query-runs/${ids.query_runs[source]}/save-card`, {
    headers: { "X-CSRF-Token": csrf }, data: { dashboard_id: ids.dashboard_id, title: `Integrity ${source}` }
  });
  expect(saved.status(), await saved.text()).toBe(201);
  const id = (await saved.json()).data.id as string;
  const configured = await page.request.patch(`${apiBase}/api/v1/cards/${id}`, {
    headers: { "X-CSRF-Token": csrf }, data: { visualization: { mode: "auto", type, recommended_type: type, mapping: emptyMapping } }
  });
  expect(configured.ok(), await configured.text()).toBeTruthy();
  return id;
}

async function detail(page: Page, id: string): Promise<Detail> {
  const response = await page.request.get(`${apiBase}/api/v1/dashboards/${id}`);
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()).data;
}

async function openFromHome(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Preview dashboard Dashboard integrity checks", exact: true }).click();
  await page.getByRole("button", { name: "Open dashboard", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dashboard integrity checks", exact: true })).toBeVisible();
}

async function cardAction(page: Page, title: string, action: string) {
  await page.getByRole("button", { name: `Card actions for ${title}`, exact: true }).click();
  await page.getByRole("menuitem", { name: action, exact: true }).click();
}

async function resize(page: Page, title: string, size: string) {
  await cardAction(page, title, "Resize");
  await page.getByRole("dialog", { name: `Resize ${title}` }).getByRole("button", { name: size, exact: true }).click();
}

async function save(page: Page) {
  const saving = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/layout") && response.request().method() === "PATCH");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  const response = await saving;
  expect(response.ok(), await response.text()).toBeTruthy();
  await expect(page.getByRole("button", { name: "Edit", exact: true })).toHaveAttribute("aria-pressed", "false");
  return response.request().postDataJSON() as { expected_layout_version: number; items: Array<{ card_id: string; desktop: Item; tablet: Item; mobile: Item }> };
}

test.describe("Dashboard editing and values @m8-primary", () => {
  test.describe.configure({ mode: "serial", retries: 0 });
  test.beforeAll(() => {
    expect(process.env.M8_E2E_DATABASE_DISPOSABLE).toBe("1");
    expect(process.env.M8_E2E_DATABASE_URL).toContain("e2e");
  });

  test("desktop draft composes metadata, visualization, membership, retries, navigation and stale versions", async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 1600, height: 1000 });
    const { ids, csrf } = await prepare(page);
    const firstId = await addCard(page, ids, csrf, "chart", "bar");
    await openFromHome(page);
    await expect(page.locator('[data-visualization="bar"]')).toBeVisible();
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await resize(page, "Integrity chart", "8 × 3");
    await page.getByRole("button", { name: "Drag Integrity chart", exact: true }).press("ArrowRight");
    await page.getByRole("button", { name: "Dashboard actions", exact: true }).click();
    await page.getByRole("menuitem", { name: "Rename dashboard", exact: true }).click();
    await page.getByLabel("Title", { exact: true }).fill("Renamed integrity");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Renamed integrity", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeEnabled();
    await cardAction(page, "Integrity chart", "Rename");
    await page.getByLabel("Title", { exact: true }).fill("Renamed chart");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("article", { name: "Dashboard card Renamed chart", exact: true })).toBeVisible();
    await cardAction(page, "Renamed chart", "Change visualization");
    await page.getByRole("radio", { name: "Table", exact: true }).check();
    await page.getByRole("button", { name: "Save visualization", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await cardAction(page, "Renamed chart", "Duplicate");
    await expect(page.getByRole("article", { name: "Dashboard card Renamed chart Copy", exact: true })).toBeVisible();
    await cardAction(page, "Renamed chart Copy", "Remove");
    await page.getByRole("button", { name: "Remove card", exact: true }).click();
    await expect(page.getByRole("article", { name: "Dashboard card Renamed chart Copy", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Add Card", exact: true }).click();
    await page.getByRole("tab", { name: "Recent results", exact: true }).click();
    const source = page.getByRole("dialog", { name: "Add Card", exact: true }).getByRole("article").filter({ has: page.getByRole("heading", { name: "Integrity total_licenses", exact: true }) });
    await source.getByRole("button", { name: "Add result", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Reload latest layout", exact: true })).toHaveCount(0);
    const beforeSave = await detail(page, ids.dashboard_id);
    const payload = await save(page);
    expect(payload.expected_layout_version).toBe(beforeSave.layout_version);
    expect(payload.items.find((item) => item.card_id === firstId)?.desktop).toMatchObject({ x: 4, w: 8, h: 3 });
    const persisted = await detail(page, ids.dashboard_id);
    expect(persisted.cards.find((card) => card.id === firstId)?.layout.desktop).toMatchObject({ x: 4, w: 8, h: 3 });
    const kpi = page.getByRole("article", { name: "Dashboard card Integrity total_licenses", exact: true });
    await expect(kpi.locator(".dashboard-viz-kpi strong")).toHaveText("42");

    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await resize(page, "Renamed chart", "4 × 2");
    allowExpectedConsoleError(page, (message) => message.text().includes("net::ERR_INTERNET_DISCONNECTED"));
    await page.context().setOffline(true);
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("Dashboard changes could not be saved");
    await page.context().setOffline(false);
    const retried = await save(page);
    expect(retried.expected_layout_version).toBe(persisted.layout_version);
    expect(retried.items.find((item) => item.card_id === firstId)?.desktop).toMatchObject({ w: 4, h: 2 });

    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await resize(page, "Renamed chart", "8 × 3");
    let hashPrompts = 0;
    const dismissHashPrompt = (dialog: Dialog) => { hashPrompts += 1; void dialog.dismiss(); };
    page.on("dialog", dismissHashPrompt);
    const skip = page.getByRole("link", { name: "Skip to main content", exact: true });
    await skip.focus();
    await skip.click();
    await expect(page).toHaveURL(/#main-content$/);
    await expect(page.getByRole("main")).toBeFocused();
    await page.evaluate(() => window.history.back());
    await expect(page).toHaveURL(new RegExp(`/dashboards/${ids.dashboard_id}$`));
    page.removeListener("dialog", dismissHashPrompt);
    expect(hashPrompts).toBe(0);
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.getByRole("link", { name: "Back to My Dashboard", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/dashboards/${ids.dashboard_id}$`));
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.evaluate(() => window.history.back());
    await expect(page).toHaveURL(new RegExp(`/dashboards/${ids.dashboard_id}$`));
    await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeEnabled();

    const external = await detail(page, ids.dashboard_id);
    const changed = await page.request.patch(`${apiBase}/api/v1/dashboards/${ids.dashboard_id}/layout`, {
      headers: { "X-CSRF-Token": csrf },
      data: { expected_layout_version: external.layout_version, items: external.cards.map((card) => ({
        card_id: card.id, desktop: card.layout.desktop, tablet: card.layout.tablet, mobile: card.layout.mobile
      })) }
    });
    expect(changed.ok(), await changed.text()).toBeTruthy();
    allowExpectedConsoleError(page, (message) => message.location().url.endsWith("/layout") && message.text().includes("409"));
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(page.getByRole("button", { name: "Reload latest layout", exact: true })).toBeVisible();
    await expect(page.getByText("Unsaved layout changes", { exact: true })).toBeVisible();
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.getByRole("button", { name: "Reload latest layout", exact: true }).click();
    await expect(page.getByText("Unsaved layout changes", { exact: true })).toBeVisible();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Reload latest layout", exact: true }).click();
    await expect(page.getByText("No unsaved layout changes", { exact: true })).toBeVisible();
    await resize(page, "Renamed chart", "8 × 3");
    page.once("dialog", (dialog) => dialog.accept());
    await page.evaluate(() => window.history.back());
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "My Dashboard", exact: true })).toBeVisible();
  });

  test("numeric aliases render actual KPI values, bounded gauges and auto/manual charts", async ({ page }) => {
    const { ids, csrf } = await prepare(page);
    for (const source of ["total_licenses", "max_cost", "target_count"]) await addCard(page, ids, csrf, source, "kpi");
    await addCard(page, ids, csrf, "gauge", "semicircle_gauge");
    await addCard(page, ids, csrf, "chart", "bar");
    await page.goto(`/dashboards/${ids.dashboard_id}`);
    for (const source of ["total_licenses", "max_cost", "target_count"]) {
      const card = page.getByRole("article", { name: `Dashboard card Integrity ${source}`, exact: true });
      await expect(card.locator(".dashboard-viz-kpi strong")).toHaveText("42");
      await expect(card.getByText("—", { exact: true })).toHaveCount(0);
    }
    const gauge = page.getByRole("article", { name: "Dashboard card Integrity gauge", exact: true });
    await expect(gauge.locator(".dashboard-viz-gauge strong")).toHaveText("42");
    await expect(gauge.getByText("of 903", { exact: true })).toBeVisible();
    const chart = page.getByRole("article", { name: "Dashboard card Integrity chart", exact: true });
    await expect(chart.locator('[data-visualization="bar"]')).toBeVisible();
    await expect(chart.getByText(/Primary measure: Total Cost/)).toHaveCount(1);
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await cardAction(page, "Integrity chart", "Change visualization");
    await page.getByRole("radio", { name: "Table", exact: true }).check();
    await page.getByRole("button", { name: "Save visualization", exact: true }).click();
    await expect(chart.getByRole("table")).toBeVisible();
    await page.reload();
    await expect(chart.getByRole("table")).toBeVisible();
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await cardAction(page, "Integrity chart", "Change visualization");
    await page.getByRole("button", { name: "Reset to recommended", exact: true }).click();
    await expect(chart.locator('[data-visualization="bar"]')).toBeVisible();
    await resize(page, "Integrity total_licenses", "6 × 1");
    await cardAction(page, "Integrity total_licenses", "Change visualization");
    await page.getByRole("radio", { name: "Table", exact: true }).check();
    await page.getByRole("button", { name: "Save visualization", exact: true }).click();
    await expect(page.getByRole("button", { name: "Reload latest layout", exact: true })).toBeVisible();
    await expect(page.getByText("Unsaved layout changes", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeDisabled();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Reload latest layout", exact: true }).click();
    await expect(page.getByText("No unsaved layout changes", { exact: true })).toBeVisible();
    await expect(page.getByRole("article", { name: "Dashboard card Integrity total_licenses", exact: true }).getByRole("cell", { name: "42", exact: true })).toBeVisible();
  });

  test("mobile movement and resize survive rename, duplicate and remove; cancel restores the server layout", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const { ids, csrf } = await prepare(page);
    const firstId = await addCard(page, ids, csrf, "total_licenses", "kpi");
    await addCard(page, ids, csrf, "max_cost", "kpi");
    await openFromHome(page);
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    const first = page.getByRole("article", { name: "Dashboard card Integrity total_licenses", exact: true });
    await first.getByRole("button", { name: "Move down", exact: true }).click();
    await first.getByRole("button", { name: "Size preset", exact: true }).click();
    await page.getByRole("button", { name: "Height 2", exact: true }).click();
    await cardAction(page, "Integrity total_licenses", "Rename");
    await page.getByLabel("Title", { exact: true }).fill("Mobile total");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("article", { name: "Dashboard card Mobile total", exact: true })).toBeVisible();
    await cardAction(page, "Mobile total", "Duplicate");
    await expect(page.getByRole("article", { name: "Dashboard card Mobile total Copy", exact: true })).toBeVisible();
    await cardAction(page, "Mobile total Copy", "Remove");
    await page.getByRole("button", { name: "Remove card", exact: true }).click();
    await expect(page.getByRole("article", { name: "Dashboard card Mobile total Copy", exact: true })).toHaveCount(0);
    const payload = await save(page);
    expect(payload.items.find((item) => item.card_id === firstId)?.mobile).toMatchObject({ x: 0, y: 1, w: 1, h: 2 });
    const saved = await detail(page, ids.dashboard_id);
    expect(saved.cards.find((card) => card.id === firstId)?.layout.mobile).toMatchObject({ y: 1, h: 2 });
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await page.getByRole("article", { name: "Dashboard card Mobile total", exact: true }).getByRole("button", { name: "Move up", exact: true }).click();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeDisabled();
    expect(await detail(page, ids.dashboard_id)).toEqual(saved);
  });
});
