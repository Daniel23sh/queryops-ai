import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { listOwnActionRequests } from "../../api/actions";
import { backendActionListItem } from "../../test/appTestUtils";
import { ActionsPage } from "./ActionsPage";

vi.mock("../../api/actions", () => ({ listOwnActionRequests: vi.fn() }));
afterEach(() => vi.clearAllMocks());

describe("ActionsPage", () => {
  it("loads owned metadata, filters, links rows, and paginates", async () => {
    vi.mocked(listOwnActionRequests).mockResolvedValue({
      items: [backendActionListItem({ priority: "urgent" }) as never],
      summary: { pending: 1, completed: 2, closed: 3 },
      pagination: { limit: 10, offset: 0, returned: 1, total: 12 }
    });
    render(<MemoryRouter><ActionsPage /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Reclaim unused licenses" })).toBeInTheDocument();
    expect(screen.getByText("Status: Pending approval")).toBeInTheDocument();
    expect(screen.getByText(/Priority urgent/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Reclaim unused licenses/ })).toHaveAttribute(
      "href",
      "/actions/00000000-0000-4000-8000-000000000501"
    );
    fireEvent.click(screen.getByRole("tab", { name: "Completed" }));
    await waitFor(() => expect(listOwnActionRequests).toHaveBeenLastCalledWith(
      { statusGroup: "completed", limit: 10, offset: 0 },
      expect.any(AbortSignal)
    ));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(listOwnActionRequests).toHaveBeenLastCalledWith(
      { statusGroup: "completed", limit: 10, offset: 10 },
      expect.any(AbortSignal)
    ));
  });

  it("renders recoverable error and filtered empty states", async () => {
    vi.mocked(listOwnActionRequests)
      .mockRejectedValueOnce(new Error("unavailable"))
      .mockResolvedValueOnce({
        items: [],
        summary: { pending: 0, completed: 0, closed: 0 },
        pagination: { limit: 10, offset: 0, returned: 0, total: 0 }
      });
    render(<MemoryRouter><ActionsPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "No submitted actions yet" })).toBeInTheDocument();
  });
});
