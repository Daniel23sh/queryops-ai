import { expect, test } from "@playwright/test";

import { loginAs, openAskData, runFreeQuestion } from "./helpers";

test("mobile drawers, result controls, and focus remain contained", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAs(page, "Demo Analyst");
  await openAskData(page);

  const templatesButton = page.getByRole("button", { name: "Templates" }).first();
  await templatesButton.click();
  const templates = page.getByRole("dialog", { name: "Templates" });
  await expect(templates).toBeVisible();
  expect((await templates.boundingBox())?.width).toBe(390);
  await page.keyboard.press("Escape");
  await expect(templates).toBeHidden();
  await expect(templatesButton).toBeFocused();

  await runFreeQuestion(page, "How many open support tickets exist in my department by priority?");
  await expect(page.getByRole("button", { name: "Table" })).toBeVisible();
  await page.getByRole("button", { name: "History" }).click();
  const history = page.getByRole("dialog", { name: "Recent history" });
  await expect(history).toBeVisible();
  expect((await history.boundingBox())?.width).toBe(390);
  await page.keyboard.press("Escape");
  await expect(history).toBeHidden();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth
  );
  expect(hasHorizontalOverflow).toBeFalsy();
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe("");
});
