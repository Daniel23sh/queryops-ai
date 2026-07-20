import type { PermissionKey } from "../../auth/types";

export const APPROVAL_PERMISSION_KEYS = [
  "can_approve_scoped_action",
  "can_approve_global_action",
  "can_approve_policy_override"
] as const satisfies readonly PermissionKey[];

export const AUDIT_PERMISSION_KEYS = [
  "can_view_scope_audit",
  "can_view_global_audit"
] as const satisfies readonly PermissionKey[];
