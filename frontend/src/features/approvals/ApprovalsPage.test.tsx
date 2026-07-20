import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { listPendingApprovals } from "../../api/approvals";
import type { PendingApprovalItem } from "./types";
import { ApprovalsPage } from "./ApprovalsPage";

vi.mock("../../api/approvals", () => ({ listPendingApprovals: vi.fn() }));
afterEach(() => vi.clearAllMocks());

describe("ApprovalsPage", () => {
  it("preserves server order and renders accessible desktop/mobile approval views", async () => {
    vi.mocked(listPendingApprovals).mockResolvedValue({
      items: [approval("urgent", "First"), approval("normal", "Second")],
      pagination: { limit: 20, offset: 0, returned: 2, total: 2 }
    });
    render(<MemoryRouter><ApprovalsPage /></MemoryRouter>);

    const table = await screen.findByRole("table", { name: "Action requests waiting for your approval" });
    expect(within(table).getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Reclaim unused licenses",
      "Reclaim unused licenses"
    ]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("urgent");
    expect(rows[0]).toHaveTextContent("First");
    expect(rows[1]).toHaveTextContent("normal");
    expect(rows[1]).toHaveTextContent("Second");
    expect(screen.getByRole("list", { name: "Pending approvals" })).toBeInTheDocument();
    expect(screen.getAllByText(/Expires/).length).toBeGreaterThan(0);
  });

  it("renders exact pagination, loading-safe retry, and the required empty state", async () => {
    vi.mocked(listPendingApprovals)
      .mockRejectedValueOnce(new Error("unavailable"))
      .mockResolvedValueOnce({
        items: [],
        pagination: { limit: 20, offset: 0, returned: 0, total: 0 }
      });
    render(<MemoryRouter><ApprovalsPage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("You have no action requests waiting for your approval.")).toBeInTheDocument();

    vi.mocked(listPendingApprovals).mockResolvedValue({
      items: [approval("high", "Page two")],
      pagination: { limit: 20, offset: 0, returned: 1, total: 21 }
    });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("Page 1 of 2 · 21 approvals")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(listPendingApprovals).toHaveBeenLastCalledWith(
      { limit: 20, offset: 20 },
      expect.any(AbortSignal)
    ));
  });
});

function approval(priority: PendingApprovalItem["priority"], requester: string): PendingApprovalItem {
  return {
    approval_id: `00000000-0000-4000-8000-00000000000${requester === "First" ? "1" : "2"}`,
    action_request_id: "00000000-0000-4000-8000-000000000101",
    action_type: "reclaim_unused_license",
    requester: { id: requester, display_name: requester },
    scope: { id: "scope", type: "department", key: "finance", display_name: "Finance" },
    priority,
    affected_count: 2,
    skipped_count: 1,
    override_count: priority === "urgent" ? 1 : 0,
    requires_admin: priority === "urgent",
    expires_at: "2099-07-21T12:00:00Z",
    status: "pending"
  };
}
