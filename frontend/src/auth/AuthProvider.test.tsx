import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthProvider";
import type { DemoLoginResult } from "../api/auth";

const authUser = {
  id: "user-id",
  email: "demo.manager@queryops.local",
  fullName: "Demo Manager",
  role: "manager" as const,
  departmentId: "department-id",
  department: {
    id: "department-id",
    name: "Finance"
  },
  status: "active",
  permissions: ["can_run_free_query" as const, "can_request_action" as const],
  authMode: "demo"
};

const backendUser = {
  id: authUser.id,
  email: authUser.email,
  full_name: authUser.fullName,
  role: authUser.role,
  department_id: authUser.departmentId,
  department: authUser.department,
  status: authUser.status,
  permissions: authUser.permissions,
  auth_mode: authUser.authMode
};

afterEach(() => {
  clearCsrfCookie();
  vi.unstubAllGlobals();
});

describe("AuthProvider", () => {
  it("hydrates an authenticated user on app load", async () => {
    stubFetchSequence(successResponse(backendUser));

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    expect(screen.getByTestId("auth-status")).toHaveTextContent("loading");
    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("authenticated");
    });
    expect(screen.getByTestId("auth-email")).toHaveTextContent(authUser.email);
  });

  it("becomes unauthenticated when hydration returns 401", async () => {
    stubFetchSequence(errorResponse("UNAUTHORIZED", 401));

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("unauthenticated");
    });
    expect(screen.getByTestId("auth-email")).toHaveTextContent("none");
  });

  it("refreshMe rehydrates the current user", async () => {
    stubFetchSequence(errorResponse("UNAUTHORIZED", 401), successResponse(backendUser));

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("unauthenticated");
    });

    fireEvent.click(screen.getByRole("button", { name: "Refresh auth" }));

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("authenticated");
    });
    expect(screen.getByTestId("auth-email")).toHaveTextContent(authUser.email);
  });

  it("loads the readable CSRF cookie for later state-changing requests", async () => {
    document.cookie = "qo_csrf=csrf-from-cookie; path=/";
    stubFetchSequence(successResponse(backendUser));

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("csrf-token")).toHaveTextContent("csrf-from-cookie");
    });
  });

  it("stores a login result for the later demo login screen", async () => {
    stubFetchSequence(errorResponse("UNAUTHORIZED", 401));
    const loginResult: DemoLoginResult = {
      user: authUser,
      requiresOnboarding: false,
      csrfToken: "csrf-from-login"
    };

    render(
      <AuthProvider>
        <AuthProbe loginResult={loginResult} />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("unauthenticated");
    });

    fireEvent.click(screen.getByRole("button", { name: "Apply login" }));

    expect(screen.getByTestId("auth-status")).toHaveTextContent("authenticated");
    expect(screen.getByTestId("auth-email")).toHaveTextContent(authUser.email);
    expect(screen.getByTestId("csrf-token")).toHaveTextContent("csrf-from-login");
  });
});

function AuthProbe({ loginResult }: { loginResult?: DemoLoginResult }) {
  const auth = useAuth();

  return (
    <div>
      <span data-testid="auth-status">{auth.status}</span>
      <span data-testid="auth-email">{auth.user?.email ?? "none"}</span>
      <span data-testid="csrf-token">{auth.csrfToken ?? "none"}</span>
      <button type="button" onClick={() => void auth.refreshMe()}>
        Refresh auth
      </button>
      <button
        type="button"
        onClick={() => loginResult && auth.applyLoginResult(loginResult)}
      >
        Apply login
      </button>
    </div>
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

function errorResponse(code: string, status: number) {
  return jsonResponse({
    ok: false,
    status,
    payload: {
      error: {
        code,
        message: "Authentication is required.",
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
