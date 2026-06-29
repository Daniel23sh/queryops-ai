import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";

const demoManager = {
  id: "manager-id",
  email: "demo.manager@queryops.local",
  full_name: "Demo Manager",
  role: "manager",
  department_id: "finance-id",
  department: {
    id: "finance-id",
    name: "Finance"
  },
  status: "active",
  permissions: ["can_run_free_query", "can_request_action"],
  auth_mode: "demo"
};

afterEach(() => {
  clearCsrfCookie();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows an app-loading state while auth hydration is pending", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));

    renderApp();

    expect(screen.getByText("Checking your session...")).toBeInTheDocument();
  });

  it("shows the four demo login choices when unauthenticated", async () => {
    stubFetchSequence(errorResponse("UNAUTHORIZED", 401));

    renderApp();

    expect(
      await screen.findByRole("heading", { name: "Choose a demo profile" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /demo admin/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /demo analyst/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /demo manager/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /demo user/i })).toBeInTheDocument();
  });

  it("logs in as the selected demo user and renders the authenticated placeholder", async () => {
    const fetchMock = stubFetchSequence(
      errorResponse("UNAUTHORIZED", 401),
      successResponse({
        user: demoManager,
        requires_onboarding: false,
        csrf_token: "csrf-from-login"
      })
    );

    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /demo manager/i }));

    expect(
      await screen.findByRole("heading", { name: "Authenticated workspace placeholder" })
    ).toBeInTheDocument();
    expect(screen.getByText("demo.manager@queryops.local")).toBeInTheDocument();
    expect(screen.getByText("Manager")).toBeInTheDocument();
    expect(screen.getByText("Finance")).toBeInTheDocument();

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/demo/login",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ email: "demo.manager@queryops.local" })
      })
    );
  });

  it("shows an error when demo login fails", async () => {
    stubFetchSequence(
      errorResponse("UNAUTHORIZED", 401),
      errorResponse("INVALID_DEMO_USER", 400, "Demo login failed.")
    );

    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /demo admin/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Demo login failed.");
  });

  it("keeps authenticated users out of the login screen after hydration", async () => {
    stubFetchSequence(successResponse(demoManager));

    renderApp();

    expect(
      await screen.findByRole("heading", { name: "Authenticated workspace placeholder" })
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Choose a demo profile" })).not.toBeInTheDocument();
    });
  });

  it("logs out with the stored CSRF token and returns to the demo login screen", async () => {
    const fetchMock = stubFetchSequence(
      errorResponse("UNAUTHORIZED", 401),
      successResponse({
        user: demoManager,
        requires_onboarding: false,
        csrf_token: "csrf-from-login"
      }),
      successResponse({ ok: true })
    );

    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /demo manager/i }));

    expect(
      await screen.findByRole("heading", { name: "Authenticated workspace placeholder" })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(
      await screen.findByRole("heading", { name: "Choose a demo profile" })
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/v1/auth/logout",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({
          "X-CSRF-Token": "csrf-from-login"
        })
      })
    );
  });

  it("shows a logout error and keeps the authenticated app visible when logout fails", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    stubFetchSequence(
      successResponse(demoManager),
      errorResponse("CSRF_TOKEN_INVALID", 403, "Logout failed. Try again.")
    );

    renderApp();

    expect(
      await screen.findByRole("heading", { name: "Authenticated workspace placeholder" })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Logout failed. Try again."
    );
    expect(screen.getByText("demo.manager@queryops.local")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Choose a demo profile" })
    ).not.toBeInTheDocument();
  });
});

function renderApp() {
  render(
    <AuthProvider>
      <App />
    </AuthProvider>
  );
}

function stubFetchSequence(...responses: Array<ReturnType<typeof jsonResponse>>) {
  const fetchMock = vi.fn();
  for (const response of responses) {
    fetchMock.mockResolvedValueOnce(response);
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function successResponse(data: unknown) {
  return jsonResponse({
    ok: true,
    status: 200,
    payload: {
      data,
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T12:00:00Z"
      }
    }
  });
}

function errorResponse(code: string, status: number, message = "Authentication is required.") {
  return jsonResponse({
    ok: false,
    status,
    payload: {
      error: {
        code,
        message,
        details: {},
        request_id: "request-id"
      }
    }
  });
}

function jsonResponse({
  ok,
  status,
  payload
}: {
  ok: boolean;
  status: number;
  payload: unknown;
}) {
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(payload)
  };
}

function clearCsrfCookie() {
  document.cookie = "qo_csrf=; max-age=0; path=/";
}
