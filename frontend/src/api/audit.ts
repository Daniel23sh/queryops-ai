import type {
  AuditLogFilters,
  AuditLogList
} from "../features/audit/types";
import { apiRequest } from "./client";

export function listAuditLogs(
  filters: AuditLogFilters = {},
  signal?: AbortSignal
): Promise<AuditLogList> {
  const query = new URLSearchParams();
  append(query, "event_type", filters.eventType);
  append(query, "actor_app_user_id", filters.actorAppUserId);
  append(query, "scope_id", filters.scopeId);
  append(query, "scope_type", filters.scopeType);
  append(query, "scope_key", filters.scopeKey);
  append(query, "department_id", filters.departmentId);
  append(query, "from_date", filters.fromDate);
  append(query, "to_date", filters.toDate);
  query.set("limit", String(filters.limit ?? 20));
  query.set("offset", String(filters.offset ?? 0));
  return apiRequest<AuditLogList>(`/api/v1/audit/logs?${query}`, {
    method: "GET",
    signal
  });
}

function append(query: URLSearchParams, key: string, value: string | undefined) {
  if (value) query.set(key, value);
}
