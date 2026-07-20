import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { listPendingApprovals } from "../../api/approvals";
import { listNotifications } from "../../api/notifications";
import type { AuthUser } from "../../auth/types";
import {
  WorkflowActivityProvider,
  useWorkflowActivity
} from "./WorkflowActivityProvider";

vi.mock("../../api/approvals", () => ({ listPendingApprovals: vi.fn() }));
vi.mock("../../api/notifications", () => ({ listNotifications: vi.fn() }));

afterEach(() => vi.clearAllMocks());

describe("WorkflowActivityProvider", () => {
  it("loads exact counts and resets them across authenticated users", async () => {
    vi.mocked(listPendingApprovals).mockResolvedValue({
      items: [],
      pagination: { limit: 3, offset: 0, returned: 0, total: 4 }
    });
    vi.mocked(listNotifications)
      .mockResolvedValueOnce(notificationList(7))
      .mockResolvedValueOnce(notificationList(1));
    const view = render(
      <WorkflowActivityProvider user={analystUser}>
        <ActivityProbe />
      </WorkflowActivityProvider>
    );

    expect(await screen.findByText("pending:4 unread:7")).toBeInTheDocument();
    view.rerender(
      <WorkflowActivityProvider user={managerUser}>
        <ActivityProbe />
      </WorkflowActivityProvider>
    );

    expect(await screen.findByText("pending:unknown unread:1")).toBeInTheDocument();
    expect(listPendingApprovals).toHaveBeenCalledTimes(1);
    expect(listNotifications).toHaveBeenCalledTimes(2);
  });

  it("does not invent zero when an activity request fails", async () => {
    vi.mocked(listPendingApprovals).mockRejectedValue(new Error("unavailable"));
    vi.mocked(listNotifications).mockRejectedValue(new Error("unavailable"));
    render(
      <WorkflowActivityProvider user={analystUser}>
        <ActivityProbe />
      </WorkflowActivityProvider>
    );

    await waitFor(() => expect(screen.getByText("pending:unknown unread:unknown")).toBeInTheDocument());
  });
});

function ActivityProbe() {
  const activity = useWorkflowActivity();
  return (
    <p>
      pending:{activity.pendingApprovalCount ?? "unknown"} unread:
      {activity.unreadNotificationCount ?? "unknown"}
    </p>
  );
}

function notificationList(unreadCount: number) {
  return {
    items: [],
    pagination: { limit: 1, offset: 0, returned: 0, total: 0 },
    unread_count: unreadCount
  };
}

const analystUser: AuthUser = {
  id: "analyst",
  email: "analyst@example.com",
  fullName: "Demo Analyst",
  role: "analyst",
  departmentId: null,
  department: null,
  scopes: [],
  status: "active",
  permissions: ["can_approve_scoped_action"],
  authMode: "demo"
};

const managerUser: AuthUser = {
  ...analystUser,
  id: "manager",
  email: "manager@example.com",
  fullName: "Demo Manager",
  role: "manager",
  permissions: []
};
