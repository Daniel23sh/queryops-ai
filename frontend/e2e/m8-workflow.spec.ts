import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

import type { Locator, Page, Route } from "@playwright/test";

import { expect, test } from "./fixtures";
import { chooseTemplate, loginAs, logout, openAskData } from "./helpers";

const execFileAsync = promisify(execFile);
const apiBaseUrl = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const unusedTemplate = "Unused licenses";

type ApiEnvelope<T> = { data: T };
type QueryResult = {
  query_run_id: string;
  status: string;
  row_count: number;
  truncated: boolean;
  rows: Array<{ id?: string }>;
  suggested_actions: Array<{ action_type: string }>;
};
type ActionDetail = {
  action_request_id: string;
  status: string;
  scope: { key: string | null; display_name?: string | null };
  preview: {
    summary: {
      affected_license_assignment_count?: number;
      skipped_count?: number;
      override_required_count?: number;
      estimated_monthly_savings?: string | null;
    };
  };
  requires_admin: boolean;
};
type PendingApprovals = {
  items: Array<{ approval_id: string; action_request_id: string }>;
  pagination: { total: number };
};
type DecisionResult = {
  action_request_id: string;
  status: string;
  executed_records_count: number;
  skipped_records_count: number;
};
type AuthMe = {
  scopes: Array<{ id: string; department_id: string | null; is_default: boolean }>;
};
type ActionState = {
  action_requests: number;
  approval_requests: number;
  action_audit_events: number;
  action_notifications: number;
};

test.describe("M8 governed action release flows @m8-primary", () => {
  test.describe.configure({ mode: "serial", retries: 0 });

  test.beforeAll(() => {
    expect(process.env.M8_E2E_DATABASE_DISPOSABLE).toBe("1");
    expect(process.env.M8_E2E_DATABASE_URL).toContain("e2e");
  });

  test("Manager request is approved and executed once by an exact-scope Analyst", async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1440, height: 960 });
    await loginAs(page, "Demo Manager");
    await expect(page.getByRole("link", { name: "Actions", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /Approvals/ })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Audit", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Open notifications, 0 unread", exact: true })).toBeVisible();

    await openAskData(page);
    await chooseTemplate(page, unusedTemplate);
    const initialQueryResponse = page.waitForResponse(isQueryRunResponse);
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const initialQuery = await responseData<QueryResult>(await initialQueryResponse);
    expect(initialQuery).toMatchObject({ status: "succeeded", row_count: 2, truncated: false });
    expect(initialQuery.suggested_actions).toContainEqual(
      expect.objectContaining({ action_type: "reclaim_unused_license" })
    );
    await expect(page.getByRole("heading", { name: "Preview license reclaim", exact: true })).toBeVisible();

    const previewButton = page.getByRole("button", { name: "Preview Action", exact: true });
    const firstPreviewResponse = page.waitForResponse(isPreviewResponse);
    await previewButton.click();
    expect((await firstPreviewResponse).ok()).toBeTruthy();
    const firstDrawer = page.getByRole("dialog", { name: "Reclaim unused licenses", exact: true });
    await expect(firstDrawer).toBeVisible();
    await expect(firstDrawer).toContainText("Finance");
    await expectMetric(firstDrawer, "Actionable", "2");
    await expectMetric(firstDrawer, "Skipped", "0");
    await expectMetric(firstDrawer, "Admin review", "0");
    await expectMetric(firstDrawer, "Requires Admin", "No");
    await expectMetric(firstDrawer, "Est. monthly savings", "$29.50");
    await firstDrawer.getByRole("tab", { name: "Policy Details", exact: true }).click();
    await expect(firstDrawer.getByRole("tabpanel", { name: "policy action preview", exact: true }))
      .toContainText("An eligible Analyst or Admin must approve this request.");
    await expectSafeRenderedFields(firstDrawer);
    await page.keyboard.press("Escape");
    await expect(firstDrawer).toBeHidden();
    await expect(previewButton).toBeFocused();

    const previewResponsePromise = page.waitForResponse(isPreviewResponse);
    await previewButton.click();
    const previewResponse = await previewResponsePromise;
    const preview = await responseData<ActionDetail>(previewResponse);
    expect(preview).toMatchObject({
      status: "draft_preview",
      scope: { key: "finance" },
      requires_admin: false,
      preview: {
        summary: {
          affected_license_assignment_count: 2,
          skipped_count: 0,
          override_required_count: 0,
          estimated_monthly_savings: "29.50"
        }
      }
    });
    const requestReason = `M8 E2E Manager request ${Date.now()}`;
    const drawer = page.getByRole("dialog", { name: "Reclaim unused licenses", exact: true });
    await drawer.getByRole("textbox", { name: "Request reason", exact: true }).fill(requestReason);
    const submitResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith("/api/v1/actions/request") && response.request().method() === "POST"
    );
    await drawer.getByRole("button", { name: "Submit for Approval", exact: true }).click();
    const submitted = await responseData<ActionDetail>(await submitResponsePromise);
    expect(submitted.status).toBe("pending_approval");
    const actionId = submitted.action_request_id;
    const actionPath = `/actions/${actionId}`;
    await expect(page).toHaveURL(new RegExp(`${actionPath}$`));
    await expect(page.getByRole("heading", { name: "Reclaim unused licenses", exact: true })).toBeVisible();
    await expect(page.getByText(`Reason: ${requestReason}`, { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Persisted action status tracker", exact: true }))
      .toContainText("Recorded: Pending Approval");
    await expect(page.getByRole("region", { name: "Timeline", exact: true }))
      .toContainText("request submitted for approval");
    await expect(page.getByRole("button", { name: "Approve and Execute", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Open notifications, 0 unread", exact: true })).toBeVisible();
    await assertNoHorizontalOverflow(page);

    await page.goto("/actions");
    const requestLink = page.getByRole("link", { name: /Reclaim unused licenses/ });
    await expect(requestLink).toHaveCount(1);
    await expect(requestLink).toContainText("Pending approval");
    for (const protectedPath of ["/approvals", `/approvals/${crypto.randomUUID()}`, "/audit"]) {
      await page.goto(protectedPath);
      await expect(page).toHaveURL(/\/$/);
      await expect(page.getByRole("heading", { name: "My Dashboard", exact: true })).toBeVisible();
    }

    await logout(page, "Demo Manager");
    await loginAs(page, "Demo Analyst");
    await expect(page.getByRole("link", { name: "Approvals 1 pending approvals", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open notifications, 1 unread", exact: true })).toBeVisible();

    const pendingResponsePromise = page.waitForResponse((response) =>
      response.url().includes("/api/v1/approvals/pending?") && response.request().method() === "GET"
    );
    await page.goto("/approvals");
    const pending = await responseData<PendingApprovals>(await pendingResponsePromise);
    expect(pending.pagination.total).toBe(1);
    const approval = pending.items.find((item) => item.action_request_id === actionId);
    expect(approval).toBeDefined();
    const approvalId = approval?.approval_id ?? "";
    await page.getByRole("link", { name: "Reclaim unused licenses", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/approvals/${approvalId}$`));
    const approvalMain = page.getByRole("main");
    await expect(approvalMain).toContainText("Requested by Demo Manager · Finance");
    await expect(approvalMain).toContainText(`Requester reason: ${requestReason}`);
    await expect(approvalMain).toContainText("Approval expires");
    await expect(approvalMain).toContainText("Review context only. The server revalidates current records before execution.");
    await expect(approvalMain).toContainText("No additional policy flags were returned.");
    await expect(approvalMain).toContainText("Self-approval permitted: No");
    await expectSafeRenderedFields(approvalMain);

    const decisionReason = `M8 E2E Analyst decision ${Date.now()}`;
    const openDecision = page.getByRole("button", { name: "Approve and Execute", exact: true });
    await openDecision.click();
    const decisionDialog = page.getByRole("dialog", { name: "Approve and Execute", exact: true });
    await expect(decisionDialog).toBeVisible();
    await decisionDialog.getByRole("textbox", { name: "Decision reason", exact: true }).fill(decisionReason);
    const approvePattern = "**/api/v1/approvals/*/approve";
    let releaseApproval = () => {};
    const approvalGate = new Promise<void>((resolve) => { releaseApproval = resolve; });
    const holdApproval = async (route: Route) => {
      await approvalGate;
      await route.continue();
    };
    await page.route(approvePattern, holdApproval);
    const approveResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith(`/api/v1/approvals/${approvalId}/approve`) && response.request().method() === "POST"
    );
    const confirmDecision = decisionDialog.getByRole("button", { name: "Approve and Execute", exact: true });
    await confirmDecision.click();
    await expect(
      decisionDialog.getByRole("button", { name: "Approving and executing…", exact: true })
    ).toBeDisabled();
    await expect(decisionDialog.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
    releaseApproval();
    const decision = await responseData<DecisionResult>(await approveResponsePromise);
    await page.unroute(approvePattern, holdApproval);
    expect(decision).toEqual(expect.objectContaining({
      action_request_id: actionId,
      status: "completed",
      executed_records_count: 2,
      skipped_records_count: 0
    }));
    await expect(page.getByText("Authoritative result: completed.", { exact: true })).toBeVisible();
    await expect(page.getByText("Executed 2 records · Skipped 0", { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Persisted Timeline", exact: true }))
      .toContainText("action completed");
    await expect(page.getByRole("button", { name: "Approve and Execute", exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Approvals", exact: true })).toBeVisible();

    const emptyPendingResponse = page.waitForResponse((response) =>
      response.url().includes("/api/v1/approvals/pending?") && response.request().method() === "GET"
    );
    await page.goto("/approvals");
    expect((await responseData<PendingApprovals>(await emptyPendingResponse)).pagination.total).toBe(0);
    await expect(page.getByRole("heading", { name: "No pending approvals", exact: true })).toBeVisible();

    await page.goto("/audit");
    await expect(page.getByRole("heading", { name: "Audit", exact: true })).toBeVisible();
    const actionTarget = page.locator(`a[href="${actionPath}"]`);
    const executedRow = page.getByRole("row").filter({ has: actionTarget }).filter({ hasText: "Action Executed" });
    await expect(executedRow).toHaveCount(1);
    await executedRow.getByRole("button", { name: "View details", exact: true }).click();
    const auditDetails = page.getByRole("dialog", { name: "Audit event details", exact: true });
    await expect(auditDetails).toContainText("Reclaim unused license action completed.");
    await expect(auditDetails).toContainText("finance");
    await expectSafeRenderedFields(auditDetails);
    await auditDetails.getByRole("button", { name: "Close Audit event details", exact: true }).click();

    await expect(page.getByRole("button", { name: "Open notifications, 2 unread", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Open notifications, 2 unread", exact: true }).click();
    const analystNotifications = page.getByRole("dialog", { name: "Notifications", exact: true });
    const analystCompletion = analystNotifications.locator("li").filter({ hasText: "Approved action completed" });
    await expect(analystCompletion).toHaveCount(1);
    const analystReadResponse = page.waitForResponse(isNotificationReadResponse);
    await analystCompletion.getByRole("button", { name: "Mark as read", exact: true }).click();
    expect((await analystReadResponse).ok()).toBeTruthy();
    await expect(page.getByRole("button", { name: "Open notifications, 1 unread", exact: true })).toBeVisible();
    await analystNotifications.getByRole("button", { name: "Close Notifications", exact: true }).click();

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/approvals/${approvalId}`);
    await expect(page.getByRole("heading", { name: "Reclaim unused licenses", exact: true })).toBeVisible();
    await assertNoHorizontalOverflow(page);
    await page.goto("/audit");
    await expect(page.getByRole("list", { name: "Authorized workflow audit events", exact: true })).toBeVisible();
    await assertNoHorizontalOverflow(page);
    const themeButton = page.getByRole("button", { name: "Switch to light mode", exact: true });
    await themeButton.click();
    await expect(page.getByRole("button", { name: "Switch to dark mode", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Switch to dark mode", exact: true }).click();
    await expect(themeButton).toBeVisible();

    await page.setViewportSize({ width: 1440, height: 960 });
    await logout(page, "Demo Analyst");
    await loginAs(page, "Demo Manager");
    await page.goto(actionPath);
    const completedMain = page.getByRole("main");
    await expect(completedMain).toContainText("Status: Completed");
    await expectMetric(completedMain, "Actionable", "2");
    await expectMetric(completedMain, "Skipped", "0");
    await expect(completedMain).toContainText("Recorded: Executed");
    await expect(completedMain).toContainText("action completed");

    await expect(page.getByRole("button", { name: "Open notifications, 2 unread", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Open notifications, 2 unread", exact: true }).click();
    const managerNotifications = page.getByRole("dialog", { name: "Notifications", exact: true });
    const managerCompletion = managerNotifications.locator("li").filter({ hasText: "Action completed" });
    await expect(managerCompletion).toHaveCount(1);
    const managerReadResponse = page.waitForResponse(isNotificationReadResponse);
    await managerCompletion.getByRole("button", { name: "Mark as read", exact: true }).click();
    expect((await managerReadResponse).ok()).toBeTruthy();
    await expect(page.getByRole("button", { name: "Open notifications, 1 unread", exact: true })).toBeVisible();
    await managerNotifications.getByRole("button", { name: "Close Notifications", exact: true }).click();

    await openAskData(page);
    await chooseTemplate(page, unusedTemplate);
    const finalQueryResponse = page.waitForResponse(isQueryRunResponse);
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const finalQuery = await responseData<QueryResult>(await finalQueryResponse);
    expect(finalQuery).toMatchObject({ status: "succeeded", row_count: 0, truncated: false });
    await expect(page.getByRole("table", { name: "Query results", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Preview Action", exact: true })).toHaveCount(0);
    await assertNoHorizontalOverflow(page);
  });

  test("User action denial reaches authorization with valid CSRF and persists nothing", async ({ page }) => {
    test.setTimeout(60_000);
    await loginAs(page, "Demo User");
    await openAskData(page);
    await expect(page.getByLabel("Question")).toHaveCount(0);
    await chooseTemplate(page, unusedTemplate);
    const queryResponsePromise = page.waitForResponse(isQueryRunResponse);
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const query = await responseData<QueryResult>(await queryResponsePromise);
    expect(query.status).toBe("succeeded");
    expect(query.suggested_actions).toEqual([]);
    await expect(page.getByRole("button", { name: "Preview Action", exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Actions", exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Approvals/ })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Audit", exact: true })).toHaveCount(0);

    for (const protectedPath of [
      "/actions",
      `/actions/${crypto.randomUUID()}`,
      "/approvals",
      `/approvals/${crypto.randomUUID()}`,
      "/audit"
    ]) {
      await page.goto(protectedPath);
      await expect(page).toHaveURL(/\/$/);
      await expect(page.getByRole("heading", { name: "My Dashboard", exact: true })).toBeVisible();
    }

    const before = await inspectActionState();
    const authResponse = await page.request.get(`${apiBaseUrl}/api/v1/auth/me`);
    expect(authResponse.ok(), await authResponse.text()).toBeTruthy();
    const auth = (await authResponse.json() as ApiEnvelope<AuthMe>).data;
    const scope = auth.scopes.find((item) => item.is_default) ?? auth.scopes[0];
    expect(scope).toBeDefined();
    const csrfCookie = (await page.context().cookies(apiBaseUrl))
      .find((cookie) => cookie.name === "qo_csrf");
    expect(csrfCookie?.value).toBeTruthy();
    const forbiddenResponse = await page.request.post(`${apiBaseUrl}/api/v1/actions/preview`, {
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": decodeURIComponent(csrfCookie?.value ?? "")
      },
      data: {
        action_type: "reclaim_unused_license",
        source_query_run_id: query.query_run_id,
        scope_id: scope?.id,
        department_id: scope?.department_id,
        license_assignment_ids: [query.rows[0]?.id ?? crypto.randomUUID()],
        reason: "M8 E2E User authorization denial"
      }
    });
    expect(forbiddenResponse.status()).toBe(403);
    const forbiddenBody = await forbiddenResponse.json() as { error: { code: string } };
    expect(forbiddenBody.error.code).toBe("FORBIDDEN");
    expect(await inspectActionState()).toEqual(before);
    await assertNoHorizontalOverflow(page);
  });
});

function isQueryRunResponse(response: { url(): string; request(): { method(): string } }) {
  return response.url().endsWith("/api/v1/queries/run") && response.request().method() === "POST";
}

function isPreviewResponse(response: { url(): string; request(): { method(): string } }) {
  return response.url().endsWith("/api/v1/actions/preview") && response.request().method() === "POST";
}

function isNotificationReadResponse(response: { url(): string; request(): { method(): string } }) {
  return /\/api\/v1\/notifications\/[^/]+\/read$/.test(response.url()) && response.request().method() === "POST";
}

async function responseData<T>(response: { ok(): boolean; text(): Promise<string>; json(): Promise<unknown> }): Promise<T> {
  const body = await response.text();
  expect(response.ok(), body).toBeTruthy();
  return (JSON.parse(body) as ApiEnvelope<T>).data;
}

async function inspectActionState(): Promise<ActionState> {
  const backendDirectory = path.resolve(process.cwd(), "../backend");
  const python = process.env.M8_E2E_PYTHON ?? "python";
  const { stdout } = await execFileAsync(python, ["scripts/inspect_m8_e2e.py"], {
    cwd: backendDirectory,
    env: process.env
  });
  return JSON.parse(stdout.trim()) as ActionState;
}

async function expectSafeRenderedFields(target: Locator) {
  const text = await target.innerText();
  for (const forbidden of [
    "SELECT ",
    "demo.manager@",
    "can_request_action",
    "permission catalog",
    "audit_metadata",
    "generated_sql",
    "executed_sql",
    "queryops_action_runtime"
  ]) {
    expect(text).not.toContain(forbidden);
  }
}

async function expectMetric(container: Locator, label: string, value: string) {
  const term = container.getByRole("term").filter({ hasText: label });
  await expect(term).toHaveCount(1);
  await expect(term.locator("xpath=following-sibling::dd[1]")).toHaveText(value);
}

async function assertNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() =>
    document.documentElement.scrollWidth <= document.documentElement.clientWidth
  )).toBeTruthy();
}
