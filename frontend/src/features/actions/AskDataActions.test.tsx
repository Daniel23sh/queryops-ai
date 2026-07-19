import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendActionDetail,
  backendActionQueryResult,
  backendQueryTemplate,
  demoAdmin,
  demoAnalyst,
  demoManager,
  demoUser,
  errorResponse,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  setCsrfCookie,
  successResponse
} from "../../test/appTestUtils";

afterEach(resetAppTestState);

describe("Ask Data requester actions", () => {
  it.each([
    ["Manager", demoManager],
    ["Analyst", demoAnalyst],
    ["Admin", demoAdmin]
  ])("shows a backend-provided recommendation for %s requesters", async (_label, user) => {
    setCsrfCookie("csrf");
    installApiMock(
      authenticatedRoutes(user, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "POST /api/v1/queries/run": successResponse(backendActionQueryResult())
      })
    );
    renderAppAt("/ask");
    await runApprovedTemplate();
    expect(await screen.findByRole("complementary", { name: "Suggested action" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview Action" })).toBeInTheDocument();
  });

  it("never renders an action CTA or selector data for User", async () => {
    setCsrfCookie("csrf");
    installApiMock(
      authenticatedRoutes(demoUser, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "POST /api/v1/queries/run": successResponse(backendActionQueryResult())
      })
    );
    renderAppAt("/ask");
    await runApprovedTemplate();
    expect(screen.queryByRole("button", { name: "Preview Action" })).not.toBeInTheDocument();
  });

  it("previews once, preserves the result on preview failure, and submits to the detail route", async () => {
    setCsrfCookie("csrf");
    const draft = backendActionDetail({ status: "draft_preview" });
    const pending = backendActionDetail();
    const fetchMock = installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()]),
        "POST /api/v1/queries/run": successResponse(backendActionQueryResult()),
        "POST /api/v1/actions/preview": [
          errorResponse("ACTION_PREVIEW_UNAVAILABLE", 503, "Preview is temporarily unavailable."),
          successResponse(draft)
        ],
        "POST /api/v1/actions/request": successResponse(pending),
        "GET /api/v1/actions/00000000-0000-4000-8000-000000000501": successResponse(pending)
      })
    );
    renderAppAt("/ask");
    await runApprovedTemplate();

    fireEvent.click(screen.getByRole("button", { name: "Preview Action" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Preview is temporarily unavailable.");
    expect(screen.getByText("Microsoft 365 E5")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByLabelText("Request reason")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Submit for Approval" }));

    await waitFor(() => expect(window.location.pathname).toBe(
      "/actions/00000000-0000-4000-8000-000000000501"
    ));
    expect(await screen.findByText("Status: Pending approval")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve|reject/i })).not.toBeInTheDocument();
    const previewCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/api/v1/actions/preview"));
    expect(previewCalls).toHaveLength(2);
    const previewBody = JSON.parse(String(previewCalls[1][1]?.body));
    expect(previewBody).toEqual({
      action_type: "reclaim_unused_license",
      source_query_run_id: "00000000-0000-4000-8000-000000000401",
      scope_id: "00000000-0000-4000-8000-000000000202",
      department_id: "00000000-0000-4000-8000-000000000302",
      reason: "Request approval to reclaim unused licenses from this current governed result.",
      license_assignment_ids: ["00000000-0000-4000-8000-000000000601"]
    });
  });
});

async function runApprovedTemplate() {
  fireEvent.click((await screen.findAllByRole("button", { name: "Templates" }))[0]);
  fireEvent.click(await screen.findByRole("button", { name: "Use template" }));
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  await screen.findByText("succeeded");
}
