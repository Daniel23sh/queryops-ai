import { allowExpectedConsoleError, expect, test } from "./fixtures";

import { chooseTemplate, loginAs, openAskData, runFreeQuestion } from "./helpers";

test.describe("Ask Data governed flows", () => {
  test("template-only user runs an approved template and reruns it from five-item history", async ({ page }) => {
    await loginAs(page, "Demo User");
    await openAskData(page);

    await expect(page.getByLabel("Question")).toHaveCount(0);
    await chooseTemplate(page, "Open support tickets");
    const runResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/v1/queries/run") && response.request().method() === "POST"
    );
    await page.getByRole("button", { name: "Run", exact: true }).click();
    expect((await runResponse).ok()).toBeTruthy();
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Result details" }).click();
    await expect(page.getByRole("tab", { name: "Summary" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "SQL" })).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "Diagnostics" })).toHaveCount(0);

    await page.getByRole("button", { name: "History" }).click();
    const history = page.getByRole("dialog", { name: "Recent history" });
    await expect(history).toBeVisible();
    expect(await history.locator("ol > li").count()).toBeLessThanOrEqual(5);
    await expect(history.locator("pre, code")).toHaveCount(0);
    await expect(history.getByText("Executed SQL")).toHaveCount(0);
    await expect(history.getByRole("button", { name: "Open result" })).toHaveCount(0);
    const rerunResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/v1/queries/run") && response.request().method() === "POST"
    );
    await history.getByRole("button", { name: "Run again" }).first().click();
    expect((await rerunResponse).ok()).toBeTruthy();
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible();
  });

  test("analyst switches result views, inspects details, saves a visualized card, and sees history", async ({ page }) => {
    const dashboardTitle = `E2E Analyst Dashboard ${Date.now()}`;
    await page.setViewportSize({ width: 1600, height: 1000 });
    await loginAs(page, "Demo Analyst");
    await page.getByRole("button", { name: "New dashboard" }).click();
    await page.getByLabel("Dashboard title").fill(dashboardTitle);
    await page.getByRole("button", { name: "Create dashboard" }).click();
    await expect(page.getByText(`${dashboardTitle} was created.`)).toBeVisible();
    await openAskData(page);

    const question = "How many open support tickets exist in my department by priority?";
    await runFreeQuestion(page, question);
    const visualButton = page.getByRole("button", { name: "Visual" });
    if (await visualButton.count()) {
      await expect(visualButton).toHaveAttribute("aria-pressed", "true");
      await page.getByRole("button", { name: "Table" }).click();
      await expect(page.getByRole("table", { name: "Query results" })).toBeVisible();
      await visualButton.click();
    } else {
      await expect(page.getByRole("button", { name: "Table" })).toHaveAttribute("aria-pressed", "true");
    }

    await page.getByRole("button", { name: "Result details" }).click();
    await page.getByRole("tab", { name: "SQL" }).click();
    await expect(page.getByRole("heading", { name: "Executed SQL" })).toBeVisible();
    await page.getByRole("tab", { name: "Diagnostics" }).click();
    await expect(page.getByRole("region", { name: "Run diagnostics" })).toBeVisible();

    allowExpectedConsoleError(page, (message) =>
      message.text() === "Failed to load resource: the server responded with a status of 403 (Forbidden)" &&
      /\/api\/v1\/query-runs\/[^/]+\/export-csv$/.test(message.location().url)
    );
    const deniedExport = page.waitForResponse((response) =>
      response.url().endsWith("/export-csv") && response.request().method() === "POST"
    );
    await page.getByRole("button", { name: "Export CSV" }).click();
    expect((await deniedExport).status()).toBe(403);
    await expect(page.getByText("This result cannot be exported with your current permissions.")).toBeVisible();

    await page.getByRole("button", { name: "Save to Dashboard" }).click();
    const saveDialog = page.getByRole("dialog", { name: "Save to Dashboard" });
    await saveDialog.getByLabel("Target dashboard").selectOption({ label: dashboardTitle });
    const saveResponse = page.waitForResponse((response) =>
      response.url().includes("/save-card") && response.request().method() === "POST"
    );
    await saveDialog.getByRole("button", { name: "Save", exact: true }).click();
    expect((await saveResponse).ok()).toBeTruthy();
    await expect(saveDialog.getByText(`Saved to ${dashboardTitle}`, { exact: true })).toBeVisible();
    await saveDialog.getByRole("link", { name: "Open dashboard" }).click();
    await expect(page).toHaveURL(/\/dashboards\//);
    await expect(page.getByRole("heading", { name: dashboardTitle })).toBeVisible();
    await expect(page.getByRole("article", { name: `Dashboard card ${question}` })).toBeVisible();

    await openAskData(page);
    await page.getByRole("button", { name: "History" }).click();
    await expect(page.getByRole("dialog", { name: "Recent history" })).toContainText(question);
  });

  test("admin restricted export downloads through the backend", async ({ page }) => {
    await loginAs(page, "Demo Admin");
    await openAskData(page);
    await runFreeQuestion(page, "Show unused paid licenses in my department.");

    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export CSV" }).click();
    const csv = await download;
    expect(csv.suggestedFilename()).toMatch(/\.csv$/);

    await page.goto("/audit");
    await expect(page.getByRole("heading", { name: "Audit", exact: true })).toBeVisible();
    await page.getByLabel("Event type").fill("csv_export");
    await page.getByRole("button", { name: "Apply filters", exact: true }).click();
    const exportRow = page.getByRole("row").filter({ hasText: "Csv Export" });
    await expect(exportRow).toHaveCount(1);
    await exportRow.getByRole("button", { name: "View details", exact: true }).click();
    const auditDetails = page.getByRole("dialog", { name: "Audit event details", exact: true });
    await expect(auditDetails).toContainText("Only fields explicitly returned for your current audit permission are shown.");
    const safeAuditText = await auditDetails.innerText();
    for (const forbidden of ["generated_sql", "executed_sql", "audit_metadata", "permission catalog"]) {
      expect(safeAuditText).not.toContain(forbidden);
    }
  });
});
