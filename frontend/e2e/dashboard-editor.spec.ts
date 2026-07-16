import type { Locator, Page, Response } from "@playwright/test";

import { expect, test } from "./fixtures";
import {
  createDashboardWithSavedCard,
  loginAs,
  openAskData,
  runFreeQuestion,
  saveCurrentResultToDashboard
} from "./helpers";

const question = "Show high severity security events in my department.";
const chartQuestion = "How many open support tickets exist in my department by priority?";
const GRID_MARGIN = 14;

test("dashboard cards use native handle-only drag and persist desktop and tablet layouts", async ({ page }) => {
  const dashboardTitle = `E2E Drag Dashboard ${Date.now()}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  await createDashboardWithSavedCard(page, dashboardTitle, question);
  await expect(page.getByText("Status list", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const editor = page.locator('.dashboard-editor-grid[data-editing="true"]');
  await expect(editor).toHaveAttribute("data-breakpoint", "desktop");
  await waitForStatusListResults(page, question);
  await settleGridLayout(page);

  const handle = page.getByRole("button", { name: `Drag ${question}` });
  const gridItem = handle.locator(
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' react-grid-item ')]"
  );
  const saveButton = page.getByRole("button", { name: "Save changes" });
  await expect(gridItem).toHaveClass(/react-draggable/);
  await expect(saveButton).toBeDisabled();

  await assertNonHandleDoesNotDrag(
    page,
    gridItem,
    page.getByRole("heading", { name: question, exact: true }),
    saveButton
  );
  await assertNonHandleDoesNotDrag(
    page,
    gridItem,
    page.getByRole("button", { name: `Card actions for ${question}` }),
    saveButton
  );
  await assertSubCellHandleMoveDoesNotDirty(page, handle, gridItem, saveButton);

  const desktopBeforeStyle = await gridItem.getAttribute("style");
  await dragWhileActive(page, handle, gridItem, 300, 0);
  await expect(saveButton).toBeEnabled();

  const resizeHandle = gridItem.locator(".react-resizable-handle-se");
  const widthBeforeResize = (await gridItem.boundingBox())?.width;
  expect(widthBeforeResize).toBeDefined();
  await resizeWhileActive(page, resizeHandle, gridItem, 260, 0);
  const widthAfterResize = (await gridItem.boundingBox())?.width;
  expect(widthAfterResize).toBeGreaterThan(widthBeforeResize ?? 0);

  const desktopStyle = await gridItem.getAttribute("style");
  expect(desktopStyle).not.toBe(desktopBeforeStyle);
  const desktopPayload = await saveAndReadLayoutPayload(page, saveButton);
  expect(desktopPayload.items).toHaveLength(1);
  const desktopItem = desktopPayload.items[0];
  expect(desktopItem.card_id).toBeTruthy();
  expect(desktopItem.desktop.x).toBeGreaterThan(0);
  expect(desktopItem.desktop.w).toBeGreaterThan(4);
  expect(desktopItem.tablet.x).toBe(0);
  expect(desktopItem.mobile).toMatchObject({ x: 0, w: 1 });

  await page.reload();
  const reloadedDesktop = await readCurrentDashboardDetail(page);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor).toHaveAttribute("data-breakpoint", "desktop");
  await waitForStatusListResults(page, question);
  await settleGridLayout(page);
  expect(reloadedDesktop.data.cards.find((card) => card.id === desktopItem.card_id)?.layout.desktop)
    .toEqual(desktopItem.desktop);

  await page.setViewportSize({ width: 1200, height: 900 });
  await page.reload();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor).toHaveAttribute("data-breakpoint", "tablet");
  await waitForStatusListResults(page, question);
  await settleGridLayout(page);
  await expect(saveButton).toBeDisabled();
  const tabletBeforeStyle = await gridItem.getAttribute("style");
  await dragWhileActive(page, handle, gridItem, 260, 0);
  const tabletStyle = await gridItem.getAttribute("style");
  expect(tabletStyle).not.toBe(tabletBeforeStyle);

  const tabletPayload = await saveAndReadLayoutPayload(page, saveButton);
  expect(tabletPayload.items).toHaveLength(1);
  const tabletItem = tabletPayload.items[0];
  expect(tabletItem.desktop).toEqual(desktopItem.desktop);
  expect(tabletItem.tablet.x).toBeGreaterThan(0);
  expect(tabletItem.mobile).toEqual(desktopItem.mobile);

  await page.reload();
  const reloadedTablet = await readCurrentDashboardDetail(page);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor).toHaveAttribute("data-breakpoint", "tablet");
  await waitForStatusListResults(page, question);
  await settleGridLayout(page);
  expect(reloadedTablet.data.cards.find((card) => card.id === tabletItem.card_id)?.layout.tablet)
    .toEqual(tabletItem.tablet);
});

test("off-preset resize snaps immediately and remains stable when another card moves", async ({ page }) => {
  test.setTimeout(90_000);
  const dashboardTitle = `E2E Resize Dashboard ${Date.now()}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  await createDashboardWithSavedCard(page, dashboardTitle, question);
  await page.getByRole("button", { name: "Edit", exact: true }).click();

  const editor = page.locator('.dashboard-editor-grid[data-editing="true"]');
  const saveButton = page.getByRole("button", { name: "Save changes" });
  await expect(editor).toHaveAttribute("data-breakpoint", "desktop");

  const duplicateResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith("/duplicate") &&
    response.url().includes("/api/v1/cards/") &&
    response.request().method() === "POST"
  );
  const detailResponsePromise = page.waitForResponse((response) =>
    /^\/api\/v1\/dashboards\/[^/]+$/.test(new URL(response.url()).pathname) &&
    response.request().method() === "GET"
  );
  await page.getByRole("button", { name: `Card actions for ${question}` }).click();
  await page.getByRole("menuitem", { name: "Duplicate", exact: true }).click();
  const duplicateResponse = await duplicateResponsePromise;
  expect(duplicateResponse.ok()).toBeTruthy();
  const duplicatePayload = await duplicateResponse.json() as CardMutationEnvelope;
  const duplicateCard = duplicatePayload.data.card;
  const detailResponse = await detailResponsePromise;
  expect(detailResponse.ok()).toBeTruthy();
  const detailPayload = await detailResponse.json() as DashboardDetailEnvelope;
  const initialLayouts = new Map(
    detailPayload.data.cards.map((card) => [card.id, card.layout])
  );
  await expect(page.getByRole("button", { name: `Card actions for ${duplicateCard.title}` })).toBeVisible();
  await expect(saveButton).toBeDisabled();

  const firstHandle = page.getByRole("button", { name: `Drag ${question}`, exact: true });
  const secondHandle = page.getByRole("button", { name: `Drag ${duplicateCard.title}`, exact: true });
  const firstItem = gridItemFor(firstHandle);
  const secondItem = gridItemFor(secondHandle);
  await waitForStatusListResults(page, question, duplicateCard.title);
  await settleGridLayout(page);
  const firstInitialWidth = await itemWidth(firstItem);
  const desktopStep = (firstInitialWidth + GRID_MARGIN) / 4;

  await resizeWhileActive(
    page,
    firstItem.locator(".react-resizable-handle-se"),
    firstItem,
    desktopStep * 1.05,
    0,
    () => expect.poll(() => itemWidth(firstItem)).toBeGreaterThan(firstInitialWidth + 10)
  );
  await expectRelativeGridWidth(firstItem, 6, secondItem, 4);
  await expect(editor.locator('[aria-live="polite"]')).toHaveText(
    `${question} resized to 6 by 2. Save changes to persist.`
  );
  await expect(saveButton).toBeEnabled();

  const firstSnappedWidth = await itemWidth(firstItem);
  const secondWidth = await itemWidth(secondItem);
  const secondStep = (secondWidth + GRID_MARGIN) / 4;
  await dragWhileActive(page, secondHandle, secondItem, secondStep * 2, 0);
  await expectItemSize(firstItem, firstSnappedWidth, undefined);

  const firstPayload = await saveAndReadLayoutPayload(page, saveButton);
  expect(firstPayload.items).toHaveLength(2);
  const firstCardId = detailPayload.data.cards.find((card) => card.title === question)?.id;
  expect(firstCardId).toBeTruthy();
  const resizedItem = firstPayload.items.find((item) => item.card_id === firstCardId);
  expect(resizedItem?.desktop).toMatchObject({ w: 6, h: 2 });
  for (const item of firstPayload.items) {
    expectStatusListSize(item.desktop, "desktop");
    expect(item.tablet).toEqual(initialLayouts.get(item.card_id)?.tablet);
    expect(item.mobile).toEqual(initialLayouts.get(item.card_id)?.mobile);
  }
  expectNoOverlaps(firstPayload.items, "desktop");

  await page.reload();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor).toHaveAttribute("data-breakpoint", "desktop");
  await waitForStatusListResults(page, question, duplicateCard.title);
  await settleGridLayout(page);
  await expectRelativeGridWidth(firstItem, 6, secondItem, 4);

  const widthAtSixColumns = await itemWidth(firstItem);
  const stepAtSixColumns = (widthAtSixColumns + GRID_MARGIN) / 6;
  await resizeWhileActive(
    page,
    firstItem.locator(".react-resizable-handle-se"),
    firstItem,
    stepAtSixColumns * 1.05,
    0,
    () => expect.poll(() => itemWidth(firstItem)).toBeGreaterThan(widthAtSixColumns + 10)
  );
  await expectRelativeGridWidth(firstItem, 8, secondItem, 4);
  const secondPayload = await saveAndReadLayoutPayload(page, saveButton);
  expect(secondPayload.items.find((item) => item.card_id === firstCardId)?.desktop)
    .toMatchObject({ w: 8, h: 2 });

  await page.reload();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor).toHaveAttribute("data-breakpoint", "desktop");
  await waitForStatusListResults(page, question, duplicateCard.title);
  await settleGridLayout(page);
  await expectRelativeGridWidth(firstItem, 8, secondItem, 4);
  const widthAtEightColumns = await itemWidth(firstItem);
  const stepAtEightColumns = (widthAtEightColumns + GRID_MARGIN) / 8;
  await resizeWhileActive(
    page,
    firstItem.locator(".react-resizable-handle-se"),
    firstItem,
    stepAtEightColumns * 1.05,
    0,
    () => expect.poll(() => itemWidth(firstItem)).toBeGreaterThan(widthAtEightColumns + 10)
  );
  await expectRelativeGridWidth(firstItem, 8, secondItem, 4);
  await expect(saveButton).toBeDisabled();

  await page.setViewportSize({ width: 1200, height: 900 });
  await page.reload();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor).toHaveAttribute("data-breakpoint", "tablet");
  await waitForStatusListResults(page, question, duplicateCard.title);
  await settleGridLayout(page);
  await expectRelativeGridWidth(firstItem, 4, secondItem, 4);
  const tabletWidth = await itemWidth(firstItem);
  const tabletHeight = await itemHeight(firstItem);
  const tabletRowStep = (tabletHeight + GRID_MARGIN) / 2;
  await resizeWhileActive(
    page,
    firstItem.locator(".react-resizable-handle-se"),
    firstItem,
    0,
    -tabletRowStep * 1.05,
    () => expect.poll(() => itemHeight(firstItem)).toBeLessThan(tabletHeight - 10)
  );
  await expectItemSize(firstItem, tabletWidth, tabletHeight);
  await expect(saveButton).toBeDisabled();

  const tabletSecondWidth = await itemWidth(secondItem);
  const tabletColumnStep = (tabletSecondWidth + GRID_MARGIN) / 4;
  await dragWhileActive(page, secondHandle, secondItem, tabletColumnStep * 2, 0);
  await expectItemSize(firstItem, tabletWidth, tabletHeight);
  await expect(saveButton).toBeEnabled();
});

test("expanded presets keep compact tables and charts usable across breakpoints", async ({ page }) => {
  test.setTimeout(120_000);
  const dashboardTitle = `E2E Expanded Presets ${Date.now()}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  await loginAs(page, "Demo Analyst");
  await page.getByRole("button", { name: "New dashboard" }).click();
  await page.getByLabel("Dashboard title").fill(dashboardTitle);
  await page.getByRole("button", { name: "Create dashboard" }).click();
  await expect(page.getByText(`${dashboardTitle} was created.`)).toBeVisible();

  await openAskData(page);
  await runFreeQuestion(page, question);
  await saveCurrentResultToDashboard(page, dashboardTitle);
  await runFreeQuestion(page, chartQuestion);
  await saveCurrentResultToDashboard(page, dashboardTitle, true);

  await expect(page.getByRole("article", { name: `Dashboard card ${question}` })).toBeVisible();
  await expect(page.getByRole("article", { name: `Dashboard card ${chartQuestion}` })).toBeVisible();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const editor = page.locator('.dashboard-editor-grid[data-editing="true"]');
  const saveButton = page.getByRole("button", { name: "Save changes" });
  await expect(editor).toHaveAttribute("data-breakpoint", "desktop");

  const visualizationResponse = page.waitForResponse((response) =>
    /\/api\/v1\/cards\/[^/]+$/.test(new URL(response.url()).pathname) &&
    response.request().method() === "PATCH"
  );
  await page.getByRole("button", { name: `Card actions for ${question}` }).click();
  await page.getByRole("menuitem", { name: "Change visualization", exact: true }).click();
  const visualizationDialog = page.getByRole("dialog", { name: `Visualization for ${question}` });
  await visualizationDialog.getByRole("radio", { name: "Table", exact: true }).click();
  await visualizationDialog.getByRole("button", { name: "Save visualization" }).click();
  expect((await visualizationResponse).ok()).toBeTruthy();
  await expect(visualizationDialog).toBeHidden();

  const tableCard = page.getByRole("article", { name: `Dashboard card ${question}` });
  const chartCard = page.getByRole("article", { name: `Dashboard card ${chartQuestion}` });
  await expect(tableCard.getByRole("table", { name: "Dashboard card results" })).toBeVisible();
  await expect(chartCard.locator(".recharts-responsive-container")).toBeVisible();

  await selectResizePreset(page, question, "12 × 3");
  const standardTablePayload = await saveAndReadLayoutPayload(page, saveButton);
  expect(
    standardTablePayload.items.some((item) => item.desktop.w === 12 && item.desktop.h === 3),
    JSON.stringify(standardTablePayload.items)
  )
    .toBeTruthy();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor).toHaveAttribute("data-breakpoint", "desktop");
  await expect(tableCard.getByRole("table", { name: "Dashboard card results" })).toBeVisible();
  await expect(chartCard.locator(".recharts-responsive-container")).toBeVisible();

  const tableItem = gridItemFor(page.getByRole("button", { name: `Drag ${question}`, exact: true }));
  const chartItem = gridItemFor(page.getByRole("button", { name: `Drag ${chartQuestion}`, exact: true }));
  await settleGridLayout(page);
  await expect.poll(async () => {
    const editorBox = await editor.boundingBox();
    return Math.abs((await itemWidth(tableItem)) - ((editorBox?.width ?? 0) - GRID_MARGIN * 2));
  }).toBeLessThan(2);
  const standardTableHeight = await itemHeight(tableItem);
  const rowStep = (standardTableHeight + GRID_MARGIN) / 3;
  const compactTableHeight = rowStep * 2 - GRID_MARGIN;
  await resizeWhileActive(
    page,
    tableItem.locator(".react-resizable-handle-se"),
    tableItem,
    0,
    -rowStep * 1.05,
    () => expect.poll(() => itemHeight(tableItem)).toBeLessThan(standardTableHeight - 10)
  );
  await expectItemSize(tableItem, undefined, compactTableHeight);
  await expect(editor.locator('[aria-live="polite"]')).toHaveText(
    `${question} resized to 12 by 2. Save changes to persist.`
  );
  expect(await tableCard.getByRole("row").count()).toBeGreaterThanOrEqual(4);
  await expectNoCardVerticalOverflow(tableCard);

  const compactTablePayload = await saveAndReadLayoutPayload(page, saveButton);
  expect(compactTablePayload.items).toHaveLength(2);
  expect(compactTablePayload.items.some((item) => item.desktop.w === 12 && item.desktop.h === 2))
    .toBeTruthy();
  expectNoOverlaps(compactTablePayload.items, "desktop");

  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await selectResizePreset(page, question, "4 × 2");
  await selectResizePreset(page, chartQuestion, "4 × 2");
  const compactCardsPayload = await saveAndReadLayoutPayload(page, saveButton);
  expect(compactCardsPayload.items.filter((item) => item.desktop.w === 4 && item.desktop.h === 2))
    .toHaveLength(2);
  expectNoOverlaps(compactCardsPayload.items, "desktop");
  await expect(tableCard.locator(".dashboard-viz-table")).toHaveCSS("overflow-x", "auto");
  await expect(chartCard.locator(".recharts-responsive-container")).toBeVisible();
  await expect(chartCard.locator(".recharts-xAxis")).toBeVisible();
  await expect(chartCard.locator(".recharts-yAxis")).toBeVisible();
  await expectNoCardVerticalOverflow(chartCard);

  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await selectResizePreset(page, chartQuestion, "12 × 4");
  const largeChartPayload = await saveAndReadLayoutPayload(page, saveButton);
  expect(largeChartPayload.items.some((item) => item.desktop.w === 12 && item.desktop.h === 4))
    .toBeTruthy();

  await page.setViewportSize({ width: 1200, height: 900 });
  await page.reload();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor).toHaveAttribute("data-breakpoint", "tablet");
  await selectResizePreset(page, question, "3 × 2");
  await selectResizePreset(page, chartQuestion, "3 × 2");
  const tabletPayload = await saveAndReadLayoutPayload(page, saveButton);
  expect(tabletPayload.items.filter((item) => item.tablet.w === 3 && item.tablet.h === 2))
    .toHaveLength(2);
  expectNoOverlaps(tabletPayload.items, "tablet");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(editor).toHaveAttribute("data-breakpoint", "mobile");
  await expect(tableCard.getByRole("button", { name: `Drag ${question}` })).toHaveCount(0);
  await tableCard.getByRole("button", { name: "Size preset" }).click();
  const mobileResizeDialog = page.getByRole("dialog", { name: `Resize ${question}` });
  await expect(mobileResizeDialog.getByRole("button", { name: "Height 2" })).toBeVisible();
  await expect(mobileResizeDialog.getByRole("button", { name: "Height 3" })).toBeVisible();
  await expect(mobileResizeDialog.getByRole("button", { name: "Height 4" })).toBeVisible();
});

async function assertNonHandleDoesNotDrag(
  page: Page,
  gridItem: Locator,
  target: Locator,
  saveButton: Locator
) {
  const beforeStyle = await gridItem.getAttribute("style");
  const box = await target.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  try {
    await page.mouse.move(center.x + 80, center.y + 20, { steps: 4 });
    await expect(gridItem).not.toHaveClass(/react-draggable-dragging/);
  } finally {
    await page.mouse.up();
  }
  await expect(gridItem).toHaveAttribute("style", beforeStyle ?? "");
  await expect(saveButton).toBeDisabled();
}

async function assertSubCellHandleMoveDoesNotDirty(
  page: Page,
  handle: Locator,
  gridItem: Locator,
  saveButton: Locator
) {
  const beforeStyle = await gridItem.getAttribute("style");
  await handle.scrollIntoViewIfNeeded();
  await handle.hover();
  const box = await handle.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  try {
    await page.mouse.move(center.x + 5, center.y, { steps: 2 });
    await expect(gridItem).toHaveClass(/react-draggable-dragging/);
  } finally {
    await page.mouse.up();
  }
  await expect(gridItem).toHaveAttribute("style", beforeStyle ?? "");
  await expect(saveButton).toBeDisabled();
}

async function dragWhileActive(
  page: Page,
  handle: Locator,
  gridItem: Locator,
  deltaX: number,
  deltaY: number
) {
  const beforeStyle = await gridItem.getAttribute("style");
  await handle.scrollIntoViewIfNeeded();
  await expect(handle).toHaveClass(/dashboard-card-drag-handle/);
  await handle.hover();
  const box = await handle.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  try {
    await page.mouse.move(center.x + deltaX, center.y + deltaY, { steps: 8 });
    await expect(gridItem).toHaveClass(/react-draggable-dragging/);
    await expect(page.locator(".react-grid-placeholder")).toBeVisible();
    await expect(gridItem).not.toHaveAttribute("style", beforeStyle ?? "");
  } finally {
    await page.mouse.up();
  }
  await expect(gridItem).not.toHaveClass(/react-draggable-dragging/);
}

async function resizeWhileActive(
  page: Page,
  resizeHandle: Locator,
  gridItem: Locator,
  deltaX: number,
  deltaY: number,
  onActive?: () => Promise<void>
) {
  await resizeHandle.scrollIntoViewIfNeeded();
  await resizeHandle.hover();
  const box = await resizeHandle.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  try {
    await page.mouse.move(center.x + deltaX, center.y + deltaY, { steps: 8 });
    await expect(gridItem).toHaveClass(/resizing/);
    await expect(page.locator(".react-grid-placeholder.placeholder-resizing")).toBeVisible();
    await onActive?.();
  } finally {
    await page.mouse.up();
  }
  await expect(gridItem).not.toHaveClass(/resizing/);
}

function gridItemFor(handle: Locator): Locator {
  return handle.locator(
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' react-grid-item ')]"
  );
}

async function itemWidth(item: Locator): Promise<number> {
  const box = await item.boundingBox();
  expect(box).not.toBeNull();
  return box?.width ?? 0;
}

async function itemHeight(item: Locator): Promise<number> {
  const box = await item.boundingBox();
  expect(box).not.toBeNull();
  return box?.height ?? 0;
}

async function expectItemSize(
  item: Locator,
  expectedWidth: number | undefined,
  expectedHeight: number | undefined
) {
  if (expectedWidth !== undefined) {
    await expect.poll(async () => Math.abs((await itemWidth(item)) - expectedWidth)).toBeLessThan(2);
  }
  if (expectedHeight !== undefined) {
    await expect.poll(async () => Math.abs((await itemHeight(item)) - expectedHeight)).toBeLessThan(2);
  }
}

async function expectRelativeGridWidth(
  item: Locator,
  itemColumns: number,
  reference: Locator,
  referenceColumns: number
) {
  await expect.poll(async () => {
    const referenceStep = ((await itemWidth(reference)) + GRID_MARGIN) / referenceColumns;
    const expectedWidth = referenceStep * itemColumns - GRID_MARGIN;
    return Math.abs((await itemWidth(item)) - expectedWidth);
  }).toBeLessThan(2);
}

async function expectNoCardVerticalOverflow(card: Locator) {
  await expect.poll(() => card.evaluate((element) =>
    element.scrollHeight - element.clientHeight
  )).toBeLessThanOrEqual(2);
}

async function selectResizePreset(page: Page, cardTitle: string, preset: string) {
  await page.getByRole("button", { name: `Card actions for ${cardTitle}` }).click();
  await page.getByRole("menuitem", { name: "Resize", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: `Resize ${cardTitle}` });
  await dialog.getByRole("button", { name: preset, exact: true }).click();
  await expect(dialog).toBeHidden();
}

async function settleGridLayout(page: Page) {
  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  }));
}

async function waitForStatusListResults(page: Page, ...titles: string[]) {
  for (const title of titles) {
    const card = page.getByRole("article", {
      name: `Dashboard card ${title}`,
      exact: true
    });
    await expect(card.getByRole("list")).toBeVisible();
  }
}

async function dashboardDetail(response: Response) {
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<DashboardDetailEnvelope>;
}

async function readCurrentDashboardDetail(page: Page) {
  const dashboardId = decodeURIComponent(new URL(page.url()).pathname.split("/").pop() ?? "");
  const apiBaseUrl = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const response = await page.request.get(
    new URL(`/api/v1/dashboards/${encodeURIComponent(dashboardId)}`, apiBaseUrl).toString()
  );
  const body = await response.text();
  expect(
    response.ok(),
    `Dashboard detail request failed with ${response.status()}: ${body}`
  ).toBeTruthy();
  return JSON.parse(body) as DashboardDetailEnvelope;
}

function expectStatusListSize(
  item: { w: number; h: number },
  breakpoint: "desktop" | "tablet" | "mobile"
) {
  const allowed = breakpoint === "desktop"
    ? [
        { w: 4, h: 2 }, { w: 4, h: 3 },
        { w: 6, h: 2 }, { w: 6, h: 3 },
        { w: 8, h: 2 }, { w: 8, h: 3 }, { w: 8, h: 4 },
        { w: 12, h: 4 }
      ]
    : breakpoint === "tablet"
      ? [{ w: 4, h: 2 }, { w: 4, h: 3 }, { w: 6, h: 2 }, { w: 6, h: 3 }, { w: 6, h: 4 }]
      : [{ w: 1, h: 2 }, { w: 1, h: 3 }];
  expect(allowed).toContainEqual({ w: item.w, h: item.h });
}

function expectNoOverlaps(
  items: LayoutPayload["items"],
  breakpoint: "desktop" | "tablet" | "mobile"
) {
  for (let leftIndex = 0; leftIndex < items.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < items.length; rightIndex += 1) {
      const left = items[leftIndex][breakpoint];
      const right = items[rightIndex][breakpoint];
      expect(
        left.x + left.w <= right.x ||
        right.x + right.w <= left.x ||
        left.y + left.h <= right.y ||
        right.y + right.h <= left.y
      ).toBeTruthy();
    }
  }
}

async function saveAndReadLayoutPayload(page: Page, saveButton: Locator) {
  await expect(saveButton).toBeEnabled();
  const responsePromise = page.waitForResponse((response) =>
    response.url().includes("/layout") && response.request().method() === "PATCH"
  );
  await saveButton.click();
  const response = await responsePromise;
  expect(response.ok(), await response.text()).toBeTruthy();
  await expect(page.getByRole("button", { name: "Edit", exact: true })).toHaveAttribute(
    "aria-pressed",
    "false"
  );
  return response.request().postDataJSON() as LayoutPayload;
}

type GridItemPayload = { x: number; y: number; w: number; h: number };
type CardLayoutPayload = {
  version: 1;
  desktop: GridItemPayload;
  tablet: GridItemPayload;
  mobile: GridItemPayload;
};
type LayoutPayload = {
  expected_layout_version: number;
  items: Array<{
    card_id: string;
    desktop: GridItemPayload;
    tablet: GridItemPayload;
    mobile: GridItemPayload;
  }>;
};
type CardMutationEnvelope = {
  data: { card: { id: string; title: string } };
};
type DashboardDetailEnvelope = {
  data: {
    cards: Array<{
      id: string;
      title: string;
      layout: CardLayoutPayload;
    }>;
  };
};
