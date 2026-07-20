import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode
} from "react";

import { listPendingApprovals } from "../../api/approvals";
import { listNotifications } from "../../api/notifications";
import { hasAnyPermission } from "../../auth/permissions";
import type { AuthUser } from "../../auth/types";
import type { PendingApprovalItem } from "../approvals/types";
import { APPROVAL_PERMISSION_KEYS } from "./permissions";

type ActivityLoadStatus = "idle" | "loading" | "success" | "error";

type WorkflowActivityContextValue = {
  pendingApprovalCount: number | null;
  pendingApprovals: PendingApprovalItem[];
  pendingStatus: ActivityLoadStatus;
  unreadNotificationCount: number | null;
  refreshApprovals: () => Promise<void>;
  refreshNotifications: () => Promise<void>;
  refreshAll: () => Promise<void>;
};

const WorkflowActivityContext = createContext<WorkflowActivityContextValue | null>(
  null
);

export function WorkflowActivityProvider({
  children,
  user
}: {
  children: ReactNode;
  user: AuthUser;
}) {
  const canViewApprovals = hasAnyPermission(user, APPROVAL_PERMISSION_KEYS);
  const [pendingApprovalCount, setPendingApprovalCount] = useState<number | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<PendingApprovalItem[]>([]);
  const [pendingStatus, setPendingStatus] = useState<ActivityLoadStatus>("idle");
  const [unreadNotificationCount, setUnreadNotificationCount] = useState<number | null>(null);
  const approvalRequestRef = useRef<AbortController | null>(null);
  const notificationRequestRef = useRef<AbortController | null>(null);

  const refreshApprovals = useCallback(async () => {
    approvalRequestRef.current?.abort();
    if (!canViewApprovals) {
      setPendingApprovalCount(null);
      setPendingApprovals([]);
      setPendingStatus("idle");
      return;
    }
    const controller = new AbortController();
    approvalRequestRef.current = controller;
    setPendingStatus("loading");
    try {
      const result = await listPendingApprovals(
        { limit: 3, offset: 0 },
        controller.signal
      );
      if (controller.signal.aborted) return;
      setPendingApprovalCount(result.pagination.total);
      setPendingApprovals(result.items);
      setPendingStatus("success");
    } catch {
      if (controller.signal.aborted) return;
      setPendingApprovalCount(null);
      setPendingApprovals([]);
      setPendingStatus("error");
    }
  }, [canViewApprovals, user.id]);

  const refreshNotifications = useCallback(async () => {
    notificationRequestRef.current?.abort();
    const controller = new AbortController();
    notificationRequestRef.current = controller;
    try {
      const result = await listNotifications(
        { limit: 1, offset: 0 },
        controller.signal
      );
      if (controller.signal.aborted) return;
      setUnreadNotificationCount(result.unread_count);
    } catch {
      if (controller.signal.aborted) return;
      setUnreadNotificationCount(null);
    }
  }, [user.id]);

  const refreshAll = useCallback(async () => {
    await Promise.allSettled([refreshApprovals(), refreshNotifications()]);
  }, [refreshApprovals, refreshNotifications]);

  useEffect(() => {
    setPendingApprovalCount(null);
    setPendingApprovals([]);
    setPendingStatus("idle");
    setUnreadNotificationCount(null);
    void refreshAll();
    return () => {
      approvalRequestRef.current?.abort();
      notificationRequestRef.current?.abort();
    };
  }, [refreshAll, user.id]);

  const value = useMemo<WorkflowActivityContextValue>(
    () => ({
      pendingApprovalCount,
      pendingApprovals,
      pendingStatus,
      unreadNotificationCount,
      refreshApprovals,
      refreshNotifications,
      refreshAll
    }),
    [
      pendingApprovalCount,
      pendingApprovals,
      pendingStatus,
      refreshAll,
      refreshApprovals,
      refreshNotifications,
      unreadNotificationCount
    ]
  );

  return (
    <WorkflowActivityContext.Provider value={value}>
      {children}
    </WorkflowActivityContext.Provider>
  );
}

export function useWorkflowActivity(): WorkflowActivityContextValue {
  const value = useContext(WorkflowActivityContext);
  if (!value) {
    throw new Error("useWorkflowActivity must be used within WorkflowActivityProvider.");
  }
  return value;
}
