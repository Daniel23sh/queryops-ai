import { actionStatusLabel, actionStatusTone } from "../presentation";
import type { ActionStatus } from "../types";

export function ActionStatusBadge({ status }: { status: ActionStatus }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${actionStatusTone(status)}`}
    >
      Status: {actionStatusLabel(status)}
    </span>
  );
}
