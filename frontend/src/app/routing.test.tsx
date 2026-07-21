import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendHomeOverview,
  backendEvaluationOverview,
  demoAdmin,
  demoAnalyst,
  demoManager,
  demoUser,
  errorResponse,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  successResponse
} from "../test/appTestUtils";

afterEach(() => {
  resetAppTestState();
});

describe("application routing", () => {
  it("redirects an unauthenticated protected route to login", async () => {
    installApiMock({
      "GET /api/v1/auth/me": errorResponse("UNAUTHORIZED", 401)
    });

    renderAppAt("/ask");

    expect(
      await screen.findByRole("heading", { name: "Choose a demo profile" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
  });

  it("redirects a successful login to My Dashboard", async () => {
    installApiMock({
      "GET /api/v1/auth/me": errorResponse("UNAUTHORIZED", 401),
      "POST /api/v1/demo/login": successResponse({
        user: demoManager,
        requires_onboarding: false,
        csrf_token: "csrf-from-login"
      }),
      "GET /api/v1/home/overview": successResponse(backendHomeOverview(demoManager)),
      "GET /api/v1/dashboards/library": successResponse([])
    });

    renderAppAt("/login");
    fireEvent.click(await screen.findByRole("button", { name: /demo manager/i }));

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("redirects an authenticated login route to My Dashboard", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );

    renderAppAt("/login");

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("renders Ask Data from a direct URL", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/query-templates": successResponse([])
      })
    );

    renderAppAt("/ask");

    expect(await screen.findByRole("heading", { name: "Ask Data" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/ask");
  });

  it("renders Profile from a direct URL", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/role-requests/my": successResponse([])
      })
    );

    renderAppAt("/profile");

    expect(
      await screen.findByRole("heading", { name: "Profile" })
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Role Upgrade" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/profile");
  });

  it("renders requester Actions routes and guards users without the permission", async () => {
    installApiMock(authenticatedRoutes(demoManager));
    const managerView = renderAppAt("/actions");
    expect(await screen.findByRole("heading", { name: "Actions" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/actions");

    managerView.unmount();
    installApiMock(
      authenticatedRoutes(demoUser, {
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );
    renderAppAt("/actions");
    expect(await screen.findByRole("region", { name: "My Dashboard" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Actions" })).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("renders Role Requests for a user with its permission", async () => {
    installApiMock(
      authenticatedRoutes(demoAdmin, {
        "GET /api/v1/admin/role-requests": successResponse([])
      })
    );

    renderAppAt("/admin/role-requests");

    expect(
      await screen.findByRole("heading", { name: "Admin Role Requests" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/admin/role-requests");
  });

  it("guards Approvals and Audit routes with effective permissions", async () => {
    installApiMock(authenticatedRoutes(demoAnalyst));
    const analystView = renderAppAt("/approvals");
    expect(await screen.findByRole("heading", { name: "Approvals" })).toBeInTheDocument();
    analystView.unmount();

    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/dashboards/my": successResponse([])
    }));
    renderAppAt("/audit");
    expect(await screen.findByRole("region", { name: "My Dashboard" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Audit" })).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("deep-links Evaluation for an authorized viewer and guards a User", async () => {
    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/evaluation/overview": successResponse(backendEvaluationOverview())
    }));
    const managerView = renderAppAt("/evaluation?tab=overview");
    expect(await screen.findByRole("heading", { name: "Evaluation" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/evaluation");
    managerView.unmount();

    installApiMock(authenticatedRoutes(demoUser, { "GET /api/v1/dashboards/my": successResponse([]) }));
    renderAppAt("/evaluation");
    expect(await screen.findByRole("region", { name: "My Dashboard" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Evaluation" })).not.toBeInTheDocument();
  });

  it("redirects a direct unauthorized Admin route without rendering it", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );

    renderAppAt("/admin/role-requests");

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Admin Role Requests" })
    ).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("redirects an unknown authenticated route to My Dashboard", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );

    renderAppAt("/not-a-real-route");

    expect(
      await screen.findByRole("region", { name: "My Dashboard" })
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("uses links so Browser Back and Forward restore routed screens", async () => {
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": [successResponse([]), successResponse([])],
        "GET /api/v1/query-templates": [successResponse([]), successResponse([])]
      })
    );

    renderAppAt("/");
    fireEvent.click(await screen.findByRole("link", { name: "Ask Data" }));
    expect(await screen.findByRole("heading", { name: "Ask Data" })).toBeInTheDocument();

    window.history.back();
    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(await screen.findByRole("region", { name: "My Dashboard" })).toBeInTheDocument();

    window.history.forward();
    await waitFor(() => expect(window.location.pathname).toBe("/ask"));
    expect(await screen.findByRole("heading", { name: "Ask Data" })).toBeInTheDocument();
  });
});
