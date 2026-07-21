import { describe, expect, it } from "vitest";

import type { AuthUser } from "../../auth/types";
import { evaluationIdentityKey } from "./identity";

describe("evaluationIdentityKey", () => {
  it("changes for permission, role, department and assigned-scope context changes", () => {
    const original = user();
    const originalKey = evaluationIdentityKey(original);
    const variants: AuthUser[] = [
      { ...original, role: "analyst" },
      { ...original, departmentId: "department-b" },
      { ...original, permissions: ["can_view_scope_evaluation"] },
      { ...original, scopes: [{ ...original.scopes[0], key: "other" }] },
      { ...original, scopes: [{ ...original.scopes[0], accessLevel: "manage" }] },
      { ...original, scopes: [{ ...original.scopes[0], departmentId: "department-b" }] }
    ];
    for (const variant of variants) expect(evaluationIdentityKey(variant)).not.toBe(originalKey);
  });

  it("is stable when permission and scope arrays are reordered", () => {
    const original = user();
    const reordered = {
      ...original,
      permissions: [...original.permissions].reverse(),
      scopes: [...original.scopes].reverse()
    };
    expect(evaluationIdentityKey(reordered)).toBe(evaluationIdentityKey(original));
  });
});

function user(): AuthUser {
  return {
    id: "user-a",
    email: "not-part-of-cache-key@example.invalid",
    fullName: "Viewer",
    role: "manager",
    departmentId: "department-a",
    department: { id: "department-a", name: "Department A" },
    scopes: [
      { id: "scope-a", type: "department", key: "department-a", displayName: "Department A", accessLevel: "read", isDefault: true, departmentId: "department-a" },
      { id: "scope-b", type: "department", key: "department-b", displayName: "Department B", accessLevel: "read", isDefault: false, departmentId: "department-b" }
    ],
    status: "active",
    permissions: ["can_view_department_evaluation", "can_view_own_data"],
    authMode: "demo"
  };
}
