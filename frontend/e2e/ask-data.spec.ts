import { expect, test } from "@playwright/test";

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
    await page.setViewportSize({ width: 1600, height: 1000 });
    await loginAs(page, "Demo Analyst");
    await page.getByRole("button", { name: "New dashboard" }).click();
    await page.getByLabel("Dashboard title").fill("E2E Analyst Dashboard");
    await page.getByRole("button", { name: "Create dashboard" }).click();
    await expect(page.getByText("E2E Analyst Dashboard was created.")).toBeVisible();
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

    await page.getByRole("button", { name: "Export CSV" }).click();
    await expect(page.getByText("This result cannot be exported with your current permissions.")).toBeVisible();

    await page.getByRole("button", { name: "Save to Dashboard" }).click();
    const saveDialog = page.getByRole("dialog", { name: "Save to Dashboard" });
    await saveDialog.getByLabel("Target dashboard").selectOption({ label: "E2E Analyst Dashboard" });
    const saveResponse = page.waitForResponse((response) =>
      response.url().includes("/save-card") && response.request().method() === "POST"
    );
    await saveDialog.getByRole("button", { name: "Save", exact: true }).click();
    expect((await saveResponse).ok()).toBeTruthy();
    await expect(saveDialog.getByText("Saved to E2E Analyst Dashboard", { exact: true })).toBeVisible();
    await saveDialog.getByRole("link", { name: "Open dashboard" }).click();
    await expect(page).toHaveURL(/\/dashboards\//);
    await expect(page.getByRole("heading", { name: "E2E Analyst Dashboard" })).toBeVisible();
    await expect(page.getByRole("article", { name: `Dashboard card ${question}` })).toBeVisible();

    await page.getByRole("button", { name: "Edit", exact: true }).click();
    const dragHandle = page.getByRole("button", { name: `Drag ${question}` });
    const gridItem = dragHandle.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' react-grid-item ')]").first();
    await expect(gridItem).toHaveClass(/react-draggable/);
    const beforeDragStyle = await gridItem.getAttribute("style");
    const handleBox = await dragHandle.boundingBox();
    expect(handleBox).not.toBeNull();
    if (handleBox) {
      const handleCenter = {
        x: handleBox.x + handleBox.width / 2,
        y: handleBox.y + handleBox.height / 2
      };
      expect(await page.evaluate(({ x, y }) =>
        document.elementFromPoint(x, y)?.closest(".dashboard-card-drag-handle") !== null,
      handleCenter)).toBeTruthy();
      await page.mouse.move(handleCenter.x, handleCenter.y);
      await page.mouse.down();
      await page.waitForTimeout(100);
      await page.mouse.move(handleCenter.x + 300, handleCenter.y, { steps: 8 });
      await page.waitForTimeout(100);
      await page.mouse.up();
    }
    await expect(gridItem).not.toHaveAttribute("style", beforeDragStyle ?? "");
    const saveLayoutButton = page.getByRole("button", { name: "Save changes" });
    await expect(saveLayoutButton).toBeEnabled();
    const layoutResponse = page.waitForResponse((response) =>
      response.url().includes("/layout") && response.request().method() === "PATCH"
    );
    await saveLayoutButton.click();
    expect((await layoutResponse).ok()).toBeTruthy();

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
  });
});
