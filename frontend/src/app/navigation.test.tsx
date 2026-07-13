import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  demoAdmin,
  demoAnalyst,
  demoManager,
  demoUser,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  successResponse,
  type BackendUser
} from "../test/appTestUtils";

afterEach(resetAppTestState);

const HIDDEN_NAVIGATION = [
  "Templates",
  "Role Upgrade",
  "Query History",
  "SQL / Technical",
  "Department Dashboards",
  "Admin Console",
  "Users",
  "Audit"
];

describe("focused navigation", () => {
  it.each([
    ["User", demoUser],
    ["Manager", demoManager],
    ["Analyst", demoAnalyst]
  ])("shows only active Workspace routes for %s", async (_label, user) => {
    installHome(user);
    renderAppAt("/");

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    expect(getLinkNames(nav)).toEqual(["My Dashboard", "Ask Data", "Profile"]);
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
    for (const label of HIDDEN_NAVIGATION) {
      expect(within(nav).queryByText(label)).not.toBeInTheDocument();
    }
  });

  it("shows Admin as a section with only Role Requests for the permitted user", async () => {
    installHome(demoAdmin);
    renderAppAt("/");

    const nav = await screen.findByRole("navigation", {
      name: "Workspace navigation"
    });
    expect(getLinkNames(nav)).toEqual([
      "My Dashboard",
      "Ask Data",
      "Profile",
      "Role Requests"
    ]);
    expect(within(nav).getByText("Admin")).toBeInTheDocument();
    expect(within(nav).queryByText("Role Upgrade")).not.toBeInTheDocument();
    expect(within(nav).queryByText("Users")).not.toBeInTheDocument();
    expect(within(nav).queryByText("Audit")).not.toBeInTheDocument();
  });

  it("uses permission checks rather than a hard-coded Admin role", async () => {
    const permittedManager = {
      ...demoManager,
      permissions: [...demoManager.permissions, "can_approve_role_requests"]
    } as BackendUser;
    installApiMock(
      authenticatedRoutes(permittedManager, {
        "GET /api/v1/admin/role-requests": successResponse([])
      })
    );

    renderAppAt("/admin/role-requests");

    expect(
      await screen.findByRole("heading", { name: "Admin Role Requests" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Role Requests" })
    ).toBeInTheDocument();
  });

  it("hides and protects Ask Data when its capability is absent", async () => {
    const userWithoutAskData = {
      ...demoUser,
      permissions: demoUser.permissions.filter(
        (permission) => permission !== "can_use_query_templates"
      )
    } as BackendUser;
    installApiMock(
      authenticatedRoutes(userWithoutAskData, {
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );

    renderAppAt("/ask");

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
    expect(within(nav).queryByRole("link", { name: "Ask Data" })).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });
});

function installHome(user: BackendUser) {
  installApiMock(
    authenticatedRoutes(user, {
      "GET /api/v1/dashboards/my": successResponse([])
    })
  );
}

function getLinkNames(navigation: HTMLElement): string[] {
  return within(navigation)
    .getAllByRole("link")
    .map((link) => link.textContent?.trim() ?? "");
}
