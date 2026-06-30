import { apiRequest } from "./client";
import type { AuthScope, Role } from "../auth/types";

export type RoleUpgradeTarget = Exclude<Role, "user">;

export type RoleRequestStatus = "pending" | "approved" | "rejected" | "cancelled";

export type RoleRequestUser = {
  id: string;
  email: string;
  fullName: string;
};

export type RoleRequest = {
  id: string;
  requester: RoleRequestUser | null;
  requestedRole: RoleUpgradeTarget;
  requestedScope: AuthScope | null;
  status: RoleRequestStatus;
  reason: string | null;
  decisionReason: string | null;
  decidedBy: RoleRequestUser | null;
  decidedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

type BackendRoleRequestUser = {
  id: string;
  email: string;
  full_name: string;
};

type BackendRoleRequest = {
  id: string;
  requester?: BackendRoleRequestUser | null;
  requested_role: RoleUpgradeTarget;
  requested_scope?: BackendAuthScope | null;
  status: RoleRequestStatus;
  reason: string | null;
  decision_reason: string | null;
  decided_by?: BackendRoleRequestUser | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

type BackendAuthScope = {
  id: string;
  type: string;
  key: string;
  display_name: string;
  access_level: string | null;
  is_default: boolean;
  department_id: string | null;
};

export function createRoleRequest(
  requestedRole: RoleUpgradeTarget,
  reason: string,
  csrfToken: string,
  requestedScopeId?: string
): Promise<RoleRequest> {
  return apiRequest<BackendRoleRequest>("/api/v1/role-requests", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken
    },
    body: JSON.stringify({
      requested_role: requestedRole,
      reason,
      ...(requestedScopeId ? { requested_scope_id: requestedScopeId } : {})
    })
  }).then(mapRoleRequest);
}

export function getMyRoleRequests(): Promise<RoleRequest[]> {
  return apiRequest<BackendRoleRequest[]>("/api/v1/role-requests/my", {
    method: "GET"
  }).then(mapRoleRequests);
}

export function getAdminRoleRequests(): Promise<RoleRequest[]> {
  return apiRequest<BackendRoleRequest[]>("/api/v1/admin/role-requests", {
    method: "GET"
  }).then(mapRoleRequests);
}

export function approveRoleRequest(
  id: string,
  decisionReason: string,
  csrfToken: string
): Promise<RoleRequest> {
  return decideRoleRequest(id, "approve", decisionReason, csrfToken);
}

export function rejectRoleRequest(
  id: string,
  decisionReason: string,
  csrfToken: string
): Promise<RoleRequest> {
  return decideRoleRequest(id, "reject", decisionReason, csrfToken);
}

function decideRoleRequest(
  id: string,
  action: "approve" | "reject",
  decisionReason: string,
  csrfToken: string
): Promise<RoleRequest> {
  return apiRequest<BackendRoleRequest>(
    `/api/v1/admin/role-requests/${id}/${action}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken
      },
      body: JSON.stringify({
        decision_reason: decisionReason
      })
    }
  ).then(mapRoleRequest);
}

function mapRoleRequests(roleRequests: BackendRoleRequest[]): RoleRequest[] {
  return roleRequests.map(mapRoleRequest);
}

function mapRoleRequest(roleRequest: BackendRoleRequest): RoleRequest {
  return {
    id: roleRequest.id,
    requester: mapRoleRequestUser(roleRequest.requester ?? null),
    requestedRole: roleRequest.requested_role,
    requestedScope: mapScope(roleRequest.requested_scope ?? null),
    status: roleRequest.status,
    reason: roleRequest.reason,
    decisionReason: roleRequest.decision_reason,
    decidedBy: mapRoleRequestUser(roleRequest.decided_by ?? null),
    decidedAt: roleRequest.decided_at,
    createdAt: roleRequest.created_at,
    updatedAt: roleRequest.updated_at
  };
}

function mapScope(scope: BackendAuthScope | null): AuthScope | null {
  if (scope === null) {
    return null;
  }

  return {
    id: scope.id,
    type: scope.type,
    key: scope.key,
    displayName: scope.display_name,
    accessLevel: scope.access_level,
    isDefault: scope.is_default,
    departmentId: scope.department_id
  };
}

function mapRoleRequestUser(
  user: BackendRoleRequestUser | null
): RoleRequestUser | null {
  if (user === null) {
    return null;
  }

  return {
    id: user.id,
    email: user.email,
    fullName: user.full_name
  };
}
