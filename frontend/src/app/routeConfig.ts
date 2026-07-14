export const APP_ROUTES = {
  login: "/login",
  home: "/",
  ask: "/ask",
  profile: "/profile",
  adminRoleRequests: "/admin/role-requests"
} as const;

export type AppRoutePath = (typeof APP_ROUTES)[keyof typeof APP_ROUTES];

const ROUTE_TITLES: Record<AppRoutePath, string> = {
  [APP_ROUTES.login]: "Sign in",
  [APP_ROUTES.home]: "My Dashboard",
  [APP_ROUTES.ask]: "Ask Data",
  [APP_ROUTES.profile]: "Profile",
  [APP_ROUTES.adminRoleRequests]: "Role Requests"
};

export function getRouteTitle(pathname: string): string {
  return ROUTE_TITLES[pathname as AppRoutePath] ?? ROUTE_TITLES[APP_ROUTES.home];
}
