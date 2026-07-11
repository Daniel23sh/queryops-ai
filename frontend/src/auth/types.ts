export type Role = "user" | "manager" | "analyst" | "admin";

export type PermissionKey =
  | "can_use_query_templates"
  | "can_run_free_query"
  | "can_query_department_data"
  | "can_query_scoped_data"
  | "can_query_global_data"
  | "can_query_product_tables"
  | "can_view_sql"
  | "can_view_query_history_department"
  | "can_view_query_history_scope"
  | "can_star_dashboard"
  | "can_create_personal_dashboard"
  | "can_create_department_dashboard"
  | "can_create_scope_dashboard"
  | "can_create_global_dashboard"
  | "can_manage_department_dashboard"
  | "can_manage_scope_dashboard"
  | "can_manage_global_dashboard"
  | "can_create_card"
  | "can_export_results"
  | "can_request_action"
  | "can_approve_department_action"
  | "can_approve_scoped_action"
  | "can_approve_global_action"
  | "can_approve_policy_override"
  | "can_self_approve_admin_action"
  | "can_manage_users"
  | "can_disable_app_user"
  | "can_downgrade_user_role"
  | "can_approve_role_requests"
  | "can_view_department_audit"
  | "can_view_scope_audit"
  | "can_view_global_audit"
  | "can_view_department_evaluation"
  | "can_view_scope_evaluation"
  | "can_view_global_evaluation"
  | "can_view_own_data"
  | "can_view_department_data"
  | "can_view_scoped_data"
  | "can_view_global_data";

export type Department = {
  id: string;
  name: string;
};

export type AuthScope = {
  id: string;
  type: string;
  key: string;
  displayName: string;
  accessLevel: string | null;
  isDefault: boolean;
  departmentId: string | null;
};

export type AuthUser = {
  id: string;
  email: string;
  fullName: string;
  role: Role | null;
  departmentId: string | null;
  department: Department | null;
  scopes: AuthScope[];
  status: string;
  permissions: PermissionKey[];
  authMode: string;
};
