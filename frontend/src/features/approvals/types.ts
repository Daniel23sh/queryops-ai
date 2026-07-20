import type {
  ActionPriority,
  ActionScope,
  ActionStatus,
  SafeActionPreview,
  SupportedActionType
} from "../actions/types";

export type ApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "expired"
  | "cancelled";

export type ApprovalRequester = {
  id: string;
  display_name: string;
};

export type PendingApprovalItem = {
  approval_id: string;
  action_request_id: string;
  action_type: SupportedActionType;
  requester: ApprovalRequester;
  scope: ActionScope;
  priority: ActionPriority;
  affected_count: number;
  skipped_count: number;
  override_count: number;
  requires_admin: boolean;
  expires_at: string | null;
  status: ApprovalStatus;
};

export type PendingApprovalList = {
  items: PendingApprovalItem[];
  pagination: {
    limit: number;
    offset: number;
    returned: number;
    total: number;
  };
};

export type ApprovalTimelineEvent = {
  event_type: string;
  timestamp: string | null;
  actor: ApprovalRequester | null;
  summary: string;
  status: string | null;
  self_approved?: boolean;
};

export type ApprovalViewerCapabilities = {
  can_approve: boolean;
  can_reject: boolean;
  can_execute_on_approval: boolean;
  self_approval: boolean;
  reason: string | null;
};

export type ApprovalDetail = PendingApprovalItem & {
  reason: string;
  preview: SafeActionPreview;
  estimated_impact: Record<string, string | number | null>;
  policy_flags: Array<{ code: string; reason: string }>;
  timeline: ApprovalTimelineEvent[];
  viewer_capabilities: ApprovalViewerCapabilities;
};

export type ApprovalDecisionResult = {
  approval_id: string;
  action_request_id: string;
  status: ActionStatus;
  executed_records_count?: number;
  skipped_records_count?: number;
  self_approved?: boolean;
  override_used?: boolean;
  completed_at?: string | null;
  decided_at?: string | null;
};
