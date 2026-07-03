import { hasAnyPermission, hasPermission } from "../auth/permissions";
import type { AuthUser } from "../auth/types";

export type NavIconName =
  | "templates"
  | "dashboard"
  | "upgrade"
  | "requests"
  | "ask"
  | "history"
  | "sql"
  | "department"
  | "admin"
  | "users"
  | "audit";

export type NavItem = {
  id: string;
  label: string;
  title: string;
  summary: string;
  icon: NavIconName;
  canView: (user: AuthUser) => boolean;
};

export const WORKSPACE_NAV_ITEMS: NavItem[] = [
  {
    id: "templates",
    label: "Templates",
    title: "Templates",
    summary:
      "Approved query templates are available from Ask Data while standalone template management waits for a later milestone.",
    icon: "templates",
    canView: () => true
  },
  {
    id: "my-dashboard",
    label: "My Dashboard",
    title: "QueryOps Command Center",
    summary: "Role-aware governed analytics overview.",
    icon: "dashboard",
    canView: () => true
  },
  {
    id: "role-upgrade",
    label: "Role Upgrade",
    title: "Request Role Upgrade",
    summary: "Request a role change and track admin approval status.",
    icon: "upgrade",
    canView: () => true
  },
  {
    id: "admin-role-requests",
    label: "Role Requests",
    title: "Admin Role Requests",
    summary: "Review role upgrade requests and record role-only decisions.",
    icon: "requests",
    canView: (user) => hasPermission(user, "can_approve_role_requests")
  },
  {
    id: "ask-data",
    label: "Ask Data",
    title: "Ask Data",
    summary: "Run governed template and permitted free-form questions.",
    icon: "ask",
    canView: (user) => hasPermission(user, "can_use_query_templates")
  },
  {
    id: "query-history",
    label: "Query History",
    title: "Query History",
    summary:
      "History navigation is role-gated; the dedicated history UI remains future work.",
    icon: "history",
    canView: (user) => hasPermission(user, "can_view_query_history_department")
  },
  {
    id: "sql-technical",
    label: "SQL / Technical",
    title: "SQL / Technical",
    summary:
      "Technical details stay role-gated and contained inside Ask Data result tabs.",
    icon: "sql",
    canView: (user) => hasPermission(user, "can_view_sql")
  },
  {
    id: "department-dashboards",
    label: "Department Dashboards",
    title: "Department Dashboards",
    summary:
      "Department dashboard management is planned for a later milestone without card persistence in this PR.",
    icon: "department",
    canView: (user) =>
      hasAnyPermission(user, [
        "can_create_department_dashboard",
        "can_manage_department_dashboard"
      ])
  },
  {
    id: "admin-console",
    label: "Admin Console",
    title: "Admin Console",
    summary:
      "Administrative controls are staged intentionally; Role Requests remains the active admin workflow.",
    icon: "admin",
    canView: (user) =>
      hasAnyPermission(user, ["can_manage_users", "can_approve_role_requests"])
  },
  {
    id: "users",
    label: "Users",
    title: "Users",
    summary:
      "User management UI is planned later; demo identity context remains read-only here.",
    icon: "users",
    canView: (user) => hasPermission(user, "can_manage_users")
  },
  {
    id: "audit",
    label: "Audit",
    title: "Audit",
    summary:
      "Audit review is planned for a later milestone while backend governance remains the source of truth.",
    icon: "audit",
    canView: (user) => hasPermission(user, "can_view_global_audit")
  }
];
