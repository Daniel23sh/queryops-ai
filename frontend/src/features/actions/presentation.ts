import type { ActionStatus, SupportedActionType } from "./types";

const ACTION_TITLES: Record<SupportedActionType, string> = {
  reclaim_unused_license: "Reclaim unused licenses",
  disable_inactive_user: "Disable inactive users"
};

const STATUS_LABELS: Record<ActionStatus, string> = {
  draft_preview: "Draft preview",
  pending_approval: "Pending approval",
  approved_executing: "Approved — executing",
  completed: "Completed",
  rejected: "Rejected",
  failed: "Failed",
  cancelled: "Cancelled",
  expired: "Expired"
};

export function actionTitle(actionType: SupportedActionType): string {
  return ACTION_TITLES[actionType];
}

export function actionStatusLabel(status: ActionStatus): string {
  return STATUS_LABELS[status];
}

export function actionStatusTone(status: ActionStatus): string {
  if (status === "completed") return "border-status-success/40 bg-status-success/10 text-status-success";
  if (status === "pending_approval" || status === "approved_executing") {
    return "border-status-warning/40 bg-status-warning/10 text-status-warning";
  }
  if (status === "failed" || status === "rejected") {
    return "border-status-danger/40 bg-status-danger/10 text-status-danger";
  }
  return "border-app-border bg-app-muted text-app-subtle";
}

export function formatActionDate(value: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Not available"
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(date);
}
