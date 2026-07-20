import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { backendActionDetail, resetAppTestState } from "../../../test/appTestUtils";
import type { ActionPreviewFlow } from "../hooks/useActionPreviewFlow";
import { ActionPreviewDrawer } from "./ActionPreviewDrawer";

afterEach(resetAppTestState);

describe("ActionPreviewDrawer", () => {
  it("renders safe preview sections, hides Manager override records, and submits once", async () => {
    const onSubmit = vi.fn();
    render(
      <ActionPreviewDrawer
        flow={readyFlow()}
        onClose={vi.fn()}
        onReasonChange={vi.fn()}
        onRecreate={vi.fn()}
        onSubmit={onSubmit}
        role="manager"
      />
    );

    const drawer = screen.getByRole("dialog", { name: "Reclaim unused licenses" });
    expect(within(drawer).getByText("Governed user 1")).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole("tab", { name: "Requires Admin" }));
    expect(within(drawer).getByText(/Record-level privileged details are hidden/)).toBeInTheDocument();
    expect(within(drawer).queryByText("Microsoft 365 E5")).not.toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole("tab", { name: "Policy Details" }));
    expect(within(drawer).getByText("Approval is required.")).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for Approval" }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("supports loading, expiry recreation, Escape, and focus restoration", async () => {
    const opener = document.createElement("button");
    opener.textContent = "Preview Action";
    document.body.appendChild(opener);
    opener.focus();
    const onClose = vi.fn();
    const onRecreate = vi.fn();
    const view = render(
      <ActionPreviewDrawer
        flow={{ ...readyFlow(), preview: backendActionDetail({ status: "draft_preview", expired: true }) as never }}
        onClose={onClose}
        onReasonChange={vi.fn()}
        onRecreate={onRecreate}
        onSubmit={vi.fn()}
        role="analyst"
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Create new preview" }));
    expect(onRecreate).toHaveBeenCalledOnce();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
    view.unmount();
    await waitFor(() => expect(opener).toHaveFocus());
    opener.remove();
  });
});

function readyFlow(): ActionPreviewFlow {
  return {
    phase: "ready",
    preview: backendActionDetail({ status: "draft_preview" }) as never,
    reason: "Request approval safely.",
    error: null,
    resolution: {
      status: "available",
      suggestion: {
        action_type: "reclaim_unused_license",
        label: "Preview license reclaim",
        selector_kind: "license_assignment",
        result_identifier_column: "id"
      },
      targetCount: 1,
      previewRequest: {
        action_type: "reclaim_unused_license",
        source_query_run_id: "00000000-0000-4000-8000-000000000401",
        scope_id: "00000000-0000-4000-8000-000000000202",
        reason: "Request approval safely.",
        license_assignment_ids: ["00000000-0000-4000-8000-000000000601"]
      },
      previewRequestSourceGeneration: 1
    }
  };
}
