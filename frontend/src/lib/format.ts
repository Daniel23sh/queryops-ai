import type { AuthUser } from "../auth/types";
import type { RoleRequestStatus } from "../api/roleRequests";

export function formatRole(role: AuthUser["role"]): string {
  if (!role) {
    return "Unassigned";
  }

  return role.charAt(0).toUpperCase() + role.slice(1);
}

export function formatRequestStatus(status: RoleRequestStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}
