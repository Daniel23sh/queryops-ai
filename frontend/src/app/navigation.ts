import {
  CircleUserRound,
  LayoutDashboard,
  MessageSquareText,
  ListChecks,
  ClipboardCheck,
  ScrollText,
  ShieldCheck,
  type LucideIcon
} from "lucide-react";

import { hasAnyPermission, hasPermission } from "../auth/permissions";
import type { AuthUser } from "../auth/types";
import { APPROVAL_PERMISSION_KEYS, AUDIT_PERMISSION_KEYS } from "../features/activity/permissions";
import { APP_ROUTES, type AppRoutePath } from "./routeConfig";

export type NavigationSection = "workspace" | "admin";

export type NavItem = {
  id: "my-dashboard" | "ask-data" | "actions" | "approvals" | "audit" | "profile" | "admin-role-requests";
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
    id: "actions",
    label: "Actions",
    title: "Actions",
    summary: "Track your governed action requests.",
    path: APP_ROUTES.actions,
    icon: ListChecks,
    section: "workspace",
    canView: (user) => hasPermission(user, "can_request_action")
  },
  {
    id: "approvals",
    label: "Approvals",
    title: "Approvals",
    summary: "Review governed action requests waiting for your decision.",
    path: APP_ROUTES.approvals,
    icon: ClipboardCheck,
    section: "workspace",
    canView: (user) => hasAnyPermission(user, APPROVAL_PERMISSION_KEYS)
  },
  {
    id: "audit",
    label: "Audit",
    title: "Audit",
    summary: "Review authorized workflow audit events.",
    path: APP_ROUTES.audit,
    icon: ScrollText,
    section: "workspace",
    canView: (user) => hasAnyPermission(user, AUDIT_PERMISSION_KEYS)
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
