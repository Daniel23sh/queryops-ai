import type { AuthUser } from "../../auth/types";

export function evaluationIdentityKey(user: AuthUser): string {
  return JSON.stringify([
    user.id,
    user.role,
    user.status,
    user.departmentId,
    [...user.permissions].sort(),
    user.scopes
      .map((scope) => [
        scope.id,
        scope.type,
        scope.key,
        scope.accessLevel,
        scope.departmentId
      ])
      .sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)))
  ]);
}
