import type {
  ApprovalDecisionResult,
  ApprovalDetail,
  PendingApprovalList
} from "../features/approvals/types";
import { apiRequest } from "./client";

export function listPendingApprovals(
  { limit = 20, offset = 0 }: { limit?: number; offset?: number } = {},
  signal?: AbortSignal
): Promise<PendingApprovalList> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiRequest<PendingApprovalList>(`/api/v1/approvals/pending?${query}`, {
    method: "GET",
    signal
  });
}

export function getApprovalDetail(
  approvalId: string,
  signal?: AbortSignal
): Promise<ApprovalDetail> {
  return apiRequest<ApprovalDetail>(
    `/api/v1/approvals/${encodeURIComponent(approvalId)}`,
    { method: "GET", signal }
  );
}

export function approveApproval(
  approvalId: string,
  decisionReason: string,
  csrfToken: string
): Promise<ApprovalDecisionResult> {
  return decideApproval(approvalId, "approve", decisionReason, csrfToken);
}

export function rejectApproval(
  approvalId: string,
  decisionReason: string,
  csrfToken: string
): Promise<ApprovalDecisionResult> {
  return decideApproval(approvalId, "reject", decisionReason, csrfToken);
}

function decideApproval(
  approvalId: string,
  decision: "approve" | "reject",
  decisionReason: string,
  csrfToken: string
): Promise<ApprovalDecisionResult> {
  return apiRequest<ApprovalDecisionResult>(
    `/api/v1/approvals/${encodeURIComponent(approvalId)}/${decision}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken
      },
      body: JSON.stringify({ decision_reason: decisionReason.trim() })
    }
  );
}
