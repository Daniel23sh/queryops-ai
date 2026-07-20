import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  demoAdmin,
  demoAnalyst,
  errorResponse,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  successResponse
} from "../../test/appTestUtils";

afterEach(resetAppTestState);

describe("AuditPage", () => {
  it("keeps scoped audit fields limited and serializes bounded filters", async () => {
    const response = auditList([auditItem()]);
    const fetchMock = installApiMock(authenticatedRoutes(demoAnalyst, {
      "GET /api/v1/audit/logs": [successResponse(response), successResponse(response)]
    }));
    renderAppAt("/audit");

    expect(await screen.findByRole("heading", { name: "Audit" })).toBeInTheDocument();
    expect(screen.queryByText("Self-approved")).not.toBeInTheDocument();
    expect(screen.queryByText("Failure category")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Event type"), { target: { value: "action_executed" } });
    fireEvent.change(screen.getByLabelText("Scope key"), { target: { value: "it" } });
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-07-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => expect(fetchMock.mock.calls.filter(([input]) => String(input).includes("/audit/logs")).length).toBe(2));
    const url = new URL(String(fetchMock.mock.calls.filter(([input]) => String(input).includes("/audit/logs"))[1]![0]));
    expect(url.searchParams.get("event_type")).toBe("action_executed");
    expect(url.searchParams.get("scope_key")).toBe("it");
    expect(url.searchParams.get("from_date")).toBe("2026-07-01T00:00:00.000Z");
  });

  it("renders only returned Admin details in an accessible, focus-restoring drawer", async () => {
    const item = {
      ...auditItem(),
      before_state: { status: "pending_approval", records: [{ raw: "hidden" }] },
      after_state: { status: "completed", records: [{ raw: "hidden" }] },
      self_approved: true,
      failure_category: "database_write"
    };
    installApiMock(authenticatedRoutes(demoAdmin, {
      "GET /api/v1/audit/logs": successResponse(auditList([item]))
    }));
    renderAppAt("/audit");
    const opener = (await screen.findAllByRole("button", { name: "View details" }))[0]!;
    opener.focus();
    fireEvent.click(opener);

    expect(await screen.findByRole("dialog", { name: "Audit event details" })).toBeInTheDocument();
    expect(screen.getByText("Self-approved")).toBeInTheDocument();
    expect(screen.getByText("database_write")).toBeInTheDocument();
    expect(screen.getByText("pending_approval → completed")).toBeInTheDocument();
    expect(screen.queryByText("hidden")).not.toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Audit event details" })).not.toBeInTheDocument());
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("shows safe empty and error states", async () => {
    installApiMock(authenticatedRoutes(demoAnalyst, {
      "GET /api/v1/audit/logs": errorResponse("SERVICE_UNAVAILABLE", 503)
    }));
    const view = renderAppAt("/audit");
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded safely");
    view.unmount();

    installApiMock(authenticatedRoutes(demoAnalyst, {
      "GET /api/v1/audit/logs": successResponse(auditList([]))
    }));
    renderAppAt("/audit");
    expect(await screen.findByText("No audit events match the current filters.")).toBeInTheDocument();
  });
});

function auditItem() {
  return {
    id: "00000000-0000-4000-8000-000000000801",
    event_type: "action_executed",
    actor: { id: "00000000-0000-4000-8000-000000000103", display_name: "Demo Analyst" },
    action_request_id: "00000000-0000-4000-8000-000000000501",
    approval_request_id: "00000000-0000-4000-8000-000000000701",
    scope: { id: "00000000-0000-4000-8000-000000000203", type: "department", key: "it", department_id: "00000000-0000-4000-8000-000000000303" },
    severity: "info",
    status: "completed",
    summary: "Action executed safely.",
    created_at: "2026-07-19T13:00:00Z"
  };
}

function auditList(items: Array<Record<string, unknown>>) {
  return { items, pagination: { limit: 20, offset: 0, returned: items.length, total: items.length } };
}
