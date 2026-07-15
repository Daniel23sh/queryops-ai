import { expect, type Page } from "@playwright/test";

export async function loginAs(page: Page, profile: "Demo Admin" | "Demo Analyst" | "Demo User") {
  await page.goto("/login");
  const loginResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/demo/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: profile }).click();
  const response = await loginResponse;
  expect(response.ok(), await response.text()).toBeTruthy();
  const apiHostname = new URL(response.url()).hostname;
  await expect.poll(async () =>
    (await page.context().cookies()).some((cookie) => cookie.name === "qo_session" && cookie.domain === apiHostname)
  ).toBeTruthy();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "My Dashboard", exact: true })).toBeVisible();
}

export async function openAskData(page: Page) {
  await page.goto("/ask");
  await expect(page).toHaveURL(/\/ask$/);
  await expect(page.getByRole("heading", { name: "Ask Data" })).toBeVisible();
}

export async function runFreeQuestion(page: Page, question: string) {
  await page.getByLabel("Question").fill(question);
  const response = page.waitForResponse((candidate) =>
    candidate.url().endsWith("/api/v1/queries/run") && candidate.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Run", exact: true }).click();
  expect((await response).ok()).toBeTruthy();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible();
}

export async function chooseTemplate(page: Page, title: string) {
  await page.getByRole("button", { name: /Templates|Choose a template/ }).first().click();
  const drawer = page.getByRole("dialog", { name: "Templates" });
  await expect(drawer).toBeVisible();
  const item = drawer.locator("li").filter({ hasText: title });
  await item.getByRole("button", { name: /Use template|Selected/ }).click();
  await expect(drawer).toBeHidden();
  const command = page.getByRole("region", { name: "Ask Data command" });
  await expect.poll(() => command.evaluate((element) =>
    element.contains(document.activeElement)
  )).toBeTruthy();
}
