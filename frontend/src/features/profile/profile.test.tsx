import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendRoleRequest,
  demoAdmin,
  demoAnalyst,
  demoManager,
  demoUser,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  setCsrfCookie,
  successResponse,
  type BackendUser
} from "../../test/appTestUtils";

afterEach(resetAppTestState);

describe("Profile", () => {
  it("shows identity, auth mode, and safely serialized scopes", async () => {
    const userWithMarkupScope = {
      ...demoUser,
      scopes: [
        {
          ...demoUser.scopes[0],
          display_name: "<script>Sales & Support</script>"
        }
      ]
    } as BackendUser;
    installProfile(userWithMarkupScope);

    renderAppAt("/profile");

    expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getAllByText("Demo User").length).toBeGreaterThan(0);
    expect(screen.getByText("demo.user@queryops.local")).toBeInTheDocument();
    expect(screen.getAllByText("Demo").length).toBeGreaterThan(0);
    expect(screen.getAllByText("<script>Sales & Support</script>").length).toBeGreaterThan(0);
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("Default / active")).toBeInTheDocument();
  });

  it.each([
    ["User", demoUser, ["Manager", "Analyst", "Admin"]],
    ["Manager", demoManager, ["Analyst", "Admin"]],
    ["Analyst", demoAnalyst, ["Admin"]]
  ])("offers valid Role Upgrade targets for %s", async (_label, user, options) => {
    installProfile(user);
    renderAppAt("/profile");

    expect(await screen.findByRole("heading", { name: "Role Upgrade" })).toBeInTheDocument();
    const roleSelect = screen.getByLabelText("Requested role");
    expect(
      within(roleSelect).getAllByRole("option").map((option) => option.textContent)
    ).toEqual(options);
  });

  it("does not render or load Role Upgrade for Admin", async () => {
    const fetchMock = installApiMock(authenticatedRoutes(demoAdmin));

    renderAppAt("/profile");
    expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();

    expect(screen.queryByRole("heading", { name: "Role Upgrade" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Requested role")).not.toBeInTheDocument();
    expect(screen.queryByText(/highest role/i)).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/v1/role-requests/my"))
    ).toBe(false);
  });

  it("loads existing requests only when the upgrade section is available", async () => {
    installApiMock(
      authenticatedRoutes(demoUser, {
        "GET /api/v1/role-requests/my": successResponse([
          backendRoleRequest({ status: "pending", requestedRole: "manager" })
        ])
      })
    );

    renderAppAt("/profile");

    expect(await screen.findByRole("heading", { name: "Existing requests" })).toBeInTheDocument();
    expect(await screen.findByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("I need broader reporting access.")).toBeInTheDocument();
  });

  it("submits a role request with the current CSRF token", async () => {
    setCsrfCookie("csrf-from-cookie");
    const createdRequest = backendRoleRequest({ requestedRole: "analyst" });
    const fetchMock = installApiMock(
      authenticatedRoutes(demoUser, {
        "GET /api/v1/role-requests/my": successResponse([]),
        "POST /api/v1/role-requests": successResponse(createdRequest)
      })
    );

    renderAppAt("/profile");
    await screen.findByRole("heading", { name: "Role Upgrade" });
    fireEvent.change(screen.getByLabelText("Requested role"), {
      target: { value: "analyst" }
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "I need scoped analysis access." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));

    expect(await screen.findByText("Role upgrade request submitted.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/role-requests",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-from-cookie" }),
        body: JSON.stringify({
          requested_role: "analyst",
          reason: "I need scoped analysis access."
        })
      })
    );
  });

  it("logs out from Profile", async () => {
    setCsrfCookie("csrf-from-cookie");
    const fetchMock = installApiMock(
      authenticatedRoutes(demoUser, {
        "GET /api/v1/role-requests/my": successResponse([]),
        "POST /api/v1/auth/logout": successResponse({ ok: true })
      })
    );

    renderAppAt("/profile");
    fireEvent.click(await screen.findByRole("button", { name: "Log out" }));

    expect(
      await screen.findByRole("heading", { name: "Choose a demo profile" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/logout",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-from-cookie" })
      })
    );
  });
});

describe("Admin Role Requests", () => {
  it("loads and approves an existing request on its own route", async () => {
    setCsrfCookie("csrf-from-cookie");
    const pendingRequest = backendRoleRequest();
    const approvedRequest = {
      ...pendingRequest,
      status: "approved",
      decision_reason: "Approved for scoped reporting."
    };
    const fetchMock = installApiMock(
      authenticatedRoutes(demoAdmin, {
        "GET /api/v1/admin/role-requests": successResponse([pendingRequest]),
        "POST /api/v1/admin/role-requests/role-request-id/approve":
          successResponse(approvedRequest)
      })
    );

    renderAppAt("/admin/role-requests");
    expect(
      await screen.findByRole("heading", { name: "Admin Role Requests" })
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Decision reason for Demo User"), {
      target: { value: "Approved for scoped reporting." }
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Approve role request from Demo User" })
    );

    expect(await screen.findByText("Role request approved.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Approved")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/admin/role-requests/role-request-id/approve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ decision_reason: "Approved for scoped reporting." })
      })
    );
  });
});

function installProfile(user: BackendUser) {
  installApiMock(
    authenticatedRoutes(user, {
      "GET /api/v1/role-requests/my": successResponse([])
    })
  );
}
