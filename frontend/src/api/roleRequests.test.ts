import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import {
  approveRoleRequest,
  createRoleRequest,
  getAdminRoleRequests,
  getMyRoleRequests,
  rejectRoleRequest
} from "./roleRequests";

const backendRoleRequest = {
  id: "role-request-id",
  requester: {
    id: "requester-id",
    email: "demo.user@queryops.local",
    full_name: "Demo User"
  },
  requested_role: "analyst",
  status: "pending",
  reason: "I need SQL-visible access for Sales reviews.",
  requested_scope: {
    id: "scope-id",
    type: "department",
    key: "sales",
    display_name: "Sales",
    access_level: "read",
    is_default: true,
    department_id: "sales-id"
  },
  decision_reason: null,
  decided_by: null,
  decided_at: null,
  created_at: "2026-06-29T12:00:00Z",
  updated_at: "2026-06-29T12:00:00Z"
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("role request API client", () => {
  it("creates role requests with cookies and the CSRF header included", async () => {
    const fetchMock = stubFetch({
      data: backendRoleRequest,
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T12:00:00Z"
      }
    });

    const result = await createRoleRequest(
      "analyst",
      "I need SQL-visible access for Sales reviews.",
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/role-requests",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: JSON.stringify({
          requested_role: "analyst",
          reason: "I need SQL-visible access for Sales reviews."
        })
      }
    );
    expect(result).toMatchObject({
      id: "role-request-id",
      requestedRole: "analyst",
      requestedScope: {
        id: "scope-id",
        type: "department",
        key: "sales",
        displayName: "Sales",
        accessLevel: "read",
        isDefault: true,
        departmentId: "sales-id"
      },
      status: "pending",
      reason: "I need SQL-visible access for Sales reviews.",
      decisionReason: null,
      decidedAt: null,
      requester: {
        fullName: "Demo User"
      }
    });
  });

  it("can create role requests with a requested scope id", async () => {
    const fetchMock = stubFetch({
      data: backendRoleRequest,
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T12:00:00Z"
      }
    });

    await createRoleRequest(
      "analyst",
      "I need SQL-visible access for Sales reviews.",
      "csrf-token",
      "scope-id"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/role-requests",
      expect.objectContaining({
        body: JSON.stringify({
          requested_role: "analyst",
          reason: "I need SQL-visible access for Sales reviews.",
          requested_scope_id: "scope-id"
        })
      })
    );
  });

  it("gets the current user's role requests with cookies included", async () => {
    const fetchMock = stubFetch({
      data: [backendRoleRequest],
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T12:00:00Z"
      }
    });

    const result = await getMyRoleRequests();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/role-requests/my",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
    expect(result).toHaveLength(1);
    expect(result[0].requestedRole).toBe("analyst");
  });

  it("gets admin role requests with cookies included", async () => {
    const fetchMock = stubFetch({
      data: [backendRoleRequest],
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T12:00:00Z"
      }
    });

    const result = await getAdminRoleRequests();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/admin/role-requests",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
    expect(result[0].requester?.email).toBe("demo.user@queryops.local");
  });

  it("approves role requests with cookies and the CSRF header included", async () => {
    const fetchMock = stubFetch({
      data: {
        ...backendRoleRequest,
        status: "approved",
        decision_reason: "Approved for Sales operations.",
        decided_by: {
          id: "admin-id",
          email: "demo.admin@queryops.local",
          full_name: "Demo Admin"
        },
        decided_at: "2026-06-29T13:00:00Z"
      },
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T13:00:00Z"
      }
    });

    const result = await approveRoleRequest(
      "role-request-id",
      "Approved for Sales operations.",
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/admin/role-requests/role-request-id/approve",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: JSON.stringify({
          decision_reason: "Approved for Sales operations."
        })
      }
    );
    expect(result.status).toBe("approved");
    expect(result.decisionReason).toBe("Approved for Sales operations.");
    expect(result.decidedBy?.fullName).toBe("Demo Admin");
  });

  it("rejects role requests with cookies and the CSRF header included", async () => {
    const fetchMock = stubFetch({
      data: {
        ...backendRoleRequest,
        status: "rejected",
        decision_reason: "Not enough business justification.",
        decided_at: "2026-06-29T13:00:00Z"
      },
      meta: {
        request_id: "request-id",
        timestamp: "2026-06-29T13:00:00Z"
      }
    });

    const result = await rejectRoleRequest(
      "role-request-id",
      "Not enough business justification.",
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/admin/role-requests/role-request-id/reject",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: JSON.stringify({
          decision_reason: "Not enough business justification."
        })
      }
    );
    expect(result.status).toBe("rejected");
    expect(result.decisionReason).toBe("Not enough business justification.");
  });

  it("throws typed API errors for backend error responses", async () => {
    stubFetch(
      {
        error: {
          code: "PENDING_ROLE_REQUEST_EXISTS",
          message: "You already have a pending role upgrade request.",
          details: {},
          request_id: "request-id"
        }
      },
      { ok: false, status: 409 }
    );

    try {
      await createRoleRequest("manager", "I need manager access.", "csrf-token");
      throw new Error("Expected createRoleRequest to reject");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({
        code: "PENDING_ROLE_REQUEST_EXISTS",
        message: "You already have a pending role upgrade request.",
        status: 409
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
