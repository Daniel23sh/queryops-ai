import {
  CircleUserRound,
  LayoutDashboard,
  MessageSquareText,
  ShieldCheck,
  type LucideIcon
} from "lucide-react";

import { hasPermission } from "../auth/permissions";
import type { AuthUser } from "../auth/types";
import { APP_ROUTES, type AppRoutePath } from "./routeConfig";

export type NavigationSection = "workspace" | "admin";

export type NavItem = {
  id: "my-dashboard" | "ask-data" | "profile" | "admin-role-requests";
  label: string;
  title: string;
  summary: string;
  path: AppRoutePath;
  icon: LucideIcon;
  section: NavigationSection;
  canView: (user: AuthUser) => boolean;
};

export const WORKSPACE_NAV_ITEMS: NavItem[] = [
  {
    id: "my-dashboard",
    label: "My Dashboard",
    title: "My Dashboard",
    summary: "Your personal dashboards and saved cards.",
    path: APP_ROUTES.home,
    icon: LayoutDashboard,
    section: "workspace",
    canView: () => true
  },
  {
    id: "ask-data",
    label: "Ask Data",
    title: "Ask Data",
    summary: "Run governed template and permitted free-form questions.",
    path: APP_ROUTES.ask,
    icon: MessageSquareText,
    section: "workspace",
    canView: (user) => hasPermission(user, "can_use_query_templates")
  },
  {
    id: "profile",
    label: "Profile",
    title: "Profile",
    summary: "Review your identity, scopes, appearance, and access requests.",
    path: APP_ROUTES.profile,
    icon: CircleUserRound,
    section: "workspace",
    canView: () => true
  },
  {
    id: "admin-role-requests",
    label: "Role Requests",
    title: "Role Requests",
    summary: "Review existing role upgrade requests.",
    path: APP_ROUTES.adminRoleRequests,
    icon: ShieldCheck,
    section: "admin",
    canView: (user) => hasPermission(user, "can_approve_role_requests")
  }
];

export function getVisibleNavItems(user: AuthUser): NavItem[] {
  return WORKSPACE_NAV_ITEMS.filter((item) => item.canView(user));
}
