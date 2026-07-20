import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { cancelActionRequest, getActionDetail } from "../../api/actions";
import { ApiError } from "../../api/client";
import type { AuthUser } from "../../auth/types";
import { backendActionDetail } from "../../test/appTestUtils";
import { ActionRequestPage } from "./ActionRequestPage";

vi.mock("../../api/actions", () => ({ cancelActionRequest: vi.fn(), getActionDetail: vi.fn() }));
afterEach(() => vi.clearAllMocks());

describe("ActionRequestPage", () => {
  it("renders persisted timeline without approval controls and cancels an owned pending request", async () => {
    const pending = backendActionDetail();
    const cancelled = backendActionDetail({ status: "cancelled" });
    vi.mocked(getActionDetail).mockResolvedValueOnce(pending as never).mockResolvedValueOnce(cancelled as never);
    vi.mocked(cancelActionRequest).mockResolvedValue(cancelled as never);
    renderPage(user);

    expect(await screen.findByRole("heading", { name: "Reclaim unused licenses" })).toBeInTheDocument();
    expect(screen.getByText("Action requested")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve|reject/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Request" }));
    fireEvent.change(screen.getByLabelText("Cancellation reason"), {
      target: { value: "No longer required." }
    });
    fireEvent.click(within(screen.getByRole("dialog", { name: "Cancel this action request?" })).getByRole("button", { name: "Cancel Request" }));
    await waitFor(() => expect(cancelActionRequest).toHaveBeenCalledWith(
      "00000000-0000-4000-8000-000000000501",
      "No longer required.",
      "csrf"
    ));
    expect(await screen.findByText("Status: Cancelled")).toBeInTheDocument();
  });

  it("uses one safe unavailable state for malformed and inaccessible IDs", async () => {
    renderPage(user, "not-a-uuid");
    expect(await screen.findByRole("heading", { name: "Action request unavailable" })).toBeInTheDocument();
    expect(getActionDetail).not.toHaveBeenCalled();
  });

  it("does not expose cancellation to an approver viewing a foreign request", async () => {
    vi.mocked(getActionDetail).mockResolvedValue(
      backendActionDetail({ requesterId: "00000000-0000-4000-8000-000000000999" }) as never
    );
    renderPage(user);
    await screen.findByRole("heading", { name: "Reclaim unused licenses" });
    expect(screen.queryByRole("button", { name: "Cancel Request" })).not.toBeInTheDocument();
  });

  it("reloads the authoritative state after a cancellation race", async () => {
    vi.mocked(getActionDetail)
      .mockResolvedValueOnce(backendActionDetail() as never)
      .mockResolvedValueOnce(backendActionDetail({ status: "completed" }) as never);
    vi.mocked(cancelActionRequest).mockRejectedValue(
      new ApiError({ code: "ACTION_STATE_CONFLICT", message: "Conflict", status: 409 })
    );
    renderPage(user);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel Request" }));
    fireEvent.change(screen.getByLabelText("Cancellation reason"), {
      target: { value: "No longer required." }
    });
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "Cancel this action request?" })).getByRole(
        "button",
        { name: "Cancel Request" }
      )
    );
    expect(await screen.findByText(/latest status has been loaded/i)).toBeInTheDocument();
    expect(screen.getByText("Status: Completed")).toBeInTheDocument();
  });
});

const user: AuthUser = {
  id: "00000000-0000-4000-8000-000000000102",
  email: "demo.manager@queryops.local",
  fullName: "Demo Manager",
  role: "manager",
  departmentId: "00000000-0000-4000-8000-000000000302",
  department: { id: "00000000-0000-4000-8000-000000000302", name: "Finance" },
  scopes: [],
  status: "active",
  permissions: ["can_request_action"],
  authMode: "demo"
};

function renderPage(currentUser: AuthUser, id = "00000000-0000-4000-8000-000000000501") {
  return render(
    <MemoryRouter initialEntries={[`/actions/${id}`]}>
      <Routes>
        <Route path="/actions/:actionRequestId" element={<ActionRequestPage csrfToken="csrf" user={currentUser} />} />
        <Route path="/actions" element={<p>Actions</p>} />
      </Routes>
    </MemoryRouter>
  );
}
