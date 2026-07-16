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

export async function createDashboardWithSavedCard(
  page: Page,
  dashboardTitle: string,
  question: string
) {
  await loginAs(page, "Demo Analyst");
  await page.getByRole("button", { name: "New dashboard" }).click();
  await page.getByLabel("Dashboard title").fill(dashboardTitle);
  await page.getByRole("button", { name: "Create dashboard" }).click();
  await expect(page.getByText(`${dashboardTitle} was created.`)).toBeVisible();

  await openAskData(page);
  await runFreeQuestion(page, question);
  await saveCurrentResultToDashboard(page, dashboardTitle, true);
  await expect(page).toHaveURL(/\/dashboards\//);
  await expect(page.getByRole("heading", { name: dashboardTitle })).toBeVisible();
  await expect(page.getByRole("article", { name: `Dashboard card ${question}` })).toBeVisible();
}

export async function saveCurrentResultToDashboard(
  page: Page,
  dashboardTitle: string,
  openDashboard = false
) {
  await page.getByRole("button", { name: "Save to Dashboard" }).click();
  const saveDialog = page.getByRole("dialog", { name: "Save to Dashboard" });
  await saveDialog.getByLabel("Target dashboard").selectOption({ label: dashboardTitle });
  const saveResponse = page.waitForResponse((response) =>
    response.url().includes("/save-card") && response.request().method() === "POST"
  );
  await saveDialog.getByRole("button", { name: "Save", exact: true }).click();
  expect((await saveResponse).ok()).toBeTruthy();
  await expect(saveDialog.getByText(`Saved to ${dashboardTitle}`, { exact: true })).toBeVisible();
  if (openDashboard) {
    await saveDialog.getByRole("link", { name: "Open dashboard" }).click();
  } else {
    await saveDialog.getByRole("button", { name: "Done" }).click();
  }
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
