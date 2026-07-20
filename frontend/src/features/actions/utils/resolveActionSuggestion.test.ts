import { describe, expect, it } from "vitest";

import type { AuthScope } from "../../../auth/types";
import type { CurrentQueryResult } from "../../ask-data/types";
import { resolveActionSuggestion } from "./resolveActionSuggestion";

const RUN_ID = "00000000-0000-4000-8000-000000000001";
const SCOPE_ID = "00000000-0000-4000-8000-000000000002";
const DEPARTMENT_ID = "00000000-0000-4000-8000-000000000003";
const TARGET_ONE = "00000000-0000-4000-8000-000000000004";
const TARGET_TWO = "00000000-0000-4000-8000-000000000005";

describe("resolveActionSuggestion", () => {
  it.each([
    ["reclaim_unused_license", "license_assignment", "license_assignment_ids"],
    ["disable_inactive_user", "directory_user", "target_user_ids"]
  ] as const)("maps %s only to its exact selector field", (actionType, selectorKind, field) => {
    const current = actionResult({ actionType, selectorKind });
    current.result.rows = [{ id: TARGET_ONE }, { id: TARGET_ONE }, { id: TARGET_TWO }];

    const resolution = resolveActionSuggestion({
      canRequestAction: true,
      current,
      activeScope: scope
    });

    expect(resolution.status).toBe("available");
    if (resolution.status !== "available") return;
    expect(resolution.targetCount).toBe(2);
    expect(resolution.previewRequest).toEqual({
      action_type: actionType,
      source_query_run_id: RUN_ID,
      scope_id: SCOPE_ID,
      department_id: DEPARTMENT_ID,
      reason: expect.stringContaining("Request approval"),
      [field]: [TARGET_ONE, TARGET_TWO]
    });
    expect(
      field === "license_assignment_ids"
        ? resolution.previewRequest.target_user_ids
        : resolution.previewRequest.license_assignment_ids
    ).toBeUndefined();
  });

  it("hides suggestions when the requester capability or backend suggestion is absent", () => {
    expect(
      resolveActionSuggestion({ canRequestAction: false, current: actionResult(), activeScope: scope })
    ).toEqual({ status: "hidden" });
    const current = actionResult();
    current.result.suggested_actions = [];
    expect(
      resolveActionSuggestion({ canRequestAction: true, current, activeScope: scope })
    ).toEqual({ status: "hidden" });
  });

  it.each([
    ["missing run ID", (current: CurrentQueryResult) => (current.result.query_run_id = null)],
    ["invalid run ID", (current: CurrentQueryResult) => (current.result.query_run_id = "invalid")],
    ["truncated", (current: CurrentQueryResult) => (current.result.truncated = true)],
    ["zero rows", (current: CurrentQueryResult) => (current.result.rows = [])],
    ["failed", (current: CurrentQueryResult) => (current.result.status = "failed")],
    [
      "clarification",
      (current: CurrentQueryResult) => (current.result.clarification_required = true)
    ],
    [
      "malformed selector",
      (current: CurrentQueryResult) => (current.result.rows = [{ id: TARGET_ONE }, { id: "bad" }])
    ],
    [
      "unsupported action pair",
      (current: CurrentQueryResult) =>
        (current.result.suggested_actions[0].selector_kind = "directory_user")
    ],
    [
      "multiple suggestions",
      (current: CurrentQueryResult) =>
        current.result.suggested_actions.push(current.result.suggested_actions[0])
    ]
  ])("fails closed for %s without a partial selector set", (_label, mutate) => {
    const current = actionResult();
    mutate(current);
    expect(
      resolveActionSuggestion({ canRequestAction: true, current, activeScope: scope }).status
    ).toBe("unavailable");
  });

  it("requires an exact active Scope and enforces the 100-target cap", () => {
    expect(
      resolveActionSuggestion({ canRequestAction: true, current: actionResult(), activeScope: null })
        .status
    ).toBe("unavailable");
    const current = actionResult();
    current.result.rows = Array.from({ length: 101 }, (_, index) => ({
      id: `00000000-0000-4000-8${String(index).padStart(3, "0")}-000000000004`
    }));
    expect(
      resolveActionSuggestion({ canRequestAction: true, current, activeScope: scope }).status
    ).toBe("unavailable");
  });
});

const scope: AuthScope = {
  id: SCOPE_ID,
  type: "department",
  key: "finance",
  displayName: "Finance",
  accessLevel: "scoped",
  isDefault: true,
  departmentId: DEPARTMENT_ID
};

function actionResult({
  actionType = "reclaim_unused_license",
  selectorKind = "license_assignment"
}: {
  actionType?: "reclaim_unused_license" | "disable_inactive_user";
  selectorKind?: "license_assignment" | "directory_user";
} = {}): CurrentQueryResult {
  return {
    question: "Approved template",
    originalQuestion: "Approved template",
    clarificationResponse: null,
    generation: 1,
    result: {
      query_run_id: RUN_ID,
      status: "succeeded",
      columns: ["id"],
      rows: [{ id: TARGET_ONE }],
      row_count: 1,
      duration_ms: 2,
      truncated: false,
      message: "Complete",
      warnings: [],
      clarification_required: false,
      metadata: { template_id: "unused_licenses_by_department" },
      suggested_actions: [
        {
          action_type: actionType,
          label: "Preview action",
          selector_kind: selectorKind,
          result_identifier_column: "id"
        }
      ]
    }
  };
}
