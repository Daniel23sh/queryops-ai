export type AuditActor = {
  id: string;
  display_name: string;
};

export type AuditScope = {
  id: string | null;
  type: string | null;
  key: string | null;
  department_id: string | null;
};

export type AuditLogItem = {
  id: string;
  event_type: string;
  actor: AuditActor | null;
  action_request_id: string | null;
  approval_request_id: string | null;
  scope: AuditScope;
  severity: string | null;
  status: string | null;
  summary: string | null;
  created_at: string;
  before_state?: Record<string, unknown> | null;
  after_state?: Record<string, unknown> | null;
  self_approved?: boolean;
  failure_category?: string;
};

export type AuditLogList = {
  items: AuditLogItem[];
  pagination: {
    limit: number;
    offset: number;
    returned: number;
    total: number;
  };
};

export type AuditLogFilters = {
  eventType?: string;
  actorAppUserId?: string;
  scopeId?: string;
  scopeType?: string;
  scopeKey?: string;
  departmentId?: string;
  fromDate?: string;
  toDate?: string;
  limit?: number;
  offset?: number;
};
