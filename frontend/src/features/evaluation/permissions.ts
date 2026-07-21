import type { PermissionKey } from "../../auth/types";

export const EVALUATION_PERMISSION_KEYS = [
  "can_view_department_evaluation",
  "can_view_scope_evaluation",
  "can_view_global_evaluation"
] as const satisfies readonly PermissionKey[];
