import type { AuthUser, PermissionKey } from "./types";

export function hasPermission(user: AuthUser, permission: PermissionKey): boolean {
  return user.permissions.includes(permission);
}

export function hasAnyPermission(
  user: AuthUser,
  permissions: readonly PermissionKey[]
): boolean {
  return permissions.some((permission) => hasPermission(user, permission));
}
