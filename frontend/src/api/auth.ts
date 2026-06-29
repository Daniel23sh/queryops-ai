import { apiRequest } from "./client";
import type { AuthUser, Department, PermissionKey, Role } from "../auth/types";

type BackendAuthUser = {
  id: string;
  email: string;
  full_name: string;
  role: Role | null;
  department_id: string | null;
  department: Department | null;
  status: string;
  permissions: PermissionKey[];
  auth_mode: string;
};

type DemoLoginResponse = {
  user: BackendAuthUser;
  requires_onboarding: boolean;
  csrf_token: string;
};

type LogoutResponse = {
  ok: boolean;
};

export type DemoLoginResult = {
  user: AuthUser;
  requiresOnboarding: boolean;
  csrfToken: string;
};

export async function demoLogin(email: string): Promise<DemoLoginResult> {
  const data = await apiRequest<DemoLoginResponse>("/api/v1/demo/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ email })
  });

  return {
    user: mapAuthUser(data.user),
    requiresOnboarding: data.requires_onboarding,
    csrfToken: data.csrf_token
  };
}

export async function getCurrentUser(): Promise<AuthUser> {
  const data = await apiRequest<BackendAuthUser>("/api/v1/auth/me", {
    method: "GET"
  });

  return mapAuthUser(data);
}

export function logout(csrfToken: string): Promise<LogoutResponse> {
  return apiRequest<LogoutResponse>("/api/v1/auth/logout", {
    method: "POST",
    headers: {
      "X-CSRF-Token": csrfToken
    }
  });
}

function mapAuthUser(user: BackendAuthUser): AuthUser {
  return {
    id: user.id,
    email: user.email,
    fullName: user.full_name,
    role: user.role,
    departmentId: user.department_id,
    department: user.department,
    status: user.status,
    permissions: user.permissions,
    authMode: user.auth_mode
  };
}
