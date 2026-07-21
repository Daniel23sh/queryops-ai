export const APP_ROUTES = {
  login: "/login",
  home: "/",
  ask: "/ask",
  actions: "/actions",
  actionRequest: "/actions/:actionRequestId",
  approvals: "/approvals",
  approvalDetail: "/approvals/:approvalId",
  audit: "/audit",
  evaluation: "/evaluation",
  dashboard: "/dashboards/:dashboardId",
  profile: "/profile",
  adminRoleRequests: "/admin/role-requests"
} as const;

export type AppRoutePath = (typeof APP_ROUTES)[keyof typeof APP_ROUTES];

const ROUTE_TITLES: Record<AppRoutePath, string> = {
  [APP_ROUTES.login]: "Sign in",
  [APP_ROUTES.home]: "My Dashboard",
  [APP_ROUTES.ask]: "Ask Data",
  [APP_ROUTES.actions]: "Actions",
  [APP_ROUTES.actionRequest]: "Action Request",
  [APP_ROUTES.approvals]: "Approvals",
  [APP_ROUTES.approvalDetail]: "Approval Review",
  [APP_ROUTES.audit]: "Audit",
  [APP_ROUTES.evaluation]: "Evaluation",
  [APP_ROUTES.dashboard]: "Dashboard",
  [APP_ROUTES.profile]: "Profile",
  [APP_ROUTES.adminRoleRequests]: "Role Requests"
};

export function getRouteTitle(pathname: string): string {
  if (pathname.startsWith("/dashboards/")) {
    return ROUTE_TITLES[APP_ROUTES.dashboard];
  }
  if (pathname.startsWith("/actions/")) {
    return ROUTE_TITLES[APP_ROUTES.actionRequest];
  }
  if (pathname.startsWith("/approvals/")) {
    return ROUTE_TITLES[APP_ROUTES.approvalDetail];
  }
  return ROUTE_TITLES[pathname as AppRoutePath] ?? ROUTE_TITLES[APP_ROUTES.home];
}

export function dashboardPath(dashboardId: string): string {
  return `/dashboards/${encodeURIComponent(dashboardId)}`;
}
