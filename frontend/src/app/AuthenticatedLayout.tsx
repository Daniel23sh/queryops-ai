import { useEffect, useRef, useState } from "react";
import {
  Outlet,
  useLocation
} from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { AuthUser } from "../auth/types";
import { AppSidebar } from "./AppSidebar";
import { getVisibleNavItems } from "./navigation";
import { ProductTopbar } from "./ProductTopbar";
import { getRouteTitle } from "./routeConfig";

const SIDEBAR_STORAGE_KEY = "queryops-sidebar-collapsed";
const MOBILE_NAVIGATION_QUERY = "(max-width: 899px)";

export type AuthenticatedOutletContext = {
  csrfToken: string | null;
  user: AuthUser;
};

export function AuthenticatedLayout() {
  const auth = useAuth();
  const location = useLocation();
  const isMobile = useMediaQuery(MOBILE_NAVIGATION_QUERY);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(readSidebarCollapsed);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const navigationToggleRef = useRef<HTMLButtonElement>(null);
  const mainContentRef = useRef<HTMLElement>(null);
  const previousPathRef = useRef(location.pathname);
  const user = auth.user;

  useEffect(() => {
    if (!isMobile || !isDrawerOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsDrawerOpen(false);
        window.requestAnimationFrame(() => navigationToggleRef.current?.focus());
      }
    }

    function keepFocusInDrawer(event: KeyboardEvent) {
      if (event.key !== "Tab") {
        return;
      }

      const drawer = document.getElementById("primary-navigation");
      const focusableElements = drawer?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!focusableElements || focusableElements.length === 0) {
        event.preventDefault();
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    }

    document.addEventListener("keydown", handleEscape);
    document.addEventListener("keydown", keepFocusInDrawer);
    window.requestAnimationFrame(() => {
      document
        .querySelector<HTMLElement>("#primary-navigation a[aria-current='page']")
        ?.focus();
    });

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleEscape);
      document.removeEventListener("keydown", keepFocusInDrawer);
    };
  }, [isDrawerOpen, isMobile]);

  useEffect(() => {
    if (location.pathname === previousPathRef.current) {
      return;
    }

    previousPathRef.current = location.pathname;
    setIsDrawerOpen(false);
    mainContentRef.current?.focus();
  }, [location.pathname]);

  useEffect(() => {
    if (!isMobile) {
      setIsDrawerOpen(false);
    }
  }, [isMobile]);

  if (!user) {
    return null;
  }

  const visibleNavItems = getVisibleNavItems(user);
  const activeScope = getActiveScopeLabel(user);
  const isNavigationExpanded = isMobile ? isDrawerOpen : !isSidebarCollapsed;

  function toggleNavigation() {
    if (isMobile) {
      setIsDrawerOpen((isOpen) => !isOpen);
      return;
    }

    setIsSidebarCollapsed((isCollapsed) => {
      const nextValue = !isCollapsed;
      persistSidebarCollapsed(nextValue);
      return nextValue;
    });
  }

  function closeDrawerAndRestoreFocus() {
    setIsDrawerOpen(false);
    window.requestAnimationFrame(() => navigationToggleRef.current?.focus());
  }

  async function handleLogout() {
    setIsLoggingOut(true);
    setLogoutError(null);

    try {
      await auth.logout();
    } catch (error) {
      setLogoutError(formatLogoutError(error));
      setIsLoggingOut(false);
    }
  }

  return (
    <div
      className="product-shell"
      data-sidebar-collapsed={!isMobile && isSidebarCollapsed ? "true" : "false"}
    >
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <AppSidebar
        collapsed={isSidebarCollapsed}
        drawerOpen={isDrawerOpen}
        isMobile={isMobile}
        items={visibleNavItems}
        onClose={closeDrawerAndRestoreFocus}
        onLinkSelect={() => {
          if (isMobile) {
            setIsDrawerOpen(false);
            window.requestAnimationFrame(() => mainContentRef.current?.focus());
          }
        }}
      />

      {isMobile && isDrawerOpen ? (
        <button
          type="button"
          className="navigation-backdrop"
          aria-label="Close navigation"
          onClick={closeDrawerAndRestoreFocus}
        />
      ) : null}

      <div className="product-shell__workspace">
        <ProductTopbar
          activeScope={activeScope}
          isLoggingOut={isLoggingOut}
          isMobile={isMobile}
          isNavigationExpanded={isNavigationExpanded}
          navigationToggleRef={navigationToggleRef}
          onLogout={() => void handleLogout()}
          onToggleNavigation={toggleNavigation}
          routeTitle={getRouteTitle(location.pathname)}
          user={user}
        />

        <main
          id="main-content"
          ref={mainContentRef}
          className="product-content"
          tabIndex={-1}
        >
          {logoutError ? (
            <p className="logout-error" role="alert">
              {logoutError}
            </p>
          ) : null}

          <Outlet
            context={{
              csrfToken: auth.csrfToken,
              user
            } satisfies AuthenticatedOutletContext}
          />
        </main>
      </div>
    </div>
  );
}

function getActiveScopeLabel(user: AuthUser): string {
  return (
    user.scopes.find((scope) => scope.isDefault)?.displayName ??
    user.scopes[0]?.displayName ??
    "Not assigned"
  );
}

function readSidebarCollapsed(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

function persistSidebarCollapsed(collapsed: boolean) {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed));
  } catch {
    // Sidebar persistence is optional; the current interaction still succeeds.
  }
}

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }

    const mediaQuery = window.matchMedia(query);
    const updateMatches = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(mediaQuery.matches);
    mediaQuery.addEventListener("change", updateMatches);
    return () => mediaQuery.removeEventListener("change", updateMatches);
  }, [query]);

  return matches;
}

function formatLogoutError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Logout failed. Try again.";
}
