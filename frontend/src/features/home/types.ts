export type HomeMode = "personal" | "scoped" | "global";

export type HomeScope = {
  type: "personal" | "department" | "global";
  display_name: string;
  scope_count: number;
};

export type PersonalSummary = {
  owned_dashboard_count: number;
  shared_dashboard_count: number;
  owned_card_count: number;
  successful_queries_last_30_days: number;
  pending_own_role_requests: number;
};

export type OperationalMetrics = {
  active_human_users: number | null;
  device_total: number | null;
  compliant_device_count: number | null;
  device_compliance_rate: number | null;
  monthly_license_cost_usd: number | null;
  unused_license_assignments: number | null;
  open_support_tickets: number | null;
  security_events_last_30_days: number | null;
};

export type AdminMetrics = {
  active_app_users: number | null;
  pending_role_requests: number | null;
  app_audit_events_last_7_days: number | null;
};

export type HomeOverview = {
  mode: HomeMode;
  scope: HomeScope;
  personal_summary: PersonalSummary;
  operational_metrics: OperationalMetrics | null;
  admin_metrics: AdminMetrics | null;
};
