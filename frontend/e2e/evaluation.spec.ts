import type { Page, Route } from "@playwright/test";

import { expect, test } from "./fixtures";
import { loginAs } from "./helpers";

test.describe("role-aware Evaluation workspace", () => {
  test("Manager sees the stable business projection without technical fields", async ({ page }) => {
    await installEvaluationRoutes(page, false);
    await loginAs(page, "Demo Manager");
    await page.getByRole("link", { name: "Evaluation" }).click();
    await expect(page.getByRole("heading", { name: "MockLLM quality measurement" })).toBeVisible();
    await page.getByRole("navigation", { name: "Evaluation sections" }).getByRole("link", { name: "Queries" }).click();
    await expect(page.getByText("itops-security-003")).toBeVisible();
    await expect(page.getByText("Technical measurement details")).toHaveCount(0);
  });

  test("Analyst sees only returned technical measurement metadata", async ({ page }) => {
    await installEvaluationRoutes(page, true);
    await loginAs(page, "Demo Analyst");
    await page.goto("/evaluation?tab=queries");
    await expect(page.getByText("Technical measurement details")).toBeVisible();
    await page.getByText("Technical measurement details").click();
    await expect(page.getByText("Unsafe query blocked")).toBeVisible();
    await expect(page.getByText("SELECT secret FROM audit")).toHaveCount(0);
  });

  test("Admin can open the global projection and unmeasured capability tabs", async ({ page }) => {
    await installEvaluationRoutes(page, true);
    await loginAs(page, "Demo Admin");
    await page.goto("/evaluation?tab=actions");
    await expect(page.getByText("global evaluation projection")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Action evaluation" })).toBeVisible();
    await expect(page.getByText("Not measured in this dataset")).toBeVisible();
    await expect(page.getByRole("button", { name: /run|start|rerun/i })).toHaveCount(0);
  });

  test("User has no Evaluation navigation or direct-route access", async ({ page }) => {
    await loginAs(page, "Demo User");
    await expect(page.getByRole("link", { name: "Evaluation" })).toHaveCount(0);
    await page.goto("/evaluation");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Evaluation" })).toHaveCount(0);
  });

  test("keeps the Evaluation workspace within a narrow mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installEvaluationRoutes(page, false);
    await loginAs(page, "Demo Manager");
    await page.goto("/evaluation?tab=queries");
    await expect(page.getByRole("heading", { name: "Query measurements" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Evaluation sections" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});

async function installEvaluationRoutes(page: Page, technical: boolean) {
  await page.route("**/api/v1/evaluation/**", async (route) => {
    const parts = new URL(route.request().url()).pathname.split("/");
    const endpoint = parts[parts.length - 1];
    const data = endpoint === "overview" ? overview() : endpoint === "queries" ? queries(technical) : endpoint === "security" ? security(technical) : capability(endpoint === "dashboards" ? "dashboards" : "actions");
    await respond(route, data);
  });
}

const run = { id: "00000000-0000-4000-8000-000000000901", provider: "mock", model_label: "mock-queryops-v1", dataset_id: "it_operations_v1", dataset_version: "1.0.0", dataset_digest: "a".repeat(64), status: "succeeded", started_at: "2026-07-20T11:00:00Z", completed_at: "2026-07-20T11:02:00Z" };
const metrics = { availability: "measured", eligible_count: 40, selected_count: 40, completed_count: 40, passed_count: 10, failed_count: 30, overall_score: 0.25, expected_behavior_match_rate: 0.25, security_pass_rate: 0.8, query_execution_succeeded_count: 6, query_execution_failed_count: 0 };
const breakdown = (key: string, eligible = 1, passed = 0) => ({ key, eligible_count: eligible, completed_count: eligible, passed_count: passed, failed_count: eligible - passed, score: eligible ? passed / eligible : null });

function overview() {
  return { run, metrics, by_difficulty: [breakdown("security", 5, 4)], by_category: [breakdown("directory_users")], by_case_type: [breakdown("unsafe_sql")], coverage: [{ capability: "queries", availability: "measured", measured_case_count: 40, score: 0.25 }, { capability: "actions", availability: "not_measured", measured_case_count: 0, score: null }, { capability: "security", availability: "measured", measured_case_count: 5, score: 0.8 }, { capability: "dashboards", availability: "not_measured", measured_case_count: 0, score: null }] };
}

function queries(includeTechnical: boolean) {
  const item = evaluationCase(includeTechnical);
  return { run, metrics: { ...metrics, eligible_count: 1, selected_count: 1, completed_count: 1, passed_count: 0, failed_count: 1, overall_score: 0, expected_behavior_match_rate: 0, security_pass_rate: 0 }, by_difficulty: [breakdown("security")], by_category: [breakdown("directory_users")], by_case_type: [breakdown("unsafe_sql")], items: [item], pagination: { limit: 25, offset: 0, returned: 1, total: 1 } };
}

function security(includeTechnical: boolean) {
  return { run, metrics: { ...metrics, eligible_count: 5, selected_count: 5, completed_count: 5, passed_count: 4, failed_count: 1 }, by_expected_behavior: [breakdown("unsafe_query_block")], items: [evaluationCase(includeTechnical)] };
}

function capability(value: "actions" | "dashboards") {
  return { run, capability: value, availability: "not_measured", measured_cases: 0, score: null, reason_code: value === "actions" ? "action_evaluation_not_available" : "dashboard_evaluation_not_available" };
}

function evaluationCase(includeTechnical: boolean) {
  return { case_id: "itops-security-003", category: "directory_users", difficulty: "security", case_type: "unsafe_sql", passed: false, score: 0, technical: includeTechnical ? { expected_outcome: "unsafe_blocked", actual_outcome: "execution_failed", execution_succeeded: false, query_execution_attempted: true, expected_row_count: 0, actual_row_count: 0, missing_row_count: 0, extra_row_count: 0, failure_reasons: ["unexpected_outcome"], error_code: "execution_failed", duration_ms: 12.4, referenced_tables: ["directory_users"] } : null };
}

async function respond(route: Route, data: unknown) {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { request_id: "00000000-0000-4000-8000-000000000999", timestamp: "2026-07-20T12:00:00Z" } }) });
}
