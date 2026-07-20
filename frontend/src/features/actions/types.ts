export type SupportedActionType =
  | "reclaim_unused_license"
  | "disable_inactive_user";

export type ActionSelectorKind = "license_assignment" | "directory_user";

export type ActionSuggestion = {
  action_type: SupportedActionType;
  label: string;
  selector_kind: ActionSelectorKind;
  result_identifier_column: string;
};

export type ActionStatus =
  | "draft_preview"
  | "pending_approval"
  | "approved_executing"
  | "completed"
  | "rejected"
  | "failed"
  | "cancelled"
  | "expired";

export type ActionPriority = "normal" | "high" | "critical";
export type RequesterActionStatusGroup = "all" | "pending" | "completed" | "closed";

export type ActionScope = {
  id: string | null;
  type: string | null;
  key: string | null;
  display_name?: string | null;
};

export type ActionPreviewRequest = {
  action_type: SupportedActionType;
  source_query_run_id: string;
  scope_id: string;
  department_id?: string;
  reason: string;
  license_assignment_ids?: string[];
  target_user_ids?: string[];
};

export type ActionSubmitRequest = {
  action_request_id: string;
  reason: string;
};

export type SafeActionRecord = {
  record_type: string | null;
  record_id: string | null;
  license_assignment_id?: string | null;
  directory_user_id?: string | null;
  scope: ActionScope;
  user_display_label: string | null;
  license_product?: string | null;
  license_vendor?: string | null;
  last_used_at?: string | null;
  last_successful_login_at?: string | null;
  monthly_cost_usd?: string | null;
  reason_code: string | null;
  reason: string | null;
  high_confidence?: boolean;
  override_reason_codes?: string[];
};

export type ActionPolicyFlag = {
  code: string;
  reason: string;
};

export type ActionExclusion = {
  reason_code: string;
  count: number;
};

export type ActionPreviewSummary = {
  affected_license_assignment_count?: number;
  affected_user_count?: number;
  affected_users_count?: number;
  normal_eligible_count?: number;
  skipped_count?: number;
  override_required_count?: number;
  high_confidence_count?: number;
  privileged_users_count?: number;
  service_accounts_excluded_count?: number;
  open_security_events_count?: number;
  recent_login_skipped_count?: number;
  estimated_monthly_savings?: string | null;
  override_estimated_monthly_savings?: string | null;
};

export type SafeActionPreview = {
  summary: ActionPreviewSummary;
  eligible_records: SafeActionRecord[];
  skipped_records: SafeActionRecord[];
  override_required_records: SafeActionRecord[];
  exclusions_by_reason: ActionExclusion[];
  policy_flags: ActionPolicyFlag[];
  requester_scope_ids?: string[];
  target_scope_ids?: string[];
  scope_decision_reason?: string;
};

export type ActionApprovalSummary = {
  id: string;
  status: string;
  required_approver_role: string;
  created_at: string | null;
  expires_at: string | null;
};

export type ActionTimelineEvent = {
  event_type: string;
  status: string;
  summary: string;
  timestamp: string | null;
  created_at: string | null;
  actor: { id: string; display_name: string } | null;
  self_approved?: boolean;
};

export type ActionDetail = {
  id: string;
  action_request_id: string;
  action_type: SupportedActionType;
  status: ActionStatus;
  priority: ActionPriority;
  scope: ActionScope;
  preview: SafeActionPreview;
  generated_at: string | null;
  preview_expires_at: string | null;
  expires_at: string | null;
  requires_admin: boolean;
  is_expired: boolean;
  reason?: string;
  submitted_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  approval: ActionApprovalSummary | null;
  timeline?: ActionTimelineEvent[];
  policy_details?: {
    crosses_scopes: boolean;
    requires_policy_override: boolean;
    record_count_over_analyst_threshold: boolean;
  };
};

export type RequesterActionListItem = {
  id: string;
  action_request_id: string;
  action_type: SupportedActionType;
  title: string;
  status: ActionStatus;
  priority: ActionPriority;
  scope: ActionScope;
  record_count: number;
  skipped_count: number;
  requires_admin: boolean;
  created_at: string | null;
  submitted_at: string | null;
  updated_at: string | null;
  expires_at: string | null;
  next_step: string;
};

export type RequesterActionList = {
  items: RequesterActionListItem[];
  summary: { pending: number; completed: number; closed: number };
  pagination: { limit: number; offset: number; returned: number; total: number };
};

export type ActionResolution =
  | { status: "hidden" }
  | { status: "unavailable"; reason: string }
  | {
      status: "available";
      suggestion: ActionSuggestion;
      targetCount: number;
      previewRequest: ActionPreviewRequest;
    };
