import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendActionDetail,
  backendApprovalDetail,
  demoAnalyst,
  errorResponse,
  installApiMock,
  pendingResponse,
  renderAppAt,
  resetAppTestState,
  setCsrfCookie,
  successResponse
} from "../../test/appTestUtils";

const APPROVAL_ID = "00000000-0000-4000-8000-000000000701";
const ACTION_ID = "00000000-0000-4000-8000-000000000501";

afterEach(resetAppTestState);

describe("ApprovalDetailPage", () => {
  it("renders safe approval context, controlled policy text, timeline, and exact CTAs", async () => {
    installDetail({
      detail: backendApprovalDetail({
        policyFlags: [
          { code: "mandatory_license", reason: "Internal policy text" },
          { code: "service_account", reason: "Internal policy text" },
          { code: "cross_scope", reason: "Internal policy text" }
        ]
      })
    });
    renderAppAt(`/approvals/${APPROVAL_ID}`);

    expect(await screen.findByRole("heading", { name: "Reclaim unused licenses" })).toBeInTheDocument();
    expect(screen.getAllByText("Governed user 1")).toHaveLength(2);
    expect(screen.getByText("Action requested")).toBeInTheDocument();
    expect(screen.getByText("$25.00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve and Execute" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject Request" })).toBeInTheDocument();
    expect(screen.getByText("A mandatory license requires Admin review.")).toBeInTheDocument();
    expect(screen.getByText("A service account requires Admin review.")).toBeInTheDocument();
    expect(screen.getByText("A cross-scope record requires global approval.")).toBeInTheDocument();
    expect(screen.queryByText("Internal policy text")).not.toBeInTheDocument();
    expect(screen.queryByText("record_count_over_analyst_threshold")).not.toBeInTheDocument();
  });

  it("requires a bounded reason and CSRF before approval", async () => {
    const fetchMock = installDetail();
    renderAppAt(`/approvals/${APPROVAL_ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Approve and Execute" }));
    const confirm = last(screen.getAllByRole("button", { name: "Approve and Execute" }));
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Decision reason"), { target: { value: "Reviewed current context" } });
    fireEvent.click(confirm);
    expect(await screen.findByRole("alert")).toHaveTextContent("missing a CSRF token");
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).includes("/approve") && init?.method === "POST")).toBe(false);
  });

  it("locks duplicate approval submission and handles a failed authoritative response safely", async () => {
    setCsrfCookie("csrf-token");
    const fetchMock = installDetail({
      decision: pendingResponse()
    });
    renderAppAt(`/approvals/${APPROVAL_ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Approve and Execute" }));
    fireEvent.change(screen.getByLabelText("Decision reason"), { target: { value: "Approved after review" } });
    const confirm = last(screen.getAllByRole("button", { name: "Approve and Execute" }));
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect((await screen.findAllByText("Approving and executing…"))).toHaveLength(2);
    expect(screen.getByLabelText("Decision reason")).toBeDisabled();
    expect(fetchMock.mock.calls.filter(([input]) => String(input).includes("/approve"))).toHaveLength(1);

    cleanup();
    resetAppTestState();
    setCsrfCookie("csrf-token");
    installDetail({ decision: successResponse({ approval_id: APPROVAL_ID, action_request_id: ACTION_ID, status: "failed", executed_records_count: 0, skipped_records_count: 0 }) });
    renderAppAt(`/approvals/${APPROVAL_ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Approve and Execute" }));
    fireEvent.change(screen.getByLabelText("Decision reason"), { target: { value: "Approved after review" } });
    fireEvent.click(last(screen.getAllByRole("button", { name: "Approve and Execute" })));
    expect(await screen.findByRole("heading", { name: "Execution did not complete" })).toBeInTheDocument();
    expect(screen.getByText(/No technical details/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open resulting Action Request" })).toHaveAttribute("href", `/actions/${ACTION_ID}`);
  });

  it("handles policy escalation and missing approvals without disclosing existence", async () => {
    setCsrfCookie("csrf-token");
    installDetail({ decision: errorResponse("POLICY_OVERRIDE_REQUIRED", 422), afterDecision: backendApprovalDetail({ canApprove: false }) });
    renderAppAt(`/approvals/${APPROVAL_ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Reject Request" }));
    fireEvent.change(screen.getByLabelText("Decision reason"), { target: { value: "Review requires Admin" } });
    fireEvent.click(last(screen.getAllByRole("button", { name: "Reject Request" })));
    expect(await screen.findByText(/requires an authorized Admin/)).toBeInTheDocument();

    cleanup();
    resetAppTestState();
    installApiMock(authenticatedRoutes(demoAnalyst, {
      [`GET /api/v1/approvals/${APPROVAL_ID}`]: errorResponse("APPROVAL_NOT_FOUND", 404)
    }));
    renderAppAt(`/approvals/${APPROVAL_ID}`);
    expect(await screen.findByRole("heading", { name: "Approval unavailable" })).toBeInTheDocument();
    expect(screen.getByText(/does not exist or is not available/)).toBeInTheDocument();
  });

  it("shows a completed authoritative result and locks decision controls", async () => {
    setCsrfCookie("csrf-token");
    const fetchMock = installDetail({
      decision: successResponse({ approval_id: APPROVAL_ID, action_request_id: ACTION_ID, status: "completed", executed_records_count: 1, skipped_records_count: 2 }),
      afterDecision: backendApprovalDetail({ canApprove: false, status: "approved" })
    });
    renderAppAt(`/approvals/${APPROVAL_ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Approve and Execute" }));
    fireEvent.change(screen.getByLabelText("Decision reason"), { target: { value: "Current records reviewed" } });
    fireEvent.click(last(screen.getAllByRole("button", { name: "Approve and Execute" })));
    expect(await screen.findByRole("heading", { name: "Decision recorded" })).toBeInTheDocument();
    expect(screen.getByText("Executed 1 records · Skipped 2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve and Execute" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input).includes(`/actions/${ACTION_ID}`))).toHaveLength(1);
  });

  it.each([
    ["ACTION_ALREADY_PROCESSED", 409, /Another participant or operation already completed/],
    ["ACTION_REQUEST_EXPIRED", 410, /request expired/]
  ])("reloads and locks safely after %s", async (code, status, message) => {
    setCsrfCookie("csrf-token");
    installDetail({ decision: errorResponse(code, status) });
    renderAppAt(`/approvals/${APPROVAL_ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Reject Request" }));
    fireEvent.change(screen.getByLabelText("Decision reason"), { target: { value: "Decision reviewed" } });
    fireEvent.click(last(screen.getAllByRole("button", { name: "Reject Request" })));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject Request" })).not.toBeInTheDocument();
  });
});

function installDetail({ decision, afterDecision, detail = backendApprovalDetail() }: {
  decision?: ReturnType<typeof successResponse> | Promise<ReturnType<typeof successResponse>>;
  afterDecision?: ReturnType<typeof backendApprovalDetail>;
  detail?: ReturnType<typeof backendApprovalDetail>;
} = {}) {
  return installApiMock(authenticatedRoutes(demoAnalyst, {
    [`GET /api/v1/approvals/${APPROVAL_ID}`]: afterDecision ? [successResponse(detail), successResponse(afterDecision)] : [successResponse(detail), successResponse(detail)],
    [`GET /api/v1/actions/${ACTION_ID}`]: [successResponse(backendActionDetail()), successResponse(backendActionDetail())],
    [`POST /api/v1/approvals/${APPROVAL_ID}/approve`]: decision ?? successResponse({ approval_id: APPROVAL_ID, action_request_id: ACTION_ID, status: "completed" }),
    [`POST /api/v1/approvals/${APPROVAL_ID}/reject`]: decision ?? successResponse({ approval_id: APPROVAL_ID, action_request_id: ACTION_ID, status: "rejected" })
  }));
}

function last<T>(items: T[]): T {
  return items[items.length - 1]!;
}
