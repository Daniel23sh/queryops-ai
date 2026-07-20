import { useCallback, useEffect, useRef, useState } from "react";

import { getActionDetail } from "../../../api/actions";
import { getApprovalDetail } from "../../../api/approvals";
import { ApiError } from "../../../api/client";
import type { ApprovalDetail } from "../types";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type DetailStatus = "loading" | "success" | "not-found" | "error";
export type ApprovalReloadOutcome = "success" | "not-found" | "error";

export function useApprovalDetail(approvalId: string | undefined) {
  const [detail, setDetail] = useState<ApprovalDetail | null>(null);
  const [previewGeneratedAt, setPreviewGeneratedAt] = useState<string | null>(null);
  const [previewExpiresAt, setPreviewExpiresAt] = useState<string | null>(null);
  const [status, setStatus] = useState<DetailStatus>("loading");
  const requestRef = useRef<AbortController | null>(null);
  const detailRef = useRef<ApprovalDetail | null>(null);

  const load = useCallback(async (
    { preserveOnNotFound = false }: { preserveOnNotFound?: boolean } = {}
  ): Promise<ApprovalReloadOutcome> => {
    requestRef.current?.abort();
    if (!approvalId || !UUID_PATTERN.test(approvalId)) {
      setDetail(null);
      setStatus("not-found");
      return "not-found";
    }
    const controller = new AbortController();
    requestRef.current = controller;
    if (!preserveOnNotFound) setStatus("loading");
    try {
      const approval = await getApprovalDetail(approvalId, controller.signal);
      if (controller.signal.aborted) return "error";
      setDetail(approval);
      detailRef.current = approval;
      setStatus("success");

      try {
        const action = await getActionDetail(
          approval.action_request_id,
          controller.signal
        );
        if (!controller.signal.aborted) {
          setPreviewGeneratedAt(action.generated_at);
          setPreviewExpiresAt(action.preview_expires_at);
        }
      } catch {
        if (!controller.signal.aborted) {
          setPreviewGeneratedAt(null);
          setPreviewExpiresAt(null);
        }
      }
      return "success";
    } catch (error: unknown) {
      if (controller.signal.aborted) return "error";
      const notFound = error instanceof ApiError && error.status === 404;
      if (notFound && preserveOnNotFound && detailRef.current) {
        setStatus("success");
      } else {
        setDetail(null);
        detailRef.current = null;
        setStatus(notFound ? "not-found" : "error");
      }
      return notFound ? "not-found" : "error";
    }
  }, [approvalId]);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort();
  }, [load]);

  return {
    detail,
    previewExpiresAt,
    previewGeneratedAt,
    reload: load,
    status
  };
}
