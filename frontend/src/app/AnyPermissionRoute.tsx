import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { hasAnyPermission } from "../auth/permissions";
import type { PermissionKey } from "../auth/types";
import { APP_ROUTES } from "./routeConfig";

export function AnyPermissionRoute({
  children,
  permissions
}: {
  children: ReactNode;
  permissions: readonly PermissionKey[];
}) {
  const { user } = useAuth();

  if (!user || !hasAnyPermission(user, permissions)) {
    return <Navigate to={APP_ROUTES.home} replace />;
  }

  return children;
}
