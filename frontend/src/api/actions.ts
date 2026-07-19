import type {
  ActionDetail,
  ActionPreviewRequest,
  ActionSubmitRequest,
  RequesterActionList,
  RequesterActionStatusGroup
} from "../features/actions/types";
import { apiRequest } from "./client";

export function createActionPreview(
  payload: ActionPreviewRequest,
  csrfToken: string
): Promise<ActionDetail> {
  return apiRequest<ActionDetail>("/api/v1/actions/preview", {
    method: "POST",
    headers: jsonHeaders(csrfToken),
    body: JSON.stringify(payload)
  });
}

export function submitActionRequest(
  payload: ActionSubmitRequest,
  csrfToken: string
): Promise<ActionDetail> {
  return apiRequest<ActionDetail>("/api/v1/actions/request", {
    method: "POST",
    headers: jsonHeaders(csrfToken),
    body: JSON.stringify(payload)
  });
}

export function listOwnActionRequests(
  {
    statusGroup = "all",
    limit = 25,
    offset = 0
  }: {
    statusGroup?: RequesterActionStatusGroup;
    limit?: number;
    offset?: number;
  } = {},
  signal?: AbortSignal
): Promise<RequesterActionList> {
  const query = new URLSearchParams({
    status_group: statusGroup,
    limit: String(limit),
    offset: String(offset)
  });
  return apiRequest<RequesterActionList>(`/api/v1/actions?${query}`, {
    method: "GET",
    signal
  });
}

export function getActionDetail(
  actionRequestId: string,
  signal?: AbortSignal
): Promise<ActionDetail> {
  return apiRequest<ActionDetail>(
    `/api/v1/actions/${encodeURIComponent(actionRequestId)}`,
    { method: "GET", signal }
  );
}

export function cancelActionRequest(
  actionRequestId: string,
  reason: string,
  csrfToken: string
): Promise<ActionDetail> {
  return apiRequest<ActionDetail>(
    `/api/v1/actions/${encodeURIComponent(actionRequestId)}/cancel`,
    {
      method: "POST",
      headers: jsonHeaders(csrfToken),
      body: JSON.stringify({ reason })
    }
  );
}

function jsonHeaders(csrfToken: string): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken
  };
}
