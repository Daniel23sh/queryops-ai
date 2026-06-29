import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";

import { ApiError } from "../api/client";
import { getCurrentUser, type DemoLoginResult } from "../api/auth";
import type { AuthUser } from "./types";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  status: AuthStatus;
  user: AuthUser | null;
  csrfToken: string | null;
  refreshMe: () => Promise<AuthUser | null>;
  applyLoginResult: (result: DemoLoginResult) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(() => readCsrfCookie());

  const refreshMe = useCallback(async () => {
    setStatus("loading");

    try {
      const currentUser = await getCurrentUser();
      setUser(currentUser);
      setCsrfToken(readCsrfCookie());
      setStatus("authenticated");
      return currentUser;
    } catch (error) {
      setUser(null);
      setCsrfToken(readCsrfCookie());
      setStatus("unauthenticated");

      if (error instanceof ApiError && error.status === 401) {
        return null;
      }

      return null;
    }
  }, []);

  const applyLoginResult = useCallback((result: DemoLoginResult) => {
    setUser(result.user);
    setCsrfToken(result.csrfToken);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      csrfToken,
      refreshMe,
      applyLoginResult
    }),
    [applyLoginResult, csrfToken, refreshMe, status, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return value;
}

function readCsrfCookie(): string | null {
  if (typeof document === "undefined") {
    return null;
  }

  const cookie = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith("qo_csrf="));
  if (!cookie) {
    return null;
  }

  return decodeURIComponent(cookie.slice("qo_csrf=".length));
}

