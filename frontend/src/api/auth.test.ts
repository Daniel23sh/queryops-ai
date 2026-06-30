import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import { demoLogin, getCurrentUser, logout } from "./auth";

const authUser = {
  id: "user-id",
  email: "demo.manager@queryops.local",
  full_name: "Demo Manager",
  role: "manager",
  department_id: "department-id",
  department: {
    id: "department-id",
    name: "Finance"
  },
  scopes: [
    {
      id: "scope-id",
      type: "department",
      key: "finance",
      display_name: "Finance",
      access_level: "read",
      is_default: true,
      department_id: "department-id"
    }
  ],
  status: "active",
  permissions: ["can_run_free_query", "can_query_scoped_data", "can_request_action"],
  auth_mode: "demo"
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("auth API client", () => {
  it("logs in demo users with cookies included", async () => {
    const fetchMock = stubFetch({
      data: {
        user: authUser,
        requires_onboarding: false,
        csrf_token: "csrf-token"
      },
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T12:00:00Z"
      }
    });

    const result = await demoLogin("demo.manager@queryops.local");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/demo/login",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ email: "demo.manager@queryops.local" })
      }
    );
    expect(result.user.email).toBe("demo.manager@queryops.local");
    expect(result.user.scopes).toEqual([
      {
        id: "scope-id",
        type: "department",
        key: "finance",
        displayName: "Finance",
        accessLevel: "read",
        isDefault: true,
        departmentId: "department-id"
      }
    ]);
    expect(result.csrfToken).toBe("csrf-token");
    expect(result.requiresOnboarding).toBe(false);
  });

  it("hydrates the current user with cookies included", async () => {
    const fetchMock = stubFetch({
      data: authUser,
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T12:00:00Z"
      }
    });

    const result = await getCurrentUser();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/me",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
    expect(result.email).toBe("demo.manager@queryops.local");
    expect(result.permissions).toContain("can_run_free_query");
    expect(result.permissions).toContain("can_query_scoped_data");
    expect(result.scopes[0].key).toBe("finance");
  });

  it("logs out with cookies and the CSRF header included", async () => {
    const fetchMock = stubFetch({
      data: { ok: true },
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T12:00:00Z"
      }
    });

    const result = await logout("csrf-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/logout",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "X-CSRF-Token": "csrf-token"
        }
      }
    );
    expect(result).toEqual({ ok: true });
  });

  it("throws typed API errors for backend error responses", async () => {
    stubFetch(
      {
        error: {
          code: "UNAUTHORIZED",
          message: "Authentication is required.",
          details: {},
          request_id: "request-id"
        }
      },
      { ok: false, status: 401 }
    );

    try {
      await getCurrentUser();
      throw new Error("Expected getCurrentUser to reject");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({
        code: "UNAUTHORIZED",
        message: "Authentication is required.",
        status: 401
      });
    }
  });
});

function stubFetch(
  payload: unknown,
  options: { ok?: boolean; status?: number } = {}
) {
  const response = {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    json: vi.fn().mockResolvedValue(payload)
  };
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
