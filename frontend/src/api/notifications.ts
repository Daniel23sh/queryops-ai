import type { NotificationList, WorkflowNotification } from "../features/notifications/types";
import { apiRequest } from "./client";

export function listNotifications(
  {
    isRead,
    limit = 10,
    offset = 0
  }: { isRead?: boolean; limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<NotificationList> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (isRead !== undefined) query.set("is_read", String(isRead));
  return apiRequest<NotificationList>(`/api/v1/notifications?${query}`, {
    method: "GET",
    signal
  });
}

export function markNotificationRead(
  notificationId: string,
  csrfToken: string
): Promise<WorkflowNotification> {
  return apiRequest<WorkflowNotification>(
    `/api/v1/notifications/${encodeURIComponent(notificationId)}/read`,
    { method: "POST", headers: csrfHeader(csrfToken) }
  );
}

export function markAllNotificationsRead(
  csrfToken: string
): Promise<{ affected_count: number }> {
  return apiRequest<{ affected_count: number }>("/api/v1/notifications/read-all", {
    method: "POST",
    headers: csrfHeader(csrfToken)
  });
}

function csrfHeader(csrfToken: string): Record<string, string> {
  return { "X-CSRF-Token": csrfToken };
}
