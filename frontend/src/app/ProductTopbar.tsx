import {
  ChevronDown,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  UserRound
} from "lucide-react";
import { useEffect, useRef, useState, type RefObject } from "react";
import { Link } from "react-router-dom";

import type { AuthUser } from "../auth/types";
import { formatRole } from "../lib/format";
import { useTheme } from "./useTheme";
import { APP_ROUTES } from "./routeConfig";
import { NotificationCenter } from "../features/notifications/NotificationCenter";

export function ProductTopbar({
  activeScope,
  csrfToken,
  isLoggingOut,
  isMobile,
  isNavigationExpanded,
  onLogout,
  onToggleNavigation,
  navigationToggleRef,
  routeTitle,
  user
}: {
  activeScope: string;
  csrfToken: string | null;
  isLoggingOut: boolean;
  isMobile: boolean;
  isNavigationExpanded: boolean;
  onLogout: () => void;
  onToggleNavigation: () => void;
  navigationToggleRef: RefObject<HTMLButtonElement>;
  routeTitle: string;
  user: AuthUser;
}) {
  const { theme, toggleTheme } = useTheme();
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const menuContainerRef = useRef<HTMLDivElement>(null);
  const menuTriggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isUserMenuOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!menuContainerRef.current?.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsUserMenuOpen(false);
        menuTriggerRef.current?.focus();
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isUserMenuOpen]);

  return (
    <header className="product-topbar">
      <div className="product-topbar__leading">
        <button
          ref={navigationToggleRef}
          type="button"
          className="icon-button product-topbar__nav-toggle"
          aria-controls="primary-navigation"
          aria-expanded={isNavigationExpanded}
          aria-label={getNavigationToggleLabel(isMobile, isNavigationExpanded)}
          onClick={onToggleNavigation}
        >
          {isMobile ? (
            <Menu aria-hidden="true" size={21} />
          ) : isNavigationExpanded ? (
            <PanelLeftClose aria-hidden="true" size={20} />
          ) : (
            <PanelLeftOpen aria-hidden="true" size={20} />
          )}
        </button>
        <div className="product-topbar__title-block">
          <p className="product-topbar__eyebrow">Workspace</p>
          <p className="product-topbar__title">{routeTitle}</p>
        </div>
      </div>

      <div className="product-topbar__context" aria-label="Current access context">
        <span className="context-chip">{formatRole(user.role)}</span>
        <span className="context-chip context-chip--scope" title={activeScope}>
          Scope: {activeScope}
        </span>
        {user.authMode === "demo" ? (
          <span className="context-chip context-chip--demo">Demo</span>
        ) : null}
      </div>

      <div className="product-topbar__actions">
        <NotificationCenter csrfToken={csrfToken} />
        <button
          type="button"
          className="icon-button"
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          onClick={toggleTheme}
        >
          {theme === "dark" ? (
            <Sun aria-hidden="true" size={20} />
          ) : (
            <Moon aria-hidden="true" size={20} />
          )}
        </button>

        <div className="user-menu" ref={menuContainerRef}>
          <button
            ref={menuTriggerRef}
            type="button"
            className="user-menu__trigger"
            aria-controls="user-menu-panel"
            aria-expanded={isUserMenuOpen}
            aria-haspopup="menu"
            aria-label={`Open user menu for ${user.fullName}`}
            onClick={() => setIsUserMenuOpen((isOpen) => !isOpen)}
          >
            <span className="user-menu__avatar" aria-hidden="true">
              {getInitials(user.fullName)}
            </span>
            <span className="user-menu__name">{user.fullName}</span>
            <ChevronDown aria-hidden="true" size={16} />
          </button>

          {isUserMenuOpen ? (
            <div id="user-menu-panel" className="user-menu__panel" role="menu">
              <div className="user-menu__identity">
                <strong>{user.fullName}</strong>
                <span>{user.email}</span>
              </div>
              <Link
                className="user-menu__item"
                role="menuitem"
                to={APP_ROUTES.profile}
                onClick={() => setIsUserMenuOpen(false)}
              >
                <UserRound aria-hidden="true" size={18} />
                Profile
              </Link>
              <button
                type="button"
                className="user-menu__item user-menu__item--danger"
                role="menuitem"
                disabled={isLoggingOut}
                onClick={() => {
                  setIsUserMenuOpen(false);
                  onLogout();
                }}
              >
                <LogOut aria-hidden="true" size={18} />
                {isLoggingOut ? "Logging out..." : "Log out"}
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}

function getNavigationToggleLabel(isMobile: boolean, isExpanded: boolean): string {
  if (isMobile) {
    return isExpanded ? "Close navigation" : "Open navigation";
  }

  return isExpanded ? "Collapse sidebar" : "Expand sidebar";
}

function getInitials(fullName: string): string {
  const initials = fullName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return initials || "Q";
}
