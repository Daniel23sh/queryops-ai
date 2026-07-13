import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";

import { hasPermission } from "../auth/permissions";
import { useAuth } from "../auth/AuthProvider";
import type { PermissionKey } from "../auth/types";
import { APP_ROUTES } from "./routeConfig";

export function PermissionRoute({
  children,
  permission
}: {
  children: ReactNode;
  permission: PermissionKey;
}) {
  const { user } = useAuth();

  if (!user || !hasPermission(user, permission)) {
    return <Navigate to={APP_ROUTES.home} replace />;
  }

  return children;
}
